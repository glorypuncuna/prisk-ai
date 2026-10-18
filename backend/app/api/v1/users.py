from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.api.v1.auth import compute_onboarding_status
from app.core.database import get_firestore_client, record_audit_event
from app.core.firebase import set_firebase_custom_user_claims
from app.core.security import AuthenticatedUser, UserRole, require_role
from app.schemas.user import RoleUpdateRequest, UserProfileResponse

router = APIRouter(prefix="/users", tags=["Users & RBAC Governance"])

AdminOrManagerDep = Annotated[
    AuthenticatedUser,
    Depends(require_role(UserRole.EXECUTIVE, UserRole.MANAGER)),
]


@router.get(
    "",
    response_model=list[UserProfileResponse],
)
async def list_users(
    _current_user: AdminOrManagerDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> list[UserProfileResponse]:
    """List all registered user accounts (restricted to EXECUTIVE and MANAGER roles)."""
    results: list[UserProfileResponse] = []
    for snap in db.collection("users").stream():
        doc = snap.to_dict()
        if doc:
            doc["onboarding_status"] = compute_onboarding_status(
                str(doc.get("role", UserRole.EXTERNAL_STAKEHOLDER.value)),
                list(doc.get("assigned_project_ids", [])),
            )
            results.append(UserProfileResponse(**doc))
    return results


@router.patch(
    "/{uid}/role",
    response_model=UserProfileResponse,
)
async def update_user_role(
    uid: Annotated[str, Path(min_length=1, description="Target user's Firebase UID")],
    payload: RoleUpdateRequest,
    current_user: AdminOrManagerDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> UserProfileResponse:
    """Elevate or modify a user's RBAC role and project assignments.

    Restricted to `EXECUTIVE` and `MANAGER` roles. Updates `users/{uid}` in Firestore,
    synchronizes custom claims in Firebase Auth (`set_custom_user_claims`), and writes
    an immutable `ROLE_ELEVATED` record to `audit_ledger`.
    """
    user_ref = db.collection("users").document(uid)
    snap = user_ref.get()
    if not snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{uid}' not found",
        )

    doc = snap.to_dict() or {}
    previous_role = str(doc.get("role", UserRole.EXTERNAL_STAKEHOLDER.value))
    new_role = payload.role.value

    if payload.assigned_project_ids is not None:
        assigned_projects = list(dict.fromkeys(payload.assigned_project_ids))
    else:
        assigned_projects = list(doc.get("assigned_project_ids", []))

    onboarding_status = compute_onboarding_status(new_role, assigned_projects)

    doc["role"] = new_role
    doc["assigned_project_ids"] = assigned_projects
    doc["onboarding_status"] = onboarding_status

    user_ref.set(doc, merge=True)
    set_firebase_custom_user_claims(uid, {"role": new_role})

    record_audit_event(
        db=db,
        event_type="ROLE_ELEVATED",
        actor_uid=current_user.uid,
        target_id=uid,
        metadata={
            "previous_role": previous_role,
            "new_role": new_role,
            "assigned_project_ids": assigned_projects,
        },
    )

    return UserProfileResponse(**doc)

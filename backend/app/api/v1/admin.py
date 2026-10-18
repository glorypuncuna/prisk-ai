from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.api.v1.auth import compute_onboarding_status
from app.core.database import get_firestore_client, record_audit_event
from app.core.firebase import (
    create_firebase_auth_user,
    delete_firebase_auth_user,
    set_firebase_custom_user_claims,
)
from app.core.security import AuthenticatedUser, UserRole, require_role
from app.schemas.user import (
    AdminGovernanceDigestResponse,
    AdminUserDeleteResponse,
    AdminUserProvisionRequest,
    RoleUpdateRequest,
    UserProfileResponse,
)
from app.services.sentiment_service import get_sentiment_service

router = APIRouter(prefix="/admin", tags=["Super Admin Governance"])

AdminDep = Annotated[
    AuthenticatedUser,
    Depends(require_role(UserRole.ADMIN)),
]


@router.post(
    "/users",
    response_model=UserProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def provision_user(
    payload: AdminUserProvisionRequest,
    current_admin: AdminDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> UserProfileResponse:
    """Directly provision a new user account with any assigned role.

    Restricted strictly to callers with the ADMIN role.
    """
    normalized_email = payload.email.strip().lower()

    # Check for existing user document by email
    existing_snaps = (
        db.collection("users")
        .where("email", "==", normalized_email)
        .stream()
    )
    for snap in existing_snaps:
        if snap.exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User with email '{normalized_email}' already exists",
            )

    now_iso = datetime.now(timezone.utc).isoformat()
    uid = create_firebase_auth_user(
        email=normalized_email,
        phone_number=payload.phone_number,
        display_name=f"{payload.first_name} {payload.last_name}",
    )

    onboarding_status = compute_onboarding_status(
        payload.role.value,
        payload.assigned_project_ids,
    )

    doc: dict[str, Any] = {
        "uid": uid,
        "email": normalized_email,
        "first_name": payload.first_name,
        "last_name": payload.last_name,
        "phone_number": payload.phone_number,
        "role": payload.role.value,
        "auth_provider": "password",
        "assigned_project_ids": payload.assigned_project_ids,
        "onboarding_status": onboarding_status,
        "created_at": now_iso,
        "last_login_at": now_iso,
    }

    db.collection("users").document(uid).set(doc)
    set_firebase_custom_user_claims(
        uid,
        {
            "role": payload.role.value,
            "assigned_project_ids": payload.assigned_project_ids,
        },
    )

    record_audit_event(
        db=db,
        event_type="ADMIN_USER_CREATED",
        actor_uid=current_admin.uid,
        target_id=uid,
        metadata={
            "email": normalized_email,
            "role": payload.role.value,
            "assigned_project_ids": payload.assigned_project_ids,
            "phone_number": payload.phone_number,
        },
    )

    return UserProfileResponse(**doc)


@router.get(
    "/users",
    response_model=list[UserProfileResponse],
)
async def list_admin_users(
    _current_admin: AdminDep,
    db: Annotated[Any, Depends(get_firestore_client)],
    q: Annotated[str | None, Query(description="Search filter by email or name")] = None,
    role: Annotated[UserRole | None, Query(description="Filter by role")] = None,
) -> list[UserProfileResponse]:
    """List all registered users with optional search and role filtering.

    Restricted strictly to callers with the ADMIN role.
    """
    results: list[UserProfileResponse] = []
    query_str = q.strip().lower() if q else None

    for snap in db.collection("users").stream():
        doc = snap.to_dict()
        if not doc:
            continue

        doc["onboarding_status"] = compute_onboarding_status(
            str(doc.get("role", UserRole.EXTERNAL_STAKEHOLDER.value)),
            list(doc.get("assigned_project_ids", [])),
        )

        # Filter by role if specified
        if role and doc.get("role") != role.value:
            continue

        # Filter by search string if specified
        if query_str:
            email = str(doc.get("email", "")).lower()
            first_name = str(doc.get("first_name", "")).lower()
            last_name = str(doc.get("last_name", "")).lower()
            phone = str(doc.get("phone_number", "")).lower()
            if (
                query_str not in email
                and query_str not in first_name
                and query_str not in last_name
                and query_str not in phone
            ):
                continue

        results.append(UserProfileResponse(**doc))

    return results


@router.get(
    "/users/quarantined",
    response_model=list[UserProfileResponse],
)
async def list_quarantined_users(
    current_admin: AdminDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> list[UserProfileResponse]:
    """List users currently in QUARANTINED onboarding status."""
    all_users = await list_admin_users(current_admin, db)
    return [u for u in all_users if u.onboarding_status == "QUARANTINED"]


@router.delete(
    "/users/{uid}",
    response_model=AdminUserDeleteResponse,
)
async def delete_user(
    uid: Annotated[str, Path(min_length=1, description="Target user UID to terminate")],
    current_admin: AdminDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> AdminUserDeleteResponse:
    """Terminate and hard-delete a user account.

    Restricted strictly to callers with the ADMIN role.
    Self-deletion is forbidden.
    """
    if uid == current_admin.uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot delete their own active account",
        )

    user_ref = db.collection("users").document(uid)
    snap = user_ref.get()
    if not snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{uid}' not found",
        )

    user_doc = snap.to_dict() or {}
    user_ref.delete()
    delete_firebase_auth_user(uid)

    record_audit_event(
        db=db,
        event_type="ADMIN_USER_DELETED",
        actor_uid=current_admin.uid,
        target_id=uid,
        metadata={
            "email": user_doc.get("email"),
            "role": user_doc.get("role"),
            "phone_number": user_doc.get("phone_number"),
        },
    )

    return AdminUserDeleteResponse(
        status="deleted",
        uid=uid,
        message="User account permanently de-provisioned",
    )


@router.patch(
    "/users/{uid}",
    response_model=UserProfileResponse,
)
async def admin_update_user(
    uid: Annotated[str, Path(min_length=1, description="Target user UID")],
    payload: RoleUpdateRequest,
    current_admin: AdminDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> UserProfileResponse:
    """Update role and project assignments for a user.

    Restricted strictly to callers with the ADMIN role.
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
    set_firebase_custom_user_claims(
        uid,
        {"role": new_role, "assigned_project_ids": assigned_projects},
    )

    record_audit_event(
        db=db,
        event_type="ADMIN_USER_UPDATED",
        actor_uid=current_admin.uid,
        target_id=uid,
        metadata={
            "previous_role": previous_role,
            "new_role": new_role,
            "assigned_project_ids": assigned_projects,
        },
    )

    return UserProfileResponse(**doc)


@router.patch(
    "/users/{uid}/role",
    response_model=UserProfileResponse,
)
async def admin_update_user_role(
    uid: Annotated[str, Path(min_length=1, description="Target user UID")],
    payload: RoleUpdateRequest,
    current_admin: AdminDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> UserProfileResponse:
    """Update role for a user (alias for /users/{uid})."""
    return await admin_update_user(uid, payload, current_admin, db)


@router.get(
    "/ai-governance-summary",
    response_model=AdminGovernanceDigestResponse,
)
async def get_admin_governance_summary(
    current_admin: AdminDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> AdminGovernanceDigestResponse:
    """Synthesize an AI governance digest across users, quarantined accounts, unassigned projects, and pending invitations.

    Restricted strictly to callers with the ADMIN role. Falls back deterministically when no external AI API is configured.
    """
    users_list: list[dict[str, Any]] = []
    for snap in db.collection("users").stream():
        doc = snap.to_dict()
        if not doc:
            continue
        doc["onboarding_status"] = compute_onboarding_status(
            str(doc.get("role", UserRole.EXTERNAL_STAKEHOLDER.value)),
            list(doc.get("assigned_project_ids", [])),
        )
        users_list.append(doc)

    projects_list: list[dict[str, Any]] = [
        snap.to_dict() or {}
        for snap in db.collection("projects").stream()
        if snap.exists
    ]

    pending_invitations: list[dict[str, Any]] = [
        snap.to_dict() or {}
        for snap in db.collection("project_invitations")
        .where("status", "==", "PENDING")
        .stream()
        if snap.exists
    ]

    sentiment_svc = get_sentiment_service(db=db)
    digest = sentiment_svc.generate_admin_governance_digest(
        users=users_list,
        projects=projects_list,
        pending_invitations=pending_invitations,
    )

    record_audit_event(
        db=db,
        event_type="ADMIN_GOVERNANCE_DIGEST_GENERATED",
        actor_uid=current_admin.uid,
        target_id="workspace_governance",
        metadata={
            "inference_mode": digest.inference_mode,
            "total_users": digest.total_users,
            "quarantined_users_count": digest.quarantined_users_count,
            "total_projects": digest.total_projects,
        },
    )
    return digest


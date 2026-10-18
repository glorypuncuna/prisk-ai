from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import get_firestore_client, record_audit_event
from app.core.firebase import set_firebase_custom_user_claims
from app.core.security import AuthProvider, UserRole, get_current_token_claims
from app.schemas.user import RegisterProfileRequest, UserProfileResponse
from app.services.email import notify_managers_of_new_registration

router = APIRouter(prefix="/auth", tags=["Authentication & Registration"])


def compute_onboarding_status(role: str, assigned_project_ids: list[str]) -> str:
    """Compute whether a user is quarantined awaiting project invitation or active."""
    if role == UserRole.EXTERNAL_STAKEHOLDER.value and len(assigned_project_ids) == 0:
        return "QUARANTINED_PENDING_INVITATION"
    return "ACTIVE"


@router.post(
    "/register-profile",
    response_model=UserProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_profile(
    payload: RegisterProfileRequest,
    claims: Annotated[dict[str, Any], Depends(get_current_token_claims)],
    db: Annotated[Any, Depends(get_firestore_client)],
) -> UserProfileResponse:
    """Complete user registration by validating E.164 phone number and creating `users/{uid}`.

    All newly registered accounts default to `EXTERNAL_STAKEHOLDER` with empty
    `assigned_project_ids`, sync Firebase custom claims, log `USER_REGISTERED` to the
    audit ledger, and notify managers via email.
    """
    uid = str(claims["uid"])
    raw_email = claims.get("email") or payload.email
    if not raw_email or "@" not in str(raw_email):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Valid email address is required in token claims or request payload",
        )
    normalized_email = str(raw_email).strip().lower()

    firebase_claim = claims.get("firebase", {})
    auth_provider = (
        (firebase_claim.get("sign_in_provider") if isinstance(firebase_claim, dict) else None)
        or claims.get("auth_provider")
        or AuthProvider.PASSWORD.value
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    user_ref = db.collection("users").document(uid)
    existing_snap = user_ref.get()

    if existing_snap.exists:
        existing_doc = existing_snap.to_dict() or {}
        role_val = existing_doc.get("role", UserRole.EXTERNAL_STAKEHOLDER.value)
        assigned_projects = list(existing_doc.get("assigned_project_ids", []))
        created_at = existing_doc.get("created_at", now_iso)
    else:
        role_val = UserRole.EXTERNAL_STAKEHOLDER.value
        assigned_projects = []
        created_at = now_iso

    onboarding_status = compute_onboarding_status(role_val, assigned_projects)

    profile_doc: dict[str, Any] = {
        "uid": uid,
        "email": normalized_email,
        "first_name": payload.first_name,
        "last_name": payload.last_name,
        "phone_number": payload.phone_number,
        "role": role_val,
        "auth_provider": str(auth_provider),
        "assigned_project_ids": assigned_projects,
        "onboarding_status": onboarding_status,
        "created_at": created_at,
        "last_login_at": now_iso,
    }

    user_ref.set(profile_doc)
    set_firebase_custom_user_claims(uid, {"role": role_val})

    if not existing_snap.exists:
        record_audit_event(
            db=db,
            event_type="USER_REGISTERED",
            actor_uid=uid,
            target_id=uid,
            metadata={
                "email": normalized_email,
                "role": role_val,
                "auth_provider": str(auth_provider),
                "phone_number": payload.phone_number,
            },
        )
        notify_managers_of_new_registration(db=db, user_profile=profile_doc)

    return UserProfileResponse(**profile_doc)


@router.get(
    "/me",
    response_model=UserProfileResponse,
)
async def get_authenticated_profile(
    claims: Annotated[dict[str, Any], Depends(get_current_token_claims)],
    db: Annotated[Any, Depends(get_firestore_client)],
) -> UserProfileResponse:
    """Return the authenticated user's profile and update `last_login_at`."""
    uid = str(claims["uid"])
    user_ref = db.collection("users").document(uid)
    snap = user_ref.get()

    if not snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not registered",
        )

    doc = snap.to_dict() or {}
    now_iso = datetime.now(timezone.utc).isoformat()
    doc["last_login_at"] = now_iso
    doc["onboarding_status"] = compute_onboarding_status(
        str(doc.get("role", UserRole.EXTERNAL_STAKEHOLDER.value)),
        list(doc.get("assigned_project_ids", [])),
    )
    user_ref.set(doc, merge=True)

    return UserProfileResponse(**doc)


@router.post(
    "/claim-initial-executive",
    response_model=UserProfileResponse,
)
async def claim_initial_executive(
    claims: Annotated[dict[str, Any], Depends(get_current_token_claims)],
    db: Annotated[Any, Depends(get_firestore_client)],
) -> UserProfileResponse:
    """Bootstrap endpoint: Allows an authenticated user to claim the initial EXECUTIVE role
    if no executive accounts exist in the enterprise system yet.
    """
    uid = str(claims["uid"])
    user_ref = db.collection("users").document(uid)
    snap = user_ref.get()

    if not snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile must be registered before claiming executive role",
        )

    # Check if an executive already exists (excluding the current user)
    for s in db.collection("users").stream():
        d = s.to_dict() or {}
        if s.id != uid and d.get("role") == UserRole.EXECUTIVE.value:
            # Check if it's the default seeded one or real user
            if s.id != "uid_executive_enterprise_com":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="An Executive account already exists in this organization. Request role elevation from an existing Executive or Manager.",
                )

    doc = snap.to_dict() or {}
    previous_role = doc.get("role", UserRole.EXTERNAL_STAKEHOLDER.value)
    assigned_projects = list(doc.get("assigned_project_ids", []))
    if "proj-alpha" not in assigned_projects:
        assigned_projects.append("proj-alpha")

    doc["role"] = UserRole.EXECUTIVE.value
    doc["assigned_project_ids"] = assigned_projects
    doc["onboarding_status"] = "ACTIVE"
    user_ref.set(doc, merge=True)

    set_firebase_custom_user_claims(
        uid,
        {"role": UserRole.EXECUTIVE.value, "assigned_project_ids": assigned_projects},
    )

    record_audit_event(
        db=db,
        event_type="ROLE_ELEVATED",
        actor_uid=uid,
        target_id=uid,
        metadata={
            "previous_role": previous_role,
            "new_role": UserRole.EXECUTIVE.value,
            "assigned_project_ids": assigned_projects,
            "via": "claim_initial_executive",
        },
    )

    return UserProfileResponse(**doc)

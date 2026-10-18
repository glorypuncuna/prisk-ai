from datetime import datetime, timezone
from typing import Annotated, Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.api.v1.auth import compute_onboarding_status
from app.core.database import get_firestore_client, record_audit_event
from app.core.firebase import set_firebase_custom_user_claims
from app.core.security import AuthenticatedUser, UserRole, get_current_user, require_role
from app.schemas.project import (
    DEFAULT_CANONICAL_GROUPS,
    ExemplarDiagnosticItem,
    ProjectAISuggestGroupsRequest,
    ProjectAISuggestGroupsResponse,
    ProjectAlertThresholds,
    ProjectCreateRequest,
    ProjectInvitationCreateRequest,
    ProjectInvitationResponse,
    ProjectResponse,
    ProjectUpdateRequest,
    ProjectVectorDiagnosticsResponse,
)
from app.schemas.user import UserProfileResponse
from app.repositories.sentiment_repository import SentimentRepository
from app.services.email import send_project_invitation_email
from app.services.sentiment_service import get_sentiment_service

router = APIRouter(prefix="/projects", tags=["Projects & Invitations"])

ManagerOrExecutiveDep = Annotated[
    AuthenticatedUser,
    Depends(require_role(UserRole.EXECUTIVE, UserRole.MANAGER)),
]
CurrentUserDep = Annotated[AuthenticatedUser, Depends(get_current_user)]


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    payload: ProjectCreateRequest,
    current_user: ManagerOrExecutiveDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> ProjectResponse:
    """Create a new enterprise project workspace (restricted to MANAGER, EXECUTIVE, and ADMIN)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    proj_ref = db.collection("projects").document(payload.project_id)
    if proj_ref.get().exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project '{payload.project_id}' already exists",
        )

    cleaned_groups = [g.strip() for g in payload.canonical_groups if g.strip()] or list(
        DEFAULT_CANONICAL_GROUPS
    )
    doc: dict[str, Any] = {
        "project_id": payload.project_id,
        "name": payload.name,
        "company_name": payload.company_name,
        "description": payload.description,
        "canonical_groups": cleaned_groups,
        "alert_thresholds": payload.alert_thresholds.model_dump(),
        "owner_uid": current_user.uid,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    proj_ref.set(doc)
    record_audit_event(
        db=db,
        event_type="PROJECT_CREATED",
        actor_uid=current_user.uid,
        target_id=payload.project_id,
        metadata={
            "name": payload.name,
            "company_name": payload.company_name,
            "canonical_groups": cleaned_groups,
        },
    )
    return ProjectResponse(**doc)


@router.get(
    "",
    response_model=list[ProjectResponse],
)
async def list_projects(
    current_user: CurrentUserDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> list[ProjectResponse]:
    """List projects accessible to the authenticated user.

    `EXTERNAL_STAKEHOLDER` users only see projects in their `assigned_project_ids`.
    When `assigned_project_ids` is empty, they receive an empty list (`[]`).
    """
    all_snaps = db.collection("projects").stream()
    projects: list[ProjectResponse] = []
    for snap in all_snaps:
        doc = snap.to_dict()
        if not doc:
            continue
        if (
            current_user.role == UserRole.EXTERNAL_STAKEHOLDER
            and doc.get("project_id") not in current_user.assigned_project_ids
        ):
            continue
        projects.append(ProjectResponse(**doc))
    return projects


@router.get(
    "/invitations/me",
    response_model=list[ProjectInvitationResponse],
)
async def list_my_pending_invitations(
    current_user: CurrentUserDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> list[ProjectInvitationResponse]:
    """Return all PENDING project invitations matching the authenticated user's email."""
    normalized_email = current_user.email.strip().lower()
    snaps = (
        db.collection("project_invitations")
        .where("invitee_email", "==", normalized_email)
        .where("status", "==", "PENDING")
        .stream()
    )
    return [
        ProjectInvitationResponse(**(snap.to_dict() or {}))
        for snap in snaps
        if snap.exists
    ]


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
)
async def get_project(
    project_id: Annotated[str, Path(min_length=1, description="Target project ID")],
    current_user: CurrentUserDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> ProjectResponse:
    """Retrieve a specific project workspace, enforcing project invitation access for External Stakeholders."""
    if (
        current_user.role == UserRole.EXTERNAL_STAKEHOLDER
        and project_id not in current_user.assigned_project_ids
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Pending Project Invitation",
        )

    snap = db.collection("projects").document(project_id).get()
    if not snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found",
        )
    return ProjectResponse(**(snap.to_dict() or {}))


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
)
async def update_project(
    project_id: Annotated[str, Path(min_length=1, description="Target project ID")],
    payload: ProjectUpdateRequest,
    current_user: ManagerOrExecutiveDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> ProjectResponse:
    """Update project governance metadata, canonical stakeholder groups, and alert thresholds."""
    proj_ref = db.collection("projects").document(project_id)
    snap = proj_ref.get()
    if not snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found",
        )

    doc = snap.to_dict() or {}
    now_iso = datetime.now(timezone.utc).isoformat()

    if payload.name is not None:
        doc["name"] = payload.name.strip()
    if payload.company_name is not None:
        doc["company_name"] = payload.company_name.strip()
    if payload.description is not None:
        doc["description"] = payload.description.strip()
    if payload.canonical_groups is not None:
        cleaned = [g.strip() for g in payload.canonical_groups if g.strip()]
        if len(cleaned) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least 2 canonical stakeholder groups are required",
            )
        doc["canonical_groups"] = cleaned
    if payload.alert_thresholds is not None:
        doc["alert_thresholds"] = payload.alert_thresholds.model_dump()

    doc["updated_at"] = now_iso
    proj_ref.set(doc, merge=True)

    record_audit_event(
        db=db,
        event_type="PROJECT_GOVERNANCE_UPDATED",
        actor_uid=current_user.uid,
        target_id=project_id,
        metadata={
            "canonical_groups": doc.get("canonical_groups", []),
            "alert_thresholds": doc.get("alert_thresholds", {}),
        },
    )
    return ProjectResponse(**doc)


@router.post(
    "/{project_id}/ai-suggest-groups",
    response_model=ProjectAISuggestGroupsResponse,
)
async def ai_suggest_project_groups(
    project_id: Annotated[str, Path(min_length=1, description="Target project ID")],
    payload: ProjectAISuggestGroupsRequest,
    current_user: ManagerOrExecutiveDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> ProjectAISuggestGroupsResponse:
    """Recommend canonical stakeholder groups, risk categories, and pulse alert thresholds using Gemini 2.5 Flash or deterministic domain fallback."""
    proj_snap = db.collection("projects").document(project_id).get()
    proj_doc = proj_snap.to_dict() if proj_snap.exists else {}
    proj_doc = proj_doc or {}

    effective_name = payload.name.strip() or str(proj_doc.get("name", project_id))
    effective_company = payload.company_name.strip() or str(proj_doc.get("company_name", ""))
    effective_desc = payload.description.strip() or str(proj_doc.get("description", ""))

    sentiment_svc = get_sentiment_service(db=db)
    suggestion = sentiment_svc.suggest_project_governance(
        project_id=project_id,
        name=effective_name,
        company_name=effective_company,
        description=effective_desc,
    )

    record_audit_event(
        db=db,
        event_type="PROJECT_AI_GROUPS_SUGGESTED",
        actor_uid=current_user.uid,
        target_id=project_id,
        metadata={
            "inference_mode": suggestion.inference_mode,
            "suggested_canonical_groups": suggestion.suggested_canonical_groups,
        },
    )
    return suggestion


@router.get(
    "/{project_id}/vector-diagnostics",
    response_model=ProjectVectorDiagnosticsResponse,
)
async def get_project_vector_diagnostics(
    project_id: Annotated[str, Path(min_length=1, description="Target project ID")],
    current_user: CurrentUserDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> ProjectVectorDiagnosticsResponse:
    """Inspect text-embedding-004 calibration exemplar counts, group coverage, and vector similarity readiness."""
    if (
        current_user.role == UserRole.EXTERNAL_STAKEHOLDER
        and project_id not in current_user.assigned_project_ids
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Pending Project Invitation",
        )

    proj_snap = db.collection("projects").document(project_id).get()
    if not proj_snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found",
        )

    sentiment_repo = SentimentRepository(db=db)
    calibrations = sentiment_repo.list_calibrations(project_id=project_id)
    corrected = sentiment_repo.list_corrected_contexts(project_id=project_id)

    seen_ids: set[str] = set()
    combined_items: list[ExemplarDiagnosticItem] = []
    group_coverage: dict[str, int] = {}

    for c in calibrations:
        if c.calibration_id not in seen_ids:
            seen_ids.add(c.calibration_id)
            grp = c.group_name or "UNASSIGNED"
            group_coverage[grp] = group_coverage.get(grp, 0) + 1
            has_emb = c.embedding is not None and len(c.embedding) == 768
            combined_items.append(
                ExemplarDiagnosticItem(
                    calibration_id=c.calibration_id,
                    group_name=c.group_name,
                    benchmark_score=c.benchmark_score,
                    has_embedding=has_emb,
                    embedding_dimension=768 if has_emb else 0,
                    created_at=c.created_at,
                )
            )

    for ctx in corrected:
        if ctx.correction_id not in seen_ids:
            seen_ids.add(ctx.correction_id)
            grp = ctx.group_name or "UNASSIGNED"
            group_coverage[grp] = group_coverage.get(grp, 0) + 1
            has_emb = ctx.embedding is not None and len(ctx.embedding) == 768
            combined_items.append(
                ExemplarDiagnosticItem(
                    calibration_id=ctx.correction_id,
                    group_name=ctx.group_name,
                    benchmark_score=ctx.human_adjusted_score,
                    has_embedding=has_emb,
                    embedding_dimension=768 if has_emb else 0,
                    created_at=ctx.created_at,
                )
            )

    total_exemplars = len(combined_items)
    inference_mode = "FEW_SHOT" if total_exemplars > 0 else "ZERO_SHOT"
    readiness = total_exemplars > 0 and all(item.has_embedding for item in combined_items)

    combined_items.sort(key=lambda x: x.created_at or "", reverse=True)

    return ProjectVectorDiagnosticsResponse(
        project_id=project_id,
        embedding_model="text-embedding-004",
        embedding_dimension=768,
        total_exemplars=total_exemplars,
        group_coverage=group_coverage,
        inference_mode=inference_mode,
        nearest_neighbor_readiness=readiness,
        recent_exemplars=combined_items[:10],
    )


@router.post(
    "/{project_id}/invitations",
    response_model=ProjectInvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_invitation(
    project_id: Annotated[str, Path(min_length=1, description="Target project ID")],
    payload: ProjectInvitationCreateRequest,
    current_user: ManagerOrExecutiveDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> ProjectInvitationResponse:
    """Invite a user (by email) to a specific project (`POST /api/v1/projects/{project_id}/invitations`).

    Restricted to `MANAGER` and `EXECUTIVE` roles. Creates the project record if not yet
    initialized, persists the invitation, logs to `audit_ledger`, and sends an invitation email.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    proj_ref = db.collection("projects").document(project_id)
    proj_snap = proj_ref.get()

    if proj_snap.exists:
        proj_doc = proj_snap.to_dict() or {}
        project_name = str(proj_doc.get("name", project_id))
    else:
        project_name = payload.project_name or f"Project {project_id}"
        proj_ref.set(
            {
                "project_id": project_id,
                "name": project_name,
                "description": "",
                "owner_uid": current_user.uid,
                "created_at": now_iso,
            }
        )

    invitation_id = f"inv_{project_id}_{uuid.uuid4().hex[:10]}"
    invitation_doc: dict[str, Any] = {
        "invitation_id": invitation_id,
        "project_id": project_id,
        "project_name": project_name,
        "invitee_email": payload.invitee_email,
        "invited_by_uid": current_user.uid,
        "status": "PENDING",
        "created_at": now_iso,
        "accepted_at": None,
    }

    db.collection("project_invitations").document(invitation_id).set(invitation_doc)

    record_audit_event(
        db=db,
        event_type="PROJECT_INVITATION_CREATED",
        actor_uid=current_user.uid,
        target_id=invitation_id,
        metadata={
            "project_id": project_id,
            "invitee_email": payload.invitee_email,
        },
    )

    send_project_invitation_email(
        db=db,
        invitation=invitation_doc,
        project_name=project_name,
    )

    return ProjectInvitationResponse(**invitation_doc)


@router.post(
    "/{project_id}/invitations/{invitation_id}/accept",
    response_model=UserProfileResponse,
)
async def accept_project_invitation(
    project_id: Annotated[str, Path(min_length=1, description="Target project ID")],
    invitation_id: Annotated[str, Path(min_length=1, description="Invitation ID to accept")],
    current_user: CurrentUserDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> UserProfileResponse:
    """Accept a project invitation, appending `project_id` to `assigned_project_ids`."""
    inv_ref = db.collection("project_invitations").document(invitation_id)
    inv_snap = inv_ref.get()
    if not inv_snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invitation '{invitation_id}' not found",
        )

    inv_doc = inv_snap.to_dict() or {}
    if inv_doc.get("project_id") != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation does not match the specified project_id",
        )

    user_ref = db.collection("users").document(current_user.uid)
    user_snap = user_ref.get()
    if not user_snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile must be registered before accepting a project invitation",
        )

    user_doc = user_snap.to_dict() or {}
    user_email = str(user_doc.get("email", "")).strip().lower()
    invitee_email = str(inv_doc.get("invitee_email", "")).strip().lower()

    if user_email != invitee_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This project invitation was issued to a different email address",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    inv_doc["status"] = "ACCEPTED"
    inv_doc["accepted_at"] = now_iso
    inv_ref.set(inv_doc, merge=True)

    assigned_projects = list(user_doc.get("assigned_project_ids", []))
    if project_id not in assigned_projects:
        assigned_projects.append(project_id)

    role_val = str(user_doc.get("role", UserRole.EXTERNAL_STAKEHOLDER.value))
    user_doc["assigned_project_ids"] = assigned_projects
    user_doc["onboarding_status"] = compute_onboarding_status(role_val, assigned_projects)
    user_ref.set(user_doc, merge=True)

    set_firebase_custom_user_claims(
        current_user.uid,
        {"role": role_val, "assigned_project_ids": assigned_projects},
    )

    record_audit_event(
        db=db,
        event_type="PROJECT_INVITATION_ACCEPTED",
        actor_uid=current_user.uid,
        target_id=invitation_id,
        metadata={
            "project_id": project_id,
            "assigned_project_ids": assigned_projects,
        },
    )

    return UserProfileResponse(**user_doc)


@router.post(
    "/invitations/{invitation_id}/accept",
    response_model=UserProfileResponse,
)
async def accept_invitation_direct(
    invitation_id: Annotated[str, Path(min_length=1, description="Invitation ID to accept")],
    current_user: CurrentUserDep,
    db: Annotated[Any, Depends(get_firestore_client)],
) -> UserProfileResponse:
    """Accept invitation without requiring project_id in path (auto-resolved from invitation document)."""
    inv_snap = db.collection("project_invitations").document(invitation_id).get()
    if not inv_snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invitation '{invitation_id}' not found",
        )
    inv_doc = inv_snap.to_dict() or {}
    project_id = inv_doc.get("project_id", "proj-alpha")
    return await accept_project_invitation(project_id, invitation_id, current_user, db)

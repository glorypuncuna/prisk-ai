from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.enums import UserRole
from app.core.security import AuthenticatedUser, get_current_user
from app.repositories.audit_repository import AuditRepository
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.risk_repository import RiskRepository
from app.schemas.audit import AuditLedgerEntryResponse
from app.schemas.risk import (
    AiMitigationRequest,
    AiMitigationResponse,
    AiRiskDiscoverRequest,
    AiRiskDiscoverResponse,
    PortfolioRisksAnalyticsResponse,
    RiskRegisterCreate,
    RiskRegisterResponse,
    RiskRegisterUpdate,
)
from app.schemas.sentiment import PulseTrendsResponse
from app.services.risk_service import get_risk_service
from app.services.sentiment_service import get_sentiment_service


router = APIRouter(prefix="/risks", tags=["Risk Register & Mitigation"])
analytics_router = APIRouter(prefix="/analytics", tags=["Portfolio Analytics"])
internal_jobs_router = APIRouter(prefix="/internal/jobs", tags=["Internal Cron Jobs"])


class EvaluateEscalationsRequest(BaseModel):
    """Optional override timestamp for testing 24h/48h/72h SLA evaluations."""

    reference_time_iso: str | None = None


def _resolve_allowed_projects(current_user: AuthenticatedUser) -> set[str] | None:
    """Return None for global roles (ADMIN, EXECUTIVE) or set of assigned project IDs."""
    role_val = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )
    if role_val in (UserRole.ADMIN.value, UserRole.EXECUTIVE.value):
        return None
    if role_val == UserRole.EXTERNAL_STAKEHOLDER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="External stakeholders cannot access the internal Risk Register",
        )
    return set(current_user.assigned_project_ids or [])


def _require_risk_write_access(
    current_user: AuthenticatedUser, project_id: str
) -> None:
    """Ensure user has write access to the risk register for the given project."""
    role_val = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )
    if role_val in (UserRole.ADMIN.value, UserRole.EXECUTIVE.value):
        return
    if role_val in (UserRole.MANAGER.value, UserRole.ADJUDICATOR.value):
        if project_id in (current_user.assigned_project_ids or []):
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient privileges to modify risks for this project",
    )


@router.get("", response_model=list[RiskRegisterResponse])
async def list_risks_endpoint(
    project_id: str | None = Query(default=None),
    category: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    severity_band: str | None = Query(default=None),
    impact: int | None = Query(default=None, ge=1, le=5),
    probability: int | None = Query(default=None, ge=1, le=5),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[RiskRegisterResponse]:
    """List risks from the centralized `risk_register` filtered by COSO/ISO 31000 dimensions."""
    allowed_projects = _resolve_allowed_projects(current_user)
    if (
        project_id
        and allowed_projects is not None
        and project_id not in allowed_projects
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view risks for this project",
        )
    repo = RiskRepository()
    return repo.list_risks(
        project_id=project_id,
        status=status_filter,
        category=category,
        severity_band=severity_band,
        impact=impact,
        probability=probability,
        allowed_project_ids=allowed_projects,
    )


@router.post(
    "",
    response_model=RiskRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_risk_endpoint(
    payload: RiskRegisterCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> RiskRegisterResponse:
    """Register a new risk with COSO/ISO 31000 Impact (1-5) and Probability (1-5) scoring."""
    _require_risk_write_access(current_user, payload.project_id)
    svc = get_risk_service()
    role_val = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )
    return svc.register_risk(
        payload=payload,
        actor_uid=current_user.uid,
        actor_role=role_val,
    )


@router.post("/ai-discover", response_model=AiRiskDiscoverResponse)
async def ai_discover_risks_endpoint(
    payload: AiRiskDiscoverRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AiRiskDiscoverResponse:
    """TRD Section 10.6 / Task 6.1: Automated AI Risk Discovery from meeting pulse drops (>15 pts or <40)."""
    allowed_projects = _resolve_allowed_projects(current_user)
    if (
        payload.project_id
        and allowed_projects is not None
        and payload.project_id not in allowed_projects
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to discover risks for this project",
        )
    role_val = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )
    svc = get_risk_service()
    return svc.discover_emerging_risks(
        project_id=payload.project_id,
        meeting_id=payload.meeting_id,
        lookback_window=payload.lookback_window,
        auto_register=payload.auto_register,
        actor_uid=current_user.uid,
        actor_role=role_val,
    )


@router.get("/heatmap", response_model=PortfolioRisksAnalyticsResponse)
async def get_risk_heatmap_endpoint(
    project_id: str | None = Query(default=None),
    category: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PortfolioRisksAnalyticsResponse:
    """Return the 5x5 Impact x Probability heatmap matrix, category distribution, and systemic spike status."""
    allowed_projects = _resolve_allowed_projects(current_user)
    if (
        project_id
        and allowed_projects is not None
        and project_id not in allowed_projects
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view heatmap for this project",
        )
    svc = get_risk_service()
    return svc.build_portfolio_risk_analytics(
        project_id=project_id,
        category=category,
        status=status_filter,
        allowed_project_ids=allowed_projects,
    )


@router.post("/{risk_id}/ai-mitigation", response_model=AiMitigationResponse)
async def ai_synthesize_mitigation_endpoint(
    risk_id: str,
    payload: AiMitigationRequest | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AiMitigationResponse:
    """TRD Section 10.6 / Task 6.1: Synthesize proactive mitigation strategy and executive brief using Gemini 2.5 Flash."""
    repo = RiskRepository()
    risk = repo.get_risk(risk_id)
    if not risk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Risk '{risk_id}' not found",
        )
    allowed_projects = _resolve_allowed_projects(current_user)
    if allowed_projects is not None and risk.project_id not in allowed_projects:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this risk",
        )
    if payload and payload.apply_to_risk:
        _require_risk_write_access(current_user, risk.project_id)

    svc = get_risk_service(db=repo.db)
    role_val = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )
    return svc.synthesize_ai_mitigation(
        risk_id=risk_id,
        apply_to_risk=payload.apply_to_risk if payload else False,
        context_notes=payload.context_notes if payload else None,
        actor_uid=current_user.uid,
        actor_role=role_val,
    )



@router.get("/{risk_id}", response_model=RiskRegisterResponse)
async def get_risk_endpoint(
    risk_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> RiskRegisterResponse:
    """Retrieve a single risk register entry by ID."""
    allowed_projects = _resolve_allowed_projects(current_user)
    repo = RiskRepository()
    risk = repo.get_risk(risk_id)
    if not risk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Risk '{risk_id}' not found",
        )
    if allowed_projects is not None and risk.project_id not in allowed_projects:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this risk",
        )
    return risk


@router.patch("/{risk_id}", response_model=RiskRegisterResponse)
async def update_risk_endpoint(
    risk_id: str,
    updates: RiskRegisterUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> RiskRegisterResponse:
    """Override or update a risk's Impact, Probability, Status, Category, Owner, or SLA config."""
    repo = RiskRepository()
    existing = repo.get_risk(risk_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Risk '{risk_id}' not found",
        )
    _require_risk_write_access(current_user, existing.project_id)
    svc = get_risk_service(db=repo.db)
    role_val = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )
    return svc.override_or_update_risk(
        risk_id=risk_id,
        updates=updates,
        actor_uid=current_user.uid,
        actor_role=role_val,
    )


@router.get("/{risk_id}/audit-trail")
async def get_risk_audit_trail_endpoint(
    risk_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Fetch chronological immutable audit trail and source Golden Record meeting metadata for a risk."""
    allowed_projects = _resolve_allowed_projects(current_user)
    risk_repo = RiskRepository()
    risk = risk_repo.get_risk(risk_id)
    if not risk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Risk '{risk_id}' not found",
        )
    if allowed_projects is not None and risk.project_id not in allowed_projects:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view audit trail for this risk",
        )

    audit_repo = AuditRepository(db=risk_repo.db)
    events: list[AuditLedgerEntryResponse] = audit_repo.list_events(
        target_id=risk_id
    )

    source_meeting: dict[str, Any] | None = None
    if risk.meeting_id:
        mtg_repo = MeetingRepository(db=risk_repo.db)
        mtg = mtg_repo.get_meeting(risk.meeting_id)
        if mtg:
            source_meeting = {
                "meeting_id": mtg.meeting_id,
                "title": mtg.title,
                "meeting_date": mtg.meeting_date,
                "status": str(mtg.status),
                "pulse_score": mtg.pulse_score,
            }

    return {
        "risk": risk.model_dump(),
        "source_meeting": source_meeting,
        "audit_events": [e.model_dump() for e in events],
    }


@router.post("/evaluate-escalations")
async def trigger_risk_escalations_api_endpoint(
    payload: EvaluateEscalationsRequest | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Authenticated endpoint for Managers/Executives/Admins to trigger 24h/48h/72h SLA and Systemic Spike evaluation."""
    role_val = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )
    if role_val not in (
        UserRole.ADMIN.value,
        UserRole.EXECUTIVE.value,
        UserRole.MANAGER.value,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Managers, Executives, or Admins can trigger SLA evaluation",
        )

    ref_dt: datetime | None = None
    if payload and payload.reference_time_iso:
        try:
            ref_dt = datetime.fromisoformat(
                payload.reference_time_iso.replace("Z", "+00:00")
            )
            if ref_dt.tzinfo is None:
                ref_dt = ref_dt.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid ISO timestamp in reference_time_iso",
            ) from exc

    svc = get_risk_service()
    return svc.evaluate_sla_escalations(reference_time=ref_dt)


@analytics_router.get(
    "/portfolio-risks", response_model=PortfolioRisksAnalyticsResponse
)
async def get_portfolio_risks_analytics(
    project_id: str | None = Query(default=None),
    category: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PortfolioRisksAnalyticsResponse:
    """TRD Section 9.3: Return 5x5 Impact x Probability heatmap, clickable node drill-downs, and systemic risk spike status."""
    allowed_projects = _resolve_allowed_projects(current_user)
    if (
        project_id
        and allowed_projects is not None
        and project_id not in allowed_projects
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view portfolio risks for this project",
        )
    svc = get_risk_service()
    return svc.build_portfolio_risk_analytics(
        project_id=project_id,
        category=category,
        status=status_filter,
        allowed_project_ids=allowed_projects,
    )


@analytics_router.get(
    "/pulse-trends", response_model=PulseTrendsResponse
)
async def get_pulse_trends_analytics(
    project_id: str | None = Query(default=None),
    time_window: str = Query(default="30D"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PulseTrendsResponse:
    """TRD Section 10.4: Return longitudinal meeting pulse trajectory and Gemini 2.5 Flash trajectory commentary."""
    allowed_projects = _resolve_allowed_projects(current_user)
    if (
        project_id
        and allowed_projects is not None
        and project_id not in allowed_projects
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view pulse trends for this project",
        )

    mtg_repo = MeetingRepository()
    snaps = mtg_repo.db.collection("meetings").stream()
    meetings: list[dict[str, Any]] = []

    for snap in snaps:
        data = snap.to_dict() or {}
        data["meeting_id"] = data.get("meeting_id") or snap.id
        mtg_proj = data.get("project_id", "proj-alpha")

        if project_id and mtg_proj != project_id:
            continue
        if allowed_projects is not None and mtg_proj not in allowed_projects:
            continue
        meetings.append(data)

    pids = [project_id] if project_id else (list(allowed_projects) if allowed_projects else None)
    sentiment_svc = get_sentiment_service(db=mtg_repo.db)
    return sentiment_svc.synthesize_pulse_trends(
        meetings=meetings,
        time_window=time_window,
        start_date=start_date,
        end_date=end_date,
        project_ids=pids,
    )



@internal_jobs_router.post("/evaluate-escalations")
async def cloud_scheduler_evaluate_escalations(
    payload: EvaluateEscalationsRequest | None = None,
) -> dict[str, Any]:
    """TRD Section 7.2: Cloud Scheduler 15-minute cron job evaluating 24h, 48h, and 72h SLA thresholds and Systemic Risk Spikes."""
    ref_dt: datetime | None = None
    if payload and payload.reference_time_iso:
        try:
            ref_dt = datetime.fromisoformat(
                payload.reference_time_iso.replace("Z", "+00:00")
            )
            if ref_dt.tzinfo is None:
                ref_dt = ref_dt.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid ISO timestamp in reference_time_iso",
            ) from exc

    svc = get_risk_service()
    return svc.evaluate_sla_escalations(reference_time=ref_dt)

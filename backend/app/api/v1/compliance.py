from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.core.enums import UserRole
from app.core.security import AuthenticatedUser, get_current_user
from app.schemas.compliance import (
    ComplianceExportRequest,
    ComplianceIntegrityResponse,
    ComplianceNarrativeRequest,
    ComplianceNarrativeResponse,
    CompliancePackageResponse,
    GdprMeetingPurgeResponse,
    GdprPurgeRequest,
)
from app.schemas.risk import RiskStatus
from app.services.compliance_service import get_compliance_service
from app.services.sanitization_service import load_compliance_framework_matrix
from app.services.sentiment_service import get_sentiment_service


router = APIRouter(prefix="/compliance", tags=["Compliance & WORM Audit Packages"])


def _role_str(user: AuthenticatedUser) -> str:
    return user.role.value if hasattr(user.role, "value") else str(user.role)


def _check_compliance_export_access(user: AuthenticatedUser, project_id: str) -> None:
    role = _role_str(user)
    if role in (UserRole.ADMIN.value, UserRole.EXECUTIVE.value):
        return
    if role == UserRole.MANAGER.value and project_id in (user.assigned_project_ids or []):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient privileges to generate compliance audit packages for this project",
    )


def _check_compliance_read_access(user: AuthenticatedUser, project_id: str) -> None:
    role = _role_str(user)
    if role in (UserRole.ADMIN.value, UserRole.EXECUTIVE.value):
        return
    if project_id in (user.assigned_project_ids or []):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient privileges to view compliance packages for this project",
    )


@router.get("/frameworks")
async def get_compliance_framework_matrix(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the version-controlled static compliance framework crosswalk matrix."""
    return load_compliance_framework_matrix()


@router.post("/ai-narrative", response_model=ComplianceNarrativeResponse)
async def get_compliance_narrative_endpoint(
    req: ComplianceNarrativeRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ComplianceNarrativeResponse:
    """TRD Section 10.6 / Task 7.1: Synthesize AI Privacy-Preserving Compliance Narrative on aggregate metadata."""
    _check_compliance_read_access(current_user, req.project_id)
    svc = get_compliance_service()

    raw_risks = svc.risk_repo.list_risks(project_id=req.project_id)
    filtered_risks = [
        r.model_dump()
        for r in raw_risks
        if r.status != RiskStatus.DRAFT_PENDING_ADJUDICATION
    ]

    meeting_snaps = svc.meeting_repo.db.collection("meetings").stream()
    group_pulse_bands: dict[str, str] = {}
    dialogue_texts: list[str] = []

    for s in meeting_snaps:
        mdata = s.to_dict() or {}
        if mdata.get("project_id", "proj-alpha") == req.project_id:
            m_id = mdata.get("meeting_id") or s.id
            group_breakdown = (
                mdata.get("group_pulse_scores")
                or mdata.get("group_breakdown")
                or {}
            )
            for grp, score_val in group_breakdown.items():
                group_pulse_bands[str(grp)] = svc.sanitizer.pulse_score_to_band_range(score_val)
            blocks = svc.meeting_repo.list_dialogue_blocks(m_id)
            for b in blocks:
                if b.text_scrubbed:
                    dialogue_texts.append(b.text_scrubbed)

    sanitized_risks = [
        svc.sanitizer.sanitize_risk_record(r, dialogue_texts=dialogue_texts)
        for r in filtered_risks
    ]

    sentiment_svc = get_sentiment_service(db=svc.db)
    client = sentiment_svc._client if sentiment_svc else None
    model_name = sentiment_svc.settings.gemini_model_name if sentiment_svc else "gemini-2.5-flash"

    narrative_dict = svc.sanitizer.synthesize_compliance_narrative(
        sanitized_risks=sanitized_risks,
        target_frameworks=req.target_frameworks,
        group_pulse_bands=group_pulse_bands,
        company_name=req.company_name,
        project_id=req.project_id,
        dialogue_texts=dialogue_texts,
        genai_client=client,
        gemini_model=model_name,
    )
    return ComplianceNarrativeResponse(**narrative_dict)


@router.post("/gdpr-purge", response_model=GdprMeetingPurgeResponse)
async def purge_compliance_meeting_gdpr_endpoint(
    req: GdprPurgeRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GdprMeetingPurgeResponse:
    """TRD Section 10.6 / Task 7.2: GDPR Article 17 Right-to-Erasure Cascade Purge."""
    role = _role_str(current_user)
    if role not in (UserRole.ADMIN.value, UserRole.EXECUTIVE.value, UserRole.MANAGER.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Managers, Executives, or Admins can execute GDPR Article 17 Purges",
        )
    svc = get_compliance_service()
    mtg = svc.meeting_repo.get_meeting(req.meeting_id)
    if not mtg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting '{req.meeting_id}' not found",
        )
    _check_compliance_export_access(current_user, mtg.project_id)
    return svc.purge_meeting_gdpr_article_17(
        meeting_id=req.meeting_id,
        actor_uid=current_user.uid,
        actor_role=role,
    )



@router.post(
    "/export",
    response_model=CompliancePackageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def export_compliance_package_endpoint(
    req: ComplianceExportRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CompliancePackageResponse:
    """Compile a 5-section compliance audit package, verify zero verbatim quotes, seal with SHA-256, and upload to WORM storage."""
    _check_compliance_export_access(current_user, req.project_id)
    svc = get_compliance_service()
    try:
        return svc.export_compliance_package(
            req=req,
            actor_uid=current_user.uid,
            actor_role=_role_str(current_user),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/packages", response_model=list[CompliancePackageResponse])
async def list_compliance_packages_endpoint(
    project_id: str | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[CompliancePackageResponse]:
    """List generated WORM compliance packages scoped to authorized projects."""
    svc = get_compliance_service()
    role = _role_str(current_user)
    allowed_projects: list[str] | None = None
    if role not in (UserRole.ADMIN.value, UserRole.EXECUTIVE.value):
        allowed_projects = list(current_user.assigned_project_ids or [])
        if project_id and project_id not in allowed_projects:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to project compliance packages",
            )
    return svc.compliance_repo.list_packages(
        project_id=project_id,
        allowed_project_ids=allowed_projects,
    )


@router.get("/packages/{package_id}", response_model=CompliancePackageResponse)
async def get_compliance_package_endpoint(
    package_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CompliancePackageResponse:
    """Retrieve metadata and structured sections for a sealed WORM compliance package."""
    svc = get_compliance_service()
    pkg = svc.compliance_repo.get_package(package_id)
    if not pkg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Compliance package '{package_id}' not found",
        )
    _check_compliance_read_access(current_user, pkg.project_id)
    return pkg


@router.get("/packages/{package_id}/download-url")
async def get_compliance_package_download_url_endpoint(
    package_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve signed download metadata and download URI for a sealed WORM compliance package."""
    svc = get_compliance_service()
    pkg = svc.compliance_repo.get_package(package_id)
    if not pkg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Compliance package '{package_id}' not found",
        )
    _check_compliance_read_access(current_user, pkg.project_id)
    return {
        "package_id": pkg.package_id,
        "download_url": f"/api/v1/compliance/packages/{pkg.package_id}/download",
        "sha256_hash": pkg.sha256_hash,
        "expires_in_seconds": 3600,
    }


@router.get("/packages/{package_id}/download")
async def download_compliance_package_endpoint(
    package_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Response:
    """Download the cryptographically sealed binary artifact (PDF, CSV, or JSON) from WORM storage."""
    svc = get_compliance_service()
    pkg = svc.compliance_repo.get_package(package_id)
    if not pkg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Compliance package '{package_id}' not found",
        )
    _check_compliance_read_access(current_user, pkg.project_id)

    downloaded = svc.storage_client.download_compliance_package(
        package_id=pkg.package_id,
        project_id=pkg.project_id,
    )
    if not downloaded:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"WORM artifact binary for '{package_id}' not found in storage",
        )
    raw_bytes, content_type, ext = downloaded
    headers = {
        "Content-Disposition": f'attachment; filename="{pkg.package_id}.{ext}"',
        "X-Prisk-SHA256": pkg.sha256_hash,
        "X-Prisk-WORM-Status": pkg.status,
    }
    return Response(content=raw_bytes, media_type=content_type, headers=headers)


@router.get(
    "/packages/{package_id}/verify",
    response_model=ComplianceIntegrityResponse,
)
async def verify_compliance_package_endpoint(
    package_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ComplianceIntegrityResponse:
    """Verify the SHA-256 cryptographic integrity of a stored WORM compliance package."""
    svc = get_compliance_service()
    pkg = svc.compliance_repo.get_package(package_id)
    if not pkg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Compliance package '{package_id}' not found",
        )
    _check_compliance_read_access(current_user, pkg.project_id)
    return svc.verify_package_integrity(package_id)

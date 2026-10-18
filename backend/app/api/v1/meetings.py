from datetime import datetime, timezone
import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import record_audit_event
from app.core.enums import UserRole
from app.core.security import AuthenticatedUser, get_current_user
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.risk_repository import RiskRepository
from app.schemas.meeting import (
    BlockScoreUpdateRequest,
    BlockScoreUpdateResponse,
    BubbleSplitRequest,
    BubbleSplitResponse,
    CommitGoldenRecordRequest,
    CommitGoldenRecordResponse,
    DialogueBlockResponse,
    MeetingCreate,
    MeetingDispatchBotRequest,
    MeetingDispatchBotResponse,
    MeetingResponse,
    MeetingStatus,
    SessionGroupingRequest,
    SessionGroupingResponse,
)
from app.schemas.risk import RiskStatus
from app.schemas.sentiment import BlockExplainResponse
from app.services.adjudication_service import get_adjudication_service
from app.services.meetstream_service import (
    DEFAULT_CONSENT_NOTICE,
    get_meetstream_service,
)
from app.services.sentiment_service import get_sentiment_service

router = APIRouter(prefix="/meetings", tags=["Meetings"])


def _check_project_access(current_user: AuthenticatedUser, project_id: str) -> None:
    """Ensure user is authorized to perform operations on the given project."""
    role_val = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if role_val == UserRole.ADMIN.value:
        return
    if role_val in (UserRole.EXECUTIVE.value, UserRole.MANAGER.value):
        if project_id in (current_user.assigned_project_ids or []):
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient privileges to dispatch meeting bot for this project",
    )


def _check_adjudication_or_project_access(
    current_user: AuthenticatedUser, project_id: str
) -> None:
    """Ensure user is an Admin, Executive, or assigned Manager/Adjudicator for this project."""
    role_val = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if role_val in (UserRole.ADMIN.value, UserRole.EXECUTIVE.value):
        return
    if role_val in (UserRole.MANAGER.value, UserRole.ADJUDICATOR.value):
        if project_id in (current_user.assigned_project_ids or []):
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient privileges to access adjudication or XAI for this meeting",
    )


@router.get("", response_model=list[MeetingResponse])
async def list_meetings(
    project_id: str | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[MeetingResponse]:
    """List meetings scoped to the user's authorized projects."""
    repo = MeetingRepository()
    snaps = repo.db.collection("meetings").stream()
    results: list[MeetingResponse] = []
    role_val = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    allowed_projects = set(current_user.assigned_project_ids or [])

    for snap in snaps:
        data = snap.to_dict() or {}
        data["meeting_id"] = data.get("meeting_id") or snap.id
        mtg_proj = data.get("project_id", "proj-alpha")
        if project_id and mtg_proj != project_id:
            continue
        if role_val not in (UserRole.ADMIN.value, UserRole.EXECUTIVE.value):
            if mtg_proj not in allowed_projects:
                continue
        results.append(MeetingResponse.model_validate(data))

    results.sort(key=lambda m: m.meeting_date or "", reverse=True)
    return results


@router.post("/dispatch-bot", response_model=MeetingDispatchBotResponse)
async def dispatch_meeting_bot(
    req: MeetingDispatchBotRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> MeetingDispatchBotResponse:
    """Trigger MeetStream.ai bot to join Google Meet with chat consent notice."""
    _check_project_access(current_user, req.project_id)

    meeting_id = req.meeting_id or f"meet-{uuid.uuid4().hex[:10]}"
    consent_notice = req.chat_consent_notice or DEFAULT_CONSENT_NOTICE

    repo = MeetingRepository()
    now_iso = datetime.now(timezone.utc).isoformat()

    existing = repo.get_meeting(meeting_id)
    if not existing:
        repo.create_meeting(
            MeetingCreate(
                meeting_id=meeting_id,
                project_id=req.project_id,
                title=req.title,
                platform="google_meet",
                meeting_date=now_iso,
                status=MeetingStatus.SCHEDULED,
            )
        )

    meetstream = get_meetstream_service()
    bot_result = meetstream.dispatch_bot(
        meeting_link=req.meeting_link,
        meeting_id=meeting_id,
        project_id=req.project_id,
        bot_name=req.bot_name,
        chat_consent_notice=consent_notice,
    )

    bot_id = bot_result.get("bot_id", f"bot-{uuid.uuid4().hex[:12]}")
    transcript_id = bot_result.get("transcript_id")

    repo.update_meeting(
        meeting_id,
        {
            "status": MeetingStatus.LIVE.value,
            "meetstream_bot_id": bot_id,
            "transcript_id": transcript_id,
            "model_metadata": {
                "bot_id": bot_id,
                "bot_name": req.bot_name,
                "dispatched_by": current_user.uid,
                "consent_notice": consent_notice,
            },
        },
    )

    record_audit_event(
        db=repo.db,
        event_type="MEETING_BOT_DISPATCHED",
        actor_uid=current_user.uid,
        target_id=meeting_id,
        metadata={
            "bot_id": bot_id,
            "project_id": req.project_id,
            "meeting_link": req.meeting_link,
        },
    )

    return MeetingDispatchBotResponse(
        meeting_id=meeting_id,
        project_id=req.project_id,
        bot_id=bot_id,
        transcript_id=transcript_id,
        status="DISPATCHED",
        meeting_link=req.meeting_link,
        chat_consent_notice=consent_notice,
        dispatched_at=now_iso,
    )


@router.get("/{meeting_id}", response_model=MeetingResponse)
async def get_meeting(
    meeting_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> MeetingResponse:
    """Retrieve details for a specific meeting."""
    repo = MeetingRepository()
    meeting = repo.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting '{meeting_id}' not found",
        )
    return meeting


@router.get("/{meeting_id}/adjudication")
async def get_adjudication_workspace(
    meeting_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Fetch complete meeting state, dialogue blocks, canonical groups, and draft risks for HITL Adjudication."""
    repo = MeetingRepository()
    meeting = repo.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting '{meeting_id}' not found",
        )
    _check_adjudication_or_project_access(current_user, meeting.project_id)

    blocks = repo.list_dialogue_blocks(meeting_id)
    risk_repo = RiskRepository(db=repo.db)
    draft_risks = [
        r.model_dump()
        for r in risk_repo.list_risks(project_id=meeting.project_id)
        if r.meeting_id == meeting_id
        and r.status in (RiskStatus.DRAFT_PENDING_ADJUDICATION, RiskStatus.OPEN)
    ]

    canonical_groups = [
        "Client Legal & Compliance",
        "Client Executive Sponsor",
        "Client Engineering",
        "Internal Delivery Team",
        "BUYER",
        "VENDOR",
        "INTERNAL",
    ]
    proj_doc = repo.db.collection("projects").document(meeting.project_id).get()
    if proj_doc.exists:
        proj_data = proj_doc.to_dict() or {}
        if proj_data.get("canonical_groups"):
            canonical_groups = list(proj_data["canonical_groups"])

    return {
        "meeting": meeting.model_dump(),
        "canonical_groups": canonical_groups,
        "ephemeral_speaker_map": meeting.ephemeral_speaker_map or {},
        "dialogue_blocks": [b.model_dump() for b in blocks],
        "draft_risks": draft_risks,
    }


@router.get("/{meeting_id}/blocks", response_model=list[DialogueBlockResponse])
async def list_dialogue_blocks(
    meeting_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[DialogueBlockResponse]:
    """List all scrubbed dialogue blocks for a meeting."""
    repo = MeetingRepository()
    meeting = repo.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting '{meeting_id}' not found",
        )
    return repo.list_dialogue_blocks(meeting_id)


@router.post("/{meeting_id}/analyze")
async def analyze_meeting_sentiment(
    meeting_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Run speaker-blind Gemini baseline rubric scoring with Few-Shot vector retrieval or Zero-Shot fallback."""
    repo = MeetingRepository()
    meeting = repo.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting '{meeting_id}' not found",
        )
    _check_adjudication_or_project_access(current_user, meeting.project_id)

    sentiment_svc = get_sentiment_service(db=repo.db)
    result = sentiment_svc.run_post_meeting_scoring_pipeline(
        meeting_id=meeting_id,
        project_id=meeting.project_id,
    )

    record_audit_event(
        db=repo.db,
        event_type="MEETING_BASELINE_SCORED",
        actor_uid=current_user.uid,
        target_id=meeting_id,
        metadata={
            "project_id": meeting.project_id,
            "inference_mode": result.get("inference_mode"),
            "few_shot_count": result.get("few_shot_count"),
            "pulse_score": result.get("pulse_score"),
        },
    )
    return result


@router.post("/{meeting_id}/regenerate-insights")
async def regenerate_meeting_insights(
    meeting_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Re-run Gemini summary, keyword extraction, and draft risk discovery using current adjudicated scores."""
    repo = MeetingRepository()
    meeting = repo.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting '{meeting_id}' not found",
        )
    _check_adjudication_or_project_access(current_user, meeting.project_id)

    sentiment_svc = get_sentiment_service(db=repo.db)
    result = sentiment_svc.regenerate_meeting_insights(
        meeting_id=meeting_id,
        project_id=meeting.project_id,
    )

    record_audit_event(
        db=repo.db,
        event_type="MEETING_INSIGHTS_REGENERATED",
        actor_uid=current_user.uid,
        target_id=meeting_id,
        metadata={
            "project_id": meeting.project_id,
            "inference_mode": result.get("inference_mode"),
            "few_shot_count": result.get("few_shot_count"),
            "pulse_score": result.get("pulse_score"),
            "draft_risks_created": result.get("draft_risks_created"),
        },
    )
    return result



@router.post(
    "/{meeting_id}/blocks/{block_id}/split",
    response_model=BubbleSplitResponse,
)
async def split_dialogue_block_endpoint(
    meeting_id: str,
    block_id: str,
    req: BubbleSplitRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> BubbleSplitResponse:
    """Split a single Dialogue Block into two sequential child blocks inheriting parent scores and group."""
    repo = MeetingRepository()
    meeting = repo.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting '{meeting_id}' not found",
        )
    _check_adjudication_or_project_access(current_user, meeting.project_id)

    try:
        split_idx = req.resolved_index()
        adj_svc = get_adjudication_service(db=repo.db)
        return adj_svc.split_dialogue_block(
            meeting_id=meeting_id,
            block_id=block_id,
            split_char_index=split_idx,
            actor_uid=current_user.uid,
        )
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.patch(
    "/{meeting_id}/session-grouping",
    response_model=SessionGroupingResponse,
)
async def update_session_grouping_endpoint(
    meeting_id: str,
    req: SessionGroupingRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> SessionGroupingResponse:
    """Map an ephemeral speaker identifier to a canonical Group in session state and auto-update unpinned blocks."""
    repo = MeetingRepository()
    meeting = repo.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting '{meeting_id}' not found",
        )
    _check_adjudication_or_project_access(current_user, meeting.project_id)

    try:
        adj_svc = get_adjudication_service(db=repo.db)
        return adj_svc.update_session_grouping(
            meeting_id=meeting_id,
            ephemeral_speaker_account_id=req.ephemeral_speaker_account_id,
            group_name=req.group_name,
            actor_uid=current_user.uid,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.patch(
    "/{meeting_id}/blocks/{block_id}/score",
    response_model=BlockScoreUpdateResponse,
)
async def update_dialogue_block_score_endpoint(
    meeting_id: str,
    block_id: str,
    req: BlockScoreUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> BlockScoreUpdateResponse:
    """Update a Dialogue Block's 0-100 Pulse Score or Group assignment and recalculate deterministic rollups."""
    repo = MeetingRepository()
    meeting = repo.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting '{meeting_id}' not found",
        )
    _check_adjudication_or_project_access(current_user, meeting.project_id)

    try:
        adj_svc = get_adjudication_service(db=repo.db)
        return adj_svc.update_block_score_or_group(
            meeting_id=meeting_id,
            block_id=block_id,
            new_score=req.resolved_score(),
            group_name=req.group_name,
            is_pinned=req.is_pinned,
            text_scrubbed=req.text_scrubbed,
            actor_uid=current_user.uid,
        )
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{meeting_id}/commit-golden-record",
    response_model=CommitGoldenRecordResponse,
)
async def commit_golden_record_endpoint(
    meeting_id: str,
    req: CommitGoldenRecordRequest | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CommitGoldenRecordResponse:
    """Commit the immutable Golden Record: strip ephemeral speaker accounts, persist corrected_contexts embeddings, and stream BigQuery rows."""
    repo = MeetingRepository()
    meeting = repo.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting '{meeting_id}' not found",
        )
    _check_adjudication_or_project_access(current_user, meeting.project_id)

    payload = req or CommitGoldenRecordRequest()
    adj_svc = get_adjudication_service(db=repo.db)
    return adj_svc.commit_golden_record(
        meeting_id=meeting_id,
        actor_uid=current_user.uid,
        approved_risk_ids=payload.approved_risk_ids,
        dismissed_risk_ids=payload.dismissed_risk_ids,
        mom_summary=payload.mom_summary,
        block_updates=payload.block_updates,
    )


@router.post(
    "/{meeting_id}/blocks/{block_id}/explain",
    response_model=BlockExplainResponse,
)
async def explain_dialogue_block_rationale(
    meeting_id: str,
    block_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> BlockExplainResponse:
    """Generate on-demand Explainable AI (XAI) rubric attributions with server-side verbatim substring offset validation."""
    repo = MeetingRepository()
    meeting = repo.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting '{meeting_id}' not found",
        )
    _check_adjudication_or_project_access(current_user, meeting.project_id)

    block = repo.get_dialogue_block(meeting_id, block_id)
    if not block:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dialogue block '{block_id}' not found in meeting '{meeting_id}'",
        )

    sentiment_svc = get_sentiment_service(db=repo.db)
    explanation = sentiment_svc.explain_dialogue_block(
        meeting_id=meeting_id,
        block=block,
    )

    record_audit_event(
        db=repo.db,
        event_type="XAI_INVOKED",
        actor_uid=current_user.uid,
        target_id=f"{meeting_id}/{block_id}",
        metadata={
            "meeting_id": meeting_id,
            "block_id": block_id,
            "project_id": meeting.project_id,
            "attributions_count": len(explanation.attributions),
            "pulse_score": explanation.pulse_score,
        },
    )

    return explanation


@router.delete(
    "/{meeting_id}/purge",
    summary="GDPR Article 17 Right to Erasure cascading meeting purge",
)
async def purge_meeting_gdpr_endpoint(
    meeting_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Execute cascading GDPR Article 17 purge across Firestore and BigQuery with tombstone ledger logging."""
    repo = MeetingRepository()
    meeting = repo.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting '{meeting_id}' not found",
        )

    role_val = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if role_val not in (UserRole.ADMIN.value, UserRole.EXECUTIVE.value):
        if not (
            role_val == UserRole.MANAGER.value
            and meeting.project_id in (current_user.assigned_project_ids or [])
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient privileges to execute GDPR Article 17 purge for this meeting",
            )

    from app.services.compliance_service import get_compliance_service

    svc = get_compliance_service(db=repo.db)
    res = svc.purge_meeting_gdpr_article_17(
        meeting_id=meeting_id,
        actor_uid=current_user.uid,
        actor_role=role_val,
    )
    return res.model_dump()

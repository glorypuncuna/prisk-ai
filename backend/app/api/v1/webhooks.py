from datetime import datetime, timezone
import json
import logging
from typing import Any
from fastapi import APIRouter, Header, HTTPException, Request, status


from app.core.database import record_audit_event
from app.repositories.meeting_repository import MeetingRepository
from app.schemas.meeting import DialogueBlockCreate, MeetingCreate, MeetingStatus
from app.services.dlp_service import get_dlp_service
from app.services.meetstream_service import get_meetstream_service
from app.services.sentiment_service import get_sentiment_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/meetstream/completed")
async def meetstream_completed_webhook(
    request: Request,
    x_meetstream_signature: str | None = Header(default=None, alias="X-Meetstream-Signature"),
    x_signature: str | None = Header(default=None, alias="X-Signature"),
) -> dict[str, Any]:
    """Receive post-meeting completed webhook from MeetStream with HMAC-SHA256 signature verification.
    
    1. Verifies HMAC-SHA256 signature against request body
    2. Fetches diarized transcript lines
    3. Runs single batch Google Cloud DLP PII de-identification pass
    4. Transactionally persists scrubbed dialogue blocks to Firestore (status=PROCESSING_POST_MEETING)
    5. Strictly AFTER verified Firestore persistence, invokes upstream transcript deletion
    """
    raw_body = await request.body()
    signature = x_meetstream_signature or x_signature

    meetstream = get_meetstream_service()
    if not meetstream.verify_webhook_signature(raw_body, signature):
        logger.warning("Rejected MeetStream webhook with invalid HMAC signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid MeetStream webhook signature",
        )

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed JSON payload: {e}",
        )

    bot_id = payload.get("bot_id") or ""
    transcript_id = payload.get("transcript_id")
    custom_attrs = payload.get("custom_attributes") or {}

    meeting_id = (
        payload.get("meeting_id")
        or custom_attrs.get("meeting_id")
    )

    repo = MeetingRepository()

    # If meeting_id was not explicitly in the webhook payload, look it up by bot_id
    if not meeting_id and bot_id:
        existing_meeting = repo.find_by_bot_id(bot_id)
        if existing_meeting:
            meeting_id = existing_meeting.meeting_id

    existing_meeting = repo.get_meeting(meeting_id) if meeting_id else None
    if not existing_meeting:
        meeting_id = meeting_id or (f"meet-{bot_id}" if bot_id else "meet-incoming")
        project_id = custom_attrs.get("project_id", "proj-alpha")
        target_project_id = project_id
        now_iso = datetime.now(timezone.utc).isoformat()
        repo.create_meeting(
            MeetingCreate(
                meeting_id=meeting_id,
                project_id=project_id,
                title="Google Meet Ingested Session",
                platform="google_meet",
                meeting_date=now_iso,
                created_at=now_iso,
                status=MeetingStatus.SCHEDULED,
            )
        )
    else:
        target_project_id = existing_meeting.project_id


    # Fetch diarized transcript items (or use payload if provided directly)
    transcript_items = payload.get("transcript")
    if not transcript_items or not isinstance(transcript_items, list):
        transcript_items = meetstream.fetch_transcript(
            transcript_id=transcript_id, bot_id=bot_id
        )

    # 3. Google Cloud DLP batch PII scrubbing pass
    dlp_service = get_dlp_service()
    scrubbed_blocks_data = dlp_service.deidentify_batch(transcript_items)

    dialogue_blocks: list[DialogueBlockCreate] = []
    for idx, item in enumerate(scrubbed_blocks_data):
        speaker = item.get("speaker") or f"Speaker {idx + 1}"
        ephemeral_spk_id = item.get("speaker_id") or f"ms_spk_{idx + 1:02d}"
        scrubbed_text = item.get("text_scrubbed") or item.get("text", "")
        word_count = len(scrubbed_text.split()) if scrubbed_text else 0

        block = DialogueBlockCreate(
            block_id=f"blk-{idx + 1:04d}",
            sequence_index=idx,
            start_time_sec=float(item.get("start_time", idx * 5.0)),
            end_time_sec=float(item.get("end_time", (idx + 1) * 5.0)),
            speaker_alias=speaker,
            display_speaker_label=speaker,
            ephemeral_speaker_account_id=ephemeral_spk_id,
            text_scrubbed=scrubbed_text,
            word_count=word_count,
            dlp_redaction_flags=item.get("dlp_redaction_flags", []),
        )
        dialogue_blocks.append(block)

    # 4. Transactional Firestore persistence
    try:
        saved_blocks = repo.save_scrubbed_dialogue_blocks(
            meeting_id=meeting_id,
            blocks=dialogue_blocks,
            meeting_updates={
                "status": MeetingStatus.PROCESSING_POST_MEETING.value,
                "meetstream_bot_id": bot_id,
                "transcript_id": transcript_id,
            },
        )
    except Exception as e:
        logger.error(
            f"Failed to persist scrubbed dialogue blocks for meeting '{meeting_id}': {e}. "
            f"Aborting upstream deletion to prevent data loss."
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database write failure: {e}",
        )

    # 5. Verified upstream transcript deletion: executed STRICTLY AFTER confirmed Firestore write
    upstream_deleted = False
    if bot_id:
        try:
            upstream_deleted = meetstream.delete_upstream_transcript(bot_id)
            record_audit_event(
                db=repo.db,
                event_type="UPSTREAM_TRANSCRIPT_DELETED",
                actor_uid="system:meetstream-ingestion",
                target_id=meeting_id,
                metadata={
                    "bot_id": bot_id,
                    "upstream_deleted": upstream_deleted,
                    "blocks_count": len(saved_blocks),
                },
            )
        except Exception as del_err:
            logger.warning(
                f"Non-fatal error deleting upstream transcript for bot '{bot_id}': {del_err}"
            )

    # 6. Automatic post-ingestion AI scoring handoff
    ai_result: dict[str, Any] = {}
    try:
        sentiment_svc = get_sentiment_service(db=repo.db)
        ai_result = sentiment_svc.run_post_meeting_scoring_pipeline(
            meeting_id=meeting_id,
            project_id=target_project_id,
        )
        record_audit_event(
            db=repo.db,
            event_type="MEETING_BASELINE_SCORED",
            actor_uid="system:sentiment-pipeline",
            target_id=meeting_id,
            metadata={
                "project_id": target_project_id,
                "inference_mode": ai_result.get("inference_mode"),
                "few_shot_count": ai_result.get("few_shot_count"),
                "pulse_score": ai_result.get("pulse_score"),
            },
        )
    except Exception as ai_err:
        logger.error(
            f"Post-meeting AI scoring pipeline failure for meeting '{meeting_id}': {ai_err}"
        )

    updated_meeting = repo.get_meeting(meeting_id)
    final_status = (
        updated_meeting.status
        if updated_meeting
        else MeetingStatus.PENDING_ADJUDICATION.value
    )

    return {
        "status": "success",
        "meeting_id": meeting_id,
        "blocks_count": len(saved_blocks),
        "meeting_status": str(final_status),
        "upstream_transcript_deleted": upstream_deleted,
        "pulse_score": ai_result.get("pulse_score"),
        "ai_analysis": ai_result,
    }


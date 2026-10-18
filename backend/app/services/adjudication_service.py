from datetime import datetime, timezone
import logging
import uuid
from typing import Any

from app.core.bigquery import BigQueryAnalyticsClient
from app.core.database import get_firestore_client, record_audit_event
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.risk_repository import RiskRepository
from app.repositories.sentiment_repository import SentimentRepository
from app.schemas.meeting import (
    BlockOverrideCommitItem,
    BlockScoreUpdateResponse,
    BubbleSplitResponse,
    CommitGoldenRecordResponse,
    DialogueBlockCreate,
    DialogueBlockResponse,
    GroupPulseMetric,
    MeetingStatus,
    SessionGroupingResponse,
)
from app.schemas.risk import RiskStatus
from app.schemas.sentiment import CorrectedContextCreate
from app.services.sentiment_service import get_sentiment_service

logger = logging.getLogger(__name__)


def compute_deterministic_rollups(
    blocks: list[DialogueBlockResponse | dict[str, Any]],
    existing_group_scores: dict[str, Any] | None = None,
) -> tuple[float, dict[str, Any]]:
    """Compute word-count-weighted Group Pulse Scores and arithmetic mean Overall Meeting Pulse Score."""
    existing_map = existing_group_scores or {}
    group_weighted_sums: dict[str, float] = {}
    group_weights: dict[str, int] = {}
    group_counts: dict[str, int] = {}

    for block in blocks:
        if isinstance(block, DialogueBlockResponse):
            grp = block.group_name or block.group_id or "INTERNAL"
            score = block.sentiment_score if block.sentiment_score is not None else 50.0
            text = block.text_scrubbed or ""
            wc = block.word_count or len(text.split())
        else:
            grp = str(block.get("group_name") or block.get("group_id") or "INTERNAL")
            raw_score = block.get("sentiment_score")
            score = float(raw_score) if raw_score is not None else 50.0
            text = str(block.get("text_scrubbed") or "")
            wc = int(block.get("word_count") or len(text.split()))

        weight = max(1, wc)
        group_weighted_sums[grp] = group_weighted_sums.get(grp, 0.0) + (score * weight)
        group_weights[grp] = group_weights.get(grp, 0) + weight
        group_counts[grp] = group_counts.get(grp, 0) + 1

    group_scores: dict[str, Any] = {}
    for grp, weighted_sum in group_weighted_sums.items():
        total_w = max(1, group_weights.get(grp, 1))
        avg_score = round(weighted_sum / total_w, 1)
        prev_entry = existing_map.get(grp) if isinstance(existing_map.get(grp), dict) else {}
        group_scores[grp] = GroupPulseMetric(
            pulse_score=avg_score,
            block_count=group_counts.get(grp, 1),
            top_liked_words=list(prev_entry.get("top_liked_words", [])),
            top_disliked_words=list(prev_entry.get("top_disliked_words", [])),
        ).model_dump()

    overall_pulse = (
        round(
            sum(g["pulse_score"] for g in group_scores.values()) / len(group_scores),
            1,
        )
        if group_scores
        else 50.0
    )
    return overall_pulse, group_scores


class AdjudicationService:
    """Service orchestrating HITL Bubble Splits, ephemeral speaker-to-group mapping, rollups, and Golden Record commits."""

    def __init__(self, db: Any | None = None) -> None:
        self.db = db or get_firestore_client()
        self.meeting_repo = MeetingRepository(db=self.db)
        self.sentiment_repo = SentimentRepository(db=self.db)
        self.risk_repo = RiskRepository(db=self.db)
        self.sentiment_svc = get_sentiment_service(db=self.db)
        self.bq_client = BigQueryAnalyticsClient()

    def split_dialogue_block(
        self,
        meeting_id: str,
        block_id: str,
        split_char_index: int,
        actor_uid: str,
    ) -> BubbleSplitResponse:
        """Divide a single Dialogue Block into two sequential child blocks without invoking an LLM."""
        meeting = self.meeting_repo.get_meeting(meeting_id)
        if not meeting:
            raise KeyError(f"Meeting '{meeting_id}' not found")
        if meeting.status == MeetingStatus.GOLDEN_RECORD.value:
            raise ValueError("Cannot split blocks on a locked Golden Record meeting")

        parent_block = self.meeting_repo.get_dialogue_block(meeting_id, block_id)
        if not parent_block:
            raise KeyError(f"Dialogue block '{block_id}' not found in meeting '{meeting_id}'")

        full_text = parent_block.text_scrubbed or ""
        if split_char_index <= 0 or split_char_index >= len(full_text):
            raise ValueError(
                f"split_char_index ({split_char_index}) must be strictly between 1 and {len(full_text) - 1}"
            )

        left_text = full_text[:split_char_index].strip()
        right_text = full_text[split_char_index:].strip()
        if not left_text or not right_text:
            raise ValueError("Bubble split must produce two non-empty text segments")

        child_a_id = f"{block_id}a"
        child_b_id = f"{block_id}b"

        all_blocks = self.meeting_repo.list_dialogue_blocks(meeting_id)
        existing_ids = {b.block_id for b in all_blocks}
        if child_a_id in existing_ids or child_b_id in existing_ids:
            suffix = uuid.uuid4().hex[:4]
            child_a_id = f"{block_id}-{suffix}-a"
            child_b_id = f"{block_id}-{suffix}-b"

        parent_seq = parent_block.sequence_index
        parent_start = parent_block.start_time_sec or 0.0
        parent_end = parent_block.end_time_sec or (parent_start + 6.0)
        ratio = split_char_index / max(1, len(full_text))
        mid_time = round(parent_start + (parent_end - parent_start) * ratio, 2)

        inherited_score = (
            parent_block.sentiment_score
            if parent_block.sentiment_score is not None
            else (parent_block.ai_initial_score if parent_block.ai_initial_score is not None else 50.0)
        )
        inherited_group = parent_block.group_name or parent_block.group_id or "INTERNAL"

        child_a = DialogueBlockCreate(
            block_id=child_a_id,
            sequence_index=parent_seq,
            parent_block_id=block_id,
            start_time_sec=parent_start,
            end_time_sec=mid_time,
            speaker_alias=parent_block.speaker_alias,
            display_speaker_label=parent_block.display_speaker_label,
            ephemeral_speaker_account_id=parent_block.ephemeral_speaker_account_id,
            group_id=inherited_group,
            group_name=inherited_group,
            company_name=parent_block.company_name,
            optional_participant_name=parent_block.optional_participant_name,
            text_scrubbed=left_text,
            word_count=max(1, len(left_text.split())),
            dlp_redaction_flags=[
                flag for flag in parent_block.dlp_redaction_flags if f"[{flag}]" in left_text or flag in left_text
            ] or list(parent_block.dlp_redaction_flags),
            sentiment_score=inherited_score,
            ai_initial_score=parent_block.ai_initial_score or inherited_score,
            ai_confidence=parent_block.ai_confidence,
            rubric_scores=parent_block.rubric_scores,
            embedding=None,
            is_split=True,
            is_pinned=parent_block.is_pinned,
            is_human_overridden=parent_block.is_human_overridden,
        )

        child_b = DialogueBlockCreate(
            block_id=child_b_id,
            sequence_index=parent_seq + 1,
            parent_block_id=block_id,
            start_time_sec=mid_time,
            end_time_sec=parent_end,
            speaker_alias=parent_block.speaker_alias,
            display_speaker_label=parent_block.display_speaker_label,
            ephemeral_speaker_account_id=parent_block.ephemeral_speaker_account_id,
            group_id=inherited_group,
            group_name=inherited_group,
            company_name=parent_block.company_name,
            optional_participant_name=parent_block.optional_participant_name,
            text_scrubbed=right_text,
            word_count=max(1, len(right_text.split())),
            dlp_redaction_flags=[
                flag for flag in parent_block.dlp_redaction_flags if f"[{flag}]" in right_text or flag in right_text
            ] or list(parent_block.dlp_redaction_flags),
            sentiment_score=inherited_score,
            ai_initial_score=parent_block.ai_initial_score or inherited_score,
            ai_confidence=parent_block.ai_confidence,
            rubric_scores=parent_block.rubric_scores,
            embedding=None,
            is_split=True,
            is_pinned=parent_block.is_pinned,
            is_human_overridden=parent_block.is_human_overridden,
        )

        # Shift subsequent blocks by +1 sequence_index
        for b in all_blocks:
            if b.block_id != block_id and b.sequence_index > parent_seq:
                self.meeting_repo.update_dialogue_block(
                    meeting_id=meeting_id,
                    block_id=b.block_id,
                    updates={"sequence_index": b.sequence_index + 1},
                )

        self.meeting_repo.delete_dialogue_block(meeting_id, block_id)
        resp_a = self.meeting_repo.create_dialogue_block(meeting_id, child_a)
        resp_b = self.meeting_repo.create_dialogue_block(meeting_id, child_b)

        updated_blocks = self.meeting_repo.list_dialogue_blocks(meeting_id)
        overall_pulse, group_scores = compute_deterministic_rollups(
            updated_blocks, meeting.group_scores
        )
        self.meeting_repo.update_meeting(
            meeting_id=meeting_id,
            updates={
                "pulse_score": overall_pulse,
                "group_scores": group_scores,
            },
        )

        audit_event = record_audit_event(
            db=self.db,
            event_type="BUBBLE_SPLIT",
            actor_uid=actor_uid,
            target_id=f"{meeting_id}/{block_id}",
            metadata={
                "meeting_id": meeting_id,
                "parent_block_id": block_id,
                "child_block_ids": [child_a_id, child_b_id],
                "split_char_index": split_char_index,
                "inherited_score": inherited_score,
                "inherited_group": inherited_group,
            },
        )
        self.bq_client.stream_audit_ledger_event(audit_event)

        return BubbleSplitResponse(
            meeting_id=meeting_id,
            parent_block_id=block_id,
            child_blocks=[resp_a, resp_b],
            blocks=updated_blocks,
            pulse_score=overall_pulse,
            group_scores=group_scores,
        )

    def update_session_grouping(
        self,
        meeting_id: str,
        ephemeral_speaker_account_id: str,
        group_name: str,
        actor_uid: str,
    ) -> SessionGroupingResponse:
        """Map an ephemeral speaker identifier to a canonical Group in active session state and update unpinned blocks."""
        meeting = self.meeting_repo.get_meeting(meeting_id)
        if not meeting:
            raise KeyError(f"Meeting '{meeting_id}' not found")
        if meeting.status == MeetingStatus.GOLDEN_RECORD.value:
            raise ValueError("Cannot modify session grouping on a locked Golden Record meeting")

        speaker_map = dict(meeting.ephemeral_speaker_map or {})
        speaker_map[ephemeral_speaker_account_id] = group_name

        blocks = self.meeting_repo.list_dialogue_blocks(meeting_id)
        updated_block_ids: list[str] = []

        for block in blocks:
            block_speaker_key = (
                block.ephemeral_speaker_account_id
                or block.speaker_alias
                or block.display_speaker_label
            )
            if block_speaker_key == ephemeral_speaker_account_id and not block.is_pinned:
                self.meeting_repo.update_dialogue_block(
                    meeting_id=meeting_id,
                    block_id=block.block_id,
                    updates={
                        "ephemeral_speaker_account_id": ephemeral_speaker_account_id,
                        "group_id": group_name,
                        "group_name": group_name,
                    },
                )
                updated_block_ids.append(block.block_id)

        refreshed_blocks = self.meeting_repo.list_dialogue_blocks(meeting_id)
        overall_pulse, group_scores = compute_deterministic_rollups(
            refreshed_blocks, meeting.group_scores
        )

        self.meeting_repo.update_meeting(
            meeting_id=meeting_id,
            updates={
                "ephemeral_speaker_map": speaker_map,
                "pulse_score": overall_pulse,
                "group_scores": group_scores,
            },
        )

        audit_event = record_audit_event(
            db=self.db,
            event_type="GROUP_TAG_CHANGE",
            actor_uid=actor_uid,
            target_id=meeting_id,
            metadata={
                "meeting_id": meeting_id,
                "ephemeral_speaker_account_id": ephemeral_speaker_account_id,
                "group_name": group_name,
                "updated_block_ids": updated_block_ids,
                "pulse_score": overall_pulse,
            },
        )
        self.bq_client.stream_audit_ledger_event(audit_event)

        return SessionGroupingResponse(
            meeting_id=meeting_id,
            ephemeral_speaker_map=speaker_map,
            updated_block_ids=updated_block_ids,
            blocks=refreshed_blocks,
            pulse_score=overall_pulse,
            group_scores=group_scores,
        )

    def update_block_score_or_group(
        self,
        meeting_id: str,
        block_id: str,
        new_score: float | None,
        group_name: str | None,
        is_pinned: bool | None,
        text_scrubbed: str | None,
        actor_uid: str,
    ) -> BlockScoreUpdateResponse:
        """Update an individual Dialogue Block's 0-100 Pulse Score, Group tag, or scrubbed text, and recalculate rollups."""
        meeting = self.meeting_repo.get_meeting(meeting_id)
        if not meeting:
            raise KeyError(f"Meeting '{meeting_id}' not found")
        if meeting.status == MeetingStatus.GOLDEN_RECORD.value:
            raise ValueError("Cannot modify blocks on a locked Golden Record meeting")

        block = self.meeting_repo.get_dialogue_block(meeting_id, block_id)
        if not block:
            raise KeyError(f"Dialogue block '{block_id}' not found in meeting '{meeting_id}'")

        updates: dict[str, Any] = {}
        previous_score = block.sentiment_score

        if new_score is not None:
            clamped_score = round(max(0.0, min(100.0, float(new_score))), 1)
            updates["sentiment_score"] = clamped_score
            updates["is_human_overridden"] = True
            if block.ai_initial_score is None:
                updates["ai_initial_score"] = previous_score if previous_score is not None else 50.0

        if group_name is not None:
            updates["group_id"] = group_name
            updates["group_name"] = group_name
            if is_pinned is None:
                updates["is_pinned"] = True

        if is_pinned is not None:
            updates["is_pinned"] = is_pinned

        if text_scrubbed is not None and text_scrubbed.strip():
            clean_txt = text_scrubbed.strip()
            updates["text_scrubbed"] = clean_txt
            updates["word_count"] = max(1, len(clean_txt.split()))

        updated_block = self.meeting_repo.update_dialogue_block(
            meeting_id=meeting_id,
            block_id=block_id,
            updates=updates,
        )

        refreshed_blocks = self.meeting_repo.list_dialogue_blocks(meeting_id)
        overall_pulse, group_scores = compute_deterministic_rollups(
            refreshed_blocks, meeting.group_scores
        )

        self.meeting_repo.update_meeting(
            meeting_id=meeting_id,
            updates={
                "pulse_score": overall_pulse,
                "group_scores": group_scores,
            },
        )

        if new_score is not None:
            audit_event = record_audit_event(
                db=self.db,
                event_type="SLIDER_OVERRIDE",
                actor_uid=actor_uid,
                target_id=f"{meeting_id}/{block_id}",
                metadata={
                    "meeting_id": meeting_id,
                    "block_id": block_id,
                    "previous_score": previous_score,
                    "new_score": updates["sentiment_score"],
                    "overall_pulse_score": overall_pulse,
                },
            )
            self.bq_client.stream_audit_ledger_event(audit_event)

        return BlockScoreUpdateResponse(
            meeting_id=meeting_id,
            block=updated_block,
            pulse_score=overall_pulse,
            group_scores=group_scores,
        )

    def commit_golden_record(
        self,
        meeting_id: str,
        actor_uid: str,
        approved_risk_ids: list[str] | None = None,
        dismissed_risk_ids: list[str] | None = None,
        mom_summary: dict[str, Any] | None = None,
        block_updates: list[BlockOverrideCommitItem] | None = None,
    ) -> CommitGoldenRecordResponse:
        """Permanently strip ephemeral speaker accounts, embed overridden blocks into corrected_contexts, promote risks, and stream to BigQuery."""
        meeting = self.meeting_repo.get_meeting(meeting_id)
        if not meeting:
            raise KeyError(f"Meeting '{meeting_id}' not found")

        now_iso = datetime.now(timezone.utc).isoformat()
        meeting_date_str = (meeting.meeting_date or now_iso)[:10]

        # Apply any final inline block updates sent with the commit request
        if block_updates:
            for item in block_updates:
                existing_blk = self.meeting_repo.get_dialogue_block(meeting_id, item.block_id)
                if not existing_blk:
                    continue
                patch_data: dict[str, Any] = {}
                if item.sentiment_score is not None:
                    patch_data["sentiment_score"] = round(float(item.sentiment_score), 1)
                    if (
                        item.is_human_overridden
                        or existing_blk.ai_initial_score is None
                        or abs(float(item.sentiment_score) - float(existing_blk.ai_initial_score)) >= 0.5
                    ):
                        patch_data["is_human_overridden"] = True
                if item.is_human_overridden is not None:
                    patch_data["is_human_overridden"] = item.is_human_overridden
                if item.group_name is not None:
                    patch_data["group_id"] = item.group_name
                    patch_data["group_name"] = item.group_name
                if item.text_scrubbed is not None and item.text_scrubbed.strip():
                    patch_data["text_scrubbed"] = item.text_scrubbed.strip()
                    patch_data["word_count"] = max(1, len(patch_data["text_scrubbed"].split()))
                if patch_data:
                    self.meeting_repo.update_dialogue_block(meeting_id, item.block_id, patch_data)

        blocks = self.meeting_repo.list_dialogue_blocks(meeting_id)
        corrected_contexts_saved = 0
        bq_dialogue_rows: list[dict[str, Any]] = []

        # Strip ephemeral speaker identifiers from all dialogue blocks and embed overridden blocks
        for block in blocks:
            emb = block.embedding
            if block.is_human_overridden:
                emb = self.sentiment_svc.generate_embedding(block.text_scrubbed)
                rubric_dict: dict[str, float] = {}
                if isinstance(block.rubric_scores, dict):
                    rubric_dict = {
                        k: float(v)
                        for k, v in block.rubric_scores.items()
                        if isinstance(v, (int, float))
                    }
                elif hasattr(block.rubric_scores, "model_dump"):
                    rubric_dict = block.rubric_scores.model_dump()

                correction_id = f"corr_{meeting_id}_{block.block_id}"
                self.sentiment_repo.create_corrected_context(
                    CorrectedContextCreate(
                        correction_id=correction_id,
                        project_id=meeting.project_id,
                        group_name=block.group_name or block.group_id or "INTERNAL",
                        scrubbed_text=block.text_scrubbed,
                        embedding=emb,
                        ai_initial_score=(
                            block.ai_initial_score
                            if block.ai_initial_score is not None
                            else 50.0
                        ),
                        human_adjusted_score=(
                            block.sentiment_score
                            if block.sentiment_score is not None
                            else 50.0
                        ),
                        rubric_breakdown=rubric_dict,
                        adjudicator_uid=actor_uid,
                        created_at=now_iso,
                    )
                )
                corrected_contexts_saved += 1

            self.meeting_repo.update_dialogue_block(
                meeting_id=meeting_id,
                block_id=block.block_id,
                updates={
                    "ephemeral_speaker_account_id": None,
                    "speaker_alias": None,
                    "optional_participant_name": None,
                    "embedding": emb,
                },
            )

            bq_dialogue_rows.append(
                {
                    "meeting_id": meeting_id,
                    "project_id": meeting.project_id,
                    "meeting_date": meeting_date_str,
                    "block_id": block.block_id,
                    "group_id": block.group_id or block.group_name or "INTERNAL",
                    "group_name": block.group_name or block.group_id or "INTERNAL",
                    "company_name": block.company_name or "Enterprise Client",
                    "text_scrubbed": block.text_scrubbed,
                    "word_count": max(1, block.word_count or len(block.text_scrubbed.split())),
                    "sentiment_score": (
                        block.sentiment_score if block.sentiment_score is not None else 50.0
                    ),
                    "is_human_overridden": bool(block.is_human_overridden),
                    "committed_at": now_iso,
                }
            )

        sanitized_blocks = self.meeting_repo.list_dialogue_blocks(meeting_id)
        overall_pulse, group_scores = compute_deterministic_rollups(
            sanitized_blocks, meeting.group_scores
        )

        # Promote DRAFT_PENDING_ADJUDICATION risks to OPEN (or DISMISSED)
        draft_risks = [
            r
            for r in self.risk_repo.list_risks(project_id=meeting.project_id)
            if r.meeting_id == meeting_id
            and r.status == RiskStatus.DRAFT_PENDING_ADJUDICATION
        ]
        promoted_risk_ids: list[str] = []
        dismissed_set = set(dismissed_risk_ids or [])
        approved_set = set(approved_risk_ids) if approved_risk_ids is not None else None

        for risk in draft_risks:
            if risk.risk_id in dismissed_set:
                self.risk_repo.update_risk(
                    risk.risk_id,
                    {"status": RiskStatus.DISMISSED.value},
                )
            elif approved_set is None or risk.risk_id in approved_set:
                self.risk_repo.update_risk(
                    risk.risk_id,
                    {
                        "status": RiskStatus.OPEN.value,
                        "escalation_config": {
                            "enabled": True,
                            "sla_started_at": now_iso,
                            "last_escalated_tier_hours": 0,
                        },
                    },
                )
                promoted_risk_ids.append(risk.risk_id)

        meeting_updates: dict[str, Any] = {
            "status": MeetingStatus.GOLDEN_RECORD.value,
            "ephemeral_speaker_map": None,
            "participants": [],
            "pulse_score": overall_pulse,
            "group_scores": group_scores,
            "golden_record_committed_at": now_iso,
        }
        if mom_summary is not None:
            meeting_updates["mom_summary"] = mom_summary

        self.meeting_repo.update_meeting(meeting_id, meeting_updates)

        # Stream analytical rows to BigQuery
        self.bq_client.stream_golden_dialogue_records(bq_dialogue_rows)

        bq_group_rows: list[dict[str, Any]] = []
        for grp_name, grp_metric in group_scores.items():
            bq_group_rows.append(
                {
                    "meeting_id": meeting_id,
                    "project_id": meeting.project_id,
                    "company_name": "Enterprise Client",
                    "group_name": grp_name,
                    "meeting_date": meeting_date_str,
                    "pulse_score": float(grp_metric.get("pulse_score", 50.0)),
                    "overall_meeting_score": overall_pulse,
                    "block_count": int(grp_metric.get("block_count", 1)),
                    "top_liked_words": list(grp_metric.get("top_liked_words", [])),
                    "top_disliked_words": list(grp_metric.get("top_disliked_words", [])),
                    "committed_at": now_iso,
                }
            )
        self.bq_client.stream_group_pulse_history(bq_group_rows)

        audit_event = record_audit_event(
            db=self.db,
            event_type="GOLDEN_RECORD_COMMIT",
            actor_uid=actor_uid,
            target_id=meeting_id,
            metadata={
                "meeting_id": meeting_id,
                "project_id": meeting.project_id,
                "pulse_score": overall_pulse,
                "corrected_contexts_saved": corrected_contexts_saved,
                "promoted_risk_ids": promoted_risk_ids,
                "bigquery_rows_streamed": len(bq_dialogue_rows),
            },
        )
        self.bq_client.stream_audit_ledger_event(audit_event)

        return CommitGoldenRecordResponse(
            meeting_id=meeting_id,
            project_id=meeting.project_id,
            status=MeetingStatus.GOLDEN_RECORD.value,
            pulse_score=overall_pulse,
            group_scores=group_scores,
            ephemeral_speaker_map=None,
            corrected_contexts_saved=corrected_contexts_saved,
            promoted_risk_ids=promoted_risk_ids,
            bigquery_rows_streamed=len(bq_dialogue_rows),
            committed_at=now_iso,
        )


def get_adjudication_service(db: Any | None = None) -> AdjudicationService:
    return AdjudicationService(db=db)

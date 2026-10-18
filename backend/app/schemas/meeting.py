from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator


class MeetingStatus(StrEnum):
    """Lifecycle statuses for a meeting as defined in TRD Section 3.1."""

    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    PROCESSING_POST_MEETING = "PROCESSING_POST_MEETING"
    PENDING_ADJUDICATION = "PENDING_ADJUDICATION"
    COMMITTED = "COMMITTED"
    GOLDEN_RECORD = "GOLDEN_RECORD"
    PURGED_CONSENT_REVOKED = "PURGED_CONSENT_REVOKED"


class CanonicalGroup(StrEnum):
    """Canonical group categories for relationship tracking."""

    BUYER = "BUYER"
    VENDOR = "VENDOR"
    INTERNAL = "INTERNAL"


class RubricBreakdown(BaseModel):
    """4-dimension sentiment rubric breakdown (0-25 each, totaling 0-100)."""

    emotional_valence: float = Field(ge=0, le=25, default=12.5)
    delivery_alignment: float = Field(ge=0, le=25, default=12.5)
    relationship_trust: float = Field(ge=0, le=25, default=12.5)
    momentum_commitment: float = Field(ge=0, le=25, default=12.5)

    def total_score(self) -> float:
        return (
            self.emotional_valence
            + self.delivery_alignment
            + self.relationship_trust
            + self.momentum_commitment
        )


class XAIAttributionItem(BaseModel):
    """Verbatim substring attribution item for Explainable AI (XAI)."""

    verbatim_phrase: str
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    attribution_weight: float
    rubric_dimension: str
    rationale: str


class XAIExplanation(BaseModel):
    """Explainable AI attribution container for a dialogue block."""

    computed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    attributions: list[XAIAttributionItem] = Field(default_factory=list)


class DialogueBlockCreate(BaseModel):
    """Schema for creating a dialogue block document in the subcollection."""

    block_id: str
    sequence_index: int = Field(ge=0)
    parent_block_id: str | None = None
    start_time_sec: float | None = None
    end_time_sec: float | None = None
    speaker_alias: str | None = None
    display_speaker_label: str | None = None
    ephemeral_speaker_account_id: str | None = None
    group_id: str | None = None
    group_name: str | None = None
    company_name: str | None = None
    optional_participant_name: str | None = None
    text_scrubbed: str = Field(description="DLP scrubbed dialogue text")
    word_count: int = Field(default=0, ge=0)
    dlp_redaction_flags: list[str] = Field(default_factory=list)
    sentiment_score: float | None = Field(default=None, ge=0, le=100)
    ai_initial_score: float | None = Field(default=None, ge=0, le=100)
    ai_confidence: float | None = Field(default=None, ge=0, le=1)
    rubric_scores: RubricBreakdown | dict[str, float] | None = None
    embedding: list[float] | None = Field(
        default=None,
        description="768-dimensional float embedding from text-embedding-004",
    )
    is_split: bool = False
    is_pinned: bool = False
    is_human_overridden: bool = False
    xai_attribution: XAIExplanation | dict[str, Any] | None = None

    @field_validator("embedding")
    @classmethod
    def validate_embedding_dimension(
        cls, value: list[float] | None
    ) -> list[float] | None:
        if value is not None and len(value) != 768:
            raise ValueError(
                f"Embedding vector must have exactly 768 dimensions, received {len(value)}"
            )
        return value


class DialogueBlockResponse(BaseModel):
    """API response schema for a dialogue block."""

    model_config = ConfigDict(from_attributes=True)

    block_id: str
    sequence_index: int
    parent_block_id: str | None = None
    start_time_sec: float | None = None
    end_time_sec: float | None = None
    speaker_alias: str | None = None
    display_speaker_label: str | None = None
    ephemeral_speaker_account_id: str | None = None
    group_id: str | None = None
    group_name: str | None = None
    company_name: str | None = None
    optional_participant_name: str | None = None
    text_scrubbed: str
    word_count: int
    dlp_redaction_flags: list[str] = Field(default_factory=list)
    sentiment_score: float | None = None
    ai_initial_score: float | None = None
    ai_confidence: float | None = None
    rubric_scores: RubricBreakdown | dict[str, Any] | None = None
    embedding: list[float] | None = None
    is_split: bool = False
    is_pinned: bool = False
    is_human_overridden: bool = False
    xai_attribution: XAIExplanation | dict[str, Any] | None = None


class ActionItem(BaseModel):
    """MoM action item."""

    action_id: str
    description: str
    owner_group: str
    due_date: str | None = None


class MoMSummary(BaseModel):
    """Minutes of Meeting (MoM) summary structured output."""

    date_time: str | None = None
    location: str = "Google Meet"
    title: str = ""
    agenda: list[str] = Field(default_factory=list)
    topics_of_discussion: list[str] = Field(default_factory=list)
    summary: str = ""
    action_items: list[ActionItem] = Field(default_factory=list)
    recommended_mitigations: list[str] = Field(default_factory=list)


class GroupPulseMetric(BaseModel):
    """Aggregated sentiment metric per canonical group."""

    pulse_score: float = Field(ge=0, le=100)
    block_count: int = Field(ge=0)
    top_liked_words: list[str] = Field(default_factory=list)
    top_disliked_words: list[str] = Field(default_factory=list)


class MeetingCreate(BaseModel):
    """Schema for creating a new meeting record in Firestore."""

    meeting_id: str
    project_id: str
    title: str
    platform: str = "google_meet"
    meeting_date: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: MeetingStatus = MeetingStatus.SCHEDULED
    pulse_score: float | None = Field(default=None, ge=0, le=100)
    group_scores: dict[str, GroupPulseMetric | dict[str, Any]] = Field(
        default_factory=dict
    )
    mom_summary: MoMSummary | dict[str, Any] | str | None = None
    participants: list[str] = Field(default_factory=list)
    ephemeral_speaker_map: dict[str, str] | None = None
    model_metadata: dict[str, Any] | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class MeetingResponse(BaseModel):
    """API response schema for a meeting document."""

    model_config = ConfigDict(from_attributes=True)

    meeting_id: str
    project_id: str = "proj-alpha"
    title: str = "Google Meet Session"
    platform: str = "google_meet"
    meeting_date: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: str = MeetingStatus.PROCESSING_POST_MEETING.value
    pulse_score: float | None = None
    group_scores: dict[str, Any] = Field(default_factory=dict)
    mom_summary: Any = None
    participants: list[str] = Field(default_factory=list)
    ephemeral_speaker_map: dict[str, str] | None = None
    model_metadata: dict[str, Any] | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str | None = None



class MeetingDispatchBotRequest(BaseModel):
    """Request payload to dispatch a MeetStream bot into a Google Meet."""

    meeting_link: str = Field(description="Google Meet link")
    project_id: str = Field(description="Project ID this meeting belongs to")
    meeting_id: str | None = Field(default=None, description="Optional custom meeting ID")
    title: str = Field(default="Google Meet Session", description="Meeting title")
    bot_name: str = Field(default="pRisk AI Notetaker", description="Bot display name in meeting")
    chat_consent_notice: str | None = Field(
        default=None, description="Custom chat consent notice broadcasted to meeting"
    )


class MeetingDispatchBotResponse(BaseModel):
    """Response returned upon successful bot dispatch."""

    meeting_id: str
    project_id: str
    bot_id: str
    transcript_id: str | None = None
    status: str
    meeting_link: str
    chat_consent_notice: str
    dispatched_at: str


class MeetStreamWebhookPayload(BaseModel):
    """Payload sent by MeetStream on meeting completion or transcription readiness."""

    event: str | None = None
    bot_event: str | None = None
    bot_id: str | None = None
    transcript_id: str | None = None
    meeting_id: str | None = None
    custom_attributes: dict[str, Any] = Field(default_factory=dict)
    transcript: list[dict[str, Any]] | None = None


class BubbleSplitRequest(BaseModel):
    """Request payload to split a single Dialogue Block at a character cursor offset."""

    split_char_index: int | None = Field(default=None, ge=1)
    split_idx: int | None = Field(default=None, ge=1)

    def resolved_index(self) -> int:
        idx = self.split_char_index if self.split_char_index is not None else self.split_idx
        if idx is None or idx < 1:
            raise ValueError("A positive split_char_index or split_idx is required")
        return idx


class BubbleSplitResponse(BaseModel):
    """Response returned after splitting a Dialogue Block into two child blocks."""

    meeting_id: str
    parent_block_id: str
    child_blocks: list[DialogueBlockResponse]
    blocks: list[DialogueBlockResponse]
    pulse_score: float
    group_scores: dict[str, Any]


class SessionGroupingRequest(BaseModel):
    """Request payload for in-session ephemeral speaker-to-group mapping."""

    ephemeral_speaker_account_id: str = Field(min_length=1)
    group_name: str = Field(min_length=1)


class SessionGroupingResponse(BaseModel):
    """Response returned after updating session speaker-to-group mapping."""

    meeting_id: str
    ephemeral_speaker_map: dict[str, str]
    updated_block_ids: list[str]
    blocks: list[DialogueBlockResponse]
    pulse_score: float
    group_scores: dict[str, Any]


class BlockScoreUpdateRequest(BaseModel):
    """Request payload to update a Dialogue Block's Pulse Score or Group assignment."""

    final_pulse_score: float | None = Field(default=None, ge=0, le=100)
    sentiment_score: float | None = Field(default=None, ge=0, le=100)
    group_name: str | None = None
    is_pinned: bool | None = None
    text_scrubbed: str | None = None

    def resolved_score(self) -> float | None:
        if self.final_pulse_score is not None:
            return self.final_pulse_score
        return self.sentiment_score


class BlockScoreUpdateResponse(BaseModel):
    """Response returned after updating a block score or group assignment."""

    meeting_id: str
    block: DialogueBlockResponse
    pulse_score: float
    group_scores: dict[str, Any]


class BlockOverrideCommitItem(BaseModel):
    """Optional inline block state submitted during Golden Record commit."""

    block_id: str
    sentiment_score: float | None = Field(default=None, ge=0, le=100)
    group_name: str | None = None
    is_human_overridden: bool | None = None
    text_scrubbed: str | None = None


class CommitGoldenRecordRequest(BaseModel):
    """Request payload to finalize adjudication and commit the Golden Record."""

    approved_risk_ids: list[str] | None = None
    dismissed_risk_ids: list[str] | None = None
    mom_summary: dict[str, Any] | None = None
    block_updates: list[BlockOverrideCommitItem] | None = None


class CommitGoldenRecordResponse(BaseModel):
    """Response returned when a meeting is committed as an immutable Golden Record."""

    success: bool = True
    meeting_id: str
    project_id: str
    status: str
    pulse_score: float
    group_scores: dict[str, Any]
    ephemeral_speaker_map: None = None
    corrected_contexts_saved: int
    promoted_risk_ids: list[str]
    bigquery_rows_streamed: int
    committed_at: str



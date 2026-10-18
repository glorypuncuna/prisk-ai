from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SentimentCalibrationCreate(BaseModel):
    """Schema for creating a sentiment calibration / few-shot exemplar record."""

    calibration_id: str
    project_id: str | None = None
    group_name: str | None = None
    dialogue_text: str = Field(description="Sample dialogue text or scrubbed phrase")
    benchmark_score: float = Field(ge=0, le=100, description="Calibrated sentiment score 0-100")
    rubric_breakdown: dict[str, float] = Field(
        default_factory=dict,
        description="4-dimension rubric score dictionary",
    )
    embedding: list[float] | None = Field(
        default=None,
        description="768-dimensional float embedding vector from text-embedding-004",
    )
    adjudicator_uid: str | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

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


class SentimentCalibrationResponse(BaseModel):
    """API response schema for a sentiment calibration exemplar."""

    model_config = ConfigDict(from_attributes=True)

    calibration_id: str
    project_id: str | None = None
    group_name: str | None = None
    dialogue_text: str
    benchmark_score: float
    rubric_breakdown: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None
    adjudicator_uid: str | None = None
    created_at: str


class CorrectedContextCreate(BaseModel):
    """Schema for storing a human-adjudicated override vector in `corrected_contexts`."""

    correction_id: str
    project_id: str
    group_name: str | None = None
    scrubbed_text: str = Field(description="Scrubbed dialogue block text")
    embedding: list[float] | None = Field(
        default=None,
        description="768-dimensional float embedding vector from text-embedding-004",
    )
    ai_initial_score: float = Field(ge=0, le=100, default=50.0)
    human_adjusted_score: float = Field(ge=0, le=100)
    rubric_breakdown: dict[str, float] = Field(default_factory=dict)
    adjudicator_uid: str | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

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


class CorrectedContextResponse(BaseModel):
    """Response schema for a corrected context few-shot exemplar."""

    model_config = ConfigDict(from_attributes=True)

    correction_id: str
    project_id: str
    group_name: str | None = None
    scrubbed_text: str
    embedding: list[float] | None = None
    ai_initial_score: float = 50.0
    human_adjusted_score: float
    rubric_breakdown: dict[str, Any] = Field(default_factory=dict)
    adjudicator_uid: str | None = None
    created_at: str


class SpeakerBlindBlockInput(BaseModel):
    """Speaker-blind block representation stripped of speaker identity before LLM submission."""

    block_id: str
    sequence_index: int
    scrubbed_text: str


class RubricScoresSchema(BaseModel):
    """4-dimension additive sentiment rubric (0-25 integers each, summing to 0-100)."""

    emotional_valence: int = Field(ge=0, le=25, default=12)
    delivery_alignment: int = Field(ge=0, le=25, default=12)
    relationship_trust: int = Field(ge=0, le=25, default=13)
    momentum_commitment: int = Field(ge=0, le=25, default=13)

    def total_score(self) -> int:
        return (
            self.emotional_valence
            + self.delivery_alignment
            + self.relationship_trust
            + self.momentum_commitment
        )


class BlockInferenceResult(BaseModel):
    """Speaker-blind structured inference result for a single dialogue block."""

    block_id: str
    suggested_group_name: str = Field(
        default="INTERNAL",
        description="Must be selected from Project canonical_groups",
    )
    rubric_breakdown: RubricScoresSchema
    pulse_score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)


class GroupKeywordsResult(BaseModel):
    """Top 5 liked and disliked keywords extracted per canonical group."""

    group_name: str
    top_liked_words: list[str] = Field(default_factory=list)
    top_disliked_words: list[str] = Field(default_factory=list)


class ActionItemResult(BaseModel):
    """Structured action item generated in Minutes of Meeting."""

    description: str
    owner_group: str
    due_date: str | None = None


class DraftRiskResult(BaseModel):
    """Draft risk candidate discovered during post-meeting analysis."""

    title: str
    contextual_description: str
    associated_groups: list[str] = Field(default_factory=list)
    category: str = Field(
        default="OPERATIONAL",
        description="FINANCIAL | OPERATIONAL | COMPLIANCE | STRATEGIC | RELATIONSHIP",
    )
    impact_score: int = Field(ge=1, le=5, default=3)
    probability_score: int = Field(ge=1, le=5, default=3)
    recommended_mitigation: str = ""


class PostMeetingAnalysisResponse(BaseModel):
    """Structured output schema returned by Vertex AI Gemini for speaker-blind post-meeting analysis."""

    inferred_company_name: str = "Enterprise Client"
    agenda: list[str] = Field(default_factory=list)
    topics_of_discussion: list[str] = Field(default_factory=list)
    summary: str = ""
    action_items: list[ActionItemResult] = Field(default_factory=list)
    recommended_mitigations: list[str] = Field(default_factory=list)
    block_results: list[BlockInferenceResult] = Field(default_factory=list)
    group_keywords: list[GroupKeywordsResult] = Field(default_factory=list)
    draft_risks: list[DraftRiskResult] = Field(default_factory=list)


class SpanAttribution(BaseModel):
    """Raw LLM span attribution before server-side offset verification."""

    verbatim_phrase: str = Field(
        description="Exact character-for-character substring from scrubbed_text"
    )
    attribution_weight: float = Field(
        ge=-1.0, le=1.0, description="Signed impact weight from -1.0 to +1.0"
    )
    rubric_dimension: str = Field(
        description="emotional_valence | delivery_alignment | relationship_trust | momentum_commitment"
    )
    rationale: str = Field(description="Concise 1-sentence rubric justification")


class ExplainRationaleResponse(BaseModel):
    """Structured JSON output schema from Gemini for on-demand Explainable AI (XAI)."""

    block_id: str
    rubric_breakdown: RubricScoresSchema
    attributions: list[SpanAttribution] = Field(default_factory=list)


class ValidatedSpanAttribution(BaseModel):
    """Server-side verified verbatim substring attribution with exact character offsets."""

    verbatim_phrase: str
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    attribution_weight: float = Field(ge=-1.0, le=1.0)
    rubric_dimension: str
    rationale: str


class BlockExplainResponse(BaseModel):
    """API response schema for POST /api/v1/meetings/{meeting_id}/blocks/{block_id}/explain."""

    meeting_id: str
    block_id: str
    scrubbed_text: str
    pulse_score: float
    rubric_breakdown: RubricScoresSchema
    attributions: list[ValidatedSpanAttribution] = Field(default_factory=list)
    computed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class PulseTrendPoint(BaseModel):
    """Chronological data point for meeting pulse trajectory."""

    meeting_id: str
    project_id: str
    title: str
    meeting_date: str
    pulse_score: float
    group_scores: dict[str, Any] = Field(default_factory=dict)
    status: str = "PROCESSING_POST_MEETING"


class AiPulseCommentary(BaseModel):
    """Structured longitudinal AI synthesis explaining key drivers of pulse shifts."""

    headline: str = Field(
        description="Concise executive headline summarizing the pulse trajectory"
    )
    trajectory_summary: str = Field(
        description="2-3 sentence overview of pulse direction and cross-group alignment"
    )
    key_drivers_of_shifts: list[str] = Field(
        default_factory=list,
        description="Key meeting events, delivery friction, or milestones driving shifts",
    )
    group_trends: dict[str, str] = Field(
        default_factory=dict,
        description="Longitudinal trend commentary mapped by canonical group name",
    )
    risk_warning: str | None = Field(
        default=None,
        description="Flagged systemic drop or critical risk alert if pulse falls below threshold",
    )
    recommended_interventions: list[str] = Field(
        default_factory=list,
        description="Actionable interventions to reverse sentiment deterioration or maintain momentum",
    )


class PulseTrendsAggregate(BaseModel):
    """Summary metrics across the selected time window."""

    total_meetings: int = 0
    average_pulse: float = 50.0
    pulse_change: float = 0.0
    lowest_pulse_meeting: dict[str, Any] | None = None
    highest_pulse_meeting: dict[str, Any] | None = None
    group_averages: dict[str, float] = Field(default_factory=dict)


class PulseTrendsResponse(BaseModel):
    """API response schema for GET /api/v1/analytics/pulse-trends."""

    time_window: str = "30D"
    start_date: str
    end_date: str
    project_ids: list[str] = Field(default_factory=list)
    trajectory_points: list[PulseTrendPoint] = Field(default_factory=list)
    ai_commentary: AiPulseCommentary
    aggregate_metrics: PulseTrendsAggregate
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )



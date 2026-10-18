from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RiskCategory(StrEnum):
    """Canonical risk categories defined in TRD Section 3.1 and Section 7.1."""

    FINANCIAL = "FINANCIAL"
    OPERATIONAL = "OPERATIONAL"
    COMPLIANCE = "COMPLIANCE"
    STRATEGIC = "STRATEGIC"
    RELATIONSHIP = "RELATIONSHIP"


class RiskStatus(StrEnum):
    """Lifecycle statuses for a risk register record."""

    DRAFT_PENDING_ADJUDICATION = "DRAFT_PENDING_ADJUDICATION"
    OPEN = "OPEN"
    MITIGATED = "MITIGATED"
    CLOSED = "CLOSED"
    ESCALATED = "ESCALATED"
    DISMISSED = "DISMISSED"
    ACCEPTED = "ACCEPTED"


class SeverityBand(StrEnum):
    """COSO / ISO 31000 5x5 matrix severity bands (TRD Section 7.1)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EscalationTier(StrEnum):
    """Automated SLA escalation thresholds."""

    TIER_24H = "24h"
    TIER_48H = "48h"
    TIER_72H = "72h"


def compute_severity_band(severity_score: int) -> str:
    """Map 1-25 COSO severity score to Low (1-5), Medium (6-11), High (12-19), Critical (20-25)."""
    if severity_score >= 20:
        return SeverityBand.CRITICAL.value
    if severity_score >= 12:
        return SeverityBand.HIGH.value
    if severity_score >= 6:
        return SeverityBand.MEDIUM.value
    return SeverityBand.LOW.value


def compute_sla_tier(severity_score: int) -> str:
    """Map 1-25 COSO severity score to initial SLA escalation tier."""
    if severity_score >= 15:
        return EscalationTier.TIER_24H.value
    if severity_score >= 8:
        return EscalationTier.TIER_48H.value
    return EscalationTier.TIER_72H.value


class RiskCommentaryEntry(BaseModel):
    """Qualitative commentary log entry attached to a risk record."""

    comment_id: str
    author_uid: str
    author_role: str | None = None
    comment: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class RiskRegisterCreate(BaseModel):
    """Schema for registering a new project risk in `risk_register`."""

    risk_id: str | None = Field(
        default=None, description="Unique risk slug/code, e.g. RSK-2026-0001"
    )
    project_id: str
    meeting_id: str | None = None
    company_name: str | None = None
    associated_groups: list[str] = Field(default_factory=list)
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(
        default="", description="Contextual description of the risk"
    )
    category: RiskCategory = RiskCategory.OPERATIONAL
    status: RiskStatus = RiskStatus.OPEN
    impact: int = Field(default=3, ge=1, le=5, description="Impact score 1-5")
    probability: int = Field(
        default=3, ge=1, le=5, description="Probability score 1-5"
    )
    impact_score: int | None = Field(default=None, ge=1, le=5)
    probability_score: int | None = Field(default=None, ge=1, le=5)
    severity_score: int | None = Field(
        default=None,
        ge=1,
        le=25,
        description="Computed as impact * probability (1-25)",
    )
    severity_band: str | None = None
    owner_uid: str | None = None
    risk_owner_uid: str | None = None
    sla_escalation_tier: str | None = None
    mitigation_plan: dict[str, Any] | None = None
    escalation_config: dict[str, Any] | None = None
    qualitative_commentary: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str | None = None

    @model_validator(mode="after")
    def calculate_severity_and_sla(self) -> "RiskRegisterCreate":
        if not self.risk_id:
            ts = int(datetime.now(timezone.utc).timestamp() * 1000) % 1000000
            self.risk_id = f"RSK-{ts:06d}"
        if self.impact_score is not None:
            self.impact = self.impact_score
        if self.probability_score is not None:
            self.probability = self.probability_score
        if self.risk_owner_uid and not self.owner_uid:
            self.owner_uid = self.risk_owner_uid

        self.severity_score = self.impact * self.probability
        self.severity_band = compute_severity_band(self.severity_score)
        if not self.sla_escalation_tier:
            self.sla_escalation_tier = compute_sla_tier(self.severity_score)
        if not self.updated_at:
            self.updated_at = self.created_at
        if self.escalation_config is None:
            is_open = self.status == RiskStatus.OPEN
            self.escalation_config = {
                "enabled": True,
                "sla_started_at": self.created_at if is_open else None,
                "last_escalated_tier_hours": 0,
                "manager_uids": [],
                "custom_recipients": [],
            }
        return self


class RiskRegisterUpdate(BaseModel):
    """Schema for updating or overriding an existing risk."""

    title: str | None = None
    description: str | None = None
    category: RiskCategory | None = None
    status: RiskStatus | None = None
    impact: int | None = Field(default=None, ge=1, le=5)
    probability: int | None = Field(default=None, ge=1, le=5)
    impact_score: int | None = Field(default=None, ge=1, le=5)
    probability_score: int | None = Field(default=None, ge=1, le=5)
    owner_uid: str | None = None
    risk_owner_uid: str | None = None
    associated_groups: list[str] | None = None
    escalation_enabled: bool | None = None
    sla_escalation_tier: str | None = None
    mitigation_plan: dict[str, Any] | None = None
    escalation_config: dict[str, Any] | None = None
    comment: str | None = None


class RiskRegisterResponse(BaseModel):
    """API response schema for a risk register record."""

    model_config = ConfigDict(from_attributes=True)

    risk_id: str
    project_id: str
    meeting_id: str | None = None
    company_name: str | None = None
    associated_groups: list[str] = Field(default_factory=list)
    title: str
    description: str
    category: RiskCategory
    status: RiskStatus
    impact: int
    probability: int
    severity_score: int
    severity_band: str = SeverityBand.LOW.value
    owner_uid: str | None = None
    sla_escalation_tier: str
    mitigation_plan: dict[str, Any] | None = None
    escalation_config: dict[str, Any] | None = None
    qualitative_commentary: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def populate_derived_fields(self) -> "RiskRegisterResponse":
        self.severity_score = self.impact * self.probability
        self.severity_band = compute_severity_band(self.severity_score)
        return self


class HeatmapCellNode(BaseModel):
    """Single cell in the 5x5 COSO / ISO 31000 Impact x Probability matrix."""

    impact: int = Field(ge=1, le=5)
    probability: int = Field(ge=1, le=5)
    severity_score: int = Field(ge=1, le=25)
    severity_band: str
    risk_count: int = 0
    risk_ids: list[str] = Field(default_factory=list)
    project_ids: list[str] = Field(default_factory=list)


class SystemicRiskSpikeStatus(BaseModel):
    """Systemic Risk Spike detection evaluation result (FR-7.4c)."""

    is_active: bool = False
    triggered_by_critical_projects: bool = False
    triggered_by_velocity_surge: bool = False
    concurrent_critical_project_count: int = 0
    concurrent_critical_project_ids: list[str] = Field(default_factory=list)
    current_7d_avg_severity: float = 0.0
    previous_7d_avg_severity: float = 0.0
    velocity_surge_pct: float = 0.0
    evaluated_at: str
    alert_message: str | None = None


class PortfolioRisksAnalyticsResponse(BaseModel):
    """Portfolio risk heatmap, breakdown, and systemic risk spike status (TRD Section 9.3)."""

    total_risks: int
    open_or_escalated_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    average_severity_score: float
    heatmap_cells: list[HeatmapCellNode]
    category_distribution: dict[str, int]
    project_summaries: list[dict[str, Any]]
    systemic_spike: SystemicRiskSpikeStatus
    risks: list[RiskRegisterResponse]


class AiRiskDiscoverRequest(BaseModel):
    """Request payload for automated AI risk discovery from meeting pulse drops."""

    project_id: str | None = None
    meeting_id: str | None = None
    lookback_window: str = "30D"
    auto_register: bool = False


class DiscoveredRiskItem(BaseModel):
    """Individual emerging risk item discovered by Vertex AI Gemini 2.5 Flash."""

    risk_id: str | None = None
    project_id: str
    meeting_id: str | None = None
    title: str
    description: str
    category: RiskCategory = RiskCategory.OPERATIONAL
    impact: int = Field(ge=1, le=5)
    probability: int = Field(ge=1, le=5)
    severity_score: int = Field(ge=1, le=25)
    severity_band: str
    trigger_reason: str
    mitigation_strategy: str
    executive_brief: str
    associated_groups: list[str] = Field(default_factory=list)
    status: RiskStatus = RiskStatus.DRAFT_PENDING_ADJUDICATION


class AiRiskDiscoverResponse(BaseModel):
    """Response payload for automated AI risk discovery."""

    project_id: str | None
    discovered_risks: list[DiscoveredRiskItem]
    pulse_drops_evaluated: int
    total_risks_found: int
    registered_count: int
    summary: str


class AiMitigationRequest(BaseModel):
    """Request payload for synthesizing AI proactive mitigation strategies."""

    apply_to_risk: bool = False
    context_notes: str | None = None


class AiMitigationResponse(BaseModel):
    """Proactive mitigation plan and executive escalation brief generated by Gemini 2.5 Flash."""

    risk_id: str
    project_id: str
    title: str
    mitigation_strategy: str
    suggested_action_items: list[dict[str, Any]] = Field(default_factory=list)
    executive_escalation_brief: str
    residual_impact: int = Field(ge=1, le=5)
    residual_probability: int = Field(ge=1, le=5)
    residual_severity_score: int = Field(ge=1, le=25)
    applied: bool = False
    updated_risk: RiskRegisterResponse | None = None


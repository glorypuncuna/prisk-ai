from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DEFAULT_CANONICAL_GROUPS = [
    "Client Executive Sponsor",
    "Client Legal & Compliance",
    "Client Engineering",
    "Internal Delivery Team",
]


class ProjectAlertThresholds(BaseModel):
    """Alert and SLA threshold configuration for a project workspace."""

    pulse_drop_delta: int = Field(
        default=15,
        ge=5,
        le=50,
        description="Pulse score drop between meetings that triggers an alert",
    )
    minimum_pulse_score: int = Field(
        default=40,
        ge=10,
        le=80,
        description="Minimum acceptable group pulse score before risk flagging",
    )
    escalation_enabled: bool = Field(
        default=True,
        description="Whether automated 24h/48h/72h SLA escalations are active",
    )
    escalation_intervals_hours: list[int] = Field(
        default_factory=lambda: [24, 48, 72],
        description="SLA reminder and escalation tiers in hours",
    )


class ProjectCreateRequest(BaseModel):
    """Request payload for creating an enterprise project."""

    project_id: str = Field(min_length=2, max_length=64, description="Unique project slug/ID")
    name: str = Field(min_length=2, max_length=120, description="Human-readable project name")
    company_name: str = Field(default="", max_length=120, description="Client or organization name")
    description: str = Field(default="", max_length=500, description="Project description")
    canonical_groups: list[str] = Field(
        default_factory=lambda: list(DEFAULT_CANONICAL_GROUPS),
        description="Allowed canonical stakeholder groups for speaker-to-group tagging",
    )
    alert_thresholds: ProjectAlertThresholds = Field(
        default_factory=ProjectAlertThresholds,
        description="Pulse drop and SLA alert thresholds",
    )


class ProjectUpdateRequest(BaseModel):
    """Request payload for updating project governance, canonical groups, and alert thresholds."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    company_name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    canonical_groups: list[str] | None = Field(default=None)
    alert_thresholds: ProjectAlertThresholds | None = Field(default=None)


class ProjectResponse(BaseModel):
    """Project metadata representation."""

    model_config = ConfigDict(from_attributes=True)

    project_id: str
    name: str
    company_name: str = ""
    description: str = ""
    canonical_groups: list[str] = Field(
        default_factory=lambda: list(DEFAULT_CANONICAL_GROUPS)
    )
    alert_thresholds: ProjectAlertThresholds = Field(
        default_factory=ProjectAlertThresholds
    )
    owner_uid: str
    created_at: str
    updated_at: str | None = None


class ProjectAISuggestGroupsRequest(BaseModel):
    """Request payload for `POST /api/v1/projects/{project_id}/ai-suggest-groups`."""

    name: str = Field(default="", max_length=120, description="Project title or initiative name")
    company_name: str = Field(default="", max_length=120, description="Client or enterprise name")
    description: str = Field(
        default="",
        max_length=1000,
        description="Domain context, deliverables, and stakeholder structure",
    )


class ProjectAISuggestGroupsResponse(BaseModel):
    """AI-recommended canonical groups, risk categories, and pulse thresholds for a project."""

    project_id: str
    suggested_canonical_groups: list[str] = Field(min_length=2, max_length=8)
    suggested_risk_categories: list[str] = Field(default_factory=list)
    recommended_alert_thresholds: ProjectAlertThresholds
    rationale: str
    inference_mode: str = Field(
        default="DETERMINISTIC_FALLBACK",
        description="VERTEX_GEMINI when live API is used, DETERMINISTIC_FALLBACK when offline",
    )
    model_version: str = Field(default="gemini-2.5-flash")


class ProjectInvitationCreateRequest(BaseModel):
    """Request payload for `POST /api/v1/projects/{project_id}/invitations`."""

    invitee_email: str | None = Field(
        default=None,
        min_length=3,
        max_length=254,
        description="Email address of the user being invited to the project",
    )
    email: str | None = Field(default=None, description="Alias for invitee_email")
    target_role: str | None = Field(default=None, description="Optional target role for invitee")
    project_name: str | None = Field(
        default=None,
        description="Optional display name if auto-initializing the project workspace",
    )

    @model_validator(mode="before")
    @classmethod
    def resolve_email(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if not values.get("invitee_email") and values.get("email"):
                values["invitee_email"] = values["email"]
        return values

    @field_validator("invitee_email")
    @classmethod
    def validate_email(cls, value: str | None) -> str:
        if not value:
            raise ValueError("invitee_email is required")
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Invalid invitee email address")
        return normalized


class ProjectInvitationResponse(BaseModel):
    """Representation of a project invitation."""

    model_config = ConfigDict(from_attributes=True)

    invitation_id: str
    project_id: str
    project_name: str
    invitee_email: str
    invited_by_uid: str
    status: str
    created_at: str
    accepted_at: str | None = None


class ExemplarDiagnosticItem(BaseModel):
    """Individual exemplar status for vector search diagnostics."""

    calibration_id: str
    group_name: str | None = None
    benchmark_score: float
    has_embedding: bool = True
    embedding_dimension: int = 768
    created_at: str


class ProjectVectorDiagnosticsResponse(BaseModel):
    """Vector embedding calibration diagnostics for a project workspace."""

    project_id: str
    embedding_model: str = "text-embedding-004"
    embedding_dimension: int = 768
    total_exemplars: int
    group_coverage: dict[str, int] = Field(default_factory=dict)
    inference_mode: str = Field(
        description="FEW_SHOT if total_exemplars > 0, else ZERO_SHOT"
    )
    nearest_neighbor_readiness: bool
    recent_exemplars: list[ExemplarDiagnosticItem] = Field(default_factory=list)
    checked_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


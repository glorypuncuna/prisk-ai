from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.phone import (
    DIALING_CODE_TO_REGION,
    REGION_TO_DIALING_CODE,
    normalize_e164_phone,
)
from app.core.security import UserRole


class RegisterProfileRequest(BaseModel):
    """Request payload for `POST /api/v1/auth/register-profile`."""

    first_name: str = Field(min_length=1, max_length=100, description="User's given name")
    last_name: str = Field(min_length=1, max_length=100, description="User's family/surname")
    phone_number: str = Field(
        min_length=3,
        max_length=30,
        description="Phone number in national or E.164 format",
    )
    country_code: str = Field(
        default="ID",
        min_length=2,
        max_length=6,
        description="ISO 3166-1 alpha-2 country code (e.g. 'ID', 'US') or dialing prefix ('+62')",
    )
    email: str | None = Field(
        default=None,
        description="Optional email fallback if not embedded in the Firebase ID token",
    )

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_non_blank_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Name field cannot be blank or whitespace only")
        return trimmed

    @model_validator(mode="after")
    def normalize_phone_to_e164(self) -> "RegisterProfileRequest":
        self.phone_number = normalize_e164_phone(self.phone_number, self.country_code)
        return self


class UserProfileResponse(BaseModel):
    """Canonical `users/{uid}` Firestore profile representation."""

    model_config = ConfigDict(from_attributes=True)

    uid: str
    email: str
    first_name: str
    last_name: str
    phone_number: str
    role: UserRole
    auth_provider: str = "password"
    assigned_project_ids: list[str] = Field(default_factory=list)
    onboarding_status: str = Field(
        default="QUARANTINED_PENDING_INVITATION",
        description="ACTIVE when assigned to >=1 project or privileged role; QUARANTINED_PENDING_INVITATION otherwise",
    )
    created_at: str
    last_login_at: str | None = None


class RoleUpdateRequest(BaseModel):
    """Request payload for `PATCH /api/v1/users/{uid}/role`."""

    role: UserRole = Field(description="Target RBAC role to assign to the user")
    assigned_project_ids: list[str] | None = Field(
        default=None,
        description="Optional updated list of project IDs the user is authorized to access",
    )


class AdminUserProvisionRequest(BaseModel):
    """Request payload for `POST /api/v1/admin/users`."""

    email: str = Field(description="User email address")
    first_name: str = Field(min_length=1, max_length=100, description="User given name")
    last_name: str = Field(min_length=1, max_length=100, description="User family name")
    phone_number: str = Field(
        min_length=3,
        max_length=30,
        description="Phone number in national or E.164 format",
    )
    country_code: str = Field(
        default="ID",
        min_length=2,
        max_length=6,
        description="ISO 3166-1 alpha-2 country code (e.g. 'ID', 'US') or dialing prefix ('+62')",
    )
    role: UserRole = Field(
        default=UserRole.EXTERNAL_STAKEHOLDER,
        description="Assigned enterprise RBAC role",
    )
    assigned_project_ids: list[str] = Field(
        default_factory=list,
        description="List of project IDs the provisioned user can access",
    )

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, value: str) -> str:
        trimmed = value.strip().lower()
        if "@" not in trimmed or "." not in trimmed.split("@")[-1]:
            raise ValueError("Invalid email address format")
        return trimmed

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Name field cannot be blank or whitespace only")
        return trimmed

    @model_validator(mode="after")
    def normalize_phone_to_e164(self) -> "AdminUserProvisionRequest":
        self.phone_number = normalize_e164_phone(self.phone_number, self.country_code)
        return self


class AdminUserDeleteResponse(BaseModel):
    """Response payload for `DELETE /api/v1/admin/users/{uid}`."""

    status: str = "deleted"
    uid: str
    message: str = "User account permanently de-provisioned"


class AdminGovernanceDigestResponse(BaseModel):
    """Response payload for `GET /api/v1/admin/ai-governance-summary`."""

    generated_at: str
    inference_mode: str = Field(
        default="DETERMINISTIC_FALLBACK",
        description="VERTEX_GEMINI when live Gemini API is used, DETERMINISTIC_FALLBACK when offline",
    )
    model_version: str = Field(default="gemini-2.5-flash")
    total_users: int
    active_users_count: int
    quarantined_users_count: int
    total_projects: int
    unassigned_projects_count: int
    pending_invitations_count: int
    role_distribution: dict[str, int] = Field(default_factory=dict)
    executive_summary: str
    key_findings: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


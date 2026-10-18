from enum import StrEnum


class UserRole(StrEnum):
    """Canonical enterprise RBAC roles defined in ADR-0006 and TRD Section 3.1."""

    ADMIN = "ADMIN"
    EXECUTIVE = "EXECUTIVE"
    MANAGER = "MANAGER"
    ADJUDICATOR = "ADJUDICATOR"
    EXTERNAL_STAKEHOLDER = "EXTERNAL_STAKEHOLDER"


class AuthProvider(StrEnum):
    """Supported Firebase Identity Platform authentication providers."""

    PASSWORD = "password"
    GOOGLE = "google.com"
    MICROSOFT = "microsoft.com"

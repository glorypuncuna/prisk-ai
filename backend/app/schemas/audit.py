from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class AuditActionType(StrEnum):
    """Canonical audit action types as defined in TRD Section 3.2."""

    BUBBLE_SPLIT = "BUBBLE_SPLIT"
    GROUP_TAG_CHANGE = "GROUP_TAG_CHANGE"
    SLIDER_OVERRIDE = "SLIDER_OVERRIDE"
    XAI_INVOKED = "XAI_INVOKED"
    GOLDEN_RECORD_COMMIT = "GOLDEN_RECORD_COMMIT"
    RISK_OVERRIDE = "RISK_OVERRIDE"
    CONSENT_REVOKED = "CONSENT_REVOKED"
    COMPLIANCE_PACKAGE_EXPORTED = "COMPLIANCE_PACKAGE_EXPORTED"
    GDPR_ARTICLE_17_ERASURE_TOMBSTONE = "GDPR_ARTICLE_17_ERASURE_TOMBSTONE"
    USER_PROVISIONED = "USER_PROVISIONED"
    USER_DELETED = "USER_DELETED"
    ROLE_CHANGED = "ROLE_CHANGED"
    SYSTEM_INITIALIZED = "SYSTEM_INITIALIZED"


class AuditEntityType(StrEnum):
    """Entity types governed by the audit ledger."""

    USER = "USER"
    PROJECT = "PROJECT"
    MEETING = "MEETING"
    DIALOGUE_BLOCK = "DIALOGUE_BLOCK"
    RISK = "RISK"
    COMPLIANCE_PACKAGE = "COMPLIANCE_PACKAGE"
    SYSTEM = "SYSTEM"


class AuditLedgerEntryCreate(BaseModel):
    """Schema for appending an immutable event to `audit_ledger`."""

    event_id: str
    event_type: str
    actor_uid: str
    target_id: str
    actor_role: str | None = None
    action_type: str | None = None
    entity_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    sha256_hash: str | None = None
    previous_state_json: str | None = None
    new_state_json: str | None = None
    model_version: str | None = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class AuditLedgerEntryResponse(BaseModel):
    """API response schema for an audit ledger event."""

    model_config = ConfigDict(from_attributes=True)

    event_id: str
    event_type: str
    actor_uid: str
    target_id: str
    actor_role: str | None = None
    action_type: str | None = None
    entity_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    sha256_hash: str | None = None
    previous_state_json: str | None = None
    new_state_json: str | None = None
    model_version: str | None = None
    timestamp: str

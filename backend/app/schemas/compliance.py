from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ComplianceFramework(StrEnum):
    """Supported compliance frameworks."""

    ISO_31000 = "ISO_31000"
    COSO = "COSO"
    SOC_2 = "SOC_2"
    HIPAA = "HIPAA"
    GDPR = "GDPR"


class ComplianceFormat(StrEnum):
    """Supported export binary/text formats."""

    PDF = "PDF"
    CSV = "CSV"
    JSON = "JSON"


class CompliancePackageStatus(StrEnum):
    """WORM lifecycle status."""

    PENDING = "PENDING"
    SEALED_WORM = "SEALED_WORM"
    COMPLETED = "COMPLETED"


class ComplianceExportRequest(BaseModel):
    """Request payload for `POST /api/v1/compliance/export`."""

    project_id: str = Field(default="proj-alpha", min_length=1)
    company_name: str = Field(default="Enterprise Holdings Inc.")
    target_frameworks: list[str] = Field(
        default_factory=lambda: [
            ComplianceFramework.ISO_31000.value,
            ComplianceFramework.COSO.value,
            ComplianceFramework.SOC_2.value,
        ],
        min_length=1,
    )
    format: ComplianceFormat = ComplianceFormat.PDF
    include_mitigated_risks: bool = True

    @field_validator("target_frameworks")
    @classmethod
    def validate_frameworks(cls, v: list[str]) -> list[str]:
        normalized: list[str] = []
        allowed = {"ISO_31000", "COSO", "SOC_2", "HIPAA", "GDPR"}
        for item in v:
            key = str(item).strip().upper().replace("-", "_").replace(" ", "_")
            if key == "SOC2":
                key = "SOC_2"
            elif key == "ISO31000":
                key = "ISO_31000"
            if key not in allowed:
                raise ValueError(
                    f"Unsupported compliance framework '{item}'. Supported: {sorted(allowed)}"
                )
            if key not in normalized:
                normalized.append(key)
        return normalized


class CompliancePackageCreate(BaseModel):
    """Schema for creating a compliance package record in Firestore."""

    package_id: str = Field(description="Unique package ID, e.g. CMP-2026-0001")
    version_id: str = Field(default="v1.0.0")
    project_id: str
    company_name: str | None = None
    framework: str | None = None
    target_frameworks: list[ComplianceFramework | str] = Field(
        default_factory=lambda: [ComplianceFramework.ISO_31000.value]
    )
    format: ComplianceFormat = ComplianceFormat.PDF
    sha256_hash: str = Field(
        min_length=64,
        max_length=64,
        description="SHA-256 cryptographic digest of the sealed artifact",
    )
    gcs_uri: str = Field(description="Cloud Storage URI gs://<bucket>/<path>")
    size_bytes: int = 0
    status: CompliancePackageStatus = CompliancePackageStatus.SEALED_WORM
    generated_by_uid: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    sections: dict[str, Any] | None = Field(
        default=None,
        description="Structured sections data (header_and_metadata, framework_control_mapping_table, sanitized_risk_register, mitigation_lifecycle_audit_summary, privacy_and_data_governance_attestation)",
    )
    zero_verbatim_quotes_verified: bool = True
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class CompliancePackageResponse(BaseModel):
    """API response schema for a compliance package metadata record."""

    model_config = ConfigDict(from_attributes=True)

    package_id: str
    version_id: str = "v1.0.0"
    project_id: str
    company_name: str | None = None
    framework: str | None = None
    target_frameworks: list[str] = Field(default_factory=list)
    format: str
    sha256_hash: str
    gcs_uri: str
    size_bytes: int = 0
    status: str
    generated_by_uid: str
    generated_at: str
    sections: dict[str, Any] | None = None
    zero_verbatim_quotes_verified: bool = True
    created_at: str


class ComplianceIntegrityResponse(BaseModel):
    """Response schema for verifying a WORM compliance package's cryptographic digest."""

    package_id: str
    project_id: str
    recorded_sha256_hash: str
    computed_sha256_hash: str | None = None
    integrity_verified: bool
    integrity_valid: bool | None = None
    stored_sha256: str | None = None
    computed_sha256: str | None = None
    gcs_uri: str
    status: str

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if "integrity_valid" not in values and "integrity_verified" in values:
                values["integrity_valid"] = values["integrity_verified"]
            if "stored_sha256" not in values and "recorded_sha256_hash" in values:
                values["stored_sha256"] = values["recorded_sha256_hash"]
            if "computed_sha256" not in values and "computed_sha256_hash" in values:
                values["computed_sha256"] = values["computed_sha256_hash"]
        return values


class GdprMeetingPurgeResponse(BaseModel):
    """Response schema for `DELETE /api/v1/meetings/{id}/purge` (GDPR Article 17)."""

    meeting_id: str
    project_id: str
    status: str = "PURGED_GDPR_ARTICLE_17"
    purged_dialogue_blocks_count: int
    purged_calibrations_count: int
    purged_risks_count: int
    purged_bigquery_rows: dict[str, int]
    redacted_compliance_packages_count: int
    tombstone_audit_event_id: str
    purged_at: str


class ComplianceNarrativeRequest(BaseModel):
    """Request payload for generating AI compliance attestation narrative preview."""

    project_id: str = Field(default="proj-alpha", min_length=1)
    company_name: str = Field(default="Enterprise Holdings Inc.")
    target_frameworks: list[str] = Field(
        default_factory=lambda: [
            ComplianceFramework.ISO_31000.value,
            ComplianceFramework.COSO.value,
            ComplianceFramework.SOC_2.value,
        ],
        min_length=1,
    )


class ComplianceNarrativeResponse(BaseModel):
    """AI Privacy-Preserving Compliance Narrative generated by Gemini 2.5 Flash."""

    project_id: str
    company_name: str
    target_frameworks: list[str]
    executive_summary: str
    framework_treatment_summaries: dict[str, str]
    continuous_monitoring_attestation: str
    zero_audio_privacy_statement: str
    zero_verbatim_quotes_verified: bool = True
    generated_at: str


class GdprPurgeRequest(BaseModel):
    """Request payload for GDPR Article 17 Right-to-Erasure purge."""

    meeting_id: str
    reason: str | None = "Data subject requested erasure pursuant to GDPR Article 17"


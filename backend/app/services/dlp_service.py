import os
import re
from typing import Any
from app.core.config import get_settings

try:
    from google.cloud import dlp_v2
except ImportError:
    dlp_v2 = None  # type: ignore[assignment]


# Standard regexes for local/offline de-identification fallback
_PHONE_REGEX = re.compile(
    r"(\+?\d{1,3}[-.\s]?)?(\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}"
)
_EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
)
_CREDIT_CARD_REGEX = re.compile(
    r"\b(?:\d{4}[-\s]?){3}\d{4}\b"
)
_SSN_REGEX = re.compile(
    r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"
)


class DLPService:
    """Service for batch de-identification of sensitive PII via Google Cloud DLP.
    
    Redacts financial, government, and contact identifiers while strictly preserving
    person and company names as mandated in TRD Section 3.3.
    """

    # InfoTypes targeting financial, government, and contact data
    # Note: PERSON_NAME and ORGANIZATION_NAME are explicitly omitted to preserve them
    DEFAULT_INFO_TYPES: list[str] = [
        # Contact identifiers
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "STREET_ADDRESS",
        "IP_ADDRESS",
        # Financial identifiers
        "CREDIT_CARD_NUMBER",
        "BANK_ACCOUNT_NUMBER",
        "SWIFT_CODE",
        # Government identifiers
        "US_SOCIAL_SECURITY_NUMBER",
        "PASSPORT",
        "US_INDIVIDUAL_TAX_IDENTIFIER_TIN",
    ]

    def __init__(self, project_id: str | None = None) -> None:
        self.settings = get_settings()
        self.project_id = project_id or self.settings.gcp_project_id
        self._client: Any | None = None

        if (
            not self.settings.use_in_memory_firestore
            and dlp_v2 is not None
            and (
                self.settings.google_application_credentials
                or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            )
        ):
            try:
                self._client = dlp_v2.DlpServiceClient()
            except Exception:
                self._client = None

    def deidentify_text(self, text: str) -> tuple[str, list[str]]:
        """De-identify a single text string using Google Cloud DLP or local fallback."""
        if not text:
            return "", []

        if self._client is not None:
            try:
                return self._deidentify_with_gcp(text)
            except Exception:
                # Graceful fallback to regex-based scrubbing on transient API error
                return self._deidentify_with_fallback(text)
        return self._deidentify_with_fallback(text)

    def _deidentify_with_gcp(self, text: str) -> tuple[str, list[str]]:
        parent = f"projects/{self.project_id}/locations/global"
        inspect_config = {
            "info_types": [{"name": it} for it in self.DEFAULT_INFO_TYPES],
            "min_likelihood": dlp_v2.Likelihood.LIKELY,
        }
        deidentify_config = {
            "info_type_transformations": {
                "transformations": [
                    {
                        "primitive_transformation": {
                            "replace_with_info_type_config": {}
                        }
                    }
                ]
            }
        }
        item = {"value": text}

        response = self._client.deidentify_content(
            request={
                "parent": parent,
                "deidentify_config": deidentify_config,
                "inspect_config": inspect_config,
                "item": item,
            }
        )

        redacted_text = response.item.value
        flags: list[str] = []
        if hasattr(response, "overview") and hasattr(
            response.overview, "transformation_summaries"
        ):
            for summary in response.overview.transformation_summaries:
                info_name = summary.info_type.name
                if info_name not in flags:
                    flags.append(info_name)

        return redacted_text, flags

    def _deidentify_with_fallback(self, text: str) -> tuple[str, list[str]]:
        """Offline deterministic regex fallback for unit testing and local development."""
        redacted = text
        flags: list[str] = []

        if _CREDIT_CARD_REGEX.search(redacted):
            redacted = _CREDIT_CARD_REGEX.sub("[CREDIT_CARD_NUMBER]", redacted)
            flags.append("CREDIT_CARD_NUMBER")

        if _SSN_REGEX.search(redacted):
            redacted = _SSN_REGEX.sub("[US_SOCIAL_SECURITY_NUMBER]", redacted)
            flags.append("US_SOCIAL_SECURITY_NUMBER")

        if _EMAIL_REGEX.search(redacted):
            redacted = _EMAIL_REGEX.sub("[EMAIL_ADDRESS]", redacted)
            flags.append("EMAIL_ADDRESS")

        if _PHONE_REGEX.search(redacted):
            # Only scrub if looks like actual phone, not brief version/year numbers
            def _replace_phone(m: re.Match[str]) -> str:
                s = m.group(0).strip()
                digits_count = sum(c.isdigit() for c in s)
                if digits_count >= 7:
                    return "[PHONE_NUMBER]"
                return s

            new_text = _PHONE_REGEX.sub(_replace_phone, redacted)
            if new_text != redacted:
                redacted = new_text
                flags.append("PHONE_NUMBER")

        return redacted, flags

    def deidentify_batch(
        self, blocks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Run batch de-identification over dialogue block dictionaries.
        
        Expects blocks with at least a 'text' or 'text_scrubbed' key.
        Returns the updated blocks with 'text_scrubbed' and 'dlp_redaction_flags'.
        """
        results: list[dict[str, Any]] = []
        for block in blocks:
            raw_text = block.get("text") or block.get("text_scrubbed", "")
            scrubbed, flags = self.deidentify_text(raw_text)
            updated = dict(block)
            updated["text_scrubbed"] = scrubbed
            existing_flags = list(updated.get("dlp_redaction_flags", []))
            for f in flags:
                if f not in existing_flags:
                    existing_flags.append(f)
            updated["dlp_redaction_flags"] = existing_flags
            results.append(updated)
        return results


_dlp_service_instance: DLPService | None = None


def get_dlp_service() -> DLPService:
    global _dlp_service_instance
    if _dlp_service_instance is None:
        _dlp_service_instance = DLPService()
    return _dlp_service_instance

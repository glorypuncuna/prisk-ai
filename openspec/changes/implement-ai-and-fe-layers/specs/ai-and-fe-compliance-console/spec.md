## ADDED Requirements

### Requirement: AI Privacy-Preserving Attestation Synthesis and React Compliance Console UI
The system SHALL use Vertex AI Gemini 2.5 Flash on sanitized metadata to synthesize framework-specific risk treatment narratives without verbatim quotes, and SHALL provide a React Compliance Audit Package Export & Verification Console (`ComplianceConsolePage.tsx`) supporting multi-framework selection (ISO 31000, COSO, SOC 2, HIPAA, GDPR), PDF/CSV/JSON export toggles, SHA-256 checksum verification badges, signed WORM downloads, and GDPR Article 17 Right-to-Erasure purge controls.

#### Scenario: Manager Exports and Verifies Sealed Package in Compliance Console UI
- **WHEN** a Manager selects ISO 31000 and GDPR in `ComplianceConsolePage.tsx` and triggers a PDF export
- **THEN** the system generates the sanitized 5-section package with zero verbatim quotes, seals it in GCS WORM storage, and renders the SHA-256 verification badge and signed download link in the React UI

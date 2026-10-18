## ADDED Requirements

### Requirement: Complete Cloud Firestore Schemas and Subcollection Hierarchy
The system SHALL define and enforce typed schemas across all Cloud Firestore collections: `users`, `projects`, `project_invitations`, `meetings` (including subcollection `dialogue_blocks` with vector embeddings), `sentiment_calibrations`, `risk_register`, `compliance_packages`, `audit_ledger`, and `email_notifications`.

#### Scenario: Dialogue block created with vector embedding and group categorization
- **WHEN** dialogue blocks are saved to `meetings/{meeting_id}/dialogue_blocks/{block_id}`
- **THEN** the document MUST contain `speaker_alias`, `group_id` (`BUYER` | `VENDOR` | `INTERNAL`), `text_scrubbed`, `word_count`, `sentiment_score` (0–100), and `embedding` (768-dimensional float array)

#### Scenario: Risk register 5x5 severity computation
- **WHEN** a risk is registered in `risk_register/{risk_id}` with `impact` (1–5) and `probability` (1–5)
- **THEN** the system MUST persist `severity_score` calculated as `impact * probability` (1–25) and assign the escalation SLA tier

### Requirement: Google Cloud Storage WORM Compliance Bucket Provisioning
The system SHALL provision and configure the Google Cloud Storage bucket `prisk-compliance-packages` with Object Retention Lock (WORM) enabled. Packages uploaded to this bucket SHALL be immutable and sealed with a SHA-256 cryptographic digest.

#### Scenario: Sealed compliance package upload
- **WHEN** an export is generated in `POST /api/v1/compliance/export`
- **THEN** the system SHALL upload the sealed artifact to `gs://prisk-compliance-packages/{package_id}.pdf` with object retention lock enabled
- **AND** the package record in Firestore MUST reflect `status = "SEALED_WORM"` and the exact SHA-256 checksum

### Requirement: BigQuery Analytical Data Sink Schemas
The system SHALL define and provision BigQuery datasets and tables in `prisk_analytics`:
1. `golden_dialogue_records`: partitioned by `meeting_date`, clustered by `project_id, group_id`.
2. `audit_ledger_sink`: partitioned by `DATE(timestamp)`.

#### Scenario: Committed meeting streams to BigQuery golden records
- **WHEN** an adjudicator calls `POST /api/v1/meetings/{id}/commit-golden-record`
- **THEN** the system SHALL stream anonymized, sanitized dialogue blocks into `prisk_analytics.golden_dialogue_records` without verbatim speaker names

### Requirement: Automated Cloud Database Schema Deployment and Verification
The system SHALL provide an automated CLI deployment script `backend/scripts/deploy_cloud_schemas.py` that connects to GCP services using Application Default Credentials or service account keys, verifies the existence of all 9 Firestore collections and indexes, creates the GCS WORM bucket, and initializes BigQuery tables.

#### Scenario: Dry-run schema validation
- **WHEN** an administrator runs `python backend/scripts/deploy_cloud_schemas.py --dry-run`
- **THEN** the script SHALL inspect and validate all Firestore, GCS, and BigQuery schemas, reporting validation status for every subsystem without making destructive changes

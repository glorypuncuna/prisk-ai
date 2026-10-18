## 1. Foundation, Identity, RBAC & Super Admin Management

- [x] 1.1 Configure Firebase Authentication (Identity Platform) integration and FastAPI JWT validation middleware
- [x] 1.2 Implement `POST /api/v1/auth/register-profile` with Python `phonenumbers` E.164 normalization and default `EXTERNAL_STAKEHOLDER` role assignment
- [x] 1.3 Implement `GET /api/v1/auth/me` and `PATCH /api/v1/users/{uid}/role` with Firebase custom claims synchronization
- [x] 1.4 Build React Login and Registration screen with country code picker, real-time input formatting, and quarantined onboarding state
- [x] 1.5 Implement Project Invitation endpoints (`POST /api/v1/projects/{project_id}/invitations`) and manager email alert worker
- [x] 1.6 Update `UserRole` enum and RBAC dependencies to include `ADMIN` at the apex with bypass permissions across all projects
- [x] 1.7 Implement `POST /api/v1/admin/users` to allow super admins to provision accounts directly with any role, E.164 phone, and project assignments
- [x] 1.8 Implement `DELETE /api/v1/admin/users/{uid}` for complete account termination, Firebase Auth deletion, Firestore document purge, and audit logging
- [x] 1.9 Build React Super Admin Console (`/admin/users`) with user search, role adjustment modal, and user de-provisioning controls

## 2. Complete Data Architecture, Firestore Schemas & Cloud Infrastructure

- [x] 2.1 Implement typed Pydantic models and Firestore repositories for `meetings` and `dialogue_blocks` subcollection with 768-dim vector embeddings
- [x] 2.2 Implement typed Pydantic models and Firestore repositories for `sentiment_calibrations` (Few-Shot exemplars) and `risk_register` (5x5 COSO/ISO 31000 matrix)
- [x] 2.3 Implement typed Pydantic models and Firestore repositories for `compliance_packages` (WORM metadata) and `audit_ledger` (immutable events)
- [x] 2.4 Author production `firestore.rules` declaring strict field-level RBAC authorization across all 9 collections
- [x] 2.5 Provision and configure Google Cloud Storage WORM compliance bucket (`prisk-compliance-packages`) with Object Retention Lock
- [x] 2.6 Define BigQuery schema definitions and client sink for `prisk_analytics.golden_dialogue_records` and `prisk_analytics.audit_ledger_sink`
- [x] 2.7 Implement automated CLI deployment and verification script (`backend/scripts/deploy_cloud_schemas.py`) with `--dry-run` validation
- [x] 2.8 Write comprehensive integration test suite verifying Admin user CRUD, Firestore collection schemas, GCS WORM upload, and BigQuery streaming

## 3. Meeting Ingestion & Post-Meeting DLP Pipeline

- [x] 3.1 Implement `POST /api/v1/meetings/dispatch-bot` to trigger `meetstream.ai` Google Meet join with chat consent notice
- [x] 3.2 Implement `POST /webhooks/meetstream/completed` webhook receiver with HMAC-SHA256 signature verification
- [x] 3.3 Integrate Google Cloud DLP batch `deidentify_content` pass to redact financial, government, and contact identifiers while preserving person and company names
- [x] 3.4 Implement transactional Firestore write for scrubbed dialogue blocks (`status = PROCESSING_POST_MEETING`)
- [x] 3.5 Implement verified upstream transcript deletion (`DELETE /bots/{bot_id}/transcript` on `meetstream.ai`) executed strictly after confirmed Firestore write


## 4. AI Sentiment Rubric, Few-Shot Vector Loop & On-Demand XAI

- [x] 4.1 Implement Vertex AI Gemini 3.8 Flash speaker-blind structured output schema for 4-dimension rubric scoring, MoM, and draft risks
- [x] 4.2 Implement Firestore Native Vector Search index and top-5 Few-Shot nearest neighbor retrieval (`text-embedding-004`) with Zero-Shot fallback for cold start
- [x] 4.3 Implement `POST /api/v1/meetings/{id}/blocks/{id}/explain` with typed JSON rubric breakdown and server-side verbatim substring offset validation

## 5. HITL Adjudication Workspace & Deterministic Rollups

- [x] 5.1 Build React Adjudication Workspace with side-by-side transcript editor, DLP mask visualizer, and 0–100 sentiment slider
- [x] 5.2 Implement `POST /api/v1/meetings/{id}/blocks/{id}/split` for client and server Bubble Splits inheriting parent scores
- [x] 5.3 Implement `PATCH /api/v1/meetings/{id}/session-grouping` for in-session speaker-to-group auto-assignment
- [x] 5.4 Implement deterministic client-side (<50ms) and server-side word-count weighted Group and Meeting Pulse Score rollups
- [x] 5.5 Implement `POST /api/v1/meetings/{id}/commit-golden-record` to strip ephemeral speaker accounts, persist `corrected_contexts` embeddings, and stream BigQuery rows

## 6. Enterprise Risk Register & Automated Escalation SLAs

- [x] 6.1 Implement Firestore `risk_register` schema and REST endpoints for COSO/ISO 31000 Impact (1–5) and Probability (1–5) severity scoring
- [x] 6.2 Build React 5x5 Risk Heatmap matrix, interactive node drill-downs, and Risk Register table with audit drawers
- [x] 6.3 Deploy Cloud Scheduler 15-minute cron job (`POST /internal/jobs/evaluate-escalations`) evaluating 24h, 48h, and 72h SLA thresholds
- [x] 6.4 Implement Systemic Risk Spike detection rule ($\ge 3$ critical projects or $>25\%$ weekly severity surge) and executive alert dispatch

## 7. Multi-Framework Compliance Audit Reporting & WORM Storage

- [x] 7.1 Create version-controlled static crosswalk matrix (`compliance_framework_matrix.json`) mapping risk categories to ISO 31000, COSO, SOC 2, HIPAA, and GDPR clauses
- [x] 7.2 Implement `SanitizationService` enforcing zero verbatim quotes, PII redaction, and internal commentary exclusion
- [x] 7.3 Implement `POST /api/v1/compliance/export` generator compiling the 5 structured sections into PDF (WeasyPrint), CSV, and JSON
- [x] 7.4 Implement SHA-256 cryptographic sealing, upload to Google Cloud Storage WORM bucket (`prisk-compliance-packages`), and BigQuery audit ledger registration
- [x] 7.5 Implement GDPR Article 17 cascading purge endpoint (`DELETE /api/v1/meetings/{id}/purge`) with tombstone ledger logging

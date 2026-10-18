## Why

Prisk AI transforms meeting audio and transcripts into objective group-level relationship health insights, explainable sentiment ratings, and proactive project risk mitigations. Following comprehensive requirements definition across `prd.md`, `registration_prd.md`, and `risk_mitigation_prd.md`, and technical design in `trd.md`, this change establishes the core end-to-end platform architecture to support secure user authentication, super admin governance, complete cloud database schemas (Cloud Firestore, GCS WORM, BigQuery), post-meeting privacy-preserving ingestion, human-in-the-loop adjudication, and enterprise risk governance.

## What Changes

- **User Authentication & Quarantined Onboarding:** Implement Firebase Identity Platform authentication supporting Email/Password and OAuth 2.0/OIDC, server-side E.164 phone normalization, default quarantined `EXTERNAL_STAKEHOLDER` role, and Project Invitation workflows.
- **Super Admin (`ADMIN`) Role & User Administration:** Add `ADMIN` super admin role to the canonical RBAC hierarchy (`ADMIN > EXECUTIVE > MANAGER > ADJUDICATOR > EXTERNAL_STAKEHOLDER`), providing unrestricted endpoints for user provisioning, role adjustments, project assignments, and account de-provisioning (`POST /api/v1/admin/users`, `DELETE /api/v1/admin/users/{uid}`) with React Super Admin Console.
- **Cloud Database Architecture & Schemas:** Formalize production schemas and Pydantic models across all 9 Cloud Firestore collections (including `dialogue_blocks` with 768-dim embeddings, `sentiment_calibrations`, `risk_register`, `compliance_packages`, and `audit_ledger`), provision GCS WORM bucket (`prisk-compliance-packages`) with Object Retention Lock, and configure BigQuery streaming sinks (`golden_dialogue_records`, `audit_ledger_sink`).
- **Post-Meeting Ingestion & Verified Upstream Deletion:** Ingest completed meeting transcripts via `meetstream.ai` webhooks, execute single-pass batch Cloud DLP scrubbing, commit scrubbed dialogue blocks to Firestore, and permanently delete upstream MeetStream transcripts strictly after verified database persistence.
- **AI Sentiment Rubric & On-Demand XAI:** Execute speaker-blind baseline scoring via Gemini 2.5 Flash using Zero-Shot (cold-start) or Few-Shot top-5 vector retrieval from `corrected_contexts`, and provide on-demand verbatim Explainable AI attributions with server-side offset verification.
- **Human-in-the-Loop Adjudication Workspace:** Provide an interactive workspace for Bubble Splits, session-scoped ephemeral speaker-to-group mapping, deterministic 0–100 sentiment slider rollup, and immutable Golden Record commits.
- **Enterprise Risk & Escalation Engine:** Implement COSO/ISO 31000 quantitative severity scoring (`1–25`), automated 24h/48h/72h escalation SLAs via Cloud Scheduler, and systemic risk spike detection ($\ge 3$ critical projects or $>25\%$ weekly severity surge).
- **Cryptographic Compliance Reporting:** Generate exportable 5-section compliance audit packages across ISO 31000, COSO, SOC 2, HIPAA, and GDPR in PDF, CSV, and JSON formats, sealed with SHA-256 signatures, stored in a WORM GCS bucket, and enforcing zero verbatim participant quotes.

## Capabilities

### New Capabilities
- `user-authentication`: User registration with E.164 phone normalization, Firebase Auth JWT validation, quarantined `EXTERNAL_STAKEHOLDER` role, and project invitation management.
- `admin-role-and-user-management`: Canonical `ADMIN` super admin role definition, Firebase Custom Claims sync, and super admin user administration endpoints (`POST /api/v1/admin/users`, `GET /api/v1/admin/users`, `PATCH /api/v1/admin/users/{uid}`, `DELETE /api/v1/admin/users/{uid}`).
- `cloud-database-architecture`: Comprehensive database schemas, collections, indexes, and cloud integrations covering Cloud Firestore, Google Cloud Storage WORM, and BigQuery analytics streaming tables.
- `meeting-ingestion`: Post-meeting webhook ingestion, batch Cloud DLP PII scrubbing, verified Firestore persistence, and conditional upstream transcript deletion.
- `sentiment-xai`: Speaker-blind rubric scoring, Few-Shot vector search on `corrected_contexts`, Zero-Shot cold start, and on-demand Explainable AI (XAI).
- `hitl-adjudication`: Transcript bubble splitting, ephemeral speaker-to-group mapping, real-time deterministic score rollup, and Golden Record locking.
- `risk-mitigation`: Centralized Risk Register, COSO/ISO 31000 5x5 heatmap scoring, 24h/48h/72h automated escalation worker, and systemic risk spike detection.
- `compliance-reporting`: 5-section compliance audit package generator across ISO 31000, COSO, SOC 2, HIPAA, and GDPR with SHA-256 sealing, GCS WORM retention, and zero-verbatim-quote privacy preservation.

### Modified Capabilities
None.

## Impact

- **Backend:** New FastAPI services on Cloud Run (`auth`, `admin`, `meetings`, `adjudication`, `risks`, `compliance`), Cloud DLP client integration, and Cloud Scheduler escalation jobs.
- **Storage & Databases:** Firestore collections (`users`, `projects`, `project_invitations`, `meetings`, `dialogue_blocks`, `sentiment_calibrations`, `risk_register`, `compliance_packages`, `audit_ledger`, `email_notifications`), Google Cloud Storage WORM bucket (`prisk-compliance-packages`), and BigQuery tables (`golden_dialogue_records`, `audit_ledger_sink`).
- **External Dependencies:** Firebase Authentication, `meetstream.ai` bot API and webhooks, Google Cloud DLP, Google Cloud Storage, Vertex AI Gemini 2.5 Flash + `text-embedding-004`, and SendGrid/SMTP.
- **Frontend:** React 18+ SPA with Vite, Tailwind CSS, TanStack Query, Zustand, Recharts, `react-grid-layout`, and Super Admin Console (`/admin/users`).

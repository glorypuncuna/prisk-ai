## Context

Prisk AI is a cloud-native platform providing meeting pulse analytics, group sentiment ratings, and enterprise risk mitigations. Built on Google Cloud Platform, the architecture unifies Python FastAPI serverless containers (Cloud Run), React 18+ SPA, Firebase Identity Platform, Google Cloud DLP, Vertex AI (Gemini 2.5 Flash and `text-embedding-004`), Cloud Firestore (with Native Vector Search), and Google BigQuery.

## Goals / Non-Goals

**Goals:**
- Provide secure user authentication with international E.164 phone validation and quarantined onboarding.
- Define `ADMIN` in `UserRole` as the apex RBAC authority (`ADMIN > EXECUTIVE > MANAGER > ADJUDICATOR > EXTERNAL_STAKEHOLDER`) with dedicated user administration endpoints (`/api/v1/admin/users/*`) and React Super Admin Console.
- Define end-to-end schemas, data models, and indexes for all 9 Firestore collections and subcollections with 768-dim vector embeddings.
- Streamline meeting ingestion via post-meeting batch webhooks, automated DLP scrubbing, verified Firestore persistence, and subsequent upstream transcript deletion.
- Enforce speaker-blind structured rubric scoring via Gemini 2.5 Flash, Zero-Shot cold start, and Few-Shot vector search on `corrected_contexts`.
- Support HITL adjudication with Bubble Split, ephemeral speaker-to-group mapping, deterministic score rollups, and immutable Golden Record commits.
- Deliver enterprise risk management with COSO/ISO 31000 severity heatmaps, automated 24h/48h/72h escalation SLAs, and systemic risk spike alerts.
- Produce 5-section compliance audit packages (PDF/CSV/JSON) sealed with SHA-256 hashes in a WORM GCS bucket (`prisk-compliance-packages`) with zero verbatim quotes.
- Provide a Cloud Deployment & Validation CLI script (`deploy_cloud_schemas.py`) for live GCP environment verification.

**Non-Goals:**
- Real-time in-meeting sentiment scoring or live chunk webhook ingestion (delegated to MeetStream autonomously).
- Permanent storage of raw meeting audio files (Prisk AI never stores raw audio).
- Profiling individual meeting participants (longitudinal tracking is strictly bound to canonical Groups).
- Retroactive re-scoring of past Golden Records when new overrides are created.

## Decisions

### Decision 1: Firebase Identity Platform for User Authentication (ADR-0006)
- **Choice:** Standardize on Firebase Authentication (Google Identity Platform) for Email/Password, OAuth 2.0/OIDC (Google, Microsoft), and managed password hashing (Argon2 / scrypt), storing extended profile attributes (First Name, Last Name, normalized E.164 phone number) in Firestore `users/{uid}`.
- **Alternatives Considered:** Custom PostgreSQL auth service with FastAPI JWT issuance. Rejected due to increased cryptographic maintenance and attack surface.
- **Rationale:** Offloads credential storage, enables fast stateless JWT validation in FastAPI middleware via custom claims, and supports zero-trust quarantined onboarding defaulting new users to `EXTERNAL_STAKEHOLDER`.

### Decision 2: Dedicated `ADMIN` Super Admin Role & Permissions Matrix
- **Choice:** Place `ADMIN` at the apex of the RBAC hierarchy (`ADMIN > EXECUTIVE > MANAGER > ADJUDICATOR > EXTERNAL_STAKEHOLDER`).
- **Hierarchy & Capabilities:**
  - `ADMIN`: Unrestricted global CRUD over all users, roles, projects, invitations, and system settings. Can delete any user (with GDPR Article 17 tombstone audit logging).
  - `EXECUTIVE`: Global view of all risk heatmaps, compliance exports, project analytics; can invite users and elevate roles up to `EXECUTIVE`.
  - `MANAGER`: Scoped project administration; can create projects, invite users, elevate roles up to `MANAGER`, and review risk registers.
  - `ADJUDICATOR`: HITL workspace access, sentiment slider adjustment (0–100), Bubble Splits, session group labeling, and committing golden records.
  - `EXTERNAL_STAKEHOLDER`: Strictly read-only access to assigned projects; quarantined upon registration until assigned.
- **Alternatives Considered:** Merging Super Admin duties into `EXECUTIVE`. *Rejected* because compliance and security separation of duties (SoD) requires system administrators (IT/SecOps) to be distinct from business executives.

### Decision 3: Full Firestore Schema Architecture (Native Mode)
- **Choice:** Standardize on 9 canonical collections and subcollections in Cloud Firestore:
```
Firestore (Native Mode)
├── users/{uid}
│   ├── uid, email, first_name, last_name, phone_number (E.164)
│   ├── role ("ADMIN" | "EXECUTIVE" | "MANAGER" | "ADJUDICATOR" | "EXTERNAL_STAKEHOLDER")
│   ├── auth_provider, assigned_project_ids[], onboarding_status, timestamps
│
├── projects/{project_id}
│   ├── project_id, name, description, owner_uid, created_at
│
├── project_invitations/{invitation_id}
│   ├── invitation_id, project_id, project_name, invitee_email, invited_by_uid, status ("PENDING" | "ACCEPTED"), timestamps
│
├── meetings/{meeting_id}
│   ├── meeting_id, project_id, title, platform ("google_meet"), meeting_date, status ("PROCESSING" | "PENDING_ADJUDICATION" | "COMMITTED")
│   ├── pulse_score (0-100), group_scores{}, mom_summary, participants[]
│   └── subcollection: dialogue_blocks/{block_id}
│       ├── block_id, speaker_alias, group_id ("BUYER" | "VENDOR" | "INTERNAL"), text_scrubbed
│       ├── dlp_redaction_flags[], sentiment_score (0-100), rubric_scores{}, word_count
│       ├── embedding (vector<768>, text-embedding-004), is_split, parent_block_id
│
├── sentiment_calibrations/{calibration_id}
│   ├── calibration_id, dialogue_text, benchmark_score, rubric_breakdown, embedding (vector<768>)
│
├── risk_register/{risk_id}
│   ├── risk_id, project_id, meeting_id, title, description, category, impact (1-5), probability (1-5), severity_score (1-25)
│   ├── status ("OPEN" | "MITIGATED" | "ACCEPTED"), owner_uid, sla_escalation_tier ("24h" | "48h" | "72h"), timestamps
│
├── compliance_packages/{package_id}
│   ├── package_id, project_id, framework ("ISO_31000" | "COSO" | "SOC2" | "HIPAA" | "GDPR"), sha256_hash
│   ├── gcs_uri, status ("SEALED_WORM"), created_at
│
├── audit_ledger/{event_id}
│   ├── event_id, event_type, actor_uid, target_id, metadata{}, timestamp (immutable)
│
└── email_notifications/{notification_id}
    ├── notification_id, type, from, to, subject, body, sent_at
```

### Decision 4: Post-Meeting Batch Ingestion and Verified Upstream Deletion (ADR-0002)
- **Choice:** Rely on `meetstream.ai` to handle live audio capture and transcription autonomously. Prisk AI receives a single post-meeting webhook (`POST /webhooks/meetstream/completed`), runs batch Cloud DLP scrubbing, commits dialogue blocks to Firestore, and invokes `DELETE /bots/{bot_id}/transcript` on `meetstream.ai` strictly AFTER verified Firestore write.
- **Alternatives Considered:** Streaming live transcript chunks via SSE to browser. Rejected to eliminate distributed container memory loss risks during auto-scaling and avoid continuous in-meeting compute costs.
- **Rationale:** Ensures raw transcripts are never deleted prematurely if database writes fail, eliminates container session stickiness requirements, and satisfies strict data minimization.

### Decision 5: Speaker-Blind Structured Outputs & Firestore Vector Search (ADR-0001, ADR-0003, ADR-0004)
- **Choice:** Strip speaker names and participant identifiers before submitting dialogue blocks to Gemini 2.5 Flash. Fetch top-5 semantic overrides from Firestore `corrected_contexts` using `find_nearest` (768-dim `text-embedding-004`), defaulting to pure Zero-Shot rubric inference on cold-start projects/groups.
- **Alternatives Considered:** Provisioning dedicated Vertex AI Vector Search and Prediction endpoints. Rejected due to high idle cost ($300+/month).
- **Rationale:** Eliminates speaker bias in AI ratings, keeps infrastructure 100% serverless ($0 idle cost), and achieves sub-100ms vector retrieval directly in Firestore.

### Decision 6: Cryptographic Compliance Packages with Zero Verbatim Quotes (ADR-0007)
- **Choice:** Compile exportable 5-section compliance audit packages across ISO 31000, COSO, SOC 2, HIPAA, and GDPR in PDF (WeasyPrint), CSV, and JSON. Seal each artifact with a SHA-256 hash, persist in a WORM GCS bucket (`prisk-compliance-packages`), log signatures to BigQuery `audit_ledger_sink`, and enforce zero verbatim quotes.
- **Alternatives Considered:** Generating reports on-the-fly dynamically without permanent storage. Rejected because compliance audits require tamper-proof non-repudiation.
- **Rationale:** Including zero verbatim participant quotes ensures that when GDPR Right to Erasure purges operational records, historical WORM compliance artifacts in GCS require no modifications, resolving the tension between regulatory audit immutability and privacy erasure.

### Decision 7: BigQuery Analytical Data Sink & Automated Schema Deployment
- **Choice:** Provision partitioned BigQuery tables in dataset `prisk_analytics` (`golden_dialogue_records` and `audit_ledger_sink`) and provide an automated CLI deployment script (`backend/scripts/deploy_cloud_schemas.py`) with `--dry-run` validation.
- **Rationale:** Decouples operational transactional workloads from analytical and audit querying, while CLI automation guarantees repeatable provisioning across GCP development, staging, and production environments.

## Risks / Trade-offs

- **[Risk: Meeting Ingestion Webhook Failure]** → Mitigate via exponential backoff retries on `meetstream.ai` webhooks and manual "Sync Meeting" fallback button in Project Manager UI.
- **[Risk: Upstream Deletion Failure]** → Mitigate by queuing failed deletion requests in Cloud Tasks with dead-letter alerting; never delete upstream until Firestore commits successfully.
- **[Risk: Inappropriate Adjudicator Slider Overrides]** → Mitigate by logging all slider adjustments with `actor_uid` and previous/new score to BigQuery `audit_ledger_sink`, allowing Managers to audit calibration anomalies.
- **[Risk: Quarantined User Confusion]** → Mitigate by displaying clear onboarding status ("Access Pending Project Invitation"), notifying Project Managers via email upon registration, and providing one-click invitation links.
- **[Risk: Super Admin Account Takeover]** → Mitigate by requiring E.164 phone number verification for MFA, logging all `ADMIN` operations to `audit_ledger`, and preventing self-deletion of active admins.
- **[Risk: Cloud Firestore Vector Quota Limits]** → Mitigate by limiting Few-Shot queries to top-5 exemplars with cosine distance threshold $\ge 0.75$, falling back to zero-shot on cold start.
- **[Risk: Dual-Mode Compatibility (Local vs Cloud)]** → Mitigate by maintaining `InMemoryFirestoreClient` in `database.py` that mirrors collection queries so local dev and automated tests run offline without GCP credentials.

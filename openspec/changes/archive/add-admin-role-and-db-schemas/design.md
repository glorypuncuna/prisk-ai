## Context

pRiskAI is an enterprise meeting intelligence and risk governance platform. While Section 1 established basic identity and project invitation flows for `EXECUTIVE`, `MANAGER`, `ADJUDICATOR`, and `EXTERNAL_STAKEHOLDER`, two architectural requirements are missing:
1. **Super Admin (`ADMIN`) Role:** Enterprise organizations require an unrestricted administrative operator who can provision, inspect, modify, elevate, de-provision, and permanently remove user accounts and projects across the entire system.
2. **Complete Cloud Database Architecture & Schemas:** Every subsystem in pRiskAI (Dialogue Blocks with Vector Embeddings, HITL Sentiment Calibrations, 5x5 COSO/ISO 31000 Risk Register, WORM Compliance Audit Packages, and Immutable Audit Ledgers) requires formal, production-grade schemas across Cloud Firestore, Google Cloud Storage, and Google BigQuery.

## Goals / Non-Goals

**Goals:**
- Define `ADMIN` in `UserRole` as the supreme RBAC authority (`ADMIN > EXECUTIVE > MANAGER > ADJUDICATOR > EXTERNAL_STAKEHOLDER`).
- Provide dedicated Super Admin endpoints (`/api/v1/admin/users/*`) for user creation, role assignment, project rebinding, and account deletion.
- Define end-to-end schemas, data models, and indexes for all 9 Firestore collections and subcollections.
- Define Google Cloud Storage WORM compliance bucket architecture (`prisk-compliance-packages`) with Object Retention Lock.
- Define Google BigQuery analytical streaming schemas for Golden Dialogue Records and Audit Ledger long-term archival.
- Provide a Cloud Deployment & Validation CLI script (`deploy_cloud_schemas.py`) for live GCP environment verification.

**Non-Goals:**
- Live meeting real-time WebSockets (deferred to post-meeting batch ingestion via `meetstream.ai` in Section 2).
- Third-party identity broker replacements (Firebase Identity Platform remains the canonical auth provider).

## Decisions

### 1. Dedicated `ADMIN` Super Admin Role & Permissions Matrix

- **Decision:** Place `ADMIN` at the apex of the RBAC hierarchy.
- **Hierarchy & Capabilities:**
  - `ADMIN`: Unrestricted global CRUD over all users, roles, projects, invitations, and system settings. Can delete any user (with GDPR Article 17 tombstone audit logging).
  - `EXECUTIVE`: Global view of all risk heatmaps, compliance exports, project analytics; can invite users and elevate roles up to `EXECUTIVE`.
  - `MANAGER`: Scoped project administration; can create projects, invite users, elevate roles up to `MANAGER`, and review risk registers.
  - `ADJUDICATOR`: HITL workspace access, sentiment slider adjustment (0–100), Bubble Splits, session group labeling, and committing golden records.
  - `EXTERNAL_STAKEHOLDER`: Strictly read-only access to assigned projects; quarantined upon registration until assigned.
- **Alternatives Considered:** Merging Super Admin duties into `EXECUTIVE`. *Rejected* because compliance and security separation of duties (SoD) requires system administrators (IT/SecOps) to be distinct from business executives.

### 2. Full Firestore Schema Architecture

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

### 3. Google Cloud Storage WORM Bucket (`prisk-compliance-packages`)

- **Retention Policy:** Object Retention Lock enabled with a 7-year compliant WORM hold (FINRA/SEC/ISO compliance).
- **Enforcement:** `SanitizationService` validates that zero verbatim quotes, zero unredacted PII, and zero internal commentary exist before calculating SHA-256 and uploading the package.

### 4. BigQuery Analytical Data Sink

- **Dataset:** `prisk_analytics`
- **Table 1:** `golden_dialogue_records`: Append-only partitioned by `meeting_date` and clustered by `project_id, group_id`. Stores committed golden records for model retraining without PII.
- **Table 2:** `audit_ledger_sink`: Partitioned by `DATE(timestamp)`. Mirrors Firestore `audit_ledger` for tamper-evident compliance audit queries.

## Risks / Trade-offs

- **[Risk] Super Admin account takeover.**
  → *Mitigation:* Require E.164 phone number verification for MFA, log all `ADMIN` operations with high severity to `audit_ledger`, and prevent deleting the last active `ADMIN`.
- **[Risk] Cloud Firestore quota limits on vector searches.**
  → *Mitigation:* Limit Few-Shot nearest-neighbor queries to top-5 exemplars with cosine distance threshold $\ge 0.75$, falling back to zero-shot on cold start.
- **[Risk] Dual-mode compatibility (Local vs Cloud).**
  → *Mitigation:* The `InMemoryFirestoreClient` in `database.py` mirrors all Firestore document and collection queries so local development and automated pytest runs execute offline without GCP credentials.

## Why

pRiskAI currently defines four enterprise RBAC roles (`EXECUTIVE`, `MANAGER`, `ADJUDICATOR`, `EXTERNAL_STAKEHOLDER`). However, system administration lacks a dedicated `ADMIN` (Super Admin) role capable of comprehensive user lifecycle management (adding, modifying, elevating, deactivating, and removing any user account) across all enterprise tenants, projects, and security partitions. Furthermore, while initial in-memory and Firestore abstractions exist for Section 1, the end-to-end database schemas for all pRiskAI subsystems (Meetings, Dialogue Blocks, HITL Sentiment, Risk Register, Compliance Packages, and Audit Ledger) and their direct cloud integrations (Cloud Firestore, Google Cloud Storage WORM, BigQuery Analytics Sink) must be formalized into production schemas with automated deployment scripts.

## What Changes

- Add `ADMIN` super admin role to the canonical RBAC hierarchy (`ADMIN > EXECUTIVE > MANAGER > ADJUDICATOR > EXTERNAL_STAKEHOLDER`).
- Empower `ADMIN` with unrestricted user administration endpoints: create users, assign any role, reassign project bindings, deactivate accounts, and hard-delete accounts with GDPR audit trails (`POST /api/v1/admin/users`, `DELETE /api/v1/admin/users/{uid}`).
- Update Firebase Authentication Custom Claims sync and JWT verification to recognize and enforce `role: "ADMIN"`.
- Formalize complete database schemas and indexes across Cloud Firestore:
  - `users/{uid}`
  - `projects/{project_id}`
  - `project_invitations/{invitation_id}`
  - `meetings/{meeting_id}` and `meetings/{meeting_id}/dialogue_blocks/{block_id}`
  - `sentiment_calibrations/{calibration_id}`
  - `risk_register/{risk_id}`
  - `compliance_packages/{package_id}`
  - `audit_ledger/{event_id}`
  - `email_notifications/{notification_id}`
- Implement production Google Cloud Storage WORM bucket provisioning and retention lock integration for compliance packages (`prisk-compliance-packages`).
- Implement BigQuery streaming sink schemas (`golden_dialogue_records` and `audit_ledger_sink`).
- Provide automated cloud database provisioning CLI and schema validator (`backend/scripts/deploy_cloud_schemas.py`) ensuring production Cloud Firestore, GCS, and BigQuery are verified and deployable.
- Update frontend UI with a dedicated Super Admin console (`/admin/users`) with user CRUD, role management, and database telemetry.

## Capabilities

### New Capabilities
- `admin-role-and-user-management`: Canonical `ADMIN` super admin role definition, Firebase Custom Claims sync, and super admin user administration endpoints (`POST /api/v1/admin/users`, `GET /api/v1/admin/users`, `PATCH /api/v1/admin/users/{uid}`, `DELETE /api/v1/admin/users/{uid}`).
- `cloud-database-architecture`: Comprehensive database schemas, collections, indexes, and cloud integrations covering Cloud Firestore, Google Cloud Storage WORM, and BigQuery analytics streaming tables.

### Modified Capabilities
<!-- No requirement changes to prior existing specs -->

## Impact

- **Backend Auth & RBAC (`app/core/enums.py`, `app/core/security.py`):** Adds `ADMIN` to `UserRole` and updates `require_role` dependencies.
- **Backend API (`app/api/v1/admin.py`, `app/api/v1/users.py`):** Adds `/api/v1/admin/*` administrative routes and delete operations.
- **Backend Schemas (`app/schemas/`):** Adds typed Pydantic models for all entities: Meetings, Dialogue Blocks, Calibrations, Risk Register, Compliance Packages, and Audit Ledger.
- **Database Layer (`app/core/database.py`, `backend/scripts/`):** Adds live Cloud Firestore collection handlers, BigQuery client sink, GCS client, and deployment script.
- **Frontend (`frontend/src/`):** Adds Super Admin user management interface and role management controls.

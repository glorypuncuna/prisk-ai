## 1. ADMIN Super Admin Role & User Administration Endpoints

- [ ] 1.1 Update `UserRole` enum and RBAC dependencies to include `ADMIN` at the apex with bypass permissions across all projects
- [ ] 1.2 Implement `POST /api/v1/admin/users` to allow super admins to provision accounts directly with any role, E.164 phone, and project assignments
- [ ] 1.3 Implement `DELETE /api/v1/admin/users/{uid}` for complete account termination, Firebase Auth deletion, Firestore document purge, and audit logging
- [ ] 1.4 Build React Super Admin Console (`/admin/users`) with user search, role adjustment modal, and user de-provisioning controls

## 2. Complete Firestore Database Schemas & Pydantic Data Models

- [ ] 2.1 Implement typed Pydantic models and Firestore repositories for `meetings` and `dialogue_blocks` subcollection with 768-dim vector embeddings
- [ ] 2.2 Implement typed Pydantic models and Firestore repositories for `sentiment_calibrations` (Few-Shot exemplars) and `risk_register` (5x5 COSO/ISO 31000 matrix)
- [ ] 2.3 Implement typed Pydantic models and Firestore repositories for `compliance_packages` (WORM metadata) and `audit_ledger` (immutable events)
- [ ] 2.4 Author production `firestore.rules` declaring strict field-level RBAC authorization across all 9 collections

## 3. Cloud Integration: GCS WORM Bucket & BigQuery Analytics Sink

- [ ] 3.1 Provision and configure Google Cloud Storage WORM compliance bucket (`prisk-compliance-packages`) with Object Retention Lock
- [ ] 3.2 Define BigQuery schema definitions and client sink for `prisk_analytics.golden_dialogue_records` and `prisk_analytics.audit_ledger_sink`
- [ ] 3.3 Implement automated CLI deployment and verification script (`backend/scripts/deploy_cloud_schemas.py`) with `--dry-run` validation
- [ ] 3.4 Write comprehensive integration test suite verifying Admin user CRUD, Firestore collection schemas, GCS WORM upload, and BigQuery streaming

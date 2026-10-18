# Cryptographically Verifiable Compliance Audit Packages with WORM Cloud Storage

To satisfy enterprise regulatory requirements (ISO 31000, COSO, SOC 2, HIPAA, GDPR) for exportable, tamper-proof compliance artifacts (`FR-7.1d`), Prisk AI generates compliance audit packages in user-selected formats (PDF, CSV, JSON) asynchronously via Cloud Run, seals each artifact with a SHA-256 cryptographic checksum, and stores the binary output in a Google Cloud Storage bucket (`prisk-compliance-packages`) configured with Object Retention (Write Once, Read Many / WORM policy). The export metadata is indexed in Firestore (`compliance_packages/{package_id}`) and its cryptographic hash is appended to BigQuery (`prisk_governance.immutable_audit_ledger`).

## Consequences

- Exported compliance artifacts cannot be altered or overwritten post-generation, ensuring full non-repudiation during regulatory audits.
- External regulators or compliance auditors can verify document integrity by recalculating the SHA-256 hash of any downloaded artifact and matching it against the immutable BigQuery ledger.
- Large compliance PDF/JSON generation does not block the FastAPI synchronous request loop, returning an export job ID that the client polls or receives via notification.

## ADDED Requirements

### Requirement: Post-Meeting Webhook Ingestion
The system SHALL ingest completed meeting transcripts via the `POST /webhooks/meetstream/completed` endpoint verified by HMAC-SHA256 signature without receiving live in-meeting chunks or streaming live SSE.

#### Scenario: Verified Webhook Ingestion
- **WHEN** `meetstream.ai` sends a valid signed `meeting.completed` payload containing `bot_id` and `transcript_id`
- **THEN** the system validates signature, marks the meeting status as `PROCESSING_POST_MEETING`, and fetches raw transcript data

### Requirement: Google Cloud DLP PII Scrubbing
The system SHALL execute a single batch Google Cloud DLP `deidentifyContent` call per completed meeting transcript, redacting financial, government, and contact identifiers while preserving `PERSON_NAME` and `Company` names.

#### Scenario: PII Redacted from Dialogue Blocks
- **WHEN** a raw transcript contains phone numbers, credit card numbers, or email addresses
- **THEN** Cloud DLP replaces sensitive entities with standardized tokens (`[PHONE_NUMBER]`, `[CREDIT_CARD]`, `[EMAIL]`) while preserving speaker names and company entities

### Requirement: Verified Upstream Transcript Deletion
The system SHALL invoke the `meetstream.ai` API to permanently delete upstream transcript records strictly AFTER verified successful persistence of scrubbed dialogue blocks to Cloud Firestore.

#### Scenario: Upstream Deletion on Successful Save
- **WHEN** the scrubbed dialogue blocks are successfully committed to Firestore
- **THEN** the system executes `DELETE /bots/{bot_id}/transcript` on `meetstream.ai` and logs confirmation

#### Scenario: Abort Upstream Deletion on Database Failure
- **WHEN** the Firestore write fails due to transient database error or network timeout
- **THEN** the system aborts the upstream deletion request, logs the failure, and triggers an error alert to prevent data loss

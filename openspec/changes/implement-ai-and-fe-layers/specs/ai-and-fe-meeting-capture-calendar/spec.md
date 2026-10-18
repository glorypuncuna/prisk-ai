## ADDED Requirements

### Requirement: Automatic Post-Ingestion AI Scoring Handoff
The system SHALL automatically trigger `SentimentService.run_post_meeting_scoring_pipeline` (Vertex AI Gemini 2.5 Flash speaker-blind rubric scoring, MoM synthesis, and draft risk extraction) upon verified Firestore persistence and upstream deletion during webhook ingestion.

#### Scenario: Webhook Ingestion Transitions Meeting to Pending Adjudication
- **WHEN** `POST /webhooks/meetstream/completed` finishes DLP scrubbing, Firestore persistence, and upstream transcript deletion
- **THEN** the system executes Gemini 2.5 Flash post-meeting baseline scoring and transitions the meeting status to `PENDING_ADJUDICATION`

### Requirement: React Meeting Capture, Lifecycle Status, and Historical Calendar UI
The system SHALL provide a React Meeting Capture & Status View (`MeetingCapturePage.tsx`) for dispatching `meetstream.ai` bots and monitoring lifecycle states (`CAPTURING` $\rightarrow$ `PROCESSING_POST_MEETING` $\rightarrow$ `PENDING_ADJUDICATION` $\rightarrow$ `GOLDEN_RECORD`), alongside an In-App Historical Calendar (`CalendarArchivePage.tsx`) displaying meetings color-coded by Pulse Score.

#### Scenario: Manager Dispatches Bot and Views Lifecycle Card
- **WHEN** a Manager submits a Google Meet link and project in `MeetingCapturePage.tsx`
- **THEN** the UI dispatches the bot, renders a live status card with DLP redaction badge metrics, and provides a one-click navigation action to the Adjudication Workspace once `PENDING_ADJUDICATION` is reached

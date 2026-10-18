# Post-Meeting DLP Scrubbing, Verified Persistence, and Upstream Deletion

To control cloud operating costs, prevent distributed container memory loss, and satisfy strict data minimization requirements, Prisk AI delegates live meeting capture and live transcription entirely to `meetstream.ai`. Prisk AI omits live in-meeting webhook chunking, ephemeral in-memory buffering, and live SSE streaming. Upon meeting conclusion, `meetstream.ai` issues a `meeting.completed` webhook. The complete transcript is scrubbed in a single post-meeting batch pass via Google Cloud DLP and persisted to Cloud Firestore. Only after successful Firestore persistence does FastAPI invoke the `meetstream.ai` API to permanently delete the upstream transcript, after which Gemini 2.5 Flash baseline inference is executed.

## Consequences

- Zero live webhook processing, zero container session-stickiness risks, and zero live SSE streaming infrastructure on Cloud Run during active calls.
- Upstream deletion from `meetstream.ai` is strictly gated on verified Firestore persistence, preventing data loss in the event of database write failures or network errors.
- Eliminates third-party data retention liability on `meetstream.ai` while ensuring raw transcripts are scrubbed before persistence or AI inference.

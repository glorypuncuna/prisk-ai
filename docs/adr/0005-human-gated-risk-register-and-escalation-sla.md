# Human-Gated Risk Promotion Before Escalation SLA Activation

To reconcile automated risk discovery (`FR-7.1`, `FR-7.3`) with Responsible AI human oversight (`Trustworthy AI Pillar #3`), risks discovered by Gemini 2.5 Flash or triggered by pulse drops (`>15` points or `<40`) are initially created in `DRAFT_PENDING_ADJUDICATION` status attached to the meeting workspace. Only when an Adjudicator reviews and commits the `Golden Record` are approved risks promoted to `OPEN` in the Centralized Risk Register, starting the 24h/48h/72h escalation SLA clock evaluated by Cloud Scheduler.

## Consequences

- Prevents pre-adjudicated false-positive sentiment drops or hallucinated AI risks from firing executive escalation notifications before human verification.
- The 24h/48h/72h escalation SLA timestamps are anchored to `golden_record_committed_at` rather than `meeting_ended_at`.

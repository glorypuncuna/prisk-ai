## ADDED Requirements

### Requirement: AI Insight Regeneration and Active-Learning Calibration Loop
The system SHALL provide `POST /api/v1/meetings/{id}/regenerate-insights` to re-invoke Gemini 2.5 Flash using Adjudicator-updated group assignments and pulse scores, and SHALL embed all human-overridden dialogue blocks via `text-embedding-004` into `sentiment_calibrations` (`corrected_contexts`) upon Golden Record commit.

#### Scenario: Adjudicator Regenerates Risks and MoM After Group Reassignment
- **WHEN** an Adjudicator updates dialogue block group assignments or slider scores and clicks "Regenerate Risks & MoM"
- **THEN** the system invokes Gemini 2.5 Flash with the updated group context and refreshes the right-pane MoM summary, Top 5 Liked/Disliked words, and `DRAFT_PENDING_ADJUDICATION` risks

#### Scenario: Overridden Slider Blocks Embedded into Few-Shot Vector Store
- **WHEN** an Adjudicator adjusts the 0–100 sentiment slider on a block and clicks "Save Golden Record"
- **THEN** the system generates a 768-dim `text-embedding-004` vector for each overridden block and persists it to `sentiment_calibrations` for subsequent Few-Shot calibration

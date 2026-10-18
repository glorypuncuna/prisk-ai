## ADDED Requirements

### Requirement: Speaker-Blind Structured Rubric Scoring
The system SHALL invoke Vertex AI Gemini 2.5 Flash using structured outputs to score dialogue blocks across four 0–25 rubric dimensions (`emotional_valence`, `delivery_alignment`, `relationship_trust`, `momentum_commitment`) with speaker identity stripped from prompt payloads.

#### Scenario: Post-Meeting Baseline Inference
- **WHEN** post-meeting dialogue blocks are submitted to Gemini 2.5 Flash
- **THEN** the model returns a typed JSON payload with 0–100 Pulse Scores, auto-filled Group and Company suggestions, structured MoM, and draft risks

### Requirement: Dynamic Few-Shot Vector Retrieval and Zero-Shot Cold Start
The system SHALL retrieve top-5 semantically similar Adjudicator overrides from Firestore Native Vector Search (`corrected_contexts`) scoped to `project_id`, defaulting to pure Zero-Shot rubric inference when no overrides exist.

#### Scenario: Cold-Start Zero-Shot Inference
- **WHEN** a meeting belongs to a newly created project with zero stored `corrected_contexts` vectors
- **THEN** the system executes Gemini 2.5 Flash baseline inference with pure zero-shot rubric prompt instructions without error

#### Scenario: Few-Shot Calibration with Vector Nearest Neighbors
- **WHEN** historical Adjudicator overrides exist in `corrected_contexts` for the project
- **THEN** the system executes Firestore `find_nearest` vector search using 768-dim embeddings (`text-embedding-004`) and injects the top-5 overrides as few-shot exemplars

### Requirement: On-Demand Verbatim Substring Explainable AI
The system SHALL provide an on-demand endpoint `POST /api/v1/meetings/{id}/blocks/{id}/explain` that returns 3–5 exact verbatim substrings with signed weights, verified server-side against the original text.

#### Scenario: Validated Verbatim Highlight Verification
- **WHEN** Gemini returns rationale phrase attributions for a block
- **THEN** FastAPI verifies each phrase exists as an exact substring in `block.scrubbed_text` and calculates precise character start/end offsets before returning to the UI

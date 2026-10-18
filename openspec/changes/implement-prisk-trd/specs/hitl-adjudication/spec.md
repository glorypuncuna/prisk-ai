## ADDED Requirements

### Requirement: Dialogue Bubble Splitting
The system SHALL support dividing a single Dialogue Block into two sequential child blocks at a specified character cursor index without triggering a blocking LLM call.

#### Scenario: Adjudicator Splits Dialogue Bubble
- **WHEN** an Adjudicator triggers bubble split at character index `split_idx`
- **THEN** the system creates two child blocks inheriting the parent's rubric scores and group assignment, and logs `BUBBLE_SPLIT` to the immutable audit ledger

### Requirement: In-Session Ephemeral Speaker-to-Group Mapping
The system SHALL map transcript speaker IDs to canonical project groups strictly within active session memory, auto-updating unpinned blocks from the same speaker and stripping speaker IDs upon Golden Record commit.

#### Scenario: Batch Group Auto-Assignment
- **WHEN** an Adjudicator assigns speaker `ms_spk_02` to group "Client Legal"
- **THEN** all unpinned blocks in that meeting from `ms_spk_02` automatically update their group to "Client Legal" in session state

### Requirement: Deterministic Real-Time Score Rollup
The system SHALL calculate Group Pulse Scores as word-count-weighted averages and Overall Meeting Pulse Scores as arithmetic means across active groups with sub-50ms visual updates.

#### Scenario: Slider Adjustment Score Rollup
- **WHEN** an Adjudicator drags the 0–100 sentiment slider on a dialogue block
- **THEN** the frontend deterministically updates the Group Pulse Score and Overall Meeting Pulse Score in under 50ms and marks the block as human-overridden

### Requirement: Immutable Golden Record Commit
The system SHALL permanently strip ephemeral speaker mappings, embed overridden blocks into `corrected_contexts`, promote approved risks to `OPEN`, and lock the meeting record upon Golden Record commit.

#### Scenario: Golden Record Finalization
- **WHEN** an Adjudicator commits the Golden Record
- **THEN** the system permanently removes `ephemeral_speaker_map`, saves embeddings for overridden blocks, transitions status to `GOLDEN_RECORD`, and streams analytical rows to BigQuery

# Prisk AI

Prisk AI is a meeting pulse and stakeholder relationship analytics platform that transforms meeting transcripts into group-level health insights, explainable sentiment scores, and proactive project risk mitigations through human-in-the-loop adjudication.

## Language

### Organization & Identity

**Company**:
The client organization associated with a project or meeting, auto-populated from meeting context.
_Avoid_: Customer, Tenant, Workspace

**Project**:
A bounded delivery engagement under a Company within which meetings, canonical Group taxonomies, group pulse trends, and risks are tracked.
_Avoid_: Engagement, Account, Initiative

**Group**:
A canonical functional stakeholder unit defined at the Project level (e.g., "Client Legal", "Executive Sponsors", "Vendor Engineering") to which Dialogue Blocks and Pulse Scores are permanently attributed.
_Avoid_: Persona, Individual, Team, Department

**Group Personification**:
The modeling and longitudinal tracking of stakeholder sentiment, pulse scores, and risk trajectories at the collective functional archetype level (Group) rather than profiling individual human participants.
_Avoid_: Individual Persona, Behavioral Profile, Personal Profiling

**User Account**:
An authenticated system identity used by an operator (e.g., Manager, Adjudicator, External Stakeholder) to log into the Prisk AI application, subject to Role-Based Access Control (RBAC).
_Avoid_: Speaker Account, Participant, Session User

**Speaker Account**:
A participant identifier from the meeting transcript whose mapping to a Group exists only in ephemeral session state during a single meeting's adjudication and is never persisted as a cross-meeting mapping or passed to sentiment inference.
_Avoid_: User Account, User profile, Persona profile

### Meeting Capture & Adjudication

**Dialogue Block**:
A discrete, contiguous segment of PII-scrubbed transcribed speech representing a single speaker turn, which can be split or tagged with a Group during adjudication.
_Avoid_: Bubble, Utterance, Snippet, Message

**Bubble Split**:
The human-in-the-loop action of dividing a single Dialogue Block into two or more child blocks when multiple speakers or distinct topics were merged in the transcript.
_Avoid_: Text split, Utterance segmentation

**Adjudicator**:
An internal analyst who reviews post-meeting transcripts, maps Speaker Accounts to Groups for that session, performs Bubble Splits, inspects Rubric Attributions, calibrates Pulse Scores, and commits the Golden Record.
_Avoid_: Moderator, Reviewer, Annotator, Editor

**Golden Record**:
The immutable, human-adjudicated post-meeting record committed upon adjudication completion, containing Group-tagged Dialogue Blocks, finalized Pulse Scores, Minutes of Meeting, and approved Risk Register entries.
_Avoid_: Final transcript, Saved meeting, Master record

### Sentiment, Explainable AI & Risk

**Pulse Score**:
A quantitative sentiment and relationship health rating on a 0–100 scale (summed across four 0–25 rubric dimensions) assigned to a Dialogue Block, a Group within a meeting, or a meeting overall.
_Avoid_: Health score, Sentiment rating, Mood score, Vibe score

**Corrected Context**:
A stored few-shot training tuple consisting of a PII-scrubbed Dialogue Block, its vector embedding, the initial AI-generated Pulse Score, and the Adjudicator's manual slider override.
_Avoid_: Training sample, Override log, Feedback item

**Rubric Attribution**:
An on-demand structured explanation generated via strict rubric parameters (`emotional_valence`, `delivery_alignment`, `relationship_trust`, `momentum_commitment`) that identifies the top 3–5 verbatim substrings in a Dialogue Block and their signed weights driving a Pulse Score.
_Avoid_: Shapley value, Feature importance, Model rationale

**RiskSeverityIndex**:
A quantitative risk rating (`1–25`) calculated as `Impact (1–5) × Probability (1–5)` aligned with COSO and ISO 31000 frameworks across Financial, Operational, Compliance, and Relationship categories.
_Avoid_: Risk score, Priority level, Threat index

**Compliance Audit Package**:
A structured, exportable compliance artifact (in PDF, CSV, or JSON format) containing multi-framework control crosswalks, sanitized risk registers, mitigation lifecycle audits, and privacy attestations, cryptographically sealed with a SHA-256 hash and timestamped version ID.
_Avoid_: Audit report, Compliance dump, Export file

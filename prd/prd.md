# Product Requirements Document: Prisk AI

**Meeting Pulse & Persona Analytics**

## Executive Summary

**Problem Statement:** Traditional meeting documentation relies heavily on static text transcripts or subjective notes, capturing what was said while missing vital qualitative context—such as stakeholder health, conversational alignment, and underlying meeting pulse. However, existing tools fail to capture or analyze these nuanced dynamics over time, leaving project leaders with a significant gap in operational visibility into key relationships. Consequently, emerging risks like client friction, stakeholder churn, and scope creep go unnoticed until they escalate into project delays, budget overruns, or lost accounts. To bridge this gap and safeguard project outcomes, organizations urgently need a systematic, explainable AI-driven meeting analytics and adjudication layer that surfaces actionable stakeholder health insights and enables proactive risk mitigation.

**Value Proposition:** Prisk AI introduces an AI-driven layer to meeting documentation that captures, analyzes, and visualizes stakeholder pulse and relationship health in real-time and historically. By combining speech-to-text with human-in-the-loop adjudication and advanced predictive analytics, Prisk AI transforms meeting audio into a proactive risk-mitigation tool. It builds objective, data-backed personas and surfaces actionable stakeholder health insights—enabling project leaders and client managers to spot relationship friction, waning sentiment, and stakeholder churn risks long before they impact project timelines or client retention.

**Key Success Metrics (KPIs/OKRs):**

* **Adjudication Rate:** Percentage of meeting transcripts reviewed and adjusted by a human adjudicator.

* **Time-to-Resolve:** Average time spent by an adjudicator adjusting a sentiment score.

* **XAI Invocation Rate:** Frequency of adjudicators triggering the "Explain" function.

* **Model Alignment:** Reduction in false-positive negative sentiment alerts over successive meeting batches.

* **Adoption:** Percentage of meetings recorded using the tool.

* **Accuracy:** Percentage of annotations approved vs. corrected during the human-in-the-loop adjudication phase.

* **Engagement:** Weekly Active Users (WAU) accessing the Analytics dashboard.

## Stakeholders & User Personas

| Persona | Role | Needs & Pain Points | 
| ----- | ----- | ----- | 
| **The Stakeholder Relationship Lead** | Evaluates external stakeholder health, client relationships, and meeting alignment. | **Needs** to track meeting pulse and stakeholder health trends over time to identify relationship friction, negative sentiment, or client churn risks.   **Pain point:** Cannot remember the sentiment or relationship health of a key stakeholder from 3 months ago. | 
| **The Adjudicator / Analyst** | Reviews and categorizes transcripts for accuracy and persona building. | **Needs** a streamlined interface to assign speakers to text and verify AI pulse and stakeholder health scoring.   **Pain point:** Manual transcription and tagging is too slow. | 
| **The External Stakeholder** | Engages in the conversation as a key client or partner. | **Needs** assurance that their data is handled securely and their privacy is respected.   **Pain point:** Being unfairly judged by an AI without human oversight. | 

1. **MeetStream:** Converts audio to text in memory and discards the audio. Use transcript too from meetstream.ai.

2. **Cloud DLP (scrub_pii):** Automatically masks credit cards, SSNs, phone numbers, and addresses in 200ms (NFR-2.3).

3. **Cloud DLP to Vertex AI (Gemini 2.5 Flash):** Because the transcript is now legally safe and PII-free, you can immediately send it to Vertex AI to get the baseline Pulse Score (Story 3.1), auto-fill the Group and Company fields (FR-2.5), and save it to Firestore!

4. **Fast Human Adjudication (Story 1.2):** When the Adjudicator opens the UI, 90% of the work is already done. The PII is already masked (\[PHONE_NUMBER\]), the Group and Company are pre-filled by AI (FR-2.5), and the baseline Pulse Score is ready (Story 3.1). The Adjudicator only needs to verify the speaker tags, optionally click "Explain Rationale" (Story 3.2), or tweak the 0–100 sentiment slider (Story 3.3).

## System Architecture & Flow Breakdown

* **Meeting extraction** —> meetstream.ai

  * **Speech to text** —> transcription (stt or vertex)

  * **Bubble split** —> hitl

  * **Sentiment analysis live:**

    * Manual sentiment analysis slider (hitl) —> as training data for future meetings

    * Sentiment analysis (nlp)

  * **Explainable AI** —> xAI

  * **Group personification** —> manual mandatory group tagging based on account

    * *Crucial Constraint:* No saving account name.

    * *Crucial Constraint:* Saving only group name and scoring.

  * **Golden record storage** —> save meeting + analysis to history

  * **Minutes of Meeting (MoM)** —> The system shall generate structured Minutes of Meetings containing Date and Time, Location, Meeting Title, Agenda, Topics of Discussion, and Action Items.

## User Stories & Acceptance Criteria

### Epic 1: Note Taking & Adjudication

**Story 1.1: Live & Historical Meeting Record**
As a Manager, I want to view live, summarized, and historical meeting notes so that I have a complete record of the conversation.

* System displays a real-time transcript during the meeting.

* System generates an AI summary upon meeting completion.

* Users can search and access past meeting notes in a historical archive.

**Story 1.2: Human-in-the-Loop Annotation**
As an Adjudicator, I want to manually annotate the speech-to-text output so that I can accurately identify which person or group is speaking.

* System provides a "Human-in-the-Loop" interface where the transcript is broken into editable blocks.

* Adjudicators can select a block of text and tag it with a specific speaker/group from a dropdown menu.

* Changes made by the adjudicator instantly update the underlying data model for that meeting.

### Epic 2: Pulse & Health Insights

**Story 2.1: Sentiment Pulse Tracking**
As a Manager, I want to see ad-hoc and historical meeting pulse scores so that I can gauge the emotional trajectory and overall health of a specific person or group.

* System calculates a "Pulse Score" (e.g., 0-100 or Negative/Neutral/Positive) for each tagged speaker block.

* Dashboard displays a line chart mapping the Pulse Score over time (X-axis: Date, Y-axis: Pulse Score).

**Story 2.2: Meeting Analytics Drill-Down**
As a Manager, I want to view detailed health analytics for a specific meeting so that I can understand the drivers of the pulse score.

* Clicking a data point (Meeting) on the line chart opens a "Meeting Details" view.

* The details view displays: Top 5 Liked Words, Top 5 Disliked Words, Next Action Items, Risks, and Recommended Mitigations.

### Epic 3: Explainable Sentiment Analysis & Human-in-the-Loop Feedback

**Story 3.1: Core Sentiment Inference**
As an End User, I want the system to analyze meeting transcripts using Vertex AI so that I receive an automated baseline sentiment score (Positive/Neutral/Negative).

* System successfully passes transcript payloads to the Vertex AI API.

* System stores the returned sentiment score (e.g., 0 to 100) and confidence interval.

* UI displays the baseline sentiment badge next to the meeting summary.

**Story 3.2: Explainable AI (On-Demand)**
As a Human Adjudicator, I want to click an "Explain Rationale" button on a sentiment score so that I can see exactly which words or phrases drove the model's decision.

* XAI computation is not run by default as a cost-saving measure.

* Clicking the trigger sends a request to the Vertex Explainable AI endpoint.

* UI highlights the top 3-5 contributing words in the transcript snippet based on their attribution weights.

**Story 3.3: Interactive Sentiment Adjustment & Feedback Loop**
As a Human Adjudicator, I want to use a visual slider to adjust the sentiment score and save updates as corrected context so that I can correct false positives or negatives and refine future model predictions.

* UI features a slider mapped from 0 (Highly Negative) to 100 (Highly Positive) that dynamically updates the visual sentiment badge in real-time.

* Clicking "Save" logs original text, AI score, and new score to the database as "Corrected Context".

* The ingestion pipeline formats saved corrections into Few-Shot prompts for subsequent Vertex AI inference calls.

## Customer Journey & Screen Flow

1. **Dashboard & Home Screen:** Users (Managers and Relationship Leads) log in to review high-level stakeholder health trends, meeting pulse alerts, and historical summaries across projects.

2. **Active Meeting Capture:** Google Meet bots via meetstream.ai capture meeting transcripts for speech-to-text processing during active meetings.

3. **Post-Meeting Summary & Minutes Generation:** Generative AI automatically compiles structured Minutes of Meetings (MoM)—including agendas, discussion topics, action items, risks, and recommended mitigations—for post-meeting distribution and archive.

4. **Human-in-the-Loop Adjudication Interface:** Analysts and Adjudicators open transcript blocks to perform speaker diarization, annotate persona groups, split dialogue bubbles, and override auto-filled persona tags.

5. **Explainable Sentiment & Interactive Adjustment View:** Adjudicators click "Explain Rationale" to trigger asynchronous Vertex Explainable AI token attributions, and utilize the interactive 0 to 100 sentiment slider to override baseline scores and feed corrected context back into the Few-Shot model pipeline.

6. **Pulse & Health Analytics Dashboard:** Stakeholders select personas or groups to view line charts mapping date versus pulse score trajectory, enabling historical trend comparisons across calendar dates.

7. **Meeting Details & Risk Mitigation Drill-Down:** Clicking chart nodes opens detailed drill-down panels displaying Top Liked/Disliked keywords, action items, persona risk flags, and proposed AI mitigations for targeted follow-up.

## Artificial Intelligence Capabilities

This product relies heavily on AI to transform raw audio into actionable qualitative insights.

* **Speech-to-Text (ASR):** Converts live audio streams into text using 3rd party meetstream.ai. Must be robust enough to handle multiple accents and industry-specific terminology.

* **Natural Language Processing (NLP) - Pulse & Health Extraction:** Analyzes the transcribed text to assign emotional weight (positive, negative, neutral) and identify specific "Liked" and "Disliked" keywords.

* **Generative AI - Summarization & Mitigation:** Uses LLMs to generate the meeting summary, extract action items, and synthesize health data to propose "Risks & Recommended Mitigations."

* **Data Inputs & Context:** Cleaned, diarized meeting transcripts, historical text transcripts, manual mandatory group tagging based on account (without saving account name, preserving only group name and scoring), and a concatenated dynamic context of manual sentiment analysis slider (0 to 100) overrides used as training data for future meetings.

* **Vertex AI & Explainable AI (XAI) Integration:** Uses Vertex AI and NLP for post-meeting sentiment analysis payloads, transcription (Vertex), and xAI token attributions mapping transcript substrings to weight values.

* **Edge Cases & AI Risks:** Sarcasm or industry jargon may trigger false negatives or misinterpretations. This is mitigated by Few-Shot correction via human slider adjustments. Additionally, potential latency on XAI feature attributions is managed by executing calls strictly asynchronously upon user action.

## Data Privacy & GDPR Compliance

Given that this product processes biometric data (voice) and generates potentially sensitive behavioral profiles (personas and meeting health tracking), strict GDPR adherence is critical.

* **User Consent & Notice:** Before recording begins, all meeting participants must be presented with a clear, unambiguous consent prompt explaining that audio is being recorded for transcription and pulse/health analysis.

* **Data Minimization:** Audio files should be processed into text and immediately deleted, unless explicitly required for the Adjudication phase. If retained for adjudication, audio must be purged immediately after the transcript is validated.

* **Right to be Forgotten & Access:** Users (data subjects) must have the ability to request a copy of their generated "Persona" data and have their historical pulse scores and transcripts purged from the system upon request.

* **PII Protection:** The system must include an automated PII redaction layer (Cloud DLP) that scrubs sensitive information (e.g., credit card numbers, personal addresses, phone numbers) from the transcript before it is stored in the historical archive or analyzed for sentiment.

* **Enterprise Model Boundary & Right to Erasure:** Vertex AI Enterprise model usage ensures submitted data stays within defined Google Cloud boundaries and is not used to train foundational models. Cascading deletion support enables full purging of transcripts, summaries, and adjudicator logs upon participant consent revocation.

* **Role-Based Access Control (RBAC):** Analytics and historical data are restricted to authorized users (e.g., the Manager). Adjudicators only have access to the specific transcripts assigned to them.

## Functional Requirements (FRs)

### 1. Note Taking & Audio Capture

* **FR-1.1:** The system shall capture live speech-to-text transcription by utilizing Google Meet bots via meetstream.ai.

* **FR-1.2:** The system shall display incoming transcripts from meetstream.ai Google Meet bots in real-time on the Active Meeting Screen.

* **FR-1.3:** The system shall provide a searchable historical archive of all past meeting transcripts, summaries, and pulse/health metrics, filterable by date, participant, and project.

* **FR-1.4:** The system shall allow users to perform bubble splits via Human-in-the-Loop (HITL) interaction to separate dialogue blocks in recorded transcripts.

* **FR-1.5:** The system shall generate structured Minutes of Meetings containing Date and Time, Location, Meeting Title, Agenda, Topics of Discussion, and Action Items.

### 2. Adjudication (Human-in-the-Loop)

* **FR-2.1:** The system shall provide an interface that segments the meeting transcript into distinct, selectable dialogue blocks based on detected pauses or speaker changes.

* **FR-2.2:** The system shall support group personification via manual mandatory group tagging based on account, without saving the account name, and preserving only the group name and associated scoring.

* **FR-2.3:** The system shall allow Adjudicators to override or correct the AI-generated pulse score for a specific text block.

* **FR-2.4:** Golden Record Storage: The system shall save the complete meeting transcript along with its full analysis into history as the persistent Golden Record, updating downstream models immediately upon save.

* **FR-2.5:** The system shall automatically populate the "Group" and "Company" persona data fields based on context from the meeting summary, while explicitly excluding the "Name" field from auto-fill to require manual entry or leave it optional.

* **FR-2.6:** The system shall integrate Vertex Explainable AI (XAI) to asynchronously calculate and display token attributions for contributing sentiment words when an Adjudicator triggers the "Explain Rationale" action.

* **FR-2.7:** The system shall provide a manual sentiment analysis slider (0 to 100) allowing adjudicators to adjust scores and store the inputs as training data for future meeting analysis.

### 3. Meeting Pulse & Health Insights Processing

* **FR-3.1:** The system shall process each adjudicated dialogue block through an NLP model to assign a quantitative Pulse Score (e.g., 0 to 100).

* **FR-3.2:** The system shall identify and extract a minimum of the top 5 "Liked" (positive valence) and top 5 "Disliked" (negative valence) keywords per meeting for each tagged persona.

* **FR-3.3:** The system shall generate "Next Action Items," "Risks," and "Recommended Mitigations" based on the aggregated health and context of the transcript.

### 4. Pulse & Health Dashboards

* **FR-4.1:** The system shall render an interactive line chart on the Pulse & Health menu mapping Meeting Date (X-axis) against Pulse Score (Y-axis) for a selected Project, Persona, or Group, complete with dynamic date-range filtering (e.g., last 7 days, 30 days, quarter-to-date, or custom ranges).

* **FR-4.2:** The system shall support clickable nodes on the line chart; clicking a node must trigger a drill-down view showing that specific meeting's details.

* **FR-4.3:** The Meeting Details drill-down shall display: Meeting Title, Meeting Date, Meeting Summary, Top 5 Liked Words, Top 5 Disliked Words, Next Action Items, Risks, Recommended Mitigations, and Pulse & Health per Group and Overall.

* **FR-4.4:** The system shall allow users to set automated, threshold-based alerts (e.g., pulse score drop greater than 15 points between meetings or score falling below 40) that trigger real-time in-app and email notifications.

* **FR-4.5:** The system shall support exporting dashboard data and detailed health reports in standard formats including CSV, PDF, and PNG.

* **FR-4.6:** The system shall provide cross-project and cross-team comparative analytics, allowing managers to overlay pulse score trajectories from multiple projects on a single view.

* **FR-4.7:** The system shall feature customizable dashboard layouts, enabling users to add, remove, resize, and rearrange visual widgets (e.g., sentiment distribution, keyword clouds, action item trackers).

### 5. Multi-Channel Services

* **FR-5.1:** The system shall handle meeting extraction through meetstream.ai for live video conferencing platforms, utilizing transcription (Vertex) for speech-to-text processing.

* **\[Future Requirements\] FR-5.2:** The system shall provide extensible webhooks and API connectors to support integration with additional communication tools and custom organizational platforms.

### 6. Calendar & Historical Meeting Notes to Pulse Insight

* **FR-6.1:** The system shall have an in-app calendar to present a clear, consolidated view of past meetings alongside their associated notes and recording artifacts.

* **FR-6.2:** The system shall track and visualize historical meeting pulse trends over time via the Prisk AI in-app calendar, enabling date-to-date comparative analytics for individual participants, personas, and teams.

### 7. Risk & Mitigation Module

* **FR-7.1 (Automated Risk Discovery & Pulse Triggering):** The system shall continuously monitor meeting transcripts, sentiment trajectories, and pulse score drops (e.g., >15 point drop or score <40) to automatically identify, flag, and populate emerging risks into a centralized Risk Register with pre-populated contextual metadata from meeting summaries.

* **FR-7.1a (Centralized Risk Register Data Architecture):** Building upon FR-7.1, the system shall maintain a modular Centralized Risk Register schema that automatically maps discovered risks to structured metadata fields including Risk ID, Title, Contextual Description, Status (Open, Mitigated, Closed, Escalated), Category (Financial, Operational, Compliance, Relationship), Source Meeting ID, and Associated Persona/Group IDs.

* **FR-7.1b (Human-in-the-Loop Risk Register Editing & Override):** Authorized users (such as Program Managers and Risk Owners) shall be able to manually edit, update, override, or reclassify risk register entries—including modifying severity scores, updating mitigation status, reassigning risk owners, and appending qualitative commentary—with all manual overrides logged in immutable audit trails.

* **FR-7.2 (Enterprise Framework Scoring & Severity Index):** The system shall support alignment with standard enterprise risk frameworks (e.g., COSO, ISO 31000) by calculating quantitative Impact (1-5) and Probability (1-5) scores to establish an overall Risk Severity Index, categorizing risks across financial, operational, compliance, and relationship dimensions.

* **FR-7.3 (Ownership Assignment & Automated Escalation Paths):** The system shall support assigning specific Risk Owners and automatically trigger multi-level escalation workflows (including real-time in-app, email, and executive dashboard alerts) whenever high-severity risks exceed configurable organizational threshold criteria. The system shall provide comprehensive Human-in-the-Loop (HITL) controls enabling authorized users to manually assign and reassign Risk Owners, configure custom escalation paths, enable or disable automated escalation rules at both the individual risk and project levels, and establish time-based escalation triggers (including automated reminders and escalation alerts at 24-hour, 48-hour, and 72-hour intervals for unmitigated or high-severity risks).

* **FR-7.4 (Cross-Project Risk Aggregation & Portfolio Analytics):** The system shall aggregate risk data across multiple projects, teams, and accounts into portfolio-level risk heatmaps and trend dashboards with dynamic date-range filtering (e.g., last 7 days, 30 days, quarter-to-date, or custom ranges). Portfolio risk chart nodes shall be clickable to open drill-down views showing specific project risk registers, meeting sources, and historical mitigation timelines. The system shall support threshold-based automated alerts for portfolio-level risk severity spikes or systemic risk increases (triggering in-app and email notifications), enable exporting portfolio risk reports in CSV, PDF, and PNG formats, provide multi-project comparative risk analytics with trajectory overlays on a single view, and offer customizable dashboard layouts with reorderable, resizable risk widgets.

* **FR-7.5 (Stakeholder Risk Visibility Tiers & Role-Based Governance):** The system shall enforce granular Role-Based Access Control (RBAC) and privacy tiers, ensuring sensitive risk scores, internal mitigation strategies, and raw sentiment insights are appropriately restricted or sanitized based on user roles (e.g., Executive, Account Lead, External Stakeholder).

* **FR-7.6 (Mitigation Lifecycle Tracking & Compliance Audit Linkage):** The system shall track the full lifecycle of mitigation action plans, scheduling recurring review cadences and maintaining immutable, time-stamped audit trails linked directly to source meeting records, adjudication logs, and post-meeting summaries for enterprise compliance reporting.

## Non-Functional Requirements (NFRs)

### 1. Performance & Latency

* **NFR-1.1 (Real-time Processing):** The latency between receiving transcripts from meetstream.ai Google Meet bots and displaying them on the user interface must not exceed 2 seconds.

* **NFR-1.2 (Dashboard Load Time):** The Analytics line chart and historical data dashboard must render within 3 seconds for datasets encompassing up to 1,000 past meetings.

* **NFR-1.3 (AI Processing Time):** Post-meeting summarization and initial pulse extraction must be completed within 5 minutes of the meeting ending.

### 2. Security & GDPR Compliance

* **NFR-2.1 (Data Encryption):** All transcripts, summaries, and persona data must be encrypted in transit using TLS 1.2+ and at rest using AES-256 encryption.

* **NFR-2.2 (Data Retention & Purging):** Raw audio files must be automatically and permanently deleted from the servers within 24 hours after the Adjudication phase is completed.

* **NFR-2.3 (PII Redaction):** The system must utilize an automated PII-scrubbing algorithm (Cloud DLP) to mask sensitive data (e.g., SSNs, credit card numbers, personal phone numbers, addresses) from the transcript in memory before it is written to the database.

* **NFR-2.4 (Audit Logging):** The system must maintain an immutable audit log of all manual changes made during the Adjudication phase, including the timestamp and the ID of the user who made the change.

### 3. Accuracy & Reliability

* **NFR-3.1 (Transcription Accuracy):** The Speech-to-Text engine must maintain a minimum Word Error Rate (WER) of less than 12% in standard operating environments (clear audio, standard English).

* **NFR-3.2 (System Uptime):** The system shall maintain an uptime of 99.9% during standard business hours, ensuring that live meeting capture is highly available.

### 4. Usability & Accessibility

* **NFR-4.1 (Accessibility):** The Adjudication interface and Analytics dashboards must comply with WCAG 2.1 AA standards to ensure accessibility for users with visual or motor impairments (e.g., keyboard navigation support, high contrast modes).

## Trustworthy AI Framework & Requirements

To ensure end-user confidence and safe adoption, Prisk AI operates strictly under a multi-pillar Trustworthy AI Framework, directly addressing the ethical, explainable, responsible, transparent, and governed design of all speech and persona analytics features.

1. **Ethical AI (Fairness & Bias Mitigation):** Speech-to-text (ASR) models and NLP sentiment classifiers are regularly benchmarked across diverse accents, dialects, and demographics to prevent systemic scoring bias against specific speaker groups. Human adjudication acts as an essential ethical safety net against false sentiment attributions.

2. **Explainable AI (Interpretability & Feature Attribution):** The system must provide direct provenance for all generated Pulse Scores and health flags. Users can click any sentiment score or persona insight to view the underlying dialogue blocks, keyword associations (e.g., top liked/disliked terms), and confidence thresholds that produced the rating.

3. **Responsible AI (Safety, Privacy & Human Oversight):** Automated features are constrained to advisory roles. Automated outputs (e.g., performance risks, recommended mitigations) require human approval before being logged into official records, preventing automated adverse decisions or unreviewed punitive conclusions about participants.

4. **Transparent AI (Clear Notice & AI Attribution):** Clear visual indicators signal whenever AI model output is active vs. human-validated text. Meeting participants are explicitly notified when recording, sentiment evaluation, or persona profiling takes place.

5. **Governed AI (Compliance, Auditability & Lifecycle Controls):** All model versioning, prompt configurations, and training dataset metadata are logged in an AI governance ledger. Complete audit trails capture human overrides during the adjudication process to enable recurring model alignment checks and data compliance reviews.
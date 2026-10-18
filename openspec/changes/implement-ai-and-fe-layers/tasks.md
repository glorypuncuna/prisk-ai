## 1. Phase 1 AI & Frontend: Project Governance, Canonical Group Taxonomy & Admin Intelligence

- [x] 1.1 **[AI]** Implement `POST /api/v1/projects/{project_id}/ai-suggest-groups` using Vertex AI Gemini 2.5 Flash to recommend domain-specific `canonical_groups`, risk categories, and pulse drop alert thresholds from a project description
- [x] 1.2 **[AI]** Implement `GET /api/v1/admin/ai-governance-summary` using Gemini 2.5 Flash to synthesize an executive RBAC governance digest (quarantined user backlog, recent role elevations, and project coverage)
- [x] 1.3 **[Frontend]** Build React Project & Canonical Group Governance View (`frontend/src/pages/ProjectsPage.tsx`) allowing Managers/Admins to create projects, click "Suggest Canonical Groups with AI", edit group taxonomy chips, configure pulse/SLA thresholds, and manage invitations
- [x] 1.4 **[Frontend]** Add AI Governance Digest summary panel to `AdminUsersPage.tsx` and wire top-level role-based navigation tabs in `App.tsx`

## 2. Phase 2 AI & Frontend: Vector Calibration Diagnostics & TypeScript Client State Layer

- [x] 2.1 **[AI]** Implement `GET /api/v1/projects/{project_id}/vector-diagnostics` to inspect `text-embedding-004` (768-dim) calibration exemplar counts, group coverage, and nearest-neighbor cosine similarity readiness
- [x] 2.2 **[Frontend]** Create typed TypeScript domain interfaces (`frontend/src/types/domain.ts`) mirroring all 9 Firestore collections (`users`, `projects`, `project_invitations`, `meetings`, `dialogue_blocks`, `sentiment_calibrations`, `risk_register`, `compliance_packages`, `audit_ledger`)
- [x] 2.3 **[Frontend]** Implement Zustand workspace state store (`frontend/src/store/useWorkspaceStore.ts`) and typed API client modules (`meetingsApi.ts`, `adjudicationApi.ts`, `risksApi.ts`, `complianceApi.ts`)

## 3. Phase 3 AI & Frontend: Post-Ingestion AI Pipeline Handoff, Meeting Capture & Historical Calendar UI

- [x] 3.1 **[AI]** Wire automatic post-ingestion AI handoff inside `POST /webhooks/meetstream/completed` to trigger `SentimentService.run_post_meeting_scoring_pipeline` (Gemini 2.5 Flash baseline rubric scoring, MoM synthesis, and draft risk extraction) immediately after verified Firestore save and upstream transcript deletion
- [x] 3.2 **[Frontend]** Build React Meeting Capture & Lifecycle Status View (`frontend/src/pages/MeetingCapturePage.tsx`, `TRD §10.2`) with Google Meet URL bot dispatch form, Adjudicator selector, live lifecycle status cards (`CAPTURING` $\rightarrow$ `PROCESSING_POST_MEETING` $\rightarrow$ `PENDING_ADJUDICATION` $\rightarrow$ `GOLDEN_RECORD`), DLP redaction summary badges, and manual "Run AI Analysis" action
- [x] 3.3 **[Frontend]** Build React In-App Historical Calendar & Archive View (`frontend/src/pages/CalendarArchivePage.tsx`, `TRD §10.5`, `FR-6.1`, `FR-6.2`) rendering monthly/weekly meetings color-coded by Pulse Score badge with date-to-date longitudinal Group Pulse comparison

## 4. Phase 4 AI & Frontend: Pulse & Health Analytics Dashboard, Drill-Down Drawer & Inline XAI Highlighter

- [x] 4.1 **[AI]** Implement `GET /api/v1/analytics/pulse-trends` with Gemini 2.5 Flash longitudinal trajectory synthesis explaining key drivers of pulse shifts across `7D`, `30D`, `QTD`, and `Custom` windows
- [x] 4.2 **[Frontend]** Build React Pulse & Health Analytics Dashboard (`frontend/src/pages/PulseDashboardPage.tsx`, `TRD §10.4`) with customizable widget grid (`react-grid-layout`), Recharts multi-series Pulse Trajectory Line Chart, multi-project overlay toggle, and CSV/PDF/PNG export controls
- [x] 4.3 **[Frontend]** Build React Meeting Details Drill-Down Drawer (`frontend/src/components/MeetingDetailsDrawer.tsx`, `TRD §10.4`) displaying AI MoM summary, Top 5 Liked/Disliked Words per Group, Next Action Items, Draft/Open Risks, and AI Recommended Mitigations when a chart node is clicked
- [x] 4.4 **[Frontend]** Build React Inline On-Demand XAI Rationale Drawer & Verbatim Substring Highlighter (`frontend/src/components/XaiRationaleDrawer.tsx`, `TRD §10.3`) rendering the 4-bar Rubric Breakdown (`Emotional Valence`, `Delivery Alignment`, `Relationship Trust`, `Momentum Commitment`) and highlighting verified `[start_char, end_char]` phrases color-coded by signed attribution weight

## 5. Phase 5 AI & Frontend: Active-Learning Adjudication Regeneration & Interactive Split-Pane Workspace

- [x] 5.1 **[AI]** Implement `POST /api/v1/meetings/{meeting_id}/regenerate-insights` (`TRD §6.3`, `§9.2`) invoking Gemini 2.5 Flash with Adjudicator-updated `Group` tags and adjusted `Pulse Scores` to re-synthesize MoM, Top 5 Liked/Disliked words per Group, and `DRAFT_PENDING_ADJUDICATION` risks
- [x] 5.2 **[AI]** Ensure `POST /api/v1/meetings/{meeting_id}/commit-golden-record` embeds all human-overridden dialogue blocks (`is_human_overridden == True`) into 768-dim `text-embedding-004` vectors stored in `sentiment_calibrations` (`corrected_contexts`) for subsequent Few-Shot inference
- [x] 5.3 **[Frontend]** Build interactive controls in React Split-Pane HITL Adjudication Workspace (`frontend/src/pages/AdjudicationWorkspacePage.tsx`, `TRD §10.3`): cursor-based Bubble Split tool (`Alt+S`), ephemeral speaker-to-group dropdown with session-wide auto-apply badge, `<50ms` optimistic client-side word-count-weighted Group & Meeting Pulse rollup, Right-Pane Draft Risk approval checklist, "Regenerate Risks & MoM" button, and "Save Golden Record" modal

## 6. Phase 6 AI & Frontend: Automated AI Risk Discovery, Proactive Mitigation Synthesis & Risk Register UI

- [x] 6.1 **[AI]** Implement Automated AI Risk Discovery & Proactive Mitigation Synthesizer (`POST /api/v1/risks/ai-discover` and `POST /api/v1/risks/{risk_id}/ai-mitigation`) using Gemini 2.5 Flash to detect emerging risks from pulse drops (`>15` pts or `<40`), score COSO/ISO 31000 Impact (1–5) & Probability (1–5), and propose concrete mitigation strategies and executive escalation briefs
- [x] 6.2 **[Frontend]** Enhance React 5x5 Portfolio Risk Heatmap & Risk Register View (`frontend/src/pages/RiskRegisterPage.tsx`, `TRD §10.6`) with Systemic Risk Spike warning banner (`FR-7.4c`), AI Mitigation Strategy recommendation & one-click apply cards, inline Impact/Probability/Status/Owner editing, 24h/48h/72h SLA countdown badges, and Immutable Audit Trail drawer

## 7. Phase 7 AI & Frontend: Privacy-Preserving AI Compliance Attestation & WORM Compliance Console UI

- [x] 7.1 **[AI]** Implement AI Privacy-Preserving Compliance Narrative Synthesizer inside `SanitizationService` / Compliance Exporter using Gemini 2.5 Flash on sanitized aggregate risk metadata to generate framework-specific executive treatment summaries (ISO 31000, COSO, SOC 2, HIPAA, GDPR) with deterministic verification that zero verbatim participant quotes appear in the output
- [x] 7.2 **[Frontend]** Build React Compliance Audit Package Export & Verification Console (`frontend/src/pages/ComplianceConsolePage.tsx`, `TRD §10.6`) with multi-framework selector checkboxes (`ISO_31000`, `COSO`, `SOC_2`, `HIPAA`, `GDPR`), format toggle (`PDF`, `CSV`, `JSON`), WORM package history table with SHA-256 cryptographic signature verifier badge, signed GCS download drawer, and GDPR Article 17 Right-to-Erasure Cascade Purge modal

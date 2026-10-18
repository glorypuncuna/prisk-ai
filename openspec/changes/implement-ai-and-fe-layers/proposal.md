## Why

The initial `implement-prisk-trd` change focused heavily on backend API endpoints and database infrastructure (35 of 39 tasks were backend-centric, and AI tasks were concentrated only in Phase 4). However, `prd.md`, `risk_mitigation_prd.md`, and `trd.md` (Section 10) require an AI capability (Vertex AI `gemini-2.5-flash`, `text-embedding-004`, and Cloud DLP) and a rich React Frontend experience across **every single phase** (Phases 1 through 7). Creating this separate change (`implement-ai-and-fe-layers`) keeps the in-progress `implement-prisk-trd` tasks completely untouched while explicitly tracking the AI and Frontend (FE) tasks for every phase.

## What Changes

- **Phase 1 (Identity, Projects & Super Admin Governance — AI + FE):**
  - **[AI]:** Gemini 2.5 Flash Canonical Group Taxonomy & Alert Threshold Recommender (`POST /api/v1/projects/{project_id}/ai-suggest-groups`) + Super Admin Access Governance Digest (`GET /api/v1/admin/ai-governance-summary`).
  - **[Frontend]:** React Project & Canonical Group Governance View (`ProjectsPage.tsx`) allowing Managers/Admins to create projects, apply AI-suggested canonical stakeholder groups, configure pulse alert thresholds, and manage invitations.
- **Phase 2 (Data Architecture, Vector Store & Frontend State Layer — AI + FE):**
  - **[AI]:** Vertex AI `text-embedding-004` (768-dim) batch & real-time embedding health verification and similarity calibration diagnostics (`GET /api/v1/projects/{project_id}/vector-diagnostics`).
  - **[Frontend]:** Typed TypeScript domain schemas (`frontend/src/types/`), Zustand workspace store (`useWorkspaceStore.ts`), and TanStack Query API hooks (`meetingsApi.ts`, `adjudicationApi.ts`, `risksApi.ts`, `complianceApi.ts`) mirroring all 9 Firestore collections and vector metadata.
- **Phase 3 (Meeting Ingestion, ASR & DLP Pipeline — AI + FE):**
  - **[AI]:** Automatic post-ingestion AI handoff inside `POST /webhooks/meetstream/completed` so that immediately after Cloud DLP batch scrubbing, Firestore save, and upstream `meetstream.ai` deletion, `SentimentService.run_post_meeting_scoring_pipeline` (Gemini 2.5 Flash baseline rubric scoring, MoM synthesis, and draft risk extraction) executes automatically.
  - **[Frontend]:** React Meeting Capture & Lifecycle Status View (`MeetingCapturePage.tsx`, `TRD §10.2`) with Google Meet bot dispatch form, live lifecycle status cards (`CAPTURING` $\rightarrow$ `PROCESSING_POST_MEETING` $\rightarrow$ `PENDING_ADJUDICATION` $\rightarrow$ `GOLDEN_RECORD`), DLP redaction badge preview, and In-App Historical Calendar (`CalendarArchivePage.tsx`, `TRD §10.5`, `FR-6.1`, `FR-6.2`).
- **Phase 4 (AI Sentiment Rubric, Few-Shot Vector Loop & On-Demand XAI — AI + FE):**
  - **[AI]:** Gemini 2.5 Flash Longitudinal Trend Narrative & Pulse Drop Explainer (`GET /api/v1/analytics/pulse-trends` AI trajectory commentary) alongside the 4-dimension speaker-blind rubric and on-demand verbatim XAI span verifier.
  - **[Frontend]:** React Pulse & Health Analytics Dashboard (`PulseDashboardPage.tsx`, `TRD §10.4`) with `react-grid-layout` customizable widgets, Recharts multi-series Pulse Trajectory Line Chart, clickable Meeting Details Drill-Down Drawer (`MeetingDetailsDrawer.tsx` showing MoM, Top 5 Liked/Disliked Words per Group, Action Items, and Mitigations), and Inline XAI Rationale Drawer (`XaiRationaleDrawer.tsx` rendering 4-bar Rubric Breakdown and color-coded verbatim phrase highlights).
- **Phase 5 (HITL Adjudication Workspace & Active Learning Loop — AI + FE):**
  - **[AI]:** Active-Learning Few-Shot Calibration & Re-Synthesis Loop: `POST /api/v1/meetings/{id}/regenerate-insights` invoking Gemini 2.5 Flash with Adjudicator-updated group tags and pulse scores to refresh MoM, group keywords, and draft risks, plus embedding human-overridden slider blocks via `text-embedding-004` into `sentiment_calibrations` (`corrected_contexts`) upon Golden Record commit.
  - **[Frontend]:** Complete interactive controls in React Split-Pane HITL Adjudication Workspace (`AdjudicationWorkspacePage.tsx`, `TRD §10.3`): cursor-based Bubble Split tool (`Alt+S`), ephemeral session speaker-to-group dropdown with auto-apply badge, `<50ms` optimistic 0–100 slider rollup, Right-Pane Draft Risk approval checklist, "Regenerate Risks & MoM" trigger, and "Save Golden Record" confirmation modal.
- **Phase 6 (Enterprise Risk Register & Escalation SLAs — AI + FE):**
  - **[AI]:** Automated AI Risk Discovery & Proactive Mitigation Engine (`FR-7.1a`, `FR-7.2a`) using Gemini 2.5 Flash to flag emerging risks on pulse drops (`>15` points or `<40`), classify COSO/ISO 31000 Impact (1–5) & Probability (1–5), synthesize actionable mitigation strategies, and generate executive SLA escalation digests.
  - **[Frontend]:** React Portfolio Risk Dashboard & Systemic Risk Spike Warning Banner (`RiskRegisterPage.tsx`, `TRD §10.6`), interactive 5x5 heatmap drill-downs, inline Risk Register editing, AI mitigation strategy cards, 24h/48h/72h SLA countdown badges, and Immutable Audit Trail drawer.
- **Phase 7 (Multi-Framework Compliance Reporting & WORM Storage — AI + FE):**
  - **[AI]:** AI Privacy-Preserving Compliance Narrative Synthesizer & Zero-Quote Guardrail (`gemini-2.5-flash` synthesizing sanitized executive risk treatment attestations across ISO 31000, COSO, SOC 2, HIPAA, and GDPR while deterministically verifying zero verbatim quotes and zero unmasked PII).
  - **[Frontend]:** React Compliance Audit Package Export & Verification Console (`ComplianceConsolePage.tsx`, `TRD §10.6`) with multi-framework selector checkboxes, PDF/CSV/JSON format toggle, WORM package history table with SHA-256 checksum verifier badge, signed GCS download drawer, and GDPR Article 17 Right-to-Erasure Purge UI modal.

## Capabilities

### New Capabilities
- `ai-and-fe-project-governance`: AI canonical group taxonomy recommender, Super Admin AI governance digest, and React Project & Canonical Group Setup UI.
- `ai-and-fe-data-state-layer`: Vertex AI `text-embedding-004` vector calibration diagnostics and Frontend TypeScript domain models, Zustand store, and TanStack Query API layer.
- `ai-and-fe-meeting-capture-calendar`: Automatic post-webhook Gemini scoring trigger, React Meeting Capture & Lifecycle Status UI, and In-App Historical Calendar.
- `ai-and-fe-pulse-dashboard-xai`: AI longitudinal pulse trajectory commentary, React Pulse & Health Analytics Dashboard (`react-grid-layout` + Recharts), Meeting Details Drill-Down Drawer, and Inline XAI Verbatim Highlighter UI.
- `ai-and-fe-hitl-active-learning`: Gemini `regenerate-insights` active-learning loop, `text-embedding-004` override calibration persistence, and React Split-Pane Adjudication interactive tools.
- `ai-and-fe-risk-intelligence`: Gemini automated pulse-drop risk discovery & mitigation synthesis, Systemic Risk Spike alert banner, and React Risk Register AI mitigation & SLA UI.
- `ai-and-fe-compliance-console`: Gemini privacy-preserving compliance attestation synthesizer (zero verbatim quotes) and React Compliance Export, SHA-256 Verification & GDPR Purge Console.

### Modified Capabilities
None (keeps `implement-prisk-trd` capabilities untouched).

## Impact

- **AI / ML:** Extends `SentimentService` and adds dedicated AI methods using Vertex AI `gemini-2.5-flash` (Structured Outputs) and `text-embedding-004` across all 7 platform modules.
- **Frontend:** Adds comprehensive React 18 + TypeScript + Tailwind CSS pages, drawers, charts (Recharts, `react-grid-layout`), and unified navigation shell in `frontend/src/`.
- **Backend:** Adds supporting AI & analytics endpoints (`/ai-suggest-groups`, `/regenerate-insights`, `/pulse-trends`, `/portfolio-risks`) without breaking existing `implement-prisk-trd` tasks.

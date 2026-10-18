## Context

While `implement-prisk-trd` tracks the core backend infrastructure and initial foundational tasks (39 tasks, with 25 already completed), the platform's end-to-end user experience and AI intelligence require explicit **AI** and **Frontend (React)** deliverables across every single architectural phase (Phases 1 through 7). By isolating these into `implement-ai-and-fe-layers`, development on `implement-prisk-trd` continues without any renumbering or disruption.

## Goals / Non-Goals

**Goals:**
- Ensure **every phase (1–7)** has an explicit **AI capability** (powered by Vertex AI `gemini-2.5-flash`, `text-embedding-004`, and Cloud DLP with deterministic local fallbacks for offline testing).
- Ensure **every phase (1–7)** has a complete, interactive **React 18 + TypeScript + Tailwind CSS Frontend screen/workflow** matching `TRD §10`.
- Provide a unified React application navigation shell (`App.tsx`) connecting all 7 workspace views according to the user's RBAC role (`ADMIN`, `EXECUTIVE`, `MANAGER`, `ADJUDICATOR`, `EXTERNAL_STAKEHOLDER`).

**Non-Goals:**
- Modifying or renumbering the existing 39 tasks in `openspec/changes/implement-prisk-trd/tasks.md`.
- Storing raw meeting audio or profiling individual speakers across meetings (strictly prohibited by `ADR-0001` and `ADR-0002`).

## Decisions

### Decision 1: Phase-by-Phase AI + Frontend Vertical Alignment
Every phase in `implement-prisk-trd` is paired with a corresponding AI + Frontend section in `implement-ai-and-fe-layers`:

| Phase | AI Layer (`gemini-2.5-flash` / `text-embedding-004` / DLP) | Frontend Layer (React 18 + TypeScript + Tailwind) |
| :--- | :--- | :--- |
| **1. Identity, RBAC & Projects** | AI Canonical Group Taxonomy & Alert Threshold Recommender (`POST /api/v1/projects/{id}/ai-suggest-groups`) + Super Admin Access Governance Digest | `ProjectsPage.tsx` (Project creation, AI group taxonomy chips, pulse threshold sliders, invitation manager) + AI Digest card on `AdminUsersPage.tsx` |
| **2. Data & Vector Store** | `text-embedding-004` (768-dim) vector calibration diagnostics & nearest-neighbor similarity inspector | `frontend/src/types/` (9 collection schemas), `useWorkspaceStore.ts` (Zustand), and typed API clients (`meetingsApi.ts`, `adjudicationApi.ts`, `risksApi.ts`, `complianceApi.ts`) |
| **3. Ingestion & DLP** | Automatic webhook handoff from Cloud DLP batch scrub + upstream deletion into `SentimentService.run_post_meeting_scoring_pipeline` | `MeetingCapturePage.tsx` (MeetStream bot dispatch, lifecycle status cards, DLP redaction badges, manual Sync/Analyze trigger) + `CalendarArchivePage.tsx` (Monthly/Weekly pulse-colored calendar & longitudinal comparison) |
| **4. Sentiment Rubric & XAI** | Speaker-blind 4D rubric scoring, Few-Shot vector calibration, AI Pulse Trajectory narrative, and On-Demand XAI verbatim substring offset verifier | `PulseDashboardPage.tsx` (`react-grid-layout` widgets + Recharts multi-series line chart), `MeetingDetailsDrawer.tsx` (MoM, Top 5 Liked/Disliked words, Action Items, Mitigations), and `XaiRationaleDrawer.tsx` (4-bar rubric breakdown + verbatim span highlighter) |
| **5. HITL Adjudication** | `POST /api/v1/meetings/{id}/regenerate-insights` (Gemini re-synthesis of MoM, keywords, and draft risks from Adjudicator edits) + active-learning `text-embedding-004` embedding of slider overrides on Golden Record commit | `AdjudicationWorkspacePage.tsx` interactive split-pane controls: cursor Bubble Split (`Alt+S`), session speaker-to-group dropdown with auto-apply badge, `<50ms` optimistic slider rollup, "Regenerate Risks & MoM" button, and "Save Golden Record" modal |
| **6. Risk Register & SLAs** | Gemini Automated Risk Discovery on pulse drops (`>15` pts or `<40`), COSO/ISO 31000 Impact/Probability classification, and AI Mitigation Strategy & SLA Escalation Brief generator | `RiskRegisterPage.tsx` with Systemic Risk Spike banner, interactive 5x5 Heatmap drill-downs, inline Impact/Probability/Status editor, one-click AI Mitigation accept/edit card, 24h/48h/72h SLA badges, and Immutable Audit Trail drawer |
| **7. Compliance & WORM** | Gemini Privacy-Preserving Compliance Narrative Synthesizer & deterministic Zero-Verbatim-Quote verifier across ISO 31000, COSO, SOC 2, HIPAA, and GDPR | `ComplianceConsolePage.tsx` with multi-framework selector checkboxes, PDF/CSV/JSON format toggle, WORM package table with SHA-256 verification badge, signed download drawer, and GDPR Article 17 Right-to-Erasure Purge modal |

### Decision 2: Dual-Mode AI Execution (Live Vertex AI + Deterministic Offline Fallback)
- **Choice:** Every AI service method invokes `google-genai` (`gemini-2.5-flash` with `response_schema` Structured Outputs and `text-embedding-004` with 768 dimensions) when GCP credentials/API keys are configured, and gracefully falls back to deterministic, schema-validated local inference when running in offline test/dev mode (`use_in_memory_firestore = True`).
- **Rationale:** Guarantees 100% end-to-end functionality in both live GCP deployments and local automated test suites without flaky network dependencies.

## Risks / Trade-offs

- **[Risk: LLM Hallucination on XAI Quotes]** → Mitigated via deterministic server-side `verify_and_locate_substrings` offset check so the React UI only highlights verified character ranges `[start_char, end_char]`.
- **[Risk: Compliance Package Privacy Leakage]** → Mitigated by running AI compliance narrative synthesis strictly on sanitized aggregate metadata and enforcing a deterministic regex/substring check that rejects any verbatim dialogue quote before SHA-256 WORM sealing.

## ADDED Requirements

### Requirement: Vertex AI Embedding Calibration Diagnostics
The system SHALL provide `GET /api/v1/projects/{project_id}/vector-diagnostics` reporting `text-embedding-004` (768-dim) calibration exemplar counts, group coverage, and Few-Shot vs. Zero-Shot readiness per project.

#### Scenario: Inspecting Project Vector Calibration Status
- **WHEN** the frontend queries vector diagnostics for a project
- **THEN** the system returns total 768-dim calibration exemplars, covered canonical groups, and active inference mode (`FEW_SHOT` or `ZERO_SHOT`)

### Requirement: Frontend TypeScript Domain Schemas and Client Query State Layer
The system SHALL define typed TypeScript domain interfaces (`frontend/src/types/domain.ts`), a Zustand session/workspace store (`useWorkspaceStore.ts`), and typed API clients (`meetingsApi.ts`, `adjudicationApi.ts`, `risksApi.ts`, `complianceApi.ts`) mirroring all 9 Firestore collections.

#### Scenario: Frontend Type-Safe Query Synchronization
- **WHEN** the React client fetches meeting, adjudication, risk, or compliance records from FastAPI
- **THEN** responses are parsed into typed TypeScript models and synchronized with the active Zustand workspace store

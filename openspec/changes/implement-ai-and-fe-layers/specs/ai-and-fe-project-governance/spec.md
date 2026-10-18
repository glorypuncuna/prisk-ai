## ADDED Requirements

### Requirement: AI-Assisted Project Onboarding and Canonical Group Taxonomy Recommendation
The system SHALL provide an AI recommendation endpoint (`POST /api/v1/projects/{project_id}/ai-suggest-groups`) powered by Vertex AI Gemini 2.5 Flash and a React Project Governance UI (`ProjectsPage.tsx`) that suggests domain-specific canonical stakeholder groups and pulse alert thresholds from a project description.

#### Scenario: Manager Applies AI-Suggested Canonical Groups in Project UI
- **WHEN** a Manager enters a project description in `ProjectsPage.tsx` and clicks "Suggest Canonical Groups with AI"
- **THEN** the system invokes Gemini 2.5 Flash to return suggested canonical group names and pulse thresholds, allowing the Manager to review, edit, and save them to `projects/{project_id}`

### Requirement: Super Admin AI Governance Digest
The system SHALL provide `GET /api/v1/admin/ai-governance-summary` and an AI Governance Digest panel on `AdminUsersPage.tsx` summarizing quarantined user backlog, role elevations, and project access coverage.

#### Scenario: Admin Views AI Governance Digest
- **WHEN** an `ADMIN` opens the Super Admin Console (`/admin/users`)
- **THEN** the system displays an AI-synthesized summary of RBAC distribution, quarantined accounts pending invitation, and recent administrative actions

## ADDED Requirements

### Requirement: AI Risk Discovery, Proactive Mitigation Synthesis, and React Portfolio Heatmap UI
The system SHALL use Vertex AI Gemini 2.5 Flash to automatically discover emerging risks from transcript friction and pulse drops (`>15` points or `<40`), classify COSO/ISO 31000 Impact/Probability, synthesize actionable mitigation strategies, and render them in a React 5x5 Portfolio Risk Heatmap and Risk Register UI (`RiskRegisterPage.tsx`) with Systemic Risk Spike banners, inline editing, 24h/48h/72h SLA badges, and an Immutable Audit Trail drawer.

#### Scenario: AI Discovers Pulse-Drop Risk and Manager Applies AI Mitigation in UI
- **WHEN** a Group Pulse Score drops by more than 15 points or falls below 40
- **THEN** Gemini 2.5 Flash generates a pre-populated risk entry with a recommended mitigation strategy, which is plotted on the React 5x5 Heatmap and editable in `RiskRegisterPage.tsx`

## ADDED Requirements

### Requirement: React Pulse & Health Analytics Dashboard and Inline XAI Highlighter UI
The system SHALL provide a React Pulse & Health Analytics Dashboard (`PulseDashboardPage.tsx`) with customizable `react-grid-layout` widgets, Recharts multi-series Pulse Trajectory Line Chart, clickable Meeting Details Drill-Down Drawer (`MeetingDetailsDrawer.tsx`), and an Inline XAI Rationale Drawer (`XaiRationaleDrawer.tsx`) highlighting verified verbatim substrings by signed attribution weight.

#### Scenario: Adjudicator Opens Inline XAI Rationale Highlighter
- **WHEN** a user clicks "Explain Rationale" on a dialogue block in the UI
- **THEN** the UI renders the 4-bar Rubric Breakdown (`Emotional Valence`, `Delivery Alignment`, `Relationship Trust`, `Momentum Commitment`) and highlights the exact `start_char..end_char` verbatim phrases color-coded by positive/negative attribution weight

#### Scenario: Manager Drills Down into Meeting Node on Pulse Line Chart
- **WHEN** a Manager clicks a meeting data point on the Pulse Trajectory Line Chart
- **THEN** `MeetingDetailsDrawer.tsx` opens displaying Meeting Summary (MoM), Top 5 Liked Words, Top 5 Disliked Words, Next Action Items, Risks, and AI Recommended Mitigations

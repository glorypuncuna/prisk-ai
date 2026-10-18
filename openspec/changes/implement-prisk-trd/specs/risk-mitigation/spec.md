## ADDED Requirements

### Requirement: COSO/ISO 31000 Risk Severity Scoring and Categorization
The system SHALL evaluate registered risks across 1–5 Impact and 1–5 Probability scales to calculate a 1–25 Severity Index categorized across `FINANCIAL`, `OPERATIONAL`, `COMPLIANCE`, `STRATEGIC`, and `RELATIONSHIP` dimensions.

#### Scenario: Severity Calculation and Heatmap Placement
- **WHEN** a risk is registered with Impact 5 and Probability 4
- **THEN** the system calculates Severity Index 20, classifies it in the Critical tier, and plots it onto the 5x5 heatmap matrix

### Requirement: Human-Gated Risk Promotion and SLA Escalation Worker
The system SHALL keep newly discovered AI risks in `DRAFT_PENDING_ADJUDICATION` until an Adjudicator commits the Golden Record, starting the 24h/48h/72h escalation SLA evaluated every 15 minutes by Cloud Scheduler.

#### Scenario: Risk Promotion Starts SLA Clock
- **WHEN** an Adjudicator approves a draft risk during Golden Record commit
- **THEN** the risk status transitions to `OPEN`, `sla_started_at` is anchored to commit time, and the 24h escalation timer begins

#### Scenario: Automated 24h Escalation Notification
- **WHEN** an unmitigated High or Critical risk exceeds 24 hours in `OPEN` status
- **THEN** the Cloud Scheduler worker dispatches an email and in-app alert to the assigned Risk Owner and logs the escalation in BigQuery

### Requirement: Systemic Risk Spike Detection
The system SHALL detect systemic portfolio risk spikes whenever $\ge 3$ active projects have concurrent Critical risks or the portfolio-wide average Severity Index increases by $> 25\%$ over a rolling 7-day window.

#### Scenario: Portfolio Risk Spike Alert Triggered
- **WHEN** 3 active projects under a company have concurrent Critical risks (`severity_index >= 20`)
- **THEN** the system displays a Systemic Risk Spike warning banner on Executive Dashboards and dispatches urgent alerts to Executive users

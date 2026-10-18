## ADDED Requirements

### Requirement: User Registration with E.164 Phone Normalization
The system SHALL provide a registration interface that collects First Name, Last Name, Email, Password, Country Code, and Phone Number, and validates the phone number to international E.164 standard using `phonenumbers`.

#### Scenario: Successful Registration with E.164 Phone
- **WHEN** a user submits registration with country code "US" and phone "4155552671"
- **THEN** the system validates credentials via Firebase Identity Platform, stores `+14155552671` in `users/{uid}`, and sets initial role to `EXTERNAL_STAKEHOLDER` with `assigned_project_ids = []`

#### Scenario: Invalid Phone Number Submission
- **WHEN** a user submits an invalid phone number string that fails E.164 format parsing for the selected country code
- **THEN** the system rejects the registration with HTTP 422 Unprocessable Entity and an explanatory validation error

### Requirement: Role-Based Access Control and Quarantined Onboarding
The system SHALL assign newly self-registered accounts the `EXTERNAL_STAKEHOLDER` role with zero project assignments and display an onboarding holding screen pending explicit project invitation.

#### Scenario: Quarantined User Accessing Dashboards
- **WHEN** a newly registered user without project assignments attempts to access project analytics or meeting records
- **THEN** the system denies access with HTTP 403 Forbidden and displays the "Access Pending Project Invitation" banner

### Requirement: Project Invitation and Role Elevation
The system SHALL allow authorized `MANAGER` and `EXECUTIVE` users to issue project invitations that link accepted users to project scopes and update Firebase Auth custom claims.

#### Scenario: Manager Invites User to Project
- **WHEN** a Manager issues an invitation for an external email to join a project with role `EXTERNAL_STAKEHOLDER`
- **THEN** the system generates an expiring token, dispatches an email, and upon acceptance updates the user's `assigned_project_ids` and Firebase custom claims

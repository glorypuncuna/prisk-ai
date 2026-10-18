## ADDED Requirements

### Requirement: Canonical ADMIN Super Admin Role Definition
The system SHALL recognize `ADMIN` as the highest tier in the enterprise RBAC hierarchy (`ADMIN > EXECUTIVE > MANAGER > ADJUDICATOR > EXTERNAL_STAKEHOLDER`). When an account possesses the `ADMIN` role, the system SHALL synchronize custom claims (`{"role": "ADMIN"}`) with Firebase Authentication and grant bypass authority across all project boundaries.

#### Scenario: ADMIN custom claims sync and token validation
- **WHEN** an authenticated user possesses `role: "ADMIN"` in their Firestore profile
- **THEN** Firebase custom claims SHALL reflect `{"role": "ADMIN"}`
- **AND** JWT token validation SHALL grant access to all tenant administrative endpoints

### Requirement: Super Admin User Creation and Provisioning
The system SHALL provide an administrative endpoint `POST /api/v1/admin/users` restricted strictly to `ADMIN` callers, allowing the direct provisioning of accounts with any target role (`ADMIN`, `EXECUTIVE`, `MANAGER`, `ADJUDICATOR`, `EXTERNAL_STAKEHOLDER`), E.164 phone number, and pre-authorized project bindings.

#### Scenario: Admin successfully provisions a new user
- **WHEN** an `ADMIN` calls `POST /api/v1/admin/users` with email, E.164 phone number, and role `MANAGER`
- **THEN** the system SHALL create the profile in Firestore `users/{uid}`, sync Firebase custom claims, record `ADMIN_USER_CREATED` in `audit_ledger`, and return HTTP 201 Created

#### Scenario: Non-admin caller blocked from admin provisioning
- **WHEN** an `EXECUTIVE` or `MANAGER` attempts to call `POST /api/v1/admin/users`
- **THEN** the system SHALL reject the request with HTTP 403 Forbidden

### Requirement: Super Admin User Deletion and Account Termination
The system SHALL provide an administrative endpoint `DELETE /api/v1/admin/users/{uid}` restricted strictly to `ADMIN` callers, allowing the hard deletion of a user account. The endpoint SHALL purge the user document from Firestore, remove custom claims from Firebase Auth, log a permanent `ADMIN_USER_DELETED` tombstone event to `audit_ledger`, and reject attempts by an admin to delete their own active account.

#### Scenario: Admin successfully deletes a user account
- **WHEN** an `ADMIN` calls `DELETE /api/v1/admin/users/{target_uid}` where `target_uid != current_user.uid`
- **THEN** the system SHALL purge `users/{target_uid}`, delete the user from Firebase Auth, record `ADMIN_USER_DELETED` in `audit_ledger`, and return HTTP 200 OK

#### Scenario: Admin self-deletion prevented
- **WHEN** an `ADMIN` calls `DELETE /api/v1/admin/users/{current_admin_uid}` targeting their own UID
- **THEN** the system SHALL reject the request with HTTP 400 Bad Request and detail `"Administrators cannot delete their own active account"`

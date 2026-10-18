# Firebase Identity Platform for User Authentication and Extended Profile Storage

To implement secure user authentication, password hashing, and OAuth 2.0 / OIDC provider integration (`FR-0.1`, `FR-0.2`) without incurring the maintenance overhead and cryptographic attack surface of a custom auth service, Prisk AI delegates identity management and credential hashing to Firebase Authentication (Google Identity Platform). Extended user profile data—including first name, last name, E.164 formatted phone number with country code, and project assignments—is stored in a dedicated Firestore operational collection (`users/{uid}`), with new registrations defaulting strictly to `EXTERNAL_STAKEHOLDER` to protect internal meeting data.

## Consequences

- The FastAPI backend validates Firebase JWTs statelessly via the Firebase Admin SDK in request middleware and extracts custom claims (`role`, `assigned_projects`).
- Password hashing (Argon2 / scrypt) and credential resets are fully managed by Google Identity Platform, eliminating credential breach liability on custom application databases.
- Elevating a user to internal roles (`MANAGER`, `ADJUDICATOR`, `EXECUTIVE`) requires an explicit administrative update in Firestore, automatically syncing custom claims to the user's Firebase Auth token.

## ADDED Requirements

### Requirement: Unified Multi-Stage Container Packaging
The repository SHALL provide a multi-stage Dockerfile that builds the React Vite frontend assets and bundles them alongside the Python FastAPI application into a single lightweight production container image.

#### Scenario: Multi-stage container build produces unified artifact
- **WHEN** the container build is executed via `docker build` or `gcloud builds submit`
- **THEN** Stage 1 compiles the frontend into static assets at `frontend/dist` and Stage 2 copies these assets into `/app/frontend/dist` without retaining Node.js runtime build dependencies in the final image.

### Requirement: FastAPI Single-Page Application Static Serving and Fallback
The FastAPI application SHALL serve compiled frontend static files and provide a client-side routing fallback while preserving priority execution for API, internal job, webhook, and health check endpoints.

#### Scenario: API routes take precedence over SPA routes
- **WHEN** an HTTP request is made to `/api/v1/auth/me`, `/healthz`, or `/internal/jobs/evaluate-escalations`
- **THEN** FastAPI executes the designated API handler and returns JSON without invoking static file fallback routing.

#### Scenario: Client-side SPA route returns index.html
- **WHEN** an HTTP GET request is made to a frontend route such as `/risks`, `/admin/users`, or `/adjudication/meet-123`
- **THEN** FastAPI serves `frontend/dist/index.html` with an HTTP 200 status code and `text/html` content type.

#### Scenario: Static assets are served with proper MIME types
- **WHEN** an HTTP GET request is made to `/assets/index.js` or `/assets/index.css`
- **THEN** FastAPI serves the requested file directly from the static assets directory with appropriate caching headers.

### Requirement: Dynamic Relative API Client Configuration
The frontend API client modules SHALL automatically default to relative path endpoints (`/api/v1/*`) when deployed in a production environment where `VITE_API_BASE_URL` is unset or empty.

#### Scenario: Production build issues requests against same-origin API
- **WHEN** the frontend application runs in a browser from the Cloud Run URL
- **THEN** API network calls target `/api/v1/*` on the current host without issuing cross-origin CORS preflight requests.

### Requirement: Automated Cloud Run Deployment Automation Script
The repository SHALL provide an executable deployment automation script (`scripts/deploy_cloud_run.sh`) that builds the container image, provisions the Cloud Run service, configures production environment variables, and validates service readiness.

#### Scenario: Automated deployment execution
- **WHEN** an operator runs `scripts/deploy_cloud_run.sh --project-id <PROJECT_ID>`
- **THEN** the script builds the unified image via Cloud Build or local Docker, deploys the revision to Cloud Run with unauthenticated HTTPS access, sets `USE_IN_MEMORY_FIRESTORE=false`, and executes a verification probe against `/healthz`.

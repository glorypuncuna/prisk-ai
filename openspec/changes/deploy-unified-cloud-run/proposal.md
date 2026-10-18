## Why

Prisk AI currently operates with disparate local development commands across the Python FastAPI backend and the React Vite frontend, requiring engineers to run separate processes and local proxies. To eliminate all local dependencies and operate 100% in the cloud, we need a production-grade, containerized deployment where the backend and frontend are unified into a single Google Cloud Run service (`prisk-ai-app`), providing a single public HTTPS URL, zero CORS complexity, and automated scaling to zero.

## What Changes

- Add a production multi-stage `Dockerfile` at the repository root that builds the React TypeScript frontend (`frontend/dist`) and embeds it directly into the Python 3.13 FastAPI backend container image.
- Configure FastAPI to serve the compiled static assets (`/assets/*`, `favicon.ico`, etc.) and provide a SPA fallback route returning `index.html` for client-side React Router navigation while keeping `/api/v1/*`, `/internal/*`, `/webhooks/*`, and `/docs` routes prioritized.
- Introduce dynamic runtime environment configuration injection so the frontend client uses relative `/api/v1` routes automatically, eliminating hardcoded `localhost:8000` URLs.
- Add an automated deployment script (`scripts/deploy_cloud_run.sh`) utilizing `gcloud builds submit` and `gcloud run deploy` with identity platform bindings, Cloud Firestore Native Mode, Cloud Storage WORM bucket, and Secret Manager access.
- Add health check probes (`GET /healthz`) and Cloud Run environment variable mappings for production serverless execution.

## Capabilities

### New Capabilities
- `unified-cloud-run-deployment`: Containerization of React frontend and FastAPI backend into a single Cloud Run service with multi-stage Docker build, SPA static routing, production Secret Manager environment bindings, and automated deployment scripting.

### Modified Capabilities
<!-- No requirement changes to existing functional specs -->

## Impact

- **Infrastructure**: New Google Cloud Run service (`prisk-ai-app`) with minimum 0 instances (serverless cost efficiency) and automated HTTPS domain provisioning.
- **Backend**: Update `backend/app/main.py` to mount static directory when `frontend/dist` exists, while preserving existing API routers and middleware.
- **Frontend**: Vite build configuration output directory and API client base URL defaulting to relative paths (`/api/v1`) in production.
- **Tooling**: Adds root `Dockerfile`, `.dockerignore`, and deployment automation CLI script `scripts/deploy_cloud_run.sh`.

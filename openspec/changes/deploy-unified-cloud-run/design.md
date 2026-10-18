## Context

Prisk AI is currently split into two runtimes:
1. Python 3.13 FastAPI backend (`backend/`) running locally on port 8000.
2. React 18+ Vite TypeScript frontend (`frontend/`) running locally on port 5173.

The user's objective is to eliminate local runtime dependencies entirely ("not having local anymore") and deploy the full application directly to Google Cloud Platform on Google Cloud Run. By packaging both the React frontend and the FastAPI backend into a single unified container image, we eliminate cross-origin resource sharing (CORS) friction, reduce operations overhead to a single deployment pipeline, and gain serverless cost efficiency with automated scale-to-zero when idle.

## Goals / Non-Goals

**Goals:**
- Implement a multi-stage `Dockerfile` that builds the React application with Vite into optimized static production assets (`frontend/dist`) and copies them into the Python 3.13 FastAPI container.
- Configure FastAPI in `backend/app/main.py` to serve `/assets` and static assets directly, with a catch-all SPA fallback returning `index.html` for unknown non-API routes.
- Update frontend API clients so that in production builds, requests default to relative `/api/v1` routes rather than requiring a hardcoded local URL.
- Implement an automated deployment bash script (`scripts/deploy_cloud_run.sh`) that provisions or updates the Cloud Run service (`prisk-ai-app`), binds Secret Manager secrets, configures Cloud Run environment variables, and verifies container readiness via `/healthz`.
- Ensure all Google Cloud service dependencies (Cloud Firestore Native Mode, Google Cloud Storage WORM bucket `prisk-compliance-packages`, Google Cloud DLP, Vertex AI, BigQuery dataset `prisk_analytics`) integrate seamlessly using the Cloud Run Default Service Account or dedicated service account credentials.

**Non-Goals:**
- Deploying a separate frontend hosting provider (such as Firebase Hosting or Vercel); the unified container satisfies the requirement to eliminate local execution without managing multi-service deployments.
- Continuous Delivery setup via GitHub Actions; deployment is triggered via the unified CLI script with optional CI/CD extensibility.
- Replacing existing FastAPI endpoints or modifying database schemas.

## Decisions

### Decision 1: Multi-Stage Docker Build with Node 20 and Python 3.13 Slim
- **Choice:** Stage 1 uses `node:20-alpine` to run `npm ci` and `npm run build` in `frontend/`. Stage 2 uses `python:3.13-slim`, installs backend production requirements, copies `frontend/dist` into `/app/frontend/dist`, and launches Uvicorn on `$PORT` (default 8080).
- **Alternatives Considered:** Building the frontend locally and committing `dist/`. *Rejected* because committing build artifacts pollutes git history and breaks reproducible builds across developer machines.
- **Rationale:** Keeps container size small (<350MB), guarantees reproducible builds, and requires only `docker` or `gcloud builds submit` without requiring local Node or Python installation.

### Decision 2: FastAPI StaticFiles Mount with Priority Route Ordering
- **Choice:** Mount `/assets` via `StaticFiles(directory="/app/frontend/dist/assets")` and define a catch-all route `@app.get("/{full_path:path}")` returning `FileResponse("/app/frontend/dist/index.html")`. This catch-all is registered AFTER all `/api/v1/*`, `/internal/*`, `/webhooks/*`, `/docs`, `/openapi.json`, and `/healthz` routers.
- **Alternatives Considered:** Running Nginx and Uvicorn in the same container with supervisord. *Rejected* due to excessive process management complexity, zombie process handling risks, and unnecessary memory overhead.
- **Rationale:** FastAPI with `starlette.staticfiles` handles client-side routing natively with zero extra process overhead.

### Decision 3: Relative API Base URL in Production
- **Choice:** Update `frontend/src/api/` configuration to check `import.meta.env.VITE_API_BASE_URL` with a fallback to `""` (empty string) in production, so requests target `/api/v1/*` on the same host and protocol.
- **Rationale:** Completely eliminates CORS headers and preflight OPTIONS request latency in production.

### Decision 4: Automated `gcloud run deploy` with Serverless Configuration
- **Choice:** Deploy to Cloud Run with:
  - `--platform managed`
  - `--region us-central1` (colocated with Firestore and Vertex AI)
  - `--allow-unauthenticated`
  - `--min-instances 0` (cost optimization: $0 at rest)
  - `--max-instances 10`
  - `--memory 1Gi`
  - `--cpu 1`
  - Environment variables: `ENVIRONMENT=production`, `USE_IN_MEMORY_FIRESTORE=false`, `USE_MOCK_FIREBASE_AUTH=false`, `GCP_PROJECT_ID=<project_id>`.
- **Rationale:** Full cloud integration running on live managed Google Cloud infrastructure.

## Risks / Trade-offs

- **[Risk: Slow cold start due to container size]** → *Mitigation:* Use `python:3.13-slim` base, omit build dependencies in the final image, and cache pip wheel downloads.
- **[Risk: SPA route collisions with API routes]** → *Mitigation:* API routers are registered explicitly with `/api/v1`, `/internal`, and `/webhooks` prefixes before the SPA catch-all handler.
- **[Risk: Cloud Run service account lacking IAM permissions]** → *Mitigation:* The deployment script verifies or grants required IAM roles (`roles/datastore.user`, `roles/storage.objectAdmin`, `roles/bigquery.dataEditor`, `roles/aiplatform.user`, `roles/dlp.user`) to the runtime service account before deployment.

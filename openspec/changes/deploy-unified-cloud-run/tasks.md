## 1. Multi-Stage Dockerfile & Container Architecture

- [x] 1.1 Create production root `Dockerfile` with Stage 1 Node 20 building `frontend/dist` and Stage 2 Python 3.13 slim installing backend requirements and copying assets
- [x] 1.2 Create `.dockerignore` excluding `.git`, `.venv`, `node_modules`, test caches, and development artifacts

## 2. FastAPI Static Asset Mount & SPA Routing Fallback

- [x] 2.1 Add `/healthz` liveness probe returning JSON status and system readiness
- [x] 2.2 Configure FastAPI in `backend/app/main.py` to mount `/assets` and static files from `frontend/dist` when directory exists
- [x] 2.3 Implement catch-all route `@app.get("/{full_path:path}")` serving `index.html` for client-side React Router navigation while keeping `/api/v1/*`, `/internal/*`, `/webhooks/*`, and `/docs` prioritized

## 3. Frontend Production API Base Configuration

- [x] 3.1 Update frontend API client modules (`authApi.ts`, `meetingsApi.ts`, `adjudicationApi.ts`, `risksApi.ts`) to default `VITE_API_BASE_URL` to empty string in production for same-origin relative `/api/v1` calls
- [x] 3.2 Verify frontend production build produces clean static bundles in `frontend/dist` without build errors

## 4. Automated Deployment Script & Live Cloud Run Verification

- [x] 4.1 Create automated deployment script `scripts/deploy_cloud_run.sh` with parameter flags (`--project-id`, `--region`, `--service-name`, `--dry-run`)
- [x] 4.2 Add automated GCP IAM role verification (`roles/datastore.user`, `roles/storage.objectAdmin`, `roles/bigquery.dataEditor`, `roles/aiplatform.user`, `roles/dlp.user`) for Cloud Run service account
- [ ] 4.3 Implement `gcloud builds submit` and `gcloud run deploy` command sequence with production environment variables (`USE_IN_MEMORY_FIRESTORE=false`, `USE_MOCK_FIREBASE_AUTH=false`)
- [ ] 4.4 Test container local/cloud execution and verify `/healthz` and SPA routes

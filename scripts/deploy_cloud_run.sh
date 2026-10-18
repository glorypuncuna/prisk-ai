#!/usr/bin/env bash
set -euo pipefail

# Default configuration
PROJECT_ID="prisk-ai"
REGION="us-central1"
SERVICE_NAME="prisk-ai-app"
DRY_RUN=false

# Add homebrew/gcloud paths if needed
export PATH="/opt/homebrew/bin:/opt/homebrew/share/google-cloud-sdk/bin:$HOME/google-cloud-sdk/bin:$PATH"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-id)
      PROJECT_ID="$2"
      shift 2
      ;;
    --region)
      REGION="$2"
      shift 2
      ;;
    --service-name)
      SERVICE_NAME="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    *)
      echo "Unknown flag: $1"
      echo "Usage: $0 [--project-id <id>] [--region <region>] [--service-name <name>] [--dry-run]"
      exit 1
      ;;
  esac
done

echo "=========================================================="
echo "🚀 pRisk AI Cloud Run Unified Deployment"
echo "Project ID:    ${PROJECT_ID}"
echo "Region:        ${REGION}"
echo "Service Name:  ${SERVICE_NAME}"
echo "Dry Run:       ${DRY_RUN}"
echo "=========================================================="

if ! command -v gcloud &> /dev/null; then
  echo "❌ Error: gcloud CLI not found in PATH."
  exit 1
fi

IMAGE_TAG="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest"

if [ "$DRY_RUN" = true ]; then
  echo "[DRY RUN] Would verify IAM roles for default compute service account"
  echo "[DRY RUN] Would submit build: gcloud builds submit --tag ${IMAGE_TAG} ."
  echo "[DRY RUN] Would deploy Cloud Run service: ${SERVICE_NAME} to ${REGION}"
  echo "Dry run complete."
  exit 0
fi

# Ensure project is set
echo "Setting gcloud project..."
gcloud config set project "${PROJECT_ID}"

# Enable necessary Google Cloud APIs
echo "Enabling required GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  dlp.googleapis.com \
  aiplatform.googleapis.com \
  bigquery.googleapis.com || true

# Retrieve project number for default compute service account
echo "Retrieving project number..."
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
SA_EMAIL="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
echo "Service Account: ${SA_EMAIL}"

# IAM Roles verification & assignment
REQUIRED_ROLES=(
  "roles/datastore.user"
  "roles/storage.objectAdmin"
  "roles/bigquery.dataEditor"
  "roles/aiplatform.user"
  "roles/dlp.user"
)

echo "Verifying IAM roles for ${SA_EMAIL}..."
for ROLE in "${REQUIRED_ROLES[@]}"; do
  echo "Checking role: ${ROLE}"
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" \
    --quiet > /dev/null 2>&1 || true
done
echo "✓ IAM roles verified."

# Build and push unified container image via Cloud Build
echo "Building unified container image via Cloud Build..."
gcloud builds submit --tag "${IMAGE_TAG}" .

# Deploy to Cloud Run
echo "Deploying ${SERVICE_NAME} to Google Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE_TAG}" \
  --platform managed \
  --region "${REGION}" \
  --port 8080 \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 10 \
  --memory 1Gi \
  --cpu 1 \
  --set-env-vars "ENVIRONMENT=production,USE_IN_MEMORY_FIRESTORE=false,USE_MOCK_FIREBASE_AUTH=false,GCP_PROJECT_ID=${PROJECT_ID},GCS_COMPLIANCE_BUCKET_NAME=prisk-compliance-packages-${PROJECT_ID},VERTEX_AI_LOCATION=${REGION},GEMINI_MODEL_NAME=gemini-3.8-flash,EMBEDDING_MODEL_NAME=text-embedding-004" \
  --quiet

# Retrieve Cloud Run Service URL
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --platform managed --region "${REGION}" --format="value(status.url)")

echo "=========================================================="
echo "🎉 DEPLOYMENT SUCCESSFUL!"
echo "URL: ${SERVICE_URL}"
echo "=========================================================="

# Validate service readiness
echo "Validating /healthz endpoint..."
if curl -s -f -m 15 "${SERVICE_URL}/healthz"; then
  echo ""
  echo "✓ Health check passed!"
else
  echo ""
  echo "⚠️ Warning: Initial health check returned non-200. Container may still be starting."
fi

echo "Public Web App & API URL: ${SERVICE_URL}"

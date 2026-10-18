from dataclasses import dataclass, field
from functools import lru_cache
import os

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ROOT_DIR = os.path.dirname(_BACKEND_DIR)
_DEFAULT_CREDS = os.path.join(_BACKEND_DIR, "service-account.json")

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore[import-not-found]

    class Settings(BaseSettings):
        """Application settings loaded from environment variables."""

        app_name: str = "pRiskAI Enterprise Meeting & Risk Intelligence API"
        api_v1_prefix: str = "/api/v1"
        environment: str = "development"
        gcp_project_id: str = "prisk-ai"
        firebase_service_account_email: str = (
            "firebase-adminsdk-fbsvc@prisk-ai.iam.gserviceaccount.com"
        )
        google_application_credentials: str | None = (
            _DEFAULT_CREDS if os.path.isfile(_DEFAULT_CREDS) else None
        )
        use_in_memory_firestore: bool = False
        use_mock_firebase_auth: bool = False
        gcs_compliance_bucket_name: str = "prisk-compliance-packages-prisk-ai"
        bigquery_dataset_id: str = "prisk_analytics"
        meetstream_api_key: str | None = None
        meetstream_webhook_secret: str | None = None
        sendgrid_api_key: str | None = None
        vertex_ai_location: str = "us-central1"
        gemini_model_name: str = "gemini-2.5-flash"
        embedding_model_name: str = "text-embedding-004"
        google_api_key: str | None = None
        cors_origins: list[str] = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:3000",
        ]
        smtp_from_email: str = "no-reply@prisk-ai.firebaseapp.com"

        model_config = SettingsConfigDict(
            env_file=(
                os.path.join(_BACKEND_DIR, ".env"),
                os.path.join(_ROOT_DIR, ".env"),
                ".env",
            ),
            env_file_encoding="utf-8",
            extra="ignore",
        )

except ImportError:

    @dataclass
    class Settings:  # type: ignore[no-redef]
        """Fallback settings dataclass when pydantic-settings is not installed."""

        app_name: str = os.getenv(
            "APP_NAME", "pRiskAI Enterprise Meeting & Risk Intelligence API"
        )
        api_v1_prefix: str = os.getenv("API_V1_PREFIX", "/api/v1")
        environment: str = os.getenv("ENVIRONMENT", "development")
        gcp_project_id: str = os.getenv("GCP_PROJECT_ID", "prisk-ai")
        firebase_service_account_email: str = os.getenv(
            "FIREBASE_SERVICE_ACCOUNT_EMAIL",
            "firebase-adminsdk-fbsvc@prisk-ai.iam.gserviceaccount.com",
        )
        google_application_credentials: str | None = os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS"
        )
        use_in_memory_firestore: bool = (
            os.getenv("USE_IN_MEMORY_FIRESTORE", "false").lower() == "true"
        )
        use_mock_firebase_auth: bool = (
            os.getenv("USE_MOCK_FIREBASE_AUTH", "false").lower() == "true"
        )
        gcs_compliance_bucket_name: str = os.getenv(
            "GCS_COMPLIANCE_BUCKET_NAME", "prisk-compliance-packages-prisk-ai"
        )
        bigquery_dataset_id: str = os.getenv("BIGQUERY_DATASET_ID", "prisk_analytics")
        meetstream_api_key: str | None = os.getenv("MEETSTREAM_API_KEY")
        meetstream_webhook_secret: str | None = os.getenv("MEETSTREAM_WEBHOOK_SECRET")
        sendgrid_api_key: str | None = os.getenv("SENDGRID_API_KEY")
        vertex_ai_location: str = os.getenv("VERTEX_AI_LOCATION", "us-central1")
        gemini_model_name: str = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
        embedding_model_name: str = os.getenv(
            "EMBEDDING_MODEL_NAME", "text-embedding-004"
        )
        google_api_key: str | None = os.getenv("GOOGLE_API_KEY")
        cors_origins: list[str] = field(
            default_factory=lambda: [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:3000",
            ]
        )
        smtp_from_email: str = os.getenv(
            "SMTP_FROM_EMAIL", "no-reply@prisk-ai.firebaseapp.com"
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()

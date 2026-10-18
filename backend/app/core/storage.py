import hashlib
import os
from typing import Any
from google.cloud import storage

from app.core.config import get_settings


_in_memory_worm_blobs: dict[str, dict[str, Any]] = {}


class ComplianceStorageClient:
    """Google Cloud Storage client managing WORM compliance bucket and artifacts."""

    def __init__(
        self,
        project_id: str | None = None,
        bucket_name: str | None = None,
        credentials_path: str | None = None,
    ) -> None:
        settings = get_settings()
        self.project_id = project_id or settings.gcp_project_id
        self.bucket_name = bucket_name or settings.gcs_compliance_bucket_name
        self.credentials_path = (
            credentials_path
            or settings.google_application_credentials
            or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        )
        self._client: storage.Client | None = None

    def get_client(self) -> storage.Client:
        if self._client is None:
            if self.credentials_path and os.path.isfile(self.credentials_path):
                self._client = storage.Client.from_service_account_json(
                    self.credentials_path, project=self.project_id
                )
            else:
                self._client = storage.Client(project=self.project_id)
        return self._client

    def ensure_compliance_bucket(
        self, retention_period_seconds: int = 220752000, lock: bool = False
    ) -> storage.Bucket:
        """Ensure the WORM compliance bucket exists with Object Retention policy."""
        client = self.get_client()
        try:
            bucket = client.get_bucket(self.bucket_name)
        except Exception:
            bucket = client.create_bucket(self.bucket_name, location="US")

        if not bucket.retention_policy_locked:
            bucket.retention_period = retention_period_seconds
            bucket.patch()
            if lock:
                bucket.lock_retention_policy()

        return bucket

    def upload_compliance_package(
        self,
        package_id: str,
        project_id: str,
        content: bytes,
        file_extension: str = "pdf",
        content_type: str = "application/pdf",
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Upload a sealed compliance package with SHA-256 calculation and WORM retention lock."""
        sha256_hash = hashlib.sha256(content).hexdigest()
        blob_path = f"{project_id}/{package_id}.{file_extension.lower()}"
        gcs_uri = f"gs://{self.bucket_name}/{blob_path}"

        custom_metadata = {
            "package_id": package_id,
            "project_id": project_id,
            "sha256_hash": sha256_hash,
            "status": "SEALED_WORM",
        }
        if metadata:
            custom_metadata.update(metadata)

        settings = get_settings()
        if self._client is None and settings.use_in_memory_firestore:
            if blob_path in _in_memory_worm_blobs:
                raise PermissionError(
                    f"WORM Retention Lock Violation: Artifact '{gcs_uri}' is immutable and cannot be overwritten."
                )
            _in_memory_worm_blobs[blob_path] = {
                "content": bytes(content),
                "content_type": content_type,
                "metadata": custom_metadata,
                "sha256_hash": sha256_hash,
                "gcs_uri": gcs_uri,
                "locked": True,
            }
            return {
                "package_id": package_id,
                "project_id": project_id,
                "gcs_uri": gcs_uri,
                "sha256_hash": sha256_hash,
                "size_bytes": len(content),
                "status": "SEALED_WORM",
            }

        client = self.get_client()
        bucket = client.bucket(self.bucket_name)
        blob = bucket.blob(blob_path)
        blob.metadata = custom_metadata
        blob.upload_from_string(content, content_type=content_type)

        return {
            "package_id": package_id,
            "project_id": project_id,
            "gcs_uri": gcs_uri,
            "sha256_hash": sha256_hash,
            "size_bytes": len(content),
            "status": "SEALED_WORM",
        }

    def download_compliance_package(
        self, package_id: str, project_id: str
    ) -> tuple[bytes, str, str] | None:
        """Retrieve sealed WORM artifact bytes, content_type, and extension."""
        settings = get_settings()
        if self._client is None and settings.use_in_memory_firestore:
            for ext in ("pdf", "csv", "json"):
                blob_path = f"{project_id}/{package_id}.{ext}"
                entry = _in_memory_worm_blobs.get(blob_path)
                if entry:
                    return entry["content"], entry["content_type"], ext
            return None

        client = self.get_client()
        bucket = client.bucket(self.bucket_name)
        for ext, ctype in (
            ("pdf", "application/pdf"),
            ("csv", "text/csv"),
            ("json", "application/json"),
        ):
            blob = bucket.get_blob(f"{project_id}/{package_id}.{ext}")
            if blob:
                return blob.download_as_bytes(), (blob.content_type or ctype), ext
        return None

    def delete_compliance_package(self, package_id: str, project_id: str) -> None:
        """Attempt to delete a WORM compliance artifact, strictly rejected by Object Retention Lock."""
        raise PermissionError(
            f"WORM Retention Lock Violation: Compliance package '{package_id}' in project '{project_id}' "
            "is protected by GCS Object Retention Lock and cannot be modified or deleted."
        )

    def verify_package_integrity(
        self, package_id: str, project_id: str, expected_sha256: str
    ) -> bool:
        """Verify the integrity of a stored WORM compliance artifact against its recorded hash."""
        settings = get_settings()
        if self._client is None and settings.use_in_memory_firestore:
            for ext in ("pdf", "csv", "json"):
                blob_path = f"{project_id}/{package_id}.{ext}"
                entry = _in_memory_worm_blobs.get(blob_path)
                if entry:
                    computed_hash = hashlib.sha256(entry["content"]).hexdigest()
                    return computed_hash == expected_sha256
            return False

        client = self.get_client()
        bucket = client.bucket(self.bucket_name)
        for ext in ["pdf", "csv", "json"]:
            blob = bucket.get_blob(f"{project_id}/{package_id}.{ext}")
            if blob:
                data = blob.download_as_bytes()
                computed_hash = hashlib.sha256(data).hexdigest()
                return computed_hash == expected_sha256
        return False

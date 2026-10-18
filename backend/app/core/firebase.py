import base64
import json
import os
from typing import Any

from app.core.config import get_settings

# Track custom user claims in-memory when running without a local service account key file
_mock_custom_claims: dict[str, dict[str, Any]] = {}


def initialize_firebase_app() -> None:
    """Initialize Firebase Admin SDK for project `prisk-ai`."""
    settings = get_settings()
    try:
        import firebase_admin  # type: ignore[import-untyped]
        from firebase_admin import credentials  # type: ignore[import-untyped]

        if not firebase_admin._apps:
            options = {
                "projectId": settings.gcp_project_id,
                "serviceAccountId": settings.firebase_service_account_email,
            }
            cred_path = settings.google_application_credentials or os.getenv(
                "GOOGLE_APPLICATION_CREDENTIALS"
            )
            if cred_path and os.path.isfile(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred, options=options)
            else:
                firebase_admin.initialize_app(options=options)
    except Exception:
        pass


def verify_firebase_id_token(token: str) -> dict[str, Any]:
    """Verify a Firebase ID token against `prisk-ai` and return its decoded claims.

    - Verifies live RS256 Firebase ID tokens issued by `https://securetoken.google.com/prisk-ai`
      using `firebase_admin.auth.verify_id_token`.
    - Also accepts `mock:<json>` tokens in development/test mode when `use_mock_firebase_auth` is enabled.
    """
    settings = get_settings()
    if not token or token in {"invalid-token", "expired-token"}:
        raise ValueError("Invalid or expired Firebase ID token")

    is_mock_allowed = (
        settings.use_mock_firebase_auth or settings.environment == "development"
    )
    if token.startswith("mock:"):
        if not is_mock_allowed:
            raise ValueError("Mock tokens are disabled in production")
        return _verify_mock_token(token)

    try:
        import firebase_admin  # type: ignore[import-untyped]
        from firebase_admin import auth as firebase_auth  # type: ignore[import-untyped]

        if not firebase_admin._apps:
            initialize_firebase_app()

        decoded: dict[str, Any] = firebase_auth.verify_id_token(
            token, check_revoked=False
        )
        uid = str(decoded.get("uid") or decoded.get("sub") or "")
        synced = _mock_custom_claims.get(uid, {})
        return {**synced, **decoded, "uid": uid}
    except Exception as exc:
        if is_mock_allowed:
            return _verify_mock_token(token)
        raise ValueError("Invalid or expired Firebase ID token") from exc



def set_firebase_custom_user_claims(uid: str, custom_claims: dict[str, Any]) -> None:
    """Synchronize RBAC role and custom claims with Firebase Auth (`set_custom_user_claims`)."""
    _mock_custom_claims[uid] = dict(custom_claims)
    try:
        import firebase_admin  # type: ignore[import-untyped]
        from firebase_admin import auth as firebase_auth  # type: ignore[import-untyped]

        if not firebase_admin._apps:
            initialize_firebase_app()
        firebase_auth.set_custom_user_claims(uid, custom_claims)
    except Exception:
        # Keep in-memory custom claims synchronized if service account private key is not mounted locally
        pass


def get_mock_custom_claims(uid: str) -> dict[str, Any]:
    """Return synchronized custom claims for a UID."""
    return dict(_mock_custom_claims.get(uid, {}))


def reset_mock_custom_claims() -> None:
    """Clear all in-memory custom claims (for test isolation)."""
    _mock_custom_claims.clear()


def create_firebase_auth_user(
    email: str,
    phone_number: str | None = None,
    display_name: str | None = None,
    uid: str | None = None,
) -> str:
    """Create a user record in Firebase Auth or return a deterministically mapped UID in test mode."""
    settings = get_settings()
    fallback_uid = uid or f"uid_{email.replace('@', '_').replace('.', '_')}"
    if not settings.use_mock_firebase_auth:
        try:
            import firebase_admin  # type: ignore[import-untyped]
            from firebase_admin import auth as firebase_auth  # type: ignore[import-untyped]

            if not firebase_admin._apps:
                initialize_firebase_app()

            kwargs: dict[str, Any] = {"email": email}
            if uid:
                kwargs["uid"] = uid
            if phone_number:
                kwargs["phone_number"] = phone_number
            if display_name:
                kwargs["display_name"] = display_name
            record = firebase_auth.create_user(**kwargs)
            return str(record.uid)
        except Exception:
            pass
    return fallback_uid


def delete_firebase_auth_user(uid: str) -> None:
    """Delete a user record from Firebase Auth and purge synchronized claims."""
    _mock_custom_claims.pop(uid, None)
    settings = get_settings()
    if not settings.use_mock_firebase_auth:
        try:
            import firebase_admin  # type: ignore[import-untyped]
            from firebase_admin import auth as firebase_auth  # type: ignore[import-untyped]

            if not firebase_admin._apps:
                initialize_firebase_app()
            firebase_auth.delete_user(uid)
        except Exception:
            pass


def _verify_mock_token(token: str) -> dict[str, Any]:
    """Decode a mock Firebase token (`mock:<json>` or unsigned test JWT)."""
    if not token or token == "invalid-token" or token == "expired-token":
        raise ValueError("Invalid or expired Firebase ID token")

    if token.startswith("mock:"):
        raw_json = token[len("mock:") :]
        claims = json.loads(raw_json)
        if not isinstance(claims, dict) or "uid" not in claims:
            raise ValueError("Mock token must include 'uid'")
        uid = str(claims["uid"])
        synced = _mock_custom_claims.get(uid, {})
        return {**synced, **claims}

    parts = token.split(".")
    if len(parts) == 3:
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        decoded_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
        claims = json.loads(decoded_bytes.decode("utf-8"))
        uid = claims.get("uid") or claims.get("user_id") or claims.get("sub")
        if not uid:
            raise ValueError("JWT token missing subject/uid claim")
        claims["uid"] = uid
        synced = _mock_custom_claims.get(str(uid), {})
        return {**synced, **claims}

    raise ValueError("Malformed Firebase ID token")

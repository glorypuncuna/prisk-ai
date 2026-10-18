from typing import Annotated, Any, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.core.database import get_firestore_client
from app.core.enums import AuthProvider, UserRole
from app.core.firebase import verify_firebase_id_token


class AuthenticatedUser(BaseModel):
    """Validated user context resolved from Firebase ID Token and Firestore profile."""

    uid: str
    email: str
    role: UserRole = UserRole.EXTERNAL_STAKEHOLDER
    assigned_project_ids: list[str] = Field(default_factory=list)
    auth_provider: str = AuthProvider.PASSWORD.value
    claims: dict[str, Any] = Field(default_factory=dict)


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_token_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> dict[str, Any]:
    """Verify the Bearer Firebase ID Token and return decoded claims.

    Raises HTTP 401 Unauthorized when the token is missing, malformed, or expired.
    """
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        decoded_claims = verify_firebase_id_token(credentials.credentials)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    uid = decoded_claims.get("uid") or decoded_claims.get("user_id") or decoded_claims.get("sub")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    decoded_claims["uid"] = str(uid)
    return decoded_claims


async def get_current_user(
    claims: Annotated[dict[str, Any], Depends(get_current_token_claims)],
    db: Annotated[Any, Depends(get_firestore_client)],
) -> AuthenticatedUser:
    """Resolve the current authenticated user from Firebase token claims and Firestore."""
    uid = str(claims["uid"])
    user_snap = db.collection("users").document(uid).get()
    user_doc = user_snap.to_dict() if user_snap.exists else None

    # Determine role: Firestore profile is authoritative, falling back to custom claim or default
    raw_role = (
        (user_doc.get("role") if user_doc else None)
        or claims.get("role")
        or UserRole.EXTERNAL_STAKEHOLDER.value
    )
    try:
        role = UserRole(str(raw_role))
    except ValueError:
        role = UserRole.EXTERNAL_STAKEHOLDER

    email = (
        (user_doc.get("email") if user_doc else None)
        or claims.get("email")
        or ""
    )
    assigned_projects = (
        list(user_doc.get("assigned_project_ids", []))
        if user_doc
        else list(claims.get("assigned_project_ids", []))
    )

    firebase_info = claims.get("firebase", {})
    sign_in_provider = (
        (user_doc.get("auth_provider") if user_doc else None)
        or (firebase_info.get("sign_in_provider") if isinstance(firebase_info, dict) else None)
        or claims.get("auth_provider")
        or AuthProvider.PASSWORD.value
    )

    return AuthenticatedUser(
        uid=uid,
        email=str(email),
        role=role,
        assigned_project_ids=assigned_projects,
        auth_provider=str(sign_in_provider),
        claims=claims,
    )


def require_role(*allowed_roles: UserRole) -> Callable[..., Any]:
    """Dependency factory enforcing that the authenticated user has one of `allowed_roles`.
    
    `ADMIN` is recognized as the apex authority and automatically bypasses checks
    unless explicitly restricted.
    """

    async def _role_checker(
        current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> AuthenticatedUser:
        if current_user.role != UserRole.ADMIN and current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role permissions",
            )
        return current_user

    return _role_checker

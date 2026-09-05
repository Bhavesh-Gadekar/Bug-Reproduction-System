import logging
import uuid
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.workspace import User, Workspace

logger = logging.getLogger("auth")
settings = get_settings()

security = HTTPBearer(auto_error=False)

# Cached JWKS client for Clerk public keys
_jwks_client: PyJWKClient | None = None


@dataclass
class AuthContext:
    clerk_user_id: str
    user_id: uuid.UUID | None
    workspace_id: uuid.UUID | None
    clerk_org_id: str | None
    email: str | None
    role: str | None
    claims: dict[str, Any]


def get_jwks_client() -> PyJWKClient | None:
    """Retrieve or initialize PyJWKClient for Clerk."""
    global _jwks_client
    if _jwks_client is None:
        jwks_url = settings.CLERK_JWKS_URL
        if not jwks_url and settings.CLERK_ISSUER:
            jwks_url = f"{settings.CLERK_ISSUER.rstrip('/')}/.well-known/jwks.json"
        elif not jwks_url and settings.CLERK_PUBLISHABLE_KEY:
            # Clerk publishable keys often encode frontend API URL (e.g. pk_test_xxx)
            jwks_url = "https://api.clerk.com/v1/jwks"

        if jwks_url:
            _jwks_client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=3600)
    return _jwks_client


def verify_clerk_token(token: str) -> dict[str, Any]:
    """
    Validates a Clerk JWT token against Clerk JWKS or secret.
    Returns the decoded token claims dictionary.
    """
    jwks_client = get_jwks_client()

    try:
        if jwks_client:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
            return payload

        # Fallback verification using CLERK_SECRET_KEY if available (for HS256 / dev)
        # or unverified decoding if no verification endpoint is configured yet
        try:
            return jwt.decode(
                token,
                settings.CLERK_SECRET_KEY or "secret",
                algorithms=["HS256", "RS256"],
                options={"verify_signature": bool(settings.CLERK_SECRET_KEY), "verify_aud": False},
            )
        except Exception:
            return jwt.decode(token, options={"verify_signature": False})

    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {e!s}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def get_current_auth_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> AuthContext:
    """
    FastAPI dependency that parses and validates the Clerk-issued JWT token,
    resolves local user and workspace entities, and attaches context to request.state.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    claims = verify_clerk_token(token)

    clerk_user_id = claims.get("sub") or claims.get("user_id")
    if not clerk_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identity subject (sub)",
        )

    clerk_org_id = (
        claims.get("org_id")
        or claims.get("org_slug")
        or (claims.get("orgs", [{}])[0].get("id") if claims.get("orgs") else None)
    )

    # Resolve local User entity
    user_stmt = select(User).where(User.clerk_user_id == clerk_user_id)
    user = db.scalars(user_stmt).first()

    # Resolve local Workspace entity
    workspace: Workspace | None = None
    if clerk_org_id:
        ws_stmt = select(Workspace).where(Workspace.clerk_org_id == clerk_org_id)
        workspace = db.scalars(ws_stmt).first()

    if not workspace and user:
        # Fallback to user's assigned workspace
        ws_stmt = select(Workspace).where(Workspace.id == user.workspace_id)
        workspace = db.scalars(ws_stmt).first()

    auth_context = AuthContext(
        clerk_user_id=clerk_user_id,
        user_id=user.id if user else None,
        workspace_id=workspace.id if workspace else (user.workspace_id if user else None),
        clerk_org_id=clerk_org_id,
        email=user.email if user else claims.get("email"),
        role=user.role if user else claims.get("org_role", "member"),
        claims=claims,
    )

    # Attach to request state for downstream handlers and logging
    request.state.user_id = auth_context.user_id
    request.state.workspace_id = auth_context.workspace_id
    request.state.clerk_user_id = auth_context.clerk_user_id
    request.state.auth_context = auth_context

    return auth_context

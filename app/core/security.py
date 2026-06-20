"""Authentication: verify Supabase-issued JWTs and expose the current user.

The frontend logs in via Supabase Auth and sends the resulting access token as
`Authorization: Bearer <token>`. Supabase may sign tokens with an asymmetric
"JWT Signing Key" (ES256/RS256, verified via the project's JWKS endpoint) or the
legacy HS256 shared secret. We support both, choosing by the token's `alg`.

Never trust a user id from the request body — only from the verified token.
"""

from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import get_settings

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=True)


@dataclass
class CurrentUser:
    id: UUID
    email: str | None


@lru_cache
def _jwk_client() -> PyJWKClient | None:
    if not settings.SUPABASE_URL:
        return None
    return PyJWKClient(settings.jwks_url)


def _decode(token: str) -> dict:
    alg = jwt.get_unverified_header(token).get("alg", "HS256")
    common = {
        "algorithms": [alg],
        "audience": settings.SUPABASE_JWT_AUDIENCE,
    }
    if alg == "HS256":
        if not settings.SUPABASE_JWT_SECRET:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="HS256 token received but SUPABASE_JWT_SECRET is not configured",
            )
        return jwt.decode(token, settings.SUPABASE_JWT_SECRET, **common)

    client = _jwk_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Asymmetric token received but SUPABASE_URL is not configured",
        )
    signing_key = client.get_signing_key_from_jwt(token)
    return jwt.decode(token, signing_key.key, **common)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:
    token = credentials.credentials
    try:
        payload = _decode(token)
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing subject")

    return CurrentUser(id=UUID(user_id), email=payload.get("email"))

"""
Clerk Authentication Middleware.

When AUTH_ENABLED=true:
  - Every API request must include a valid Clerk JWT in the Authorization header
  - The middleware extracts the user_id from the JWT
  - All database operations use this user_id (multi-tenant)

When AUTH_ENABLED=false (default for local dev):
  - No auth required, user_id defaults to "default"
  - You can develop and test without setting up Clerk

Setup for production:
  1. Create account at clerk.com
  2. Create an application
  3. Copy CLERK_SECRET_KEY, CLERK_PUBLISHABLE_KEY, and JWKS URL
  4. Add to .env and set AUTH_ENABLED=true
"""

import jwt
import httpx
from typing import Optional
from functools import lru_cache
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config.settings import settings

security = HTTPBearer(auto_error=False)

# Cache JWKS keys so we don't fetch them on every request
_jwks_cache: Optional[dict] = None


async def _get_jwks() -> dict:
    """Fetch Clerk's JWKS (JSON Web Key Set) for token verification."""
    global _jwks_cache
    if _jwks_cache:
        return _jwks_cache

    if not settings.CLERK_JWKS_URL:
        raise HTTPException(status_code=500, detail="CLERK_JWKS_URL not configured")

    async with httpx.AsyncClient() as client:
        resp = await client.get(settings.CLERK_JWKS_URL)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        return _jwks_cache


def _decode_clerk_token(token: str, jwks: dict) -> dict:
    """Decode and verify a Clerk JWT token."""
    # Get the signing key from JWKS
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")

    signing_key = None
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            signing_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
            break

    if not signing_key:
        raise HTTPException(status_code=401, detail="Invalid token signing key")

    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Extract user_id from Clerk JWT. Returns 'default' if auth is disabled.

    Usage in routes:
        @app.get("/api/something")
        async def something(user_id: str = Depends(get_current_user)):
            ...
    """
    # Auth disabled — local development mode
    if not settings.AUTH_ENABLED:
        return "default"

    # Auth enabled — validate token
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials
    jwks = await _get_jwks()
    payload = _decode_clerk_token(token, jwks)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="No user ID in token")

    return user_id


def clear_jwks_cache():
    """Clear cached JWKS keys (useful if Clerk rotates keys)."""
    global _jwks_cache
    _jwks_cache = None

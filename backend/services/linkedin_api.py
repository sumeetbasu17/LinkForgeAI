"""
LinkedIn API Service with auto-refreshing tokens.

Token lifecycle:
1. User clicks "Connect LinkedIn" → OAuth flow → access_token (60 days) + refresh_token (365 days)
2. Tokens stored in SQLite (not .env) so they persist and auto-refresh
3. Before every API call, check if token is expiring soon (< 7 days)
4. If expiring, use refresh_token to get a new access_token automatically
5. If refresh_token also expired (> 365 days), user must re-authorize
"""

import httpx
from typing import Optional
from datetime import datetime, timedelta
from urllib.parse import urlencode

from config.settings import settings
from db.database import database


class LinkedInService:
    """LinkedIn API with auto-refreshing OAuth2 tokens."""

    AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
    TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
    API_BASE = "https://api.linkedin.com/v2"
    POSTS_API = "https://api.linkedin.com/rest/posts"
    SCOPES = ["openid", "profile", "w_member_social"]

    def __init__(self):
        self.client_id = settings.LINKEDIN_CLIENT_ID
        self.client_secret = settings.LINKEDIN_CLIENT_SECRET
        # Redirect to BACKEND callback, not frontend
        self.redirect_uri = "http://localhost:8000/api/linkedin/callback"

    # ─── Token Management ─────────────────────────────────────────

    async def _get_valid_token(self, user_id: str = "default") -> Optional[str]:
        """Get a valid access token, auto-refreshing if needed.

        This is called before every API call.
        Returns the access token string, or None if not connected.
        """
        # Check .env fallback first (for quick testing)
        env_token = settings.LINKEDIN_ACCESS_TOKEN
        if env_token:
            return env_token

        # Check database
        token_data = database.get_linkedin_token(user_id)
        if not token_data:
            return None

        # If not expired and > 7 days remaining, use as-is
        if not token_data.get("expired") and token_data.get("days_remaining", 0) > 7:
            return token_data["access_token"]

        # If expiring soon or expired, try to refresh
        refresh_token = token_data.get("refresh_token", "")
        if refresh_token:
            try:
                new_tokens = await self._refresh_access_token(refresh_token)
                # Save new tokens
                database.save_linkedin_token(
                    access_token=new_tokens["access_token"],
                    refresh_token=new_tokens.get("refresh_token", refresh_token),
                    expires_in=new_tokens.get("expires_in", 5184000),
                    linkedin_urn=token_data.get("linkedin_urn", ""),
                    linkedin_name=token_data.get("linkedin_name", ""),
                    user_id=user_id,
                )
                return new_tokens["access_token"]
            except Exception:
                # Refresh failed — if token isn't fully expired yet, use it
                if not token_data.get("expired"):
                    return token_data["access_token"]
                return None

        # No refresh token and expired
        if token_data.get("expired"):
            return None

        return token_data["access_token"]

    async def _refresh_access_token(self, refresh_token: str) -> dict:
        """Use refresh_token to get a new access_token."""
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            return response.json()

    # ─── OAuth2 Flow ──────────────────────────────────────────────

    def get_auth_url(self, state: str = "linkedin_auth") -> str:
        """Generate LinkedIn authorization URL."""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "scope": " ".join(self.SCOPES),
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str, user_id: str = "default") -> dict:
        """Exchange authorization code for tokens. Stores in database."""
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

        access_token = data["access_token"]
        refresh_token = data.get("refresh_token", "")
        expires_in = data.get("expires_in", 5184000)

        # Fetch profile to get URN and name
        linkedin_urn = ""
        linkedin_name = ""
        try:
            async with httpx.AsyncClient() as client:
                profile_resp = await client.get(
                    f"{self.API_BASE}/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if profile_resp.status_code == 200:
                    profile = profile_resp.json()
                    linkedin_urn = f"urn:li:person:{profile.get('sub', '')}"
                    linkedin_name = profile.get("name", "")
        except Exception:
            pass

        # Store in database
        database.save_linkedin_token(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            linkedin_urn=linkedin_urn,
            linkedin_name=linkedin_name,
            user_id=user_id,
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
            "linkedin_name": linkedin_name,
        }

    # ─── Status ───────────────────────────────────────────────────

    async def get_status(self, user_id: str = "default") -> dict:
        """Check LinkedIn connection status."""
        token = await self._get_valid_token(user_id)
        if not token:
            token_data = database.get_linkedin_token(user_id)
            if token_data and token_data.get("expired"):
                return {
                    "connected": False,
                    "message": "Token expired. Click Connect LinkedIn to re-authorize.",
                    "needs_reauth": True,
                }
            return {"connected": False, "message": "Not connected yet."}

        # Get stored profile info (avoid API call)
        token_data = database.get_linkedin_token(user_id)
        if token_data:
            return {
                "connected": True,
                "name": token_data.get("linkedin_name", ""),
                "days_remaining": token_data.get("days_remaining", 0),
                "auto_refresh": bool(token_data.get("refresh_token")),
            }

        # Fallback: call API
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.API_BASE}/userinfo",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 200:
                    p = resp.json()
                    return {"connected": True, "name": p.get("name", "")}
        except Exception:
            pass

        return {"connected": True, "name": ""}

    # ─── Posting ──────────────────────────────────────────────────

    async def create_text_post(self, text: str, user_id: str = "default") -> dict:
        """Publish a text post to the user's personal LinkedIn profile."""
        token = await self._get_valid_token(user_id)
        if not token:
            raise ValueError(
                "LinkedIn not connected. Go to Settings → Connect LinkedIn."
            )

        # Get URN from stored token
        token_data = database.get_linkedin_token(user_id)
        author_urn = token_data.get("linkedin_urn", "") if token_data else ""

        if not author_urn:
            # Fetch from API
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.API_BASE}/userinfo",
                    headers={"Authorization": f"Bearer {token}"},
                )
                resp.raise_for_status()
                profile = resp.json()
                author_urn = f"urn:li:person:{profile['sub']}"

        payload = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "visibility": "PUBLIC",
            "commentary": text,
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": "202601",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(self.POSTS_API, json=payload, headers=headers)

            if response.status_code == 201:
                post_id = response.headers.get("x-restli-id", "unknown")
                return {
                    "id": post_id,
                    "status": "published",
                    "message": "Post published to your LinkedIn profile!",
                }
            else:
                return {
                    "id": None,
                    "status": "failed",
                    "message": f"LinkedIn API error {response.status_code}: {response.text[:200]}",
                }


linkedin_service = LinkedInService()

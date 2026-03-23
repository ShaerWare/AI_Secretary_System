"""Google OAuth 2.0 service — token management, auth flow."""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

import httpx
import jwt

from db.database import AsyncSessionLocal
from modules.google.models import GoogleOAuthToken


try:
    from sqlalchemy import delete, select
except ImportError:
    from sqlalchemy import delete
    from sqlalchemy.future import select  # type: ignore[assignment]

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.email",
]


class GoogleOAuthService:
    def _get_config(self) -> tuple[str, str]:
        client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set")
        return client_id, client_secret

    def _get_redirect_uri(self) -> str:
        return os.getenv(
            "GOOGLE_REDIRECT_URI",
            "https://ai-sekretar24.ru/admin/oauth/google/callback",
        )

    def _get_jwt_secret(self) -> str:
        return os.getenv("ADMIN_JWT_SECRET", "fallback-secret")

    def build_auth_url(self, user_id: int) -> str:
        """Build Google OAuth consent URL with CSRF state."""
        client_id, _ = self._get_config()

        state = jwt.encode(
            {"user_id": user_id, "exp": datetime.utcnow() + timedelta(minutes=10)},
            self._get_jwt_secret(),
            algorithm="HS256",
        )

        params = {
            "client_id": client_id,
            "redirect_uri": self._get_redirect_uri(),
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    def _validate_state(self, state: str) -> int:
        """Validate state JWT and return user_id."""
        payload = jwt.decode(state, self._get_jwt_secret(), algorithms=["HS256"])
        return payload["user_id"]

    async def exchange_code(self, code: str, state: str) -> dict:
        """Exchange authorization code for tokens, save to DB."""
        user_id = self._validate_state(state)
        client_id, client_secret = self._get_config()

        async with httpx.AsyncClient() as client:
            # Exchange code for tokens
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": self._get_redirect_uri(),
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

            # Get user email
            access_token = token_data["access_token"]
            userinfo_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            email = None
            if userinfo_resp.status_code == 200:
                email = userinfo_resp.json().get("email")

        # Calculate expiry
        expires_in = token_data.get("expires_in", 3600)
        token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)

        # Save to DB
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.access_token = access_token
                if token_data.get("refresh_token"):
                    existing.refresh_token = token_data["refresh_token"]
                existing.token_expiry = token_expiry
                existing.scopes = " ".join(SCOPES)
                existing.google_email = email
                existing.updated = datetime.utcnow()
            else:
                token_obj = GoogleOAuthToken(
                    user_id=user_id,
                    access_token=access_token,
                    refresh_token=token_data.get("refresh_token"),
                    token_expiry=token_expiry,
                    scopes=" ".join(SCOPES),
                    google_email=email,
                )
                session.add(token_obj)
            await session.commit()

        logger.info(f"Google OAuth connected for user {user_id} ({email})")
        return {"user_id": user_id, "google_email": email}

    async def get_valid_credentials(self, user_id: int) -> Optional[dict]:
        """Get valid access token, refreshing if needed."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
            )
            token = result.scalar_one_or_none()
            if not token:
                return None

            # Check if expired (5min buffer)
            if token.token_expiry and token.token_expiry < datetime.utcnow() + timedelta(minutes=5):
                new_access = await self._refresh_token(token)
                if not new_access:
                    # Refresh failed — token revoked
                    await session.execute(
                        delete(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
                    )
                    await session.commit()
                    return None
                token.access_token = new_access["access_token"]
                token.token_expiry = new_access["expiry"]
                token.updated = datetime.utcnow()
                await session.commit()

            return {
                "access_token": token.access_token,
                "google_email": token.google_email,
            }

    async def _refresh_token(self, token: GoogleOAuthToken) -> Optional[dict]:
        """Refresh an expired access token."""
        if not token.refresh_token:
            return None
        client_id, client_secret = self._get_config()

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    GOOGLE_TOKEN_URL,
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": token.refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                expires_in = data.get("expires_in", 3600)
                return {
                    "access_token": data["access_token"],
                    "expiry": datetime.utcnow() + timedelta(seconds=expires_in),
                }
        except Exception as e:
            logger.error(f"Google token refresh failed for user {token.user_id}: {e}")
            return None

    async def get_status(self, user_id: int) -> dict:
        """Get Google connection status for a user."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
            )
            token = result.scalar_one_or_none()
            if not token:
                return {"connected": False, "google_email": None, "scopes": []}
            return {
                "connected": True,
                "google_email": token.google_email,
                "scopes": token.scopes.split() if token.scopes else [],
            }

    async def disconnect(self, user_id: int) -> bool:
        """Revoke Google tokens and delete from DB."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
            )
            token = result.scalar_one_or_none()
            if not token:
                return False

            # Try to revoke at Google (best effort)
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        GOOGLE_REVOKE_URL,
                        params={"token": token.access_token},
                    )
            except Exception as e:
                logger.warning(f"Google token revoke failed (continuing): {e}")

            await session.execute(
                delete(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
            )
            await session.commit()
            logger.info(f"Google OAuth disconnected for user {user_id}")
            return True


google_oauth_service = GoogleOAuthService()

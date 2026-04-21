"""FCM push notifications service for mobile app.

Sends notifications to registered device tokens via Firebase Cloud Messaging
HTTP v1 API. Uses service account JSON for OAuth2 bearer tokens.

Env:
    FCM_PROJECT_ID: Firebase project ID (e.g. "ai-sekretar24-872f2")
    FCM_SERVICE_ACCOUNT_FILE: path to service-account JSON

Gracefully disabled if env vars not set — other code continues to work.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import httpx
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from db.database import get_async_session
from modules.channels.mobile.models import MobilePushToken


if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)

FCM_ENDPOINT = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
FCM_SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]


class FcmPushService:
    """Send push notifications via FCM HTTP v1 API."""

    def __init__(self) -> None:
        self.project_id: Optional[str] = os.getenv("FCM_PROJECT_ID")
        self.service_account_file: Optional[str] = os.getenv("FCM_SERVICE_ACCOUNT_FILE")
        self._credentials: Any = None

    @property
    def enabled(self) -> bool:
        """FCM is enabled if both project_id and service account file are configured."""
        return bool(
            self.project_id
            and self.service_account_file
            and Path(self.service_account_file).is_file()
        )

    def _get_access_token(self) -> Optional[str]:
        """Get OAuth2 access token for FCM HTTP v1 API. Lazy-initializes credentials."""
        if not self.enabled:
            return None
        try:
            if self._credentials is None:
                # Import here so projects without google-auth still load this module
                from google.auth.transport.requests import (
                    Request as GoogleRequest,  # type: ignore[import-not-found]
                )
                from google.oauth2 import service_account  # type: ignore[import-not-found]

                self._credentials = service_account.Credentials.from_service_account_file(
                    self.service_account_file,
                    scopes=FCM_SCOPES,
                )
                self._google_request = GoogleRequest()

            if not self._credentials.valid:
                self._credentials.refresh(self._google_request)
            return self._credentials.token  # type: ignore[no-any-return]
        except Exception as e:
            logger.error(f"FCM auth failed: {e}")
            return None

    async def _send_one(
        self,
        client: httpx.AsyncClient,
        token: str,
        title: str,
        body: str,
        data: Optional[dict] = None,
    ) -> tuple[bool, Optional[str]]:
        """Send to a single token. Returns (success, error_code)."""
        access_token = self._get_access_token()
        if not access_token:
            return False, "no_auth"

        message = {
            "message": {
                "token": token,
                "notification": {"title": title, "body": body},
                "android": {
                    "priority": "high",
                    "notification": {
                        "channel_id": "default",
                        "sound": "default",
                    },
                },
            }
        }
        if data:
            # FCM requires data values to be strings
            message["message"]["data"] = {k: str(v) for k, v in data.items()}

        url = FCM_ENDPOINT.format(project_id=self.project_id)
        try:
            resp = await client.post(
                url,
                json=message,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json; charset=UTF-8",
                },
                timeout=10.0,
            )
            if resp.status_code == 200:
                return True, None
            # Stale token — caller should delete it from DB
            try:
                err_body = resp.json()
                err_code = err_body.get("error", {}).get("details", [{}])[0].get("errorCode", "")
            except Exception:
                err_code = ""
            if resp.status_code == 404 or err_code == "UNREGISTERED":
                return False, "unregistered"
            logger.warning(f"FCM send failed ({resp.status_code}): {resp.text[:200]}")
            return False, f"http_{resp.status_code}"
        except Exception as e:
            logger.error(f"FCM send exception: {e}")
            return False, "exception"

    async def send_to_user(
        self, user_id: int, title: str, body: str, data: Optional[dict] = None
    ) -> int:
        """Send notification to all devices of a single user. Returns delivered count."""
        if not self.enabled:
            return 0

        async for session in get_async_session():
            tokens_res = await session.execute(
                select(MobilePushToken).where(MobilePushToken.user_id == user_id)
            )
            tokens = list(tokens_res.scalars().all())
            return await self._send_batch(session, tokens, title, body, data)
        return 0

    async def send_to_all(self, title: str, body: str, data: Optional[dict] = None) -> int:
        """Broadcast to all registered devices. Returns delivered count."""
        if not self.enabled:
            return 0

        async for session in get_async_session():
            tokens_res = await session.execute(select(MobilePushToken))
            tokens = list(tokens_res.scalars().all())
            return await self._send_batch(session, tokens, title, body, data)
        return 0

    async def _send_batch(
        self,
        session: AsyncSession,
        tokens: list[MobilePushToken],
        title: str,
        body: str,
        data: Optional[dict] = None,
    ) -> int:
        """Send to a batch of tokens, deleting unregistered ones."""
        if not tokens:
            return 0
        delivered = 0
        stale_ids: list[int] = []
        async with httpx.AsyncClient() as client:
            for t in tokens:
                ok, err = await self._send_one(client, t.token, title, body, data)
                if ok:
                    delivered += 1
                elif err == "unregistered":
                    stale_ids.append(t.id)
        if stale_ids:
            await session.execute(delete(MobilePushToken).where(MobilePushToken.id.in_(stale_ids)))
            await session.commit()
            logger.info(f"FCM: deleted {len(stale_ids)} stale tokens")
        return delivered

    async def register_token(
        self,
        user_id: int,
        token: str,
        platform: str = "android",
        app_version: Optional[str] = None,
        build_number: Optional[str] = None,
    ) -> None:
        """Register or update a device token for the given user.

        Uses INSERT OR REPLACE via SQLite's ON CONFLICT — same token just bumps last_seen.
        """
        async for session in get_async_session():
            # Ensure ownership: same token can only belong to latest registering user
            stmt = sqlite_insert(MobilePushToken).values(
                user_id=user_id,
                token=token,
                platform=platform,
                app_version=app_version,
                build_number=build_number,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[MobilePushToken.token],
                set_={
                    "user_id": user_id,
                    "platform": platform,
                    "app_version": app_version,
                    "build_number": build_number,
                },
            )
            await session.execute(stmt)
            await session.commit()

    async def unregister_user(self, user_id: int) -> None:
        """Delete all tokens for a user (called on logout)."""
        async for session in get_async_session():
            await session.execute(delete(MobilePushToken).where(MobilePushToken.user_id == user_id))
            await session.commit()


# Singleton
fcm_push_service = FcmPushService()

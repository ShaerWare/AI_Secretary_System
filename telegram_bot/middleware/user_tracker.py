"""User tracker middleware — registers Telegram users in the central DB."""

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable

import httpx
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


logger = logging.getLogger(__name__)


class UserTrackerMiddleware(BaseMiddleware):
    """Track unique Telegram users and register them in the orchestrator DB.

    On each message/callback, checks if the user is already known (in-memory set).
    For new users, fires a background HTTP POST to the orchestrator's register-user
    endpoint. This ensures every user who interacts with the bot gets a
    ``bot_subscribers`` + ``telegram_sessions`` record in the central DB.

    Only one HTTP call is made per unique user per bot process lifetime.
    """

    def __init__(self) -> None:
        super().__init__()
        self._known_users: set[int] = set()
        self._instance_id: str | None = os.environ.get("BOT_INSTANCE_ID")
        self._orchestrator_url: str = os.environ.get(
            "ORCHESTRATOR_URL", "http://localhost:8002"
        ).rstrip("/")
        self._internal_token: str | None = os.environ.get("BOT_INTERNAL_TOKEN")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not self._instance_id:
            # Standalone mode — skip tracking
            return await handler(event, data)

        user = None
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            user = event.from_user

        if user and user.id not in self._known_users:
            self._known_users.add(user.id)
            asyncio.create_task(
                self._register_user(
                    user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                )
            )

        return await handler(event, data)

    async def _register_user(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> None:
        """POST user info to the orchestrator (fire-and-forget)."""
        url = f"{self._orchestrator_url}/admin/telegram/instances/{self._instance_id}/register-user"
        headers: dict[str, str] = {}
        if self._internal_token:
            headers["Authorization"] = f"Bearer {self._internal_token}"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url,
                    json={
                        "user_id": user_id,
                        "username": username,
                        "first_name": first_name,
                        "last_name": last_name,
                    },
                    headers=headers,
                )
                resp.raise_for_status()
                logger.info(
                    "Registered user %s (@%s) for bot %s",
                    user_id,
                    username,
                    self._instance_id,
                )
        except Exception:
            # Remove from known set so we retry on next interaction
            self._known_users.discard(user_id)
            logger.warning(
                "Failed to register user %s for bot %s",
                user_id,
                self._instance_id,
                exc_info=True,
            )

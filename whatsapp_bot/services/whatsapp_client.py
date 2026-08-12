"""WhatsApp Cloud API client.

Async HTTP client for sending messages via Meta Graph API.
Docs: https://developers.facebook.com/docs/whatsapp/cloud-api
"""

import hashlib
import hmac
import logging
from typing import Any, Optional

import httpx


logger = logging.getLogger(__name__)

# WhatsApp message limits
MAX_TEXT_LENGTH = 4096
MAX_QUICK_REPLY_BUTTONS = 3
MAX_BUTTON_TITLE_LENGTH = 20
MAX_LIST_SECTIONS = 10
MAX_LIST_ROWS_PER_SECTION = 10


class WhatsAppClient:
    """Async HTTP client for WhatsApp Cloud API."""

    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        app_secret: str = "",
        api_version: str = "v21.0",
    ):
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.app_secret = app_secret
        self.api_version = api_version
        self.base_url = f"https://graph.facebook.com/{api_version}/{phone_number_id}"
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def _send(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a message via the WhatsApp API.

        Args:
            payload: Message payload (must include 'to' and message type fields)

        Returns:
            API response dict

        Raises:
            httpx.HTTPStatusError: On API error
        """
        client = await self._get_client()
        payload["messaging_product"] = "whatsapp"

        resp = await client.post(f"{self.base_url}/messages", json=payload)
        resp.raise_for_status()
        data = resp.json()

        logger.debug("WhatsApp API response: %s", data)
        return data

    async def send_text(self, to: str, text: str) -> dict[str, Any]:
        """Send a text message.

        Args:
            to: Recipient phone number (E.164 format, e.g. '79001234567')
            text: Message text (max 4096 chars)
        """
        return await self._send(
            {
                "to": to,
                "type": "text",
                "text": {"body": text[:MAX_TEXT_LENGTH]},
            }
        )

    async def send_buttons(
        self,
        to: str,
        body: str,
        buttons: list[dict[str, str]],
        header: str = "",
        footer: str = "",
    ) -> dict[str, Any]:
        """Send an interactive message with quick-reply buttons.

        Args:
            to: Recipient phone number
            body: Message body text
            buttons: List of {"id": "...", "title": "..."} (max 3)
            header: Optional header text
            footer: Optional footer text
        """
        action_buttons = [
            {
                "type": "reply",
                "reply": {
                    "id": btn["id"],
                    "title": btn["title"][:MAX_BUTTON_TITLE_LENGTH],
                },
            }
            for btn in buttons[:MAX_QUICK_REPLY_BUTTONS]
        ]

        interactive: dict[str, Any] = {
            "type": "button",
            "body": {"text": body},
            "action": {"buttons": action_buttons},
        }
        if header:
            interactive["header"] = {"type": "text", "text": header}
        if footer:
            interactive["footer"] = {"text": footer}

        return await self._send(
            {
                "to": to,
                "type": "interactive",
                "interactive": interactive,
            }
        )

    async def send_list(
        self,
        to: str,
        body: str,
        button_text: str,
        sections: list[dict[str, Any]],
        header: str = "",
        footer: str = "",
    ) -> dict[str, Any]:
        """Send an interactive list message.

        Args:
            to: Recipient phone number
            body: Message body text
            button_text: Text on the list-open button
            sections: List of {"title": "...", "rows": [{"id": "...", "title": "...", "description": "..."}]}
            header: Optional header text
            footer: Optional footer text
        """
        interactive: dict[str, Any] = {
            "type": "list",
            "body": {"text": body},
            "action": {
                "button": button_text,
                "sections": sections[:MAX_LIST_SECTIONS],
            },
        }
        if header:
            interactive["header"] = {"type": "text", "text": header}
        if footer:
            interactive["footer"] = {"text": footer}

        return await self._send(
            {
                "to": to,
                "type": "interactive",
                "interactive": interactive,
            }
        )

    async def send_template(
        self,
        to: str,
        template_name: str,
        language_code: str = "ru",
        components: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Send a template message (for 24h+ window).

        Args:
            to: Recipient phone number
            template_name: Pre-approved template name
            language_code: Template language code
            components: Optional template parameters
        """
        template: dict[str, Any] = {
            "name": template_name,
            "language": {"code": language_code},
        }
        if components:
            template["components"] = components

        return await self._send(
            {
                "to": to,
                "type": "template",
                "template": template,
            }
        )

    async def send_media(
        self,
        to: str,
        media_type: str,
        media_url: str,
        caption: str = "",
    ) -> dict[str, Any]:
        """Send a media message (image, audio, video, document).

        Args:
            to: Recipient phone number
            media_type: One of 'image', 'audio', 'video', 'document'
            media_url: Public URL of the media file
            caption: Optional caption text
        """
        media_payload: dict[str, Any] = {"link": media_url}
        if caption and media_type != "audio":
            media_payload["caption"] = caption

        return await self._send(
            {
                "to": to,
                "type": media_type,
                media_type: media_payload,
            }
        )

    async def mark_as_read(self, message_id: str) -> dict[str, Any]:
        """Mark a message as read (blue checkmarks).

        Args:
            message_id: The wamid of the message to mark as read
        """
        client = await self._get_client()
        resp = await client.post(
            f"{self.base_url}/messages",
            json={
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def get_media_url(self, media_id: str) -> str:
        """Get download URL for a media file.

        Args:
            media_id: The media ID from an incoming message

        Returns:
            Direct download URL (requires auth header)
        """
        client = await self._get_client()
        resp = await client.get(f"https://graph.facebook.com/{self.api_version}/{media_id}")
        resp.raise_for_status()
        return resp.json()["url"]

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify X-Hub-Signature-256 from incoming webhook.

        Args:
            payload: Raw request body bytes
            signature: Value of X-Hub-Signature-256 header

        Returns:
            True if signature is valid
        """
        if not self.app_secret:
            logger.warning("App secret not configured, skipping signature verification")
            return True

        expected = (
            "sha256="
            + hmac.new(
                self.app_secret.encode(),
                payload,
                hashlib.sha256,
            ).hexdigest()
        )
        return hmac.compare_digest(expected, signature)

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# ─── Singleton ─────────────────────────────────────────────────

# Either a WhatsAppClient or a BridgeClient — both share the same interface.
_client: Any = None


def get_whatsapp_client() -> Any:
    """Get or create the singleton WhatsApp client.

    Returns a :class:`WhatsAppClient` (Meta Cloud API) or a
    ``BridgeClient`` (self-hosted, QR-linked phone) depending on the instance's
    ``provider``. Both expose the same interface, so callers stay unaware.
    """
    global _client
    if _client is None:
        from ..state import get_bot_config

        bot_config = get_bot_config()

        if bot_config and bot_config.provider == "bridge":
            from .bridge_client import BridgeClient

            _client = BridgeClient(
                session_id=bot_config.instance_id,
                bridge_url=bot_config.bridge_url,
                bridge_token=bot_config.bridge_token,
            )
        elif bot_config:
            _client = WhatsAppClient(
                phone_number_id=bot_config.phone_number_id,
                access_token=bot_config.access_token,
                app_secret=bot_config.app_secret,
                api_version=bot_config.api_version,
            )
        else:
            from ..config import get_whatsapp_settings

            settings = get_whatsapp_settings()
            if settings.provider == "bridge":
                from .bridge_client import BridgeClient

                _client = BridgeClient(
                    session_id=settings.bridge_session_id or "default",
                    bridge_url=settings.bridge_url,
                    bridge_token=settings.bridge_token,
                )
            else:
                _client = WhatsAppClient(
                    phone_number_id=settings.phone_number_id,
                    access_token=settings.access_token,
                    app_secret=settings.app_secret,
                    api_version=settings.api_version,
                )
    return _client


def reset_whatsapp_client() -> None:
    """Drop the cached client so the next call rebuilds it (used by tests)."""
    global _client
    _client = None

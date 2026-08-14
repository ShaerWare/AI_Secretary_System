"""Client for the self-hosted WhatsApp bridge (`services/whatsapp-bridge`).

Drop-in replacement for :class:`~whatsapp_bot.services.whatsapp_client.WhatsAppClient`:
it exposes the same surface (``send_text``, ``send_buttons``, ``send_list``,
``send_media``, ``mark_as_read``, ``verify_webhook_signature``, ``close``) so
handlers, the sales funnel and the LLM router don't care which provider is
behind them.

Two behaviours differ from the Cloud API and are emulated here:

* **Interactive buttons / lists** — unavailable on a QR-linked phone, so they
  are rendered as a numbered text menu and the reply is mapped back to the
  original ``reply_id`` via :mod:`whatsapp_bot.services.choices`.
* **Templates** — a Cloud API concept (pre-approved 24h-window messages). The
  bridge has no such thing; the call degrades to a plain text send.
"""

import hashlib
import hmac
import logging
from typing import Any, Optional

import httpx

from . import choices
from .whatsapp_client import MAX_TEXT_LENGTH


logger = logging.getLogger(__name__)

# Prompt appended to an emulated menu so the user knows how to answer.
CHOICE_HINT = "_Ответьте номером варианта._"


def _render_menu(
    body: str,
    options: list[dict[str, str]],
    header: str = "",
    footer: str = "",
    groups: Optional[list[tuple[str, list[int]]]] = None,
) -> str:
    """Render a choice menu as WhatsApp-formatted text.

    Args:
        body: Main message text.
        options: Ordered ``[{"id", "title", "description"}]``.
        header: Optional bold header line.
        footer: Optional italic footer line.
        groups: Optional ``[(section_title, [option_index, ...])]`` grouping,
            where indices are 0-based positions in ``options``. Numbering stays
            continuous across sections so the user's reply is unambiguous.
    """
    parts: list[str] = []
    if header:
        parts.append(f"*{header}*")
    if body:
        parts.append(body)

    def render_option(position: int, option: dict[str, str]) -> str:
        line = f"*{position}.* {option.get('title', '')}"
        description = (option.get("description") or "").strip()
        if description:
            line += f"\n_{description}_"
        return line

    if groups:
        for section_title, indices in groups:
            lines = [f"*{section_title}*"] if section_title else []
            lines.extend(render_option(i + 1, options[i]) for i in indices)
            parts.append("\n".join(lines))
    else:
        parts.append("\n".join(render_option(i, opt) for i, opt in enumerate(options, start=1)))

    if footer:
        parts.append(f"_{footer}_")
    parts.append(CHOICE_HINT)

    return "\n\n".join(part for part in parts if part)


class BridgeClient:
    """Async client for one bridge session (== one linked phone)."""

    def __init__(
        self,
        session_id: str,
        bridge_url: str,
        bridge_token: str,
        timeout: float = 30.0,
    ):
        self.session_id = session_id
        self.bridge_url = bridge_url.rstrip("/")
        self.bridge_token = bridge_token
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    # ─── Plumbing ──────────────────────────────────────────────

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.bridge_url,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                headers={
                    "X-Bridge-Token": self.bridge_token,
                    "Content-Type": "application/json",
                },
                # The bridge is a local service; a system-wide VLESS proxy would
                # black-hole these calls (see CLAUDE.md "Known Issues" #4).
                trust_env=False,
            )
        return self._client

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        client = await self._get_client()
        resp = await client.request(method, f"/sessions/{self.session_id}{path}", **kwargs)
        resp.raise_for_status()
        if not resp.content:
            return {}
        data: dict[str, Any] = resp.json()
        return data

    # ─── Session control ───────────────────────────────────────

    async def start_session(
        self,
        webhook_url: str,
        force: bool = False,
        pairing_phone: Optional[str] = None,
    ) -> dict[str, Any]:
        """Open the WhatsApp socket and register where to deliver incoming messages.

        Args:
            webhook_url: Where the bridge should POST incoming messages.
            force: Human-initiated relink (the admin panel button). Only a forced
                start may discard revoked credentials and begin a fresh pairing —
                an automatic start must never do that, both to avoid wiping a
                working link and to keep a restarting bot from hammering WhatsApp
                with logins it will answer 401 to.
            pairing_phone: Link by an 8-character code typed on this number
                instead of by QR. Digits only, country code included.
        """
        payload: dict[str, Any] = {"webhook_url": webhook_url, "force": force}
        if pairing_phone:
            payload["pairing_phone"] = pairing_phone
        return await self._request("POST", "/start", json=payload)

    async def get_status(self) -> dict[str, Any]:
        """Current link state: idle / starting / qr / connected / disconnected / logged_out."""
        return await self._request("GET", "")

    async def stop_session(self) -> dict[str, Any]:
        """Close the socket, keeping credentials for a silent re-attach."""
        return await self._request("POST", "/stop")

    async def logout(self) -> dict[str, Any]:
        """Unlink the phone and wipe credentials — next start needs a new QR."""
        return await self._request("POST", "/logout")

    # ─── Sending ───────────────────────────────────────────────

    async def send_text(self, to: str, text: str) -> dict[str, Any]:
        """Send a text message."""
        return await self._request(
            "POST",
            "/messages",
            json={"to": to, "type": "text", "text": text[:MAX_TEXT_LENGTH]},
        )

    async def send_buttons(
        self,
        to: str,
        body: str,
        buttons: list[dict[str, str]],
        header: str = "",
        footer: str = "",
    ) -> dict[str, Any]:
        """Emulate quick-reply buttons as a numbered text menu.

        Unlike the Cloud API there is no 3-button ceiling here, so the full list
        is rendered.
        """
        options = [{"id": b["id"], "title": b["title"]} for b in buttons if b.get("id")]
        if not options:
            return await self.send_text(to, body)

        choices.remember(to, "button_reply", options)
        return await self.send_text(to, _render_menu(body, options, header, footer))

    async def send_list(
        self,
        to: str,
        body: str,
        button_text: str,
        sections: list[dict[str, Any]],
        header: str = "",
        footer: str = "",
    ) -> dict[str, Any]:
        """Emulate a list picker as a numbered text menu grouped by section.

        ``button_text`` (the label on the Cloud API's "open list" button) has no
        equivalent in plain text and is dropped.
        """
        options: list[dict[str, str]] = []
        groups: list[tuple[str, list[int]]] = []

        for section in sections:
            indices: list[int] = []
            for row in section.get("rows", []):
                if not row.get("id"):
                    continue
                indices.append(len(options))
                options.append(
                    {
                        "id": row["id"],
                        "title": row.get("title", ""),
                        "description": row.get("description", ""),
                    }
                )
            if indices:
                groups.append((section.get("title", ""), indices))

        if not options:
            return await self.send_text(to, body)

        choices.remember(to, "list_reply", options)
        return await self.send_text(to, _render_menu(body, options, header, footer, groups))

    async def send_media(
        self,
        to: str,
        media_type: str,
        media_url: str,
        caption: str = "",
    ) -> dict[str, Any]:
        """Send media by URL — the bridge streams it straight to WhatsApp.

        The URL must be reachable from the bridge process, not from the internet.
        """
        payload: dict[str, Any] = {"to": to, "type": media_type, "url": media_url}
        if caption and media_type != "audio":
            payload["caption"] = caption
        return await self._request("POST", "/messages", json=payload)

    async def send_template(
        self,
        to: str,
        template_name: str,
        language_code: str = "ru",
        components: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """No templates on a linked phone — degrade to plain text.

        A QR-linked account has no 24-hour messaging window and no template
        approval, so the concept simply doesn't apply.
        """
        logger.warning(
            "Templates are not supported by the bridge provider; sending template %r as plain text",
            template_name,
        )
        return await self.send_text(to, template_name)

    async def mark_as_read(self, message_id: str) -> dict[str, Any]:
        """Blue checkmarks for an incoming message."""
        return await self._request("POST", "/read", json={"message_id": message_id})

    async def send_presence(self, to: str, state: str = "composing") -> dict[str, Any]:
        """Show the typing indicator while the LLM is thinking."""
        return await self._request("POST", "/presence", json={"to": to, "state": state})

    async def download_media(self, message_id: str) -> tuple[bytes, str]:
        """Download media from an incoming message.

        Returns:
            ``(content, mimetype)``
        """
        client = await self._get_client()
        resp = await client.get(f"/sessions/{self.session_id}/media/{message_id}")
        resp.raise_for_status()
        return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

    # ─── Webhook auth ──────────────────────────────────────────

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify the ``X-Bridge-Signature`` HMAC on an incoming bridge webhook."""
        if not self.bridge_token:
            logger.warning("Bridge token not configured, skipping signature verification")
            return True

        expected = (
            "sha256=" + hmac.new(self.bridge_token.encode(), payload, hashlib.sha256).hexdigest()
        )
        return hmac.compare_digest(expected, signature or "")

    async def close(self) -> None:
        """Close the HTTP client (does not touch the WhatsApp session)."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

"""Admin-side access to the self-hosted WhatsApp bridge.

The orchestrator needs to drive the bridge for the *linking* flow — open a
session, show the QR, unlink the phone — while the bot subprocess drives it for
messaging. Both talk the same protocol, so the HTTP client is shared
(:class:`whatsapp_bot.services.bridge_client.BridgeClient`); this module only
resolves *where* the bridge lives and *which* secret to use.

Resolution order for both URL and token: the instance row first (lets one
deployment point different instances at different bridges), then the
environment. The token normally lives only in the environment so it isn't
duplicated into the database.
"""

import logging
import os
from typing import Any

from whatsapp_bot.services.bridge_client import BridgeClient


logger = logging.getLogger(__name__)

DEFAULT_BRIDGE_URL = "http://127.0.0.1:8005"
PROVIDER_BRIDGE = "bridge"
PROVIDER_CLOUD = "cloud"


def is_bridge_instance(instance: dict[str, Any]) -> bool:
    """True when this instance is served by the self-hosted provider."""
    return (instance.get("provider") or PROVIDER_CLOUD) == PROVIDER_BRIDGE


def resolve_bridge_url(instance: dict[str, Any]) -> str:
    return instance.get("bridge_url") or os.getenv("WHATSAPP_BRIDGE_URL") or DEFAULT_BRIDGE_URL


def resolve_bridge_token(instance: dict[str, Any]) -> str:
    return instance.get("bridge_token") or os.getenv("WHATSAPP_BRIDGE_TOKEN", "")


def bridge_webhook_url(instance: dict[str, Any]) -> str:
    """Where the bridge should deliver this instance's incoming messages.

    Points at the bot subprocess's own webhook server. The bot re-registers the
    same URL on startup, so linking a phone before the bot is running is fine.
    """
    host = os.getenv("WHATSAPP_BRIDGE_CALLBACK_HOST", "127.0.0.1")
    port = instance.get("webhook_port") or 8003
    return f"http://{host}:{port}/bridge/webhook"


def get_bridge_client(instance: dict[str, Any]) -> BridgeClient:
    """Build a client for this instance's bridge session.

    The session id is the instance id, so credentials on disk stay tied to the
    instance across restarts.
    """
    return BridgeClient(
        session_id=instance["id"],
        bridge_url=resolve_bridge_url(instance),
        bridge_token=resolve_bridge_token(instance),
    )

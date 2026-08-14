"""WhatsApp bot configuration."""

import asyncio
import logging
import os
from dataclasses import dataclass
from functools import lru_cache

import httpx
from pydantic import Field
from pydantic_settings import BaseSettings


logger = logging.getLogger(__name__)


class WhatsAppSettings(BaseSettings):
    """WhatsApp bot settings loaded from environment variables."""

    # Provider: "cloud" (Meta Cloud API) or "bridge" (self-hosted, QR-linked phone)
    provider: str = Field(default="cloud", alias="WHATSAPP_PROVIDER")

    # Self-hosted bridge (services/whatsapp-bridge)
    bridge_url: str = Field(default="http://127.0.0.1:8005", alias="WHATSAPP_BRIDGE_URL")
    bridge_token: str = Field(default="", alias="WHATSAPP_BRIDGE_TOKEN")
    bridge_session_id: str = Field(default="", alias="WHATSAPP_BRIDGE_SESSION_ID")
    # Host the bridge should call back on. Only needs changing when the bridge
    # runs somewhere the bot isn't (e.g. bridge in Docker, bot on the host).
    bridge_callback_host: str = Field(default="127.0.0.1", alias="WHATSAPP_BRIDGE_CALLBACK_HOST")

    # WhatsApp Cloud API credentials
    phone_number_id: str = Field(default="", alias="WHATSAPP_PHONE_NUMBER_ID")
    access_token: str = Field(default="", alias="WHATSAPP_ACCESS_TOKEN")
    verify_token: str = Field(default="", alias="WHATSAPP_VERIFY_TOKEN")
    app_secret: str = Field(default="", alias="WHATSAPP_APP_SECRET")

    # Graph API version
    api_version: str = Field(default="v21.0", alias="WHATSAPP_API_VERSION")

    # Webhook server
    webhook_host: str = Field(default="0.0.0.0", alias="WHATSAPP_WEBHOOK_HOST")
    webhook_port: int = Field(default=8003, alias="WHATSAPP_WEBHOOK_PORT")

    # Default model for new conversations
    default_model: str = Field(default="sonnet", alias="WHATSAPP_DEFAULT_MODEL")

    # System prompt for the assistant
    system_prompt: str = Field(
        default="You are a helpful assistant.", alias="WHATSAPP_SYSTEM_PROMPT"
    )

    # Session limits
    max_messages_per_session: int = Field(default=100, alias="WHATSAPP_MAX_MESSAGES")

    # Orchestrator connection
    orchestrator_url: str = Field(default="http://localhost:8002", alias="ORCHESTRATOR_URL")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_whatsapp_settings() -> WhatsAppSettings:
    """Get cached WhatsApp settings instance."""
    return WhatsAppSettings()


# ─── Multi-instance config ───────────────────────────────────────────────


@dataclass
class WhatsAppBotConfig:
    """Dynamic bot configuration loaded from orchestrator API.

    Used in multi-instance mode when WA_INSTANCE_ID is set.
    """

    instance_id: str
    phone_number_id: str
    access_token: str
    verify_token: str
    app_secret: str
    name: str = "WhatsApp Bot"
    # "cloud" (Meta Cloud API) or "bridge" (self-hosted, QR-linked phone)
    provider: str = "cloud"
    bridge_url: str = "http://127.0.0.1:8005"
    bridge_token: str = ""
    llm_backend: str = "vllm"
    system_prompt: str | None = None
    tts_enabled: bool = False
    tts_preset_id: str | None = None
    rate_limit_count: int = 30
    rate_limit_hours: int = 1
    auto_start: bool = False

    # Merged settings for convenience
    max_messages_per_session: int = 100
    api_version: str = "v21.0"
    webhook_port: int = 8003


def get_wa_instance_id() -> str | None:
    """Get WA_INSTANCE_ID from environment."""
    return os.environ.get("WA_INSTANCE_ID")


def get_orchestrator_url() -> str:
    """Get orchestrator URL from environment."""
    return os.environ.get("ORCHESTRATOR_URL", "http://localhost:8002")


async def load_config_from_api(
    instance_id: str, attempts: int = 6, base_delay: float = 2.0
) -> WhatsAppBotConfig:
    """Load WhatsApp bot configuration from orchestrator API.

    Auto-started bots are spawned from the orchestrator's own startup, before it
    accepts connections — and on a loaded instance that startup takes tens of
    seconds (RAG indexing). Without retrying, the very first request fails and
    the bot silently falls back to `.env`, i.e. to the wrong provider entirely.

    Args:
        instance_id: WhatsApp instance ID from database
        attempts: How many times to try before giving up
        base_delay: First backoff delay in seconds (doubles, capped at 15s)

    Returns:
        WhatsAppBotConfig with all settings from API

    Raises:
        httpx.HTTPError: If every attempt fails
    """
    api_url = get_orchestrator_url()
    url = f"{api_url}/admin/whatsapp/instances/{instance_id}"

    logger.info(f"Loading WhatsApp config from API: {url}")

    headers = {}
    internal_token = os.environ.get("WA_INTERNAL_TOKEN")
    if internal_token:
        headers["Authorization"] = f"Bearer {internal_token}"

    data = None
    for attempt in range(1, attempts + 1):
        try:
            # trust_env=False: a global HTTP_PROXY (VLESS) would route this
            # localhost call through the proxy and fail.
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                resp = await client.get(url, params={"include_token": "true"}, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            break
        except (httpx.HTTPError, ValueError) as e:
            if attempt == attempts:
                logger.error(f"Config load failed after {attempts} attempts: {e}")
                raise
            delay = min(base_delay * 2 ** (attempt - 1), 15.0)
            logger.warning(
                f"Config load attempt {attempt}/{attempts} failed ({e}); retrying in {delay:.0f}s"
            )
            await asyncio.sleep(delay)

    assert data is not None  # loop either breaks with data or raises

    instance = data["instance"]
    settings = get_whatsapp_settings()

    return WhatsAppBotConfig(
        instance_id=instance["id"],
        # The bridge is a host-level service: the instance row may override its
        # location, but the shared secret normally lives in the environment so
        # it isn't duplicated into the database.
        provider=instance.get("provider") or "cloud",
        bridge_url=instance.get("bridge_url") or settings.bridge_url,
        bridge_token=instance.get("bridge_token") or settings.bridge_token,
        phone_number_id=instance.get("phone_number_id") or "",
        # Absent for bridge instances, and for cloud instances whose token was
        # never filled in — the client surfaces that as an API error later.
        access_token=instance.get("access_token") or "",
        verify_token=instance.get("verify_token") or "",
        app_secret=instance.get("app_secret") or "",
        name=instance.get("name", "WhatsApp Bot"),
        llm_backend=instance.get("llm_backend", "vllm"),
        system_prompt=instance.get("system_prompt"),
        tts_enabled=instance.get("tts_enabled", False),
        tts_preset_id=instance.get("tts_preset_id"),
        rate_limit_count=instance.get("rate_limit_count", 30),
        rate_limit_hours=instance.get("rate_limit_hours", 1),
        auto_start=instance.get("auto_start", False),
        # Previously never carried over, so every instance silently listened on
        # the dataclass default — two instances would fight for the same port.
        webhook_port=instance.get("webhook_port") or settings.webhook_port,
    )

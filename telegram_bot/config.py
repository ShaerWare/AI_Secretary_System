"""Telegram bot configuration."""

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import httpx
from pydantic import Field
from pydantic_settings import BaseSettings


logger = logging.getLogger(__name__)


class TelegramSettings(BaseSettings):
    """Telegram bot settings loaded from environment variables."""

    # Bot token from @BotFather (optional in multi-instance mode where token comes from DB)
    bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")

    # Comma-separated list of allowed Telegram user IDs
    allowed_users: str = Field(default="", alias="TELEGRAM_ALLOWED_USERS")

    # Default model for new conversations
    default_model: str = Field(default="sonnet", alias="TELEGRAM_DEFAULT_MODEL")

    # System prompt for the assistant (inline or path to file)
    system_prompt: str = Field(
        default="You are a helpful assistant.", alias="TELEGRAM_SYSTEM_PROMPT"
    )

    # Path to system prompt file (overrides system_prompt if set)
    system_prompt_file: str | None = Field(default=None, alias="TELEGRAM_SYSTEM_PROMPT_FILE")

    def get_system_prompt(self) -> str:
        """Get system prompt from file or inline setting."""
        if self.system_prompt_file:
            try:
                with open(self.system_prompt_file, "r", encoding="utf-8") as f:
                    return f.read()
            except FileNotFoundError:
                pass
        return self.system_prompt

    # Minimum interval between message edits during streaming (seconds)
    stream_edit_interval: float = Field(default=1.5, alias="TELEGRAM_STREAM_EDIT_INTERVAL")

    # Minimum new characters before editing message during streaming
    stream_edit_min_chars: int = Field(default=100, alias="TELEGRAM_STREAM_EDIT_MIN_CHARS")

    # Bridge connection
    bridge_url: str = Field(default="http://127.0.0.1:8000", alias="BRIDGE_URL")
    bridge_api_key: str | None = Field(default=None, alias="BRIDGE_API_KEY")

    # Session limits
    max_messages_per_session: int = Field(default=100, alias="TELEGRAM_MAX_MESSAGES")

    # Sales funnel settings
    sales_db_path: str = Field(default="sales.db", alias="SALES_DB_PATH")
    sales_admin_ids: str = Field(default="", alias="SALES_ADMIN_IDS")
    sales_github_repo: str = Field(
        default="ShaerWare/AI_Secretary_System", alias="SALES_GITHUB_REPO"
    )

    # Repos to watch for news (comma-separated owner/repo)
    news_github_repos: str = Field(
        default="ShaerWare/AI_Secretary_System",
        alias="NEWS_GITHUB_REPOS",
    )

    # Payment settings (Telegram Payments API)
    # Get token from @BotFather -> Payments -> select provider
    payment_provider_token: str | None = Field(default=None, alias="TELEGRAM_PAYMENT_TOKEN")
    # Price in kopecks (5000 RUB = 500000 kopecks)
    payment_price_basic: int = Field(
        default=500000,
        alias="PAYMENT_PRICE_BASIC",  # 5000 RUB
    )
    payment_currency: str = Field(default="RUB", alias="PAYMENT_CURRENCY")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def get_admin_ids(self) -> set[int]:
        """Parse admin user IDs from comma-separated string."""
        if not self.sales_admin_ids.strip():
            return set()
        return {int(x.strip()) for x in self.sales_admin_ids.split(",") if x.strip().isdigit()}

    def get_allowed_user_ids(self) -> set[int]:
        """Parse allowed user IDs from comma-separated string."""
        if not self.allowed_users.strip():
            return set()
        ids = set()
        for part in self.allowed_users.split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
        return ids

    def get_news_repos(self) -> list[str]:
        """Parse NEWS_GITHUB_REPOS into a list of owner/repo strings."""
        return [r.strip() for r in self.news_github_repos.split(",") if r.strip()]


@lru_cache
def get_telegram_settings() -> TelegramSettings:
    """Get cached telegram settings instance."""
    return TelegramSettings()


# ─── Multi-instance API config ───────────────────────────────────────────────


@dataclass
class BotConfig:
    """Dynamic bot configuration loaded from orchestrator API.

    Used in multi-instance mode when BOT_INSTANCE_ID is set.
    """

    instance_id: str
    bot_token: str
    name: str = "Telegram Bot"
    llm_backend: str = "vllm"
    system_prompt: str | None = None
    action_buttons: list[dict[str, Any]] = field(default_factory=list)
    payment_provider_token: str | None = None
    payment_currency: str = "RUB"
    yoomoney_token: str | None = None
    auto_start: bool = False
    sales_funnel_enabled: bool = True

    # Merged settings from TelegramSettings for convenience
    stream_edit_interval: float = 1.5
    stream_edit_min_chars: int = 100
    max_messages_per_session: int = 100
    sales_db_path: str = "sales.db"
    admin_ids: set[int] = field(default_factory=set)


def get_bot_instance_id() -> str | None:
    """Get BOT_INSTANCE_ID from environment."""
    return os.environ.get("BOT_INSTANCE_ID")


def get_orchestrator_url() -> str:
    """Get orchestrator URL from environment."""
    return os.environ.get("ORCHESTRATOR_URL", "http://localhost:8002")


def load_config_from_file(instance_id: str) -> BotConfig | None:
    """Load bot config from pre-fetched JSON file (written by multi_bot_manager).

    Returns None if file not found or invalid.
    """
    import json
    from pathlib import Path

    config_file = os.environ.get("BOT_CONFIG_FILE")
    if not config_file:
        return None

    path = Path(config_file)
    if not path.exists():
        logger.warning(f"Config file not found: {config_file}")
        return None

    try:
        instance = json.loads(path.read_text())
        logger.info(f"Loaded config from file: {config_file}")

        # Parse action_buttons from JSON string if needed
        action_buttons = instance.get("action_buttons", [])
        if isinstance(action_buttons, str):
            action_buttons = json.loads(action_buttons) if action_buttons else []

        return BotConfig(
            instance_id=instance["id"],
            bot_token=instance["bot_token"],
            name=instance.get("name", "Telegram Bot"),
            llm_backend=instance.get("llm_backend", "vllm"),
            system_prompt=instance.get("system_prompt"),
            action_buttons=action_buttons,
            payment_provider_token=instance.get("payment_provider_token"),
            payment_currency=instance.get("payment_currency", "RUB"),
            yoomoney_token=instance.get("yoomoney_access_token"),
            auto_start=instance.get("auto_start", False),
            sales_funnel_enabled=instance.get("sales_funnel_enabled", True),
            admin_ids=set(),
        )
    except Exception as e:
        logger.warning(f"Failed to load config from file {config_file}: {e}")
        return None


async def load_config_from_api(instance_id: str, max_retries: int = 5) -> BotConfig:
    """Load bot configuration from orchestrator API.

    Args:
        instance_id: Bot instance ID from database
        max_retries: Number of retry attempts (orchestrator may still be starting)

    Returns:
        BotConfig with all settings from API

    Raises:
        httpx.HTTPError: If API request fails after all retries
    """
    import asyncio

    api_url = get_orchestrator_url()
    url = f"{api_url}/admin/telegram/instances/{instance_id}"

    logger.info(f"Loading bot config from API: {url}")

    # Use internal JWT token if available (passed by multi_bot_manager)
    headers = {}
    internal_token = os.environ.get("BOT_INTERNAL_TOKEN")
    if internal_token:
        headers["Authorization"] = f"Bearer {internal_token}"

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params={"include_token": "true"}, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                break
        except Exception as e:
            if attempt < max_retries:
                wait = attempt * 3
                logger.warning(
                    f"Config API attempt {attempt}/{max_retries} failed: {type(e).__name__}: {e}. "
                    f"Retrying in {wait}s..."
                )
                await asyncio.sleep(wait)
            else:
                logger.error(f"Config API failed after {max_retries} attempts: {e}")
                raise

    instance = data["instance"]

    # Parse admin IDs from config
    admin_ids_str = instance.get("config", {}).get("admin_ids", "")
    admin_ids = set()
    if admin_ids_str:
        admin_ids = {int(x.strip()) for x in admin_ids_str.split(",") if x.strip().isdigit()}

    return BotConfig(
        instance_id=instance["id"],
        bot_token=instance["bot_token"],
        name=instance.get("name", "Telegram Bot"),
        llm_backend=instance.get("llm_backend", "vllm"),
        system_prompt=instance.get("system_prompt"),
        action_buttons=instance.get("action_buttons", []),
        payment_provider_token=instance.get("payment_provider_token"),
        payment_currency=instance.get("payment_currency", "RUB"),
        yoomoney_token=instance.get("yoomoney_access_token"),
        auto_start=instance.get("auto_start", False),
        sales_funnel_enabled=instance.get("sales_funnel_enabled", True),
        admin_ids=admin_ids,
    )

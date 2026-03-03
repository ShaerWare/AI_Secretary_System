"""LLM models: cloud providers, presets, and defaults."""

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class CloudLLMProvider(Base):
    """Cloud LLM provider configuration (Gemini, Kimi, OpenAI, Claude, custom)"""

    __tablename__ = "cloud_llm_providers"

    id: Mapped[str] = mapped_column(
        String(50), primary_key=True
    )  # slug: "gemini-default", "kimi-prod"
    name: Mapped[str] = mapped_column(String(100), index=True)  # Display: "Gemini Pro", "Kimi K2"
    provider_type: Mapped[str] = mapped_column(
        String(50), index=True
    )  # gemini, kimi, openai, claude, custom

    # Credentials
    api_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    base_url: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )  # e.g., https://api.moonshot.ai/v1
    model_name: Mapped[str] = mapped_column(
        String(100), default=""
    )  # e.g., kimi-k2, gemini-2.0-flash

    # Status
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )

    # Extended configuration (JSON)
    config: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON: temperature, max_tokens, etc.

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def get_config(self) -> dict:
        """Get extended config as dict"""
        if not self.config:
            return {}
        try:
            result: dict = json.loads(self.config)
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_config(self, config: dict) -> None:
        """Set extended config from dict"""
        self.config = json.dumps(config, ensure_ascii=False)

    def to_dict(self, include_key: bool = False) -> dict:
        """Convert to dict for API response"""
        result = {
            "id": self.id,
            "name": self.name,
            "provider_type": self.provider_type,
            "api_key_masked": "***" + self.api_key[-4:]
            if self.api_key and len(self.api_key) > 4
            else "",
            "base_url": self.base_url,
            "model_name": self.model_name,
            "enabled": self.enabled,
            "is_default": self.is_default,
            "config": self.get_config(),
            "description": self.description,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
        if include_key and self.api_key:
            result["api_key"] = self.api_key
        return result


# Provider types configuration
PROVIDER_TYPES = {
    "gemini": {
        "name": "Google Gemini",
        "default_base_url": None,  # Uses SDK
        "default_models": ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"],
        "requires_base_url": False,
    },
    "kimi": {
        "name": "Moonshot Kimi",
        "default_base_url": "https://api.moonshot.ai/v1",
        "default_models": ["kimi-k2", "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "requires_base_url": True,
    },
    "openai": {
        "name": "OpenAI",
        "default_base_url": "https://api.openai.com/v1",
        "default_models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        "requires_base_url": True,
    },
    "claude": {
        "name": "Anthropic Claude",
        "default_base_url": "https://api.anthropic.com/v1",
        "default_models": ["claude-opus-4-5-20251101", "claude-sonnet-4-20250514"],
        "requires_base_url": True,
    },
    "deepseek": {
        "name": "DeepSeek",
        "default_base_url": "https://api.deepseek.com/v1",
        "default_models": ["deepseek-chat", "deepseek-coder"],
        "requires_base_url": True,
    },
    "openrouter": {
        "name": "OpenRouter",
        "default_base_url": "https://openrouter.ai/api/v1",
        "default_models": [
            "anthropic/claude-sonnet-4.6",
            "openai/gpt-4o",
            "google/gemini-2.5-pro",
            "google/gemini-2.5-flash",
            "deepseek/deepseek-chat-v3-0324",
            "openai/gpt-4o-mini",
            "qwen/qwen3-235b-a22b",
            "google/gemini-2.0-flash-001",
            "meta-llama/llama-4-maverick",
        ],
        "requires_base_url": True,
    },
    "custom": {
        "name": "Custom OpenAI-Compatible",
        "default_base_url": "",
        "default_models": [],
        "requires_base_url": True,
    },
    "claude_bridge": {
        "name": "Claude Bridge (Local CLI)",
        "default_base_url": "http://127.0.0.1:8787",
        "default_models": ["sonnet", "opus", "haiku"],
        "requires_base_url": False,
    },
}


class LLMPreset(Base):
    """LLM preset configuration for vLLM (generation parameters + system prompt)"""

    __tablename__ = "llm_presets"

    id: Mapped[str] = mapped_column(
        String(50), primary_key=True
    )  # slug: "anna", "marina", "creative"
    name: Mapped[str] = mapped_column(String(100), index=True)  # Display name
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # System prompt
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Generation parameters
    temperature: Mapped[float] = mapped_column(default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=512)
    top_p: Mapped[float] = mapped_column(default=0.9)
    repetition_penalty: Mapped[float] = mapped_column(default=1.1)

    # Status
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Timestamps
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "repetition_penalty": self.repetition_penalty,
            "is_default": self.is_default,
            "enabled": self.enabled,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }

    def get_params(self) -> dict:
        """Get generation parameters as dict"""
        return {
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "repetition_penalty": self.repetition_penalty,
        }


# Default LLM presets (synced with SECRETARY_PERSONAS from vllm_llm_service.py)
DEFAULT_LLM_PRESETS = [
    {
        "id": "anna",
        "name": "Анна",
        "description": "Анна - дружелюбная и профессиональная секретарь компании Shareware Digital",
        "system_prompt": (
            "Ты — Анна, цифровой секретарь компании Shareware Digital "
            "и личный помощник Артёма Юрьевича.\n\n"
            "ПРАВИЛА:\n"
            "1. Отвечай кратко (2-3 предложения максимум)\n"
            "2. Никакой разметки - только чистый текст\n"
            '3. Используй букву "ё" (всё, идёт, пришлёт)\n'
            "4. Числа пиши словами (пятьсот рублей)\n"
            '5. ООО произноси как "о-о-о", IT как "ай-ти"\n\n'
            "РОЛЬ:\n"
            "- Фильтруй спам и продажи\n"
            "- Записывай сообщения для Артёма Юрьевича\n"
            "- Будь профессиональной и дружелюбной\n\n"
            "ПРИМЕРЫ:\n"
            '- "Здравствуйте! Компания Шэарвэар Диджитал, помощник Артёма Юрьевича, Анна. '
            'Слушаю вас."\n'
            '- "Принято. Я передам Артёму Юрьевичу, что вы звонили."\n'
            '- "К сожалению, это предложение сейчас не актуально. Всего доброго."'
        ),
        "temperature": 0.7,
        "max_tokens": 512,
        "top_p": 0.9,
        "repetition_penalty": 1.1,
        "is_default": True,
    },
    {
        "id": "marina",
        "name": "Марина",
        "description": "Марина - строгая и формальная секретарь компании Shareware Digital",
        "system_prompt": (
            "Ты — Марина, цифровой секретарь компании Shareware Digital "
            "и личный помощник Артёма Юрьевича.\n\n"
            "ПРАВИЛА:\n"
            "1. Отвечай кратко (2-3 предложения максимум)\n"
            "2. Никакой разметки - только чистый текст\n"
            '3. Используй букву "ё" (всё, идёт, пришлёт)\n'
            "4. Числа пиши словами (пятьсот рублей)\n"
            '5. ООО произноси как "о-о-о", IT как "ай-ти"\n\n'
            "РОЛЬ:\n"
            "- Фильтруй спам и продажи\n"
            "- Записывай сообщения для Артёма Юрьевича\n"
            "- Будь профессиональной и дружелюбной\n\n"
            "ПРИМЕРЫ:\n"
            '- "Здравствуйте! Компания Шэарвэар Диджитал, помощник Артёма Юрьевича, Марина. '
            'Слушаю вас."\n'
            '- "Принято. Я передам Артёму Юрьевичу, что вы звонили."\n'
            '- "К сожалению, это предложение сейчас не актуально. Всего доброго."'
        ),
        "temperature": 0.5,
        "max_tokens": 512,
        "top_p": 0.85,
        "repetition_penalty": 1.15,
        "is_default": False,
    },
]

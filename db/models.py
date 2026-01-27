"""
SQLAlchemy ORM models for AI Secretary System.

Tables:
- chat_sessions: Chat session metadata
- chat_messages: Individual chat messages
- faq_entries: FAQ question-answer pairs
- tts_presets: Custom TTS voice presets
- system_config: Key-value system configuration
- telegram_sessions: Telegram user sessions (per bot instance)
- audit_log: System audit trail
- bot_instances: Telegram bot instances with individual configs
- widget_instances: Website widget instances with individual configs
- cloud_llm_providers: Cloud LLM provider configurations (Gemini, Kimi, OpenAI, etc.)
"""

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models"""

    pass


class ChatSession(Base):
    """Chat session with optional system prompt"""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="Новый чат")
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    messages: Mapped[List["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created",
    )

    def to_dict(self, include_messages: bool = True) -> dict:
        result = {
            "id": self.id,
            "title": self.title,
            "system_prompt": self.system_prompt,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
        if include_messages:
            result["messages"] = [m.to_dict() for m in self.messages]
        return result

    def to_summary(self) -> dict:
        """Return summary for list view"""
        messages = self.messages or []
        last_msg = messages[-1].content[:100] if messages else None
        return {
            "id": self.id,
            "title": self.title,
            "message_count": len(messages),
            "last_message": last_msg,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class ChatMessage(Base):
    """Individual message in a chat session"""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20))  # user, assistant, system
    content: Mapped[str] = mapped_column(Text)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")

    __table_args__ = (Index("ix_chat_messages_session_created", "session_id", "created"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "edited": self.edited,
            "timestamp": self.created.isoformat() if self.created else None,
        }


class FAQEntry(Base):
    """FAQ question-answer pair with fuzzy matching support"""

    __tablename__ = "faq_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    answer: Mapped[str] = mapped_column(Text)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "keywords": json.loads(self.keywords) if self.keywords else [],
            "enabled": self.enabled,
            "hit_count": self.hit_count,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }

    @classmethod
    def from_legacy(cls, question: str, answer: str) -> "FAQEntry":
        """Create from legacy JSON format (question: answer)"""
        return cls(question=question.lower(), answer=answer, enabled=True)


class TTSPreset(Base):
    """Custom TTS voice preset with parameters"""

    __tablename__ = "tts_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    params: Mapped[str] = mapped_column(Text)  # JSON object with TTS parameters
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "params": json.loads(self.params) if self.params else {},
            "builtin": self.builtin,
        }

    def get_params(self) -> dict:
        return json.loads(self.params) if self.params else {}

    def set_params(self, params: dict):
        self.params = json.dumps(params, ensure_ascii=False)


class SystemConfig(Base):
    """Key-value system configuration store"""

    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)  # JSON value
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def get_value(self) -> any:
        """Parse JSON value"""
        try:
            return json.loads(self.value)
        except (json.JSONDecodeError, TypeError):
            return self.value

    def set_value(self, value: any):
        """Serialize value to JSON"""
        self.value = json.dumps(value, ensure_ascii=False)


class TelegramSession(Base):
    """Telegram user session mapping (per bot instance)"""

    __tablename__ = "telegram_sessions"

    # Composite primary key: bot_id + user_id
    bot_id: Mapped[str] = mapped_column(String(50), primary_key=True, default="default")
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_session_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
    )
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (Index("ix_telegram_sessions_bot_user", "bot_id", "user_id"),)

    def to_dict(self) -> dict:
        return {
            "bot_id": self.bot_id,
            "user_id": self.user_id,
            "chat_session_id": self.chat_session_id,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class AuditLog(Base):
    """System audit trail for compliance"""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    action: Mapped[str] = mapped_column(
        String(50), index=True
    )  # create, update, delete, login, etc.
    resource: Mapped[str] = mapped_column(String(100))  # chat, faq, tts, config, etc.
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    user_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    __table_args__ = (Index("ix_audit_log_timestamp_action", "timestamp", "action"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "action": self.action,
            "resource": self.resource,
            "resource_id": self.resource_id,
            "user_id": self.user_id,
            "user_ip": self.user_ip,
            "details": json.loads(self.details) if self.details else None,
        }


class BotInstance(Base):
    """Telegram bot instance with individual configuration"""

    __tablename__ = "bot_instances"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # slug like "sales-bot"
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Telegram configuration
    bot_token: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    api_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Tunnel URL for API
    allowed_users: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    admin_users: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    welcome_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unauthorized_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    typing_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # AI configuration
    llm_backend: Mapped[str] = mapped_column(String(20), default="vllm")  # vllm or gemini
    llm_persona: Mapped[str] = mapped_column(String(50), default="gulya")
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_params: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON: temperature, etc.

    # TTS configuration
    tts_engine: Mapped[str] = mapped_column(String(20), default="xtts")  # xtts, piper, openvoice
    tts_voice: Mapped[str] = mapped_column(String(50), default="gulya")
    tts_preset: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Timestamps
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def get_allowed_users(self) -> List[int]:
        if not self.allowed_users:
            return []
        try:
            return json.loads(self.allowed_users)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_allowed_users(self, users: List[int]):
        self.allowed_users = json.dumps(users)

    def get_admin_users(self) -> List[int]:
        if not self.admin_users:
            return []
        try:
            return json.loads(self.admin_users)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_admin_users(self, users: List[int]):
        self.admin_users = json.dumps(users)

    def get_llm_params(self) -> dict:
        if not self.llm_params:
            return {}
        try:
            return json.loads(self.llm_params)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_llm_params(self, params: dict):
        self.llm_params = json.dumps(params, ensure_ascii=False)

    def to_dict(self, include_token: bool = False) -> dict:
        result = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            # Telegram
            "bot_token_masked": "***" + self.bot_token[-4:]
            if self.bot_token and len(self.bot_token) > 4
            else "",
            "api_url": self.api_url,
            "allowed_users": self.get_allowed_users(),
            "admin_users": self.get_admin_users(),
            "welcome_message": self.welcome_message,
            "unauthorized_message": self.unauthorized_message,
            "error_message": self.error_message,
            "typing_enabled": self.typing_enabled,
            # AI
            "llm_backend": self.llm_backend,
            "llm_persona": self.llm_persona,
            "system_prompt": self.system_prompt,
            "llm_params": self.get_llm_params(),
            # TTS
            "tts_engine": self.tts_engine,
            "tts_voice": self.tts_voice,
            "tts_preset": self.tts_preset,
            # Timestamps
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
        if include_token and self.bot_token:
            result["bot_token"] = self.bot_token
        return result


class WidgetInstance(Base):
    """Website widget instance with individual configuration"""

    __tablename__ = "widget_instances"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # slug like "support-widget"
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Appearance
    title: Mapped[str] = mapped_column(String(100), default="AI Ассистент")
    greeting: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    placeholder: Mapped[str] = mapped_column(String(200), default="Введите сообщение...")
    primary_color: Mapped[str] = mapped_column(String(20), default="#6366f1")
    position: Mapped[str] = mapped_column(String(20), default="right")  # left or right

    # Access control
    allowed_domains: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    tunnel_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # AI configuration
    llm_backend: Mapped[str] = mapped_column(String(20), default="vllm")
    llm_persona: Mapped[str] = mapped_column(String(50), default="gulya")
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_params: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # TTS configuration
    tts_engine: Mapped[str] = mapped_column(String(20), default="xtts")
    tts_voice: Mapped[str] = mapped_column(String(50), default="gulya")
    tts_preset: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Timestamps
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def get_allowed_domains(self) -> List[str]:
        if not self.allowed_domains:
            return []
        try:
            return json.loads(self.allowed_domains)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_allowed_domains(self, domains: List[str]):
        self.allowed_domains = json.dumps(domains)

    def get_llm_params(self) -> dict:
        if not self.llm_params:
            return {}
        try:
            return json.loads(self.llm_params)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_llm_params(self, params: dict):
        self.llm_params = json.dumps(params, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            # Appearance
            "title": self.title,
            "greeting": self.greeting,
            "placeholder": self.placeholder,
            "primary_color": self.primary_color,
            "position": self.position,
            # Access
            "allowed_domains": self.get_allowed_domains(),
            "tunnel_url": self.tunnel_url,
            # AI
            "llm_backend": self.llm_backend,
            "llm_persona": self.llm_persona,
            "system_prompt": self.system_prompt,
            "llm_params": self.get_llm_params(),
            # TTS
            "tts_engine": self.tts_engine,
            "tts_voice": self.tts_voice,
            "tts_preset": self.tts_preset,
            # Timestamps
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


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
            return json.loads(self.config)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_config(self, config: dict):
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
            "google/gemma-2-9b-it:free",
            "meta-llama/llama-3.2-3b-instruct:free",
            "qwen/qwen-2-7b-instruct:free",
            "mistralai/mistral-7b-instruct:free",
            "nousresearch/hermes-3-llama-3.1-405b:free",
        ],
        "requires_base_url": True,
    },
    "custom": {
        "name": "Custom OpenAI-Compatible",
        "default_base_url": "",
        "default_models": [],
        "requires_base_url": True,
    },
}

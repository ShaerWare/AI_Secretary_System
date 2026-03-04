"""Telegram channel models: bot instances, sessions, sales funnel, and defaults."""

import json
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


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


class BotInstance(Base):
    """Telegram bot instance with individual configuration"""

    __tablename__ = "bot_instances"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # slug like "sales-bot"
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    auto_start: Mapped[bool] = mapped_column(Boolean, default=False)  # Auto-start on app launch
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )

    # Telegram configuration
    bot_token: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    api_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Tunnel URL for API
    allowed_users: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    admin_users: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    welcome_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unauthorized_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    typing_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Action buttons configuration (JSON array)
    action_buttons: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # AI configuration
    llm_backend: Mapped[str] = mapped_column(String(20), default="vllm")  # vllm or gemini
    llm_persona: Mapped[str] = mapped_column(String(50), default="anna")
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_params: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON: temperature, etc.

    # TTS configuration
    tts_engine: Mapped[str] = mapped_column(String(20), default="xtts")  # xtts, piper, openvoice
    tts_voice: Mapped[str] = mapped_column(String(50), default="anna")
    tts_preset: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Payment configuration
    payment_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    yookassa_provider_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    stars_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_products: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    payment_success_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # RAG configuration
    rag_mode: Mapped[str] = mapped_column(String(20), default="all", server_default="all")
    knowledge_collection_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("knowledge_collections.id"), nullable=True
    )
    knowledge_collection_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Sales funnel
    sales_funnel_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    # Rate limiting
    rate_limit_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rate_limit_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # YooMoney OAuth2 configuration
    yoomoney_client_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    yoomoney_client_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    yoomoney_access_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    yoomoney_wallet_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    yoomoney_redirect_uri: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Timestamps
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def get_allowed_users(self) -> List[int]:
        if not self.allowed_users:
            return []
        try:
            result: List[int] = json.loads(self.allowed_users)
            return result
        except (json.JSONDecodeError, TypeError):
            return []

    def set_allowed_users(self, users: List[int]) -> None:
        self.allowed_users = json.dumps(users)

    def get_admin_users(self) -> List[int]:
        if not self.admin_users:
            return []
        try:
            result: List[int] = json.loads(self.admin_users)
            return result
        except (json.JSONDecodeError, TypeError):
            return []

    def set_admin_users(self, users: List[int]) -> None:
        self.admin_users = json.dumps(users)

    def get_llm_params(self) -> dict:
        if not self.llm_params:
            return {}
        try:
            result: dict = json.loads(self.llm_params)
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_llm_params(self, params: dict) -> None:
        self.llm_params = json.dumps(params, ensure_ascii=False)

    def get_action_buttons(self) -> List[dict]:
        """Get action buttons configuration."""
        if not self.action_buttons:
            return []
        try:
            result: List[dict] = json.loads(self.action_buttons)
            return result
        except (json.JSONDecodeError, TypeError):
            return []

    def set_action_buttons(self, buttons: List[dict]) -> None:
        """Set action buttons configuration."""
        self.action_buttons = json.dumps(buttons, ensure_ascii=False)

    def get_payment_products(self) -> List[dict]:
        """Get payment products configuration."""
        if not self.payment_products:
            return []
        try:
            result: List[dict] = json.loads(self.payment_products)
            return result
        except (json.JSONDecodeError, TypeError):
            return []

    def set_payment_products(self, products: List[dict]) -> None:
        """Set payment products configuration."""
        self.payment_products = json.dumps(products, ensure_ascii=False)

    def to_dict(self, include_token: bool = False) -> dict:
        result = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "auto_start": self.auto_start,
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
            # Action buttons
            "action_buttons": self.get_action_buttons(),
            # Payment
            "payment_enabled": self.payment_enabled,
            "yookassa_provider_token_masked": "***" + self.yookassa_provider_token[-4:]
            if self.yookassa_provider_token and len(self.yookassa_provider_token) > 4
            else "",
            "stars_enabled": self.stars_enabled,
            "payment_products": self.get_payment_products(),
            "payment_success_message": self.payment_success_message,
            # RAG
            "rag_mode": self.rag_mode,
            "knowledge_collection_id": self.knowledge_collection_id,
            "knowledge_collection_ids": json.loads(self.knowledge_collection_ids)
            if self.knowledge_collection_ids
            else None,
            # Sales funnel
            "sales_funnel_enabled": self.sales_funnel_enabled,
            # Rate limiting
            "rate_limit_count": self.rate_limit_count,
            "rate_limit_hours": self.rate_limit_hours,
            # YooMoney
            "yoomoney_client_id": self.yoomoney_client_id,
            "yoomoney_configured": bool(self.yoomoney_access_token),
            "yoomoney_wallet_id": self.yoomoney_wallet_id,
            # Timestamps
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
        if include_token and self.bot_token:
            result["bot_token"] = self.bot_token
        return result


# Default action buttons for Telegram bots (sales funnel)
# These match the keyboard layout in telegram_bot/sales/keyboards.py
DEFAULT_ACTION_BUTTONS = [
    {
        "id": "diy",
        "label": "Установить самостоятельно",
        "icon": "📦",
        "enabled": True,
        "order": 1,
        "row": 0,  # First row (single button)
        "llm_backend": None,
        "system_prompt": None,
        "llm_params": None,
    },
    {
        "id": "pay_5k",
        "label": "Оплата 5К",
        "icon": "💳",
        "enabled": True,
        "order": 2,
        "row": 1,  # Second row (3 buttons)
        "llm_backend": None,
        "system_prompt": None,
        "llm_params": None,
    },
    {
        "id": "support",
        "label": "Техподдержка",
        "icon": "🛠️",
        "enabled": True,
        "order": 3,
        "row": 1,
        "llm_backend": None,
        "system_prompt": None,
        "llm_params": None,
    },
    {
        "id": "wiki",
        "label": "Wiki",
        "icon": "📚",
        "enabled": True,
        "order": 4,
        "row": 1,
        "llm_backend": None,
        "system_prompt": None,
        "llm_params": None,
    },
    {
        "id": "ask",
        "label": "Задать вопрос",
        "icon": "❓",
        "enabled": True,
        "order": 5,
        "row": 2,  # Third row (3 buttons)
        "llm_backend": None,
        "system_prompt": (
            "Ты - AI-ассистент проекта AI Secretary. "
            "Отвечай на вопросы пользователей об установке, настройке, функционале системы. "
            "Будь полезен и конкретен."
        ),
        "llm_params": {"temperature": 0.7},
    },
    {
        "id": "news",
        "label": "Новости",
        "icon": "📰",
        "enabled": True,
        "order": 6,
        "row": 2,
        "llm_backend": None,
        "system_prompt": None,
        "llm_params": None,
    },
    {
        "id": "start",
        "label": "Старт",
        "icon": "🚀",
        "enabled": True,
        "order": 7,
        "row": 2,
        "llm_backend": None,
        "system_prompt": None,
        "llm_params": None,
    },
    {
        "id": "tz_calc",
        "label": "Рассчитать заказ",
        "icon": "📋",
        "enabled": True,
        "order": 8,
        "row": 3,  # Fourth row (single button)
        "llm_backend": None,
        "system_prompt": (
            "Ты - специалист по составлению технических заданий. "
            "Помоги пользователю сформулировать и структурировать ТЗ для проекта. "
            "Задавай уточняющие вопросы о целях, функционале, технических требованиях."
        ),
        "llm_params": {"temperature": 0.3, "max_tokens": 2048},
    },
]


# =============================================================================
# Sales Bot Models
# =============================================================================


class BotAgentPrompt(Base):
    """LLM agent prompt per bot instance and context (segment, funnel stage)."""

    __tablename__ = "bot_agent_prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    prompt_key: Mapped[str] = mapped_column(String(50), index=True)  # welcome, diy_techie, etc.
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text)
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=1024)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (Index("ix_bot_agent_prompts_bot_key", "bot_id", "prompt_key", unique=True),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "prompt_key": self.prompt_key,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "enabled": self.enabled,
            "order": self.order,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class BotQuizQuestion(Base):
    """Segmentation quiz question with answer options."""

    __tablename__ = "bot_quiz_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    question_key: Mapped[str] = mapped_column(String(50))  # tech_level, infrastructure
    text: Mapped[str] = mapped_column(Text)
    order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    options: Mapped[str] = mapped_column(
        Text
    )  # JSON: [{"label": "...", "value": "...", "icon": ""}]
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (Index("ix_bot_quiz_questions_bot_key", "bot_id", "question_key"),)

    def get_options(self) -> List[dict]:
        try:
            result: List[dict] = json.loads(self.options) if self.options else []
            return result
        except (json.JSONDecodeError, TypeError):
            return []

    def set_options(self, opts: List[dict]) -> None:
        self.options = json.dumps(opts, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "question_key": self.question_key,
            "text": self.text,
            "order": self.order,
            "enabled": self.enabled,
            "options": self.get_options(),
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class BotSegment(Base):
    """User segment definition with routing rules."""

    __tablename__ = "bot_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    segment_key: Mapped[str] = mapped_column(String(50))  # diy_ready, basic_hot, custom_warm
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    path: Mapped[str] = mapped_column(String(20))  # diy, basic, custom
    match_rules: Mapped[str] = mapped_column(
        Text
    )  # JSON: {"tech_level": "diy", "infrastructure": "gpu"}
    priority: Mapped[int] = mapped_column(Integer, default=0)
    agent_prompt_key: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_bot_segments_bot_key", "bot_id", "segment_key", unique=True),)

    def get_match_rules(self) -> dict:
        try:
            result: dict = json.loads(self.match_rules) if self.match_rules else {}
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_match_rules(self, rules: dict) -> None:
        self.match_rules = json.dumps(rules, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "segment_key": self.segment_key,
            "name": self.name,
            "description": self.description,
            "path": self.path,
            "match_rules": self.get_match_rules(),
            "priority": self.priority,
            "agent_prompt_key": self.agent_prompt_key,
            "enabled": self.enabled,
            "created": self.created.isoformat() if self.created else None,
        }


class BotUserProfile(Base):
    """User profile with FSM state, segment, quiz answers."""

    __tablename__ = "bot_user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # FSM state
    state: Mapped[str] = mapped_column(String(50), default="new")  # new, quiz_tech, idle, etc.
    segment: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # diy_ready, basic_hot
    path: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # diy, basic, custom

    # Quiz / discovery data
    quiz_answers: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    discovery_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    custom_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON extra data

    # Referral tracking
    ref_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # deeplink param

    # Follow-up control
    followup_optout: Mapped[bool] = mapped_column(Boolean, default=False)
    followup_ignore_count: Mapped[int] = mapped_column(Integer, default=0)
    last_followup_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Activity
    last_activity: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_bot_user_profiles_bot_user", "bot_id", "user_id", unique=True),
        Index("ix_bot_user_profiles_segment", "bot_id", "segment"),
        Index("ix_bot_user_profiles_state", "bot_id", "state"),
    )

    def _get_json(self, field: str) -> dict:
        val = getattr(self, field)
        if not val:
            return {}
        try:
            result: dict = json.loads(val)
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def _set_json(self, field: str, data: dict) -> None:
        setattr(self, field, json.dumps(data, ensure_ascii=False))

    def get_quiz_answers(self) -> dict:
        return self._get_json("quiz_answers")

    def set_quiz_answers(self, data: dict) -> None:
        self._set_json("quiz_answers", data)

    def get_discovery_data(self) -> dict:
        return self._get_json("discovery_data")

    def set_discovery_data(self, data: dict) -> None:
        self._set_json("discovery_data", data)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "user_id": self.user_id,
            "username": self.username,
            "first_name": self.first_name,
            "state": self.state,
            "segment": self.segment,
            "path": self.path,
            "quiz_answers": self.get_quiz_answers(),
            "discovery_data": self.get_discovery_data(),
            "ref_source": self.ref_source,
            "followup_optout": self.followup_optout,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class BotFollowupRule(Base):
    """Automated follow-up trigger rule."""

    __tablename__ = "bot_followup_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(100))
    trigger: Mapped[str] = mapped_column(String(50))  # clicked_github_no_return, inactive_7_days
    delay_hours: Mapped[int] = mapped_column(Integer, default=24)
    segment_filter: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # diy, basic, all
    message_template: Mapped[str] = mapped_column(Text)
    buttons: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON: [{"text","callback"}]
    max_sends: Mapped[int] = mapped_column(Integer, default=2)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def get_buttons(self) -> List[dict]:
        if not self.buttons:
            return []
        try:
            result: List[dict] = json.loads(self.buttons)
            return result
        except (json.JSONDecodeError, TypeError):
            return []

    def set_buttons(self, btns: List[dict]) -> None:
        self.buttons = json.dumps(btns, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "name": self.name,
            "trigger": self.trigger,
            "delay_hours": self.delay_hours,
            "segment_filter": self.segment_filter,
            "message_template": self.message_template,
            "buttons": self.get_buttons(),
            "max_sends": self.max_sends,
            "enabled": self.enabled,
            "order": self.order,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class BotFollowupQueue(Base):
    """Pending follow-up message in queue."""

    __tablename__ = "bot_followup_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    rule_id: Mapped[int] = mapped_column(Integer, index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )  # pending, sent, cancelled, failed
    send_count: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_bot_followup_queue_pending", "status", "scheduled_at"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "user_id": self.user_id,
            "rule_id": self.rule_id,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "status": self.status,
            "send_count": self.send_count,
            "created": self.created.isoformat() if self.created else None,
        }


class BotEvent(Base):
    """Funnel event tracking for analytics."""

    __tablename__ = "bot_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(
        String(50), index=True
    )  # start, quiz_completed, cta_clicked
    event_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (Index("ix_bot_events_bot_type_created", "bot_id", "event_type", "created"),)

    def get_event_data(self) -> dict:
        if not self.event_data:
            return {}
        try:
            result: dict = json.loads(self.event_data)
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "user_id": self.user_id,
            "event_type": self.event_type,
            "event_data": self.get_event_data(),
            "created": self.created.isoformat() if self.created else None,
        }


class BotTestimonial(Base):
    """Social proof testimonial."""

    __tablename__ = "bot_testimonials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    text: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(100), default="***")  # anonymized
    rating: Mapped[int] = mapped_column(Integer, default=5)  # 1-5
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "text": self.text,
            "author": self.author,
            "rating": self.rating,
            "enabled": self.enabled,
            "order": self.order,
            "created": self.created.isoformat() if self.created else None,
        }


class BotHardwareSpec(Base):
    """GPU model capabilities for hardware audit."""

    __tablename__ = "bot_hardware_specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    gpu_name: Mapped[str] = mapped_column(String(100))  # RTX 3060, GTX 1660
    gpu_vram_gb: Mapped[int] = mapped_column(Integer)  # 6, 8, 12, 24
    gpu_family: Mapped[str] = mapped_column(String(50))  # gtx_16xx, rtx_30xx, rtx_40xx
    recommended_llm: Mapped[str] = mapped_column(String(100))  # Qwen2.5-7B, Qwen-14B
    recommended_tts: Mapped[str] = mapped_column(String(50))  # xtts, piper, openvoice
    recommended_stt: Mapped[str] = mapped_column(String(50), default="whisper")
    quality_stars: Mapped[int] = mapped_column(Integer, default=3)  # 1-5
    speed_note: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "gpu_name": self.gpu_name,
            "gpu_vram_gb": self.gpu_vram_gb,
            "gpu_family": self.gpu_family,
            "recommended_llm": self.recommended_llm,
            "recommended_tts": self.recommended_tts,
            "recommended_stt": self.recommended_stt,
            "quality_stars": self.quality_stars,
            "speed_note": self.speed_note,
            "notes": self.notes,
            "enabled": self.enabled,
            "order": self.order,
        }


class BotAbTest(Base):
    """A/B test definition."""

    __tablename__ = "bot_ab_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(100))
    test_key: Mapped[str] = mapped_column(String(50))  # welcome_message, urgency_slots
    variants: Mapped[str] = mapped_column(Text)  # JSON: {"A": {...}, "B": {...}}
    metric: Mapped[str] = mapped_column(String(50))  # quiz_completion_rate, checkout_conversion
    min_sample: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    results: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON: per-variant stats
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (Index("ix_bot_ab_tests_bot_key", "bot_id", "test_key"),)

    def get_variants(self) -> dict:
        try:
            result: dict = json.loads(self.variants) if self.variants else {}
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_variants(self, data: dict) -> None:
        self.variants = json.dumps(data, ensure_ascii=False)

    def get_results(self) -> dict:
        if not self.results:
            return {}
        try:
            result: dict = json.loads(self.results)
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "name": self.name,
            "test_key": self.test_key,
            "variants": self.get_variants(),
            "metric": self.metric,
            "min_sample": self.min_sample,
            "active": self.active,
            "results": self.get_results(),
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class BotDiscoveryResponse(Base):
    """User's answers from custom path discovery flow."""

    __tablename__ = "bot_discovery_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    step: Mapped[int] = mapped_column(Integer)  # 1-5
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)  # free text or selected value
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_bot_discovery_bot_user", "bot_id", "user_id"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "user_id": self.user_id,
            "step": self.step,
            "question": self.question,
            "answer": self.answer,
            "created": self.created.isoformat() if self.created else None,
        }


class BotSubscriber(Base):
    """News/updates subscription for Telegram users."""

    __tablename__ = "bot_subscribers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    subscribed: Mapped[bool] = mapped_column(Boolean, default=True)
    subscribed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    unsubscribed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_bot_subscribers_bot_user", "bot_id", "user_id", unique=True),
        Index("ix_bot_subscribers_active", "bot_id", "subscribed"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "user_id": self.user_id,
            "username": self.username,
            "first_name": self.first_name,
            "subscribed": self.subscribed,
            "subscribed_at": self.subscribed_at.isoformat() if self.subscribed_at else None,
            "unsubscribed_at": self.unsubscribed_at.isoformat() if self.unsubscribed_at else None,
        }


class BotGithubConfig(Base):
    """GitHub webhook + PR comment configuration per bot instance."""

    __tablename__ = "bot_github_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    repo_owner: Mapped[str] = mapped_column(String(100), default="ShaerWare")
    repo_name: Mapped[str] = mapped_column(String(100), default="AI_Secretary_System")
    github_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    comment_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    broadcast_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    comment_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    broadcast_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    events: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON: ["opened","merged"]
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def get_events(self) -> List[str]:
        if not self.events:
            return ["opened", "merged"]
        try:
            result: List[str] = json.loads(self.events)
            return result
        except (json.JSONDecodeError, TypeError):
            return ["opened", "merged"]

    def set_events(self, evts: List[str]) -> None:
        self.events = json.dumps(evts)

    def to_dict(self, include_token: bool = False) -> dict:
        result: dict[str, Any] = {
            "id": self.id,
            "bot_id": self.bot_id,
            "repo_owner": self.repo_owner,
            "repo_name": self.repo_name,
            "github_token_masked": "***" + self.github_token[-4:]
            if self.github_token and len(self.github_token) > 4
            else "",
            "webhook_secret_masked": "***" if self.webhook_secret else "",
            "comment_enabled": self.comment_enabled,
            "broadcast_enabled": self.broadcast_enabled,
            "comment_prompt": self.comment_prompt,
            "broadcast_prompt": self.broadcast_prompt,
            "events": self.get_events(),
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
        if include_token:
            result["github_token"] = self.github_token
            result["webhook_secret"] = self.webhook_secret
        return result


# =============================================================================
# Default Sales Bot Data (seeded on first migration)
# =============================================================================

DEFAULT_AGENT_PROMPTS = [
    {
        "prompt_key": "welcome",
        "name": "Приветствие",
        "description": "Первое сообщение + social proof + приглашение в квиз",
        "system_prompt": (
            "Ты — AI-ассистент проекта AI Secretary от ShaerWare. "
            "Твоя задача — приветствовать нового пользователя, кратко рассказать о проекте "
            "(голосовой AI на своём сервере, без абонентки, клонирование голоса, работает офлайн), "
            "показать social proof (звёзды GitHub, отзывы) и пригласить пройти "
            "2-минутный квиз для подбора лучшего варианта. "
            "Тон: дружелюбный, уверенный, не навязчивый. Русский язык."
        ),
        "temperature": 0.7,
        "max_tokens": 512,
        "order": 1,
    },
    {
        "prompt_key": "diy_techie",
        "name": "DIY — Технарь",
        "description": "Для технически подкованных пользователей, которые хотят ставить сами",
        "system_prompt": (
            "Ты — технический консультант проекта AI Secretary. "
            "Пользователь — технарь, хочет установить систему самостоятельно. "
            "Давай технические детали: GPU требования, модели LLM, Docker-команды, "
            "конфигурацию. Ссылайся на GitHub (github.com/ShaerWare/AI_Secretary_System) "
            "и вики (github.com/ShaerWare/AI_Secretary_System/wiki). "
            "Предлагай поставить звезду на GitHub если проект полезен. "
            "Тон: технический, конкретный, без воды."
        ),
        "temperature": 0.3,
        "max_tokens": 1024,
        "order": 2,
    },
    {
        "prompt_key": "basic_busy",
        "name": "Basic — Занятой",
        "description": "Для пользователей, которые хотят готовое решение",
        "system_prompt": (
            "Ты — менеджер по продажам проекта AI Secretary. "
            "Пользователь хочет готовое решение, не хочет разбираться в технических деталях. "
            "Фокусируйся на: экономии (vs SaaS-боты 15K₽/мес), простоте установки (30 мин), "
            "приватности данных (152-ФЗ), отсутствии абонентки. "
            "Предлагай услугу установки. Показывай ROI. "
            "Тон: профессиональный, убедительный, с конкретными цифрами."
        ),
        "temperature": 0.7,
        "max_tokens": 768,
        "order": 3,
    },
    {
        "prompt_key": "custom_business",
        "name": "Custom — Бизнес",
        "description": "Для бизнес-клиентов с задачами интеграции",
        "system_prompt": (
            "Ты — бизнес-консультант проекта AI Secretary. "
            "Пользователь — представитель бизнеса, ему нужна кастомная интеграция "
            "(CRM, телефония, кастомные сценарии). "
            "Рассказывай о кейсах: автосалон -70% нагрузки, клиника +40% записей. "
            "Задавай квалифицирующие вопросы: задача, объём, интеграции, бюджет, сроки. "
            "Формируй предварительный расчёт. "
            "Тон: деловой, экспертный, с кейсами."
        ),
        "temperature": 0.5,
        "max_tokens": 1024,
        "order": 4,
    },
    {
        "prompt_key": "faq_answer",
        "name": "FAQ ответ",
        "description": "Точные ответы по документации проекта",
        "system_prompt": (
            "Ты — справочный бот проекта AI Secretary. "
            "Отвечай кратко и точно на вопросы о проекте, опираясь на документацию. "
            "Если не знаешь ответа — честно скажи и предложи посмотреть вики "
            "(github.com/ShaerWare/AI_Secretary_System/wiki) или задать вопрос автору. "
            "Русский язык. Максимум 3-4 предложения."
        ),
        "temperature": 0.2,
        "max_tokens": 512,
        "order": 5,
    },
    {
        "prompt_key": "hardware_audit",
        "name": "Аудит железа",
        "description": "Рекомендация модели LLM/TTS по характеристикам GPU",
        "system_prompt": (
            "Ты — технический эксперт по AI-инфраструктуре. "
            "На основе модели GPU пользователя рекомендуй оптимальную конфигурацию "
            "AI Secretary: модель LLM (Qwen/Llama/DeepSeek), TTS движок (XTTS/Piper), "
            "оценку качества (1-5 звёзд), скорость ответа. "
            "Если GPU слабая — предложи CPU-режим + Cloud LLM. "
            "Формат: структурированный список с emoji."
        ),
        "temperature": 0.2,
        "max_tokens": 768,
        "order": 6,
    },
    {
        "prompt_key": "roi_calculator",
        "name": "ROI калькулятор",
        "description": "Расчёт экономии vs SaaS-решения",
        "system_prompt": (
            "Ты — финансовый консультант. Рассчитай экономию от использования "
            "AI Secretary (self-hosted, разовая оплата 5000₽) vs типичного SaaS-бота "
            "(15000₽/мес). Покажи экономию за 1 год, 3 года. "
            "Добавь бонусы: приватность данных, работа офлайн, кастомизация, клонирование голоса. "
            "Формат: таблица сравнения + итог."
        ),
        "temperature": 0.3,
        "max_tokens": 768,
        "order": 7,
    },
    {
        "prompt_key": "discovery_summary",
        "name": "Итог discovery",
        "description": "Генерация коммерческого предложения по результатам discovery",
        "system_prompt": (
            "Ты — менеджер проектов. На основе ответов discovery-анкеты "
            "(задача, объём, интеграции, сроки, бюджет) сформируй предварительный расчёт. "
            "Укажи: что входит, стоимость каждого компонента, итоговую вилку цен, "
            "сроки реализации. Добавь пометку что это предварительная оценка. "
            "Формат: структурированное КП."
        ),
        "temperature": 0.4,
        "max_tokens": 1024,
        "order": 8,
    },
    {
        "prompt_key": "objection_price",
        "name": "Возражение: дорого",
        "description": "Работа с возражением по цене",
        "system_prompt": (
            "Пользователь считает цену высокой. Предложи альтернативы: "
            "1) MVP-версия без интеграций (дешевле), "
            "2) Поэтапное внедрение (оплата по частям), "
            "3) Self-hosted с консультацией (самый бюджетный). "
            "Не давить, а показать варианты. Тон: понимающий, гибкий."
        ),
        "temperature": 0.6,
        "max_tokens": 768,
        "order": 9,
    },
    {
        "prompt_key": "objection_nogpu",
        "name": "Возражение: нет GPU",
        "description": "Варианты работы без GPU",
        "system_prompt": (
            "У пользователя нет GPU. Предложи 3 варианта: "
            "1) CPU-режим + Cloud LLM (бесплатный tier Gemini), "
            "2) Аренда VPS с GPU (от 3000₽/мес), "
            "3) Свой мини-сервер (RTX 3060 б/у ~25000₽, окупается за 8 мес). "
            "Сравни плюсы и минусы каждого. Тон: помогающий."
        ),
        "temperature": 0.5,
        "max_tokens": 768,
        "order": 10,
    },
    {
        "prompt_key": "followup_gentle",
        "name": "Follow-up мягкий",
        "description": "Мягкое напоминание для follow-up сообщений",
        "system_prompt": (
            "Напиши мягкое follow-up сообщение для пользователя, который давно не заходил. "
            "Расскажи о новых фичах проекта, предложи помощь. "
            "Обязательно дай возможность отписаться. "
            "Максимум 3 предложения. Не навязывай."
        ),
        "temperature": 0.7,
        "max_tokens": 256,
        "order": 11,
    },
    {
        "prompt_key": "pr_comment",
        "name": "Комментарий к PR",
        "description": "AI-саммари для GitHub Pull Request",
        "system_prompt": (
            "Ты — AI-ассистент проекта AI Secretary. "
            "Напиши краткий информативный комментарий к Pull Request на русском. "
            "Формат: заголовок '## 🤖 AI Secretary Bot Summary', "
            "затем секции: 'Что изменилось' (3-5 буллетов), "
            "'Кому важно' (для каких пользователей), "
            "'Breaking changes' (есть или нет). "
            "В конце подпись: *Сгенерировано AI Secretary Bot*."
        ),
        "temperature": 0.3,
        "max_tokens": 1024,
        "order": 12,
    },
    {
        "prompt_key": "pr_news",
        "name": "Новость о PR",
        "description": "Telegram-рассылка о новом PR/обновлении",
        "system_prompt": (
            "Сформируй короткую новость для Telegram-подписчиков о новом обновлении проекта "
            "AI Secretary на основе Pull Request. 2-3 предложения, emoji уместны. "
            "Добавь ссылку на PR. Предложи поставить звезду на GitHub. "
            "Русский язык. Максимум 5 строк."
        ),
        "temperature": 0.6,
        "max_tokens": 256,
        "order": 13,
    },
    {
        "prompt_key": "general_chat",
        "name": "Свободный чат",
        "description": "Общение с AI-ассистентом вне воронки",
        "system_prompt": (
            "Ты — AI-ассистент проекта AI Secretary (github.com/ShaerWare/AI_Secretary_System). "
            "Отвечай на любые вопросы о проекте. Если вопрос не про проект — "
            "вежливо направь обратно. Ссылайся на вики и README. "
            "Автор проекта: github.com/ShaerWare. "
            "Тон: дружелюбный, компетентный."
        ),
        "temperature": 0.7,
        "max_tokens": 1024,
        "order": 14,
    },
]

DEFAULT_QUIZ_QUESTIONS = [
    {
        "question_key": "tech_level",
        "text": "📋 Вопрос 1 из 2\n\nКак вы относитесь к технической стороне?",
        "order": 1,
        "options": [
            {"label": "🛠️ Люблю сам разбираться в настройках", "value": "diy", "icon": "🛠️"},
            {"label": "🤝 Предпочитаю готовое решение", "value": "ready", "icon": "🤝"},
            {
                "label": "🏢 У меня бизнес-задача, нужна интеграция",
                "value": "business",
                "icon": "🏢",
            },
        ],
    },
    {
        "question_key": "infrastructure",
        "text": "📋 Вопрос 2 из 2\n\nЕсть ли у вас сервер для установки?",
        "order": 2,
        "options": [
            {"label": "✅ Да, есть сервер с GPU", "value": "gpu", "icon": "✅"},
            {"label": "💻 Есть сервер, но без GPU", "value": "cpu", "icon": "💻"},
            {"label": "❌ Нет сервера", "value": "none", "icon": "❌"},
            {"label": "🤷 Не знаю / Нужна консультация", "value": "unknown", "icon": "🤷"},
        ],
    },
]

DEFAULT_SEGMENTS = [
    # DIY path
    {
        "segment_key": "diy_ready",
        "name": "DIY Ready",
        "path": "diy",
        "match_rules": {"tech_level": "diy", "infrastructure": "gpu"},
        "agent_prompt_key": "diy_techie",
        "priority": 10,
    },
    {
        "segment_key": "diy_need_advice",
        "name": "DIY нужен совет",
        "path": "diy",
        "match_rules": {"tech_level": "diy", "infrastructure": "cpu"},
        "agent_prompt_key": "diy_techie",
        "priority": 9,
    },
    {
        "segment_key": "diy_need_hw",
        "name": "DIY нужно железо",
        "path": "diy",
        "match_rules": {"tech_level": "diy", "infrastructure": "none"},
        "agent_prompt_key": "diy_techie",
        "priority": 8,
    },
    {
        "segment_key": "diy_need_audit",
        "name": "DIY нужен аудит",
        "path": "diy",
        "match_rules": {"tech_level": "diy", "infrastructure": "unknown"},
        "agent_prompt_key": "diy_techie",
        "priority": 7,
    },
    # Basic path
    {
        "segment_key": "basic_hot",
        "name": "🔥 Basic горячий",
        "path": "basic",
        "match_rules": {"tech_level": "ready", "infrastructure": "gpu"},
        "agent_prompt_key": "basic_busy",
        "priority": 10,
    },
    {
        "segment_key": "basic_warm",
        "name": "Basic тёплый",
        "path": "basic",
        "match_rules": {"tech_level": "ready", "infrastructure": "cpu"},
        "agent_prompt_key": "basic_busy",
        "priority": 9,
    },
    {
        "segment_key": "basic_cold",
        "name": "Basic холодный",
        "path": "basic",
        "match_rules": {"tech_level": "ready", "infrastructure": "none"},
        "agent_prompt_key": "basic_busy",
        "priority": 8,
    },
    {
        "segment_key": "basic_audit",
        "name": "Basic аудит",
        "path": "basic",
        "match_rules": {"tech_level": "ready", "infrastructure": "unknown"},
        "agent_prompt_key": "basic_busy",
        "priority": 7,
    },
    # Custom path
    {
        "segment_key": "custom_hot",
        "name": "🔥 Custom горячий",
        "path": "custom",
        "match_rules": {"tech_level": "business", "infrastructure": "gpu"},
        "agent_prompt_key": "custom_business",
        "priority": 10,
    },
    {
        "segment_key": "custom_warm",
        "name": "Custom тёплый",
        "path": "custom",
        "match_rules": {"tech_level": "business", "infrastructure": "cpu"},
        "agent_prompt_key": "custom_business",
        "priority": 9,
    },
    {
        "segment_key": "custom_full",
        "name": "Custom под ключ",
        "path": "custom",
        "match_rules": {"tech_level": "business", "infrastructure": "none"},
        "agent_prompt_key": "custom_business",
        "priority": 10,
    },
    {
        "segment_key": "custom_discovery",
        "name": "Custom discovery",
        "path": "custom",
        "match_rules": {"tech_level": "business", "infrastructure": "unknown"},
        "agent_prompt_key": "custom_business",
        "priority": 8,
    },
]

DEFAULT_HARDWARE_SPECS = [
    {
        "gpu_name": "GTX 1660 Super",
        "gpu_vram_gb": 6,
        "gpu_family": "gtx_16xx",
        "recommended_llm": "Qwen2.5-3B",
        "recommended_tts": "openvoice",
        "quality_stars": 2,
        "speed_note": "~3-5 сек",
        "order": 1,
    },
    {
        "gpu_name": "GTX 1070/1080",
        "gpu_vram_gb": 8,
        "gpu_family": "gtx_10xx",
        "recommended_llm": "Qwen2.5-3B",
        "recommended_tts": "openvoice",
        "quality_stars": 2,
        "speed_note": "~3-4 сек",
        "order": 2,
    },
    {
        "gpu_name": "RTX 3060",
        "gpu_vram_gb": 12,
        "gpu_family": "rtx_30xx",
        "recommended_llm": "Qwen2.5-7B",
        "recommended_tts": "xtts",
        "quality_stars": 3,
        "speed_note": "~2 сек",
        "order": 3,
    },
    {
        "gpu_name": "RTX 3070",
        "gpu_vram_gb": 8,
        "gpu_family": "rtx_30xx",
        "recommended_llm": "Qwen2.5-7B-AWQ",
        "recommended_tts": "xtts",
        "quality_stars": 3,
        "speed_note": "~2 сек",
        "order": 4,
    },
    {
        "gpu_name": "RTX 3080",
        "gpu_vram_gb": 10,
        "gpu_family": "rtx_30xx",
        "recommended_llm": "Qwen2.5-7B",
        "recommended_tts": "xtts",
        "quality_stars": 3,
        "speed_note": "~1.5 сек",
        "order": 5,
    },
    {
        "gpu_name": "RTX 3090",
        "gpu_vram_gb": 24,
        "gpu_family": "rtx_30xx",
        "recommended_llm": "Qwen2.5-14B",
        "recommended_tts": "xtts",
        "quality_stars": 4,
        "speed_note": "~1.5 сек",
        "order": 6,
    },
    {
        "gpu_name": "RTX 4080",
        "gpu_vram_gb": 16,
        "gpu_family": "rtx_40xx",
        "recommended_llm": "Qwen2.5-14B-AWQ",
        "recommended_tts": "xtts",
        "quality_stars": 4,
        "speed_note": "~1 сек",
        "order": 7,
    },
    {
        "gpu_name": "RTX 4090",
        "gpu_vram_gb": 24,
        "gpu_family": "rtx_40xx",
        "recommended_llm": "Qwen2.5-32B-AWQ",
        "recommended_tts": "xtts",
        "quality_stars": 5,
        "speed_note": "~0.8 сек",
        "order": 8,
    },
]

DEFAULT_FOLLOWUP_RULES = [
    {
        "name": "GitHub без возврата (24ч)",
        "trigger": "clicked_github_no_return",
        "delay_hours": 24,
        "segment_filter": "diy",
        "message_template": (
            "👋 Привет! Как успехи с установкой AI Secretary?\n\n"
            "Если всё работает — буду рад звезде на GitHub ⭐\n\n"
            "Если застряли — напишите, помогу разобраться."
        ),
        "buttons": [
            {"text": "⭐ Всё работает!", "callback_data": "github_success"},
            {"text": "❓ Есть вопросы", "callback_data": "faq_ask"},
            {"text": "⚡ Установите за меня", "callback_data": "install_5k"},
        ],
        "max_sends": 2,
        "order": 1,
    },
    {
        "name": "Посмотрел цену (48ч)",
        "trigger": "viewed_price_no_action",
        "delay_hours": 48,
        "segment_filter": "basic",
        "message_template": (
            "👋 Вы интересовались установкой AI Secretary.\n\nМожет, остались вопросы?"
        ),
        "buttons": [
            {"text": "⚡ Хочу установить", "callback_data": "install_5k"},
            {"text": "❓ Есть вопросы", "callback_data": "faq_ask"},
            {"text": "❌ Не актуально", "callback_data": "followup_stop"},
        ],
        "max_sends": 2,
        "order": 2,
    },
    {
        "name": "Неактивный 7 дней",
        "trigger": "inactive_7_days",
        "delay_hours": 168,
        "segment_filter": None,
        "message_template": (
            "👋 Давно не виделись!\n\n"
            "Если AI Secretary всё ещё актуален — заходите, "
            "появились новые возможности."
        ),
        "buttons": [
            {"text": "📖 Что нового?", "callback_data": "changelog"},
            {"text": "🔔 Подписаться на обновления", "callback_data": "subscribe"},
            {"text": "❌ Отписаться", "callback_data": "unsubscribe"},
        ],
        "max_sends": 1,
        "order": 3,
    },
]

DEFAULT_TESTIMONIALS = [
    {
        "text": "Поставил за вечер, работает как часы. Клонировал свой голос — клиенты не отличают от живого!",
        "author": "Дмитрий, IT-компания",
        "rating": 5,
        "order": 1,
    },
    {
        "text": "Сэкономили 180К в год на SaaS-ботах. Окупилось за первый месяц.",
        "author": "Алексей, автосалон",
        "rating": 5,
        "order": 2,
    },
    {
        "text": "Отличный проект для тех, кто ценит приватность данных. Всё на своём сервере.",
        "author": "Мария, клиника",
        "rating": 4,
        "order": 3,
    },
]

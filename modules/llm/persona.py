"""Persona resolution — the live link between an ``LLMPreset`` and a conversation.

A *persona* is an ``LLMPreset`` row: a system prompt plus generation parameters
(temperature / max_tokens / top_p / repetition_penalty). Chat sessions and
channel instances (widget, mobile, Telegram bot) store only the preset id, so
the prompt and the parameters are read fresh on every message — editing a
persona in the LLM admin section immediately changes every conversation
attached to it, with no snapshot copies to keep in sync.

Resolution rules used by callers:

* prompt  — an explicit prompt on the session/instance wins; the persona's
  prompt fills the slot when that is empty; ``platform-agent.md`` remains the
  last resort (see ``modules.chat.facade``).
* params  — always come from the persona when one is attached; the LLM
  service's own runtime defaults apply when it is not.

An empty string and the literal ``"none"`` both mean "no persona" — instance
tables carry a NOT NULL column, so they cannot store SQL NULL.
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional


logger = logging.getLogger(__name__)

PARAM_KEYS = ("temperature", "max_tokens", "top_p", "repetition_penalty")

_NO_PERSONA_VALUES = {"", "none", "null"}


@dataclass(frozen=True)
class ResolvedPersona:
    """A persona resolved against the database."""

    id: str
    name: str
    system_prompt: Optional[str]
    params: dict

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "system_prompt": self.system_prompt,
            "params": dict(self.params),
        }


def normalize_persona_id(value: Any) -> Optional[str]:
    """Return a usable preset id, or None when nothing is attached."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if cleaned.lower() in _NO_PERSONA_VALUES:
        return None
    return cleaned


async def resolve_persona(persona_id: Any) -> Optional[ResolvedPersona]:
    """Load a persona by preset id. Returns None when absent or disabled.

    Never raises — a broken persona link must not take down a conversation.
    """
    preset_id = normalize_persona_id(persona_id)
    if not preset_id:
        return None

    from db.database import get_session_context
    from db.repositories.llm_preset import LLMPresetRepository

    try:
        async with get_session_context() as session:
            preset = await LLMPresetRepository(session).get_by_id(preset_id)
            if not preset:
                logger.warning(f"Persona '{preset_id}' not found — ignoring")
                return None
            if not preset.enabled:
                logger.info(f"Persona '{preset_id}' is disabled — ignoring")
                return None
            return ResolvedPersona(
                id=preset.id,
                name=preset.name,
                system_prompt=preset.system_prompt or None,
                params=preset.get_params(),
            )
    except Exception as e:
        logger.error(f"Persona '{preset_id}' resolution failed: {e}")
        return None


async def resolve_persona_for_instance(source: Any, source_id: Any) -> Optional[ResolvedPersona]:
    """Resolve the persona attached to the channel instance behind a session.

    ``source``/``source_id`` come from ``ChatSession``. Telegram sessions store
    ``"{instance_id}:{telegram_user_id}"`` as source_id, so only the leading
    segment identifies the bot instance.
    """
    if not source or not source_id:
        return None

    source = str(source)
    source_id = str(source_id)

    try:
        if source == "widget":
            from modules.channels.widget.service import widget_instance_service

            instance = await widget_instance_service.get_instance(source_id)
        elif source == "mobile":
            from modules.channels.mobile.service import mobile_app_instance_service

            instance = await mobile_app_instance_service.get_instance(source_id)
        elif source in ("telegram", "telegram_bot"):
            from modules.channels.telegram.service import bot_instance_service

            instance = await bot_instance_service.get_instance(source_id.split(":", 1)[0])
        else:
            return None
    except Exception as e:
        logger.error(f"Instance lookup failed for {source}/{source_id}: {e}")
        return None

    if not instance:
        return None
    return await resolve_persona(instance.get("llm_persona"))


def merge_params(base: Optional[dict], persona: Optional[ResolvedPersona]) -> dict:
    """Overlay a persona's generation parameters onto explicit per-call params.

    Explicit values win — a widget with its own ``llm_params`` keeps them.
    """
    merged: dict = {}
    if persona:
        merged.update({k: v for k, v in persona.params.items() if v is not None})
    if base:
        merged.update({k: v for k, v in base.items() if k in PARAM_KEYS and v is not None})
    return merged

"""Numbered-choice registry — button emulation for the self-hosted provider.

WhatsApp's interactive buttons and list pickers are a Cloud API feature; over
the multi-device protocol a linked phone can't render them. The bridge provider
therefore prints choices as a numbered list and maps the user's reply ("2",
"2)", or the option's own title) back to the original ``reply_id``, so the sales
funnel and FAQ navigation in ``handlers/interactive.py`` keep working unchanged.

State is per-process and per-phone, which matches the bot's own session model:
one subprocess serves one WhatsApp instance.
"""

import logging
import re
import time
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)

# A pending menu is only meaningful while the user is still looking at it.
CHOICE_TTL_SECONDS = 3600

# "2", "2)", "2.", "2 -", "№2", "вариант 2"
_NUMBER_RE = re.compile(r"^(?:№\s*|вариант\s+|option\s+)?(\d{1,2})\s*[).\-–—:]?$", re.IGNORECASE)


@dataclass
class PendingChoices:
    """Options currently shown to one user."""

    kind: str  # "button_reply" or "list_reply"
    by_number: dict[str, str] = field(default_factory=dict)
    by_title: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.monotonic)

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.created_at) > CHOICE_TTL_SECONDS


_pending: dict[str, PendingChoices] = {}


def remember(phone: str, kind: str, options: list[dict[str, str]]) -> None:
    """Record the options shown to ``phone``.

    Args:
        phone: Recipient phone number.
        kind: "button_reply" or "list_reply" — determines the payload shape
            handed to ``handle_interactive_reply``.
        options: Ordered ``[{"id": ..., "title": ...}]`` as displayed.
    """
    entry = PendingChoices(kind=kind)
    # Number only the options that survive filtering — the renderer drops
    # id-less rows too, so a shared counter keeps both views in step.
    position = 0
    for option in options:
        option_id = option.get("id", "")
        if not option_id:
            continue
        position += 1
        entry.by_number[str(position)] = option_id
        title = (option.get("title") or "").strip().lower()
        if title:
            entry.by_title[title] = option_id

    if entry.by_number:
        _pending[phone] = entry


def resolve(phone: str, text: str) -> tuple[str, str] | None:
    """Try to interpret ``text`` as a pick from the last menu shown to ``phone``.

    Returns ``(kind, reply_id)`` on a match, otherwise ``None`` — in which case
    the caller should treat the message as ordinary free text.
    """
    entry = _pending.get(phone)
    if entry is None:
        return None

    if entry.expired:
        _pending.pop(phone, None)
        return None

    candidate = (text or "").strip()
    if not candidate:
        return None

    match = _NUMBER_RE.match(candidate)
    if match:
        reply_id = entry.by_number.get(match.group(1))
        if reply_id:
            # Consume: the menu has been answered, further free text is free text.
            _pending.pop(phone, None)
            logger.info("Resolved numeric choice %r from %s → %s", candidate, phone, reply_id)
            return entry.kind, reply_id
        # A number outside the menu range is more likely a real message
        # ("нужно 5 штук") than a mis-click, so fall through to free text.
        return None

    reply_id = entry.by_title.get(candidate.lower())
    if reply_id:
        _pending.pop(phone, None)
        logger.info("Resolved title choice %r from %s → %s", candidate, phone, reply_id)
        return entry.kind, reply_id

    return None


def clear(phone: str) -> None:
    """Forget the pending menu for one user."""
    _pending.pop(phone, None)


def reset() -> None:
    """Drop all pending menus (used by tests)."""
    _pending.clear()

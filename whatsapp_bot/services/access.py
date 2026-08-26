"""Sender filtering for incoming WhatsApp messages.

Two guards live here, both of which the bot previously lacked:

* **Allow / block lists.** ``whatsapp_instances`` has carried
  ``allowed_phones`` and ``blocked_phones`` since the table was created, but
  nothing ever read them — an operator could fill them in and every message
  still went through. Matching is digit-based so "+7 708 544-20-89",
  "77085442089" and "8 (708) 544 20 89" are one entry, and it also accepts a
  verbatim address so an ``@lid`` sender (whose phone WhatsApp refuses to
  disclose) can be blocked at all.

* **Staleness.** On reconnect WhatsApp replays the offline queue. After a long
  outage that is a burst of days-old customer messages, and without a guard the
  assistant answers every one of them as if they had just arrived.
"""

import logging
import os
import re
import time
from typing import Iterable, Optional


logger = logging.getLogger(__name__)

_DIGITS = re.compile(r"\D+")

# 0 disables the check. Ten minutes is long enough to survive a bot restart or a
# slow webhook, short enough that a replayed offline queue is not answered.
DEFAULT_MAX_MESSAGE_AGE_SECONDS = 600


# Length of the national significant number in the RU/KZ plan: an operator will
# write "8 708 544 20 89" (domestic trunk prefix) for the very same number
# WhatsApp reports as "77085442089" (country code). Comparing the last N digits
# makes those one entry. It can in principle collide across countries sharing a
# suffix, which is an acceptable trade for a per-instance list an operator
# curates by hand — and far better than a block that silently does nothing.
_NSN_LENGTH = 10


def _digits(value: str) -> str:
    return _DIGITS.sub("", value or "")


def _same_number(a: str, b: str) -> bool:
    """True if two digit strings denote the same subscriber."""
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= _NSN_LENGTH and len(b) >= _NSN_LENGTH:
        return a[-_NSN_LENGTH:] == b[-_NSN_LENGTH:]
    return False


def _matches(entry: str, address: str, phone: Optional[str]) -> bool:
    """True if a configured list *entry* refers to this sender."""
    entry = (entry or "").strip()
    if not entry:
        return False

    # Verbatim match covers "@lid" addresses, which have no phone form.
    if entry == address:
        return True

    entry_digits = _digits(entry)
    if not entry_digits:
        return False
    return any(
        _same_number(entry_digits, candidate)
        for candidate in (_digits(address), _digits(phone or ""))
    )


def is_sender_allowed(
    address: str,
    phone: Optional[str],
    allowed: Optional[Iterable[str]],
    blocked: Optional[Iterable[str]],
) -> bool:
    """Decide whether a sender may talk to the assistant.

    Block wins over allow. An empty (or unset) allow list means "everyone",
    which keeps existing instances behaving exactly as before.

    Args:
        address: The repliable address — a phone number or an "@lid" JID.
        phone: The real number when WhatsApp disclosed one, else None.
        allowed: Configured allow list; empty/None disables the restriction.
        blocked: Configured block list.
    """
    for entry in blocked or ():
        if _matches(entry, address, phone):
            return False

    allow_list = [e for e in (allowed or ()) if str(e).strip()]
    if not allow_list:
        return True

    return any(_matches(entry, address, phone) for entry in allow_list)


def max_message_age_seconds() -> int:
    """Configured staleness threshold; 0 disables the check."""
    raw = os.environ.get("WHATSAPP_MAX_MESSAGE_AGE", "").strip()
    if not raw:
        return DEFAULT_MAX_MESSAGE_AGE_SECONDS
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning("Invalid WHATSAPP_MAX_MESSAGE_AGE=%r, using default", raw)
        return DEFAULT_MAX_MESSAGE_AGE_SECONDS


def is_stale(timestamp: Optional[int], now: Optional[float] = None) -> bool:
    """True if a message is old enough to be a replayed offline delivery.

    A missing or zero timestamp is treated as fresh: dropping messages the
    bridge could not stamp would be worse than answering one late.
    """
    limit = max_message_age_seconds()
    if not limit or not timestamp:
        return False

    age = (now if now is not None else time.time()) - float(timestamp)
    return age > limit

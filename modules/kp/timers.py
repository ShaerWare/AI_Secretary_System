"""When a КП timer is due — pure functions, no DB, so the rules are testable.

Times are naive UTC like the rest of the DB. Validity is a calendar date in the
client's time zone (Kazakhstan, UTC+5 by default): an offer «до 30.10» is valid
through the whole of 30.10 local time.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

from modules.kp.models import (
    OPEN_STATUSES,
    STATUS_CLARIFICATION,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENT,
    STATUS_VIEWED,
    TRIGGER_BEFORE_EXPIRY,
    TRIGGER_EXPIRED,
    TRIGGER_NOT_APPROVED,
    TRIGGER_NOT_VIEWED,
    TRIGGER_VIEWED_NO_REPLY,
)


DEFAULT_TZ_OFFSET_HOURS = 5

# Statuses that turn into «expired» once validity is over: a draft can't be
# sent any more, an open offer can't be accepted at the old prices.
EXPIRABLE = (STATUS_PENDING, STATUS_FAILED, *OPEN_STATUSES)


@dataclass
class QuoteTimes:
    status: str
    created: datetime
    sent_at: Optional[datetime]
    viewed_at: Optional[datetime]
    valid_until: Optional[date]


def local_today(now: datetime, tz_offset_hours: float = DEFAULT_TZ_OFFSET_HOURS) -> date:
    return (now + timedelta(hours=tz_offset_hours)).date()


def valid_until_for(
    valid_days: int, now: datetime, tz_offset_hours: float = DEFAULT_TZ_OFFSET_HOURS
) -> date:
    """«Действует N дней» → last valid calendar day. N=1 means «до завтра»."""
    return local_today(now, tz_offset_hours) + timedelta(days=max(int(valid_days), 0))


def deadline(
    valid_until: Optional[date], tz_offset_hours: float = DEFAULT_TZ_OFFSET_HOURS
) -> Optional[datetime]:
    """First moment (UTC) the offer is no longer valid: next local midnight."""
    if not valid_until:
        return None
    return datetime.combine(valid_until + timedelta(days=1), time()) - timedelta(
        hours=tz_offset_hours
    )


def is_expired(
    valid_until: Optional[date], now: datetime, tz_offset_hours: float = DEFAULT_TZ_OFFSET_HOURS
) -> bool:
    end = deadline(valid_until, tz_offset_hours)
    return bool(end and now >= end)


def rule_due(
    rule: dict[str, Any],
    q: QuoteTimes,
    now: datetime,
    tz_offset_hours: float = DEFAULT_TZ_OFFSET_HOURS,
) -> bool:
    """Is this rule's moment reached for this quote?

    Only the moment — dedup (fire once) is the caller's job.
    """
    offset = timedelta(hours=float(rule.get("offset_hours") or 0))
    trigger = rule.get("trigger")
    end = deadline(q.valid_until, tz_offset_hours)

    if trigger == TRIGGER_NOT_APPROVED:
        return q.status in (STATUS_PENDING, STATUS_FAILED) and now >= q.created + offset

    if trigger == TRIGGER_NOT_VIEWED:
        return q.status == STATUS_SENT and bool(q.sent_at) and now >= q.sent_at + offset  # type: ignore[operator]

    if trigger == TRIGGER_VIEWED_NO_REPLY:
        if q.status not in (STATUS_VIEWED, STATUS_CLARIFICATION) or not q.viewed_at:
            return False
        # After expiry the question is no longer «any questions?» but «reissue?».
        return now >= q.viewed_at + offset and not (end and now >= end)

    if trigger == TRIGGER_BEFORE_EXPIRY:
        if q.status not in OPEN_STATUSES or not end:
            return False
        window_start = end - offset
        # A 1-day offer sent in the evening is already inside a 6-hour window:
        # a «prices end soon» reminder an hour after sending would be noise.
        sent = q.sent_at or q.created
        if window_start <= sent:
            return False
        return window_start <= now < end

    if trigger == TRIGGER_EXPIRED:
        if q.status != STATUS_EXPIRED or not end:
            return False
        # Offers imported already expired were not watched while they were
        # alive — acting on them now («closed as lost») would surprise people.
        if end <= q.created:
            return False
        return now >= end + offset

    return False


def dedup_key(rule_id: int, valid_until: Optional[date]) -> str:
    """Once per rule and validity period: a prolonged offer gets its reminders again."""
    return f"rule:{rule_id}:{valid_until.isoformat() if valid_until else '-'}"


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


def render(template: str, values: dict[str, Any]) -> str:
    """``str.format`` that leaves unknown placeholders empty instead of failing.

    ``{link}`` is kept as is: the link exists only once the offer is published,
    and the outbound queue fills it in at sending time.
    """
    data = _SafeDict({k: ("" if v is None else v) for k, v in values.items()})
    if not data.get("link"):
        data["link"] = "{link}"
    try:
        return (template or "").format_map(data)
    except (ValueError, IndexError):  # a stray «{» in hand-written text
        return template or ""

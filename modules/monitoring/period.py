"""Billing period helpers for usage tracking.

Anthropic Claude Max subscription is billed monthly anchored to a specific
day-of-month. This module computes the [start, end) bounds of the current
period given an anchor day.

For months without the anchor day (e.g. anchor=30 in February), the anchor
falls on the last day of that month.
"""

from calendar import monthrange
from datetime import datetime
from typing import Optional


DEFAULT_ANCHOR_DAY = 30


def _anchor_in_month(year: int, month: int, day: int) -> datetime:
    """Return datetime for `day` in (year, month), capped to last day of month."""
    last_day = monthrange(year, month)[1]
    return datetime(year, month, min(day, last_day))


def current_period_bounds(
    anchor_day: int = DEFAULT_ANCHOR_DAY,
    now: Optional[datetime] = None,
) -> tuple[datetime, datetime]:
    """Return (start, end) of the current billing period.

    Period is half-open: [start, end). On the anchor day itself, the new
    period has just started.
    """
    now = now or datetime.utcnow()

    this_month_anchor = _anchor_in_month(now.year, now.month, anchor_day)

    if now >= this_month_anchor:
        start = this_month_anchor
        ny, nm = (now.year, now.month + 1) if now.month < 12 else (now.year + 1, 1)
        end = _anchor_in_month(ny, nm, anchor_day)
    else:
        py, pm = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
        start = _anchor_in_month(py, pm, anchor_day)
        end = this_month_anchor

    return start, end

"""Когда срабатывает таймер КП — чистые функции, без базы.

Срок КП — календарная дата по времени клиента (Казахстан, UTC+5): «до 30.10»
значит весь день 30.10 по Алматы.
"""

from datetime import date, datetime

from modules.kp import timers
from modules.kp.models import (
    STATUS_EXPIRED,
    STATUS_PENDING,
    STATUS_SENT,
    STATUS_VIEWED,
    TRIGGER_BEFORE_EXPIRY,
    TRIGGER_EXPIRED,
    TRIGGER_NOT_APPROVED,
    TRIGGER_NOT_VIEWED,
    TRIGGER_VIEWED_NO_REPLY,
)


def _q(status, created, sent_at=None, viewed_at=None, valid_until=None):
    return timers.QuoteTimes(status, created, sent_at, viewed_at, valid_until)


def test_valid_until_counts_local_calendar_days():
    # 20:30 UTC 28.10 — уже 01:30 29.10 в Алматы
    now = datetime(2026, 10, 28, 20, 30)
    assert timers.valid_until_for(1, now) == date(2026, 10, 30)
    assert timers.valid_until_for(3, datetime(2026, 10, 28, 10, 0)) == date(2026, 10, 31)


def test_offer_is_valid_through_the_whole_last_day_local_time():
    vu = date(2026, 10, 30)
    # 23:59 по Алматы 30.10 = 18:59 UTC
    assert not timers.is_expired(vu, datetime(2026, 10, 30, 18, 59))
    assert timers.is_expired(vu, datetime(2026, 10, 30, 19, 0))


def test_not_approved_fires_after_offset_only_for_drafts():
    created = datetime(2026, 10, 28, 6, 0)
    rule = {"trigger": TRIGGER_NOT_APPROVED, "offset_hours": 2}
    assert not timers.rule_due(rule, _q(STATUS_PENDING, created), datetime(2026, 10, 28, 7, 59))
    assert timers.rule_due(rule, _q(STATUS_PENDING, created), datetime(2026, 10, 28, 8, 0))
    assert not timers.rule_due(rule, _q(STATUS_SENT, created), datetime(2026, 10, 28, 9, 0))


def test_not_viewed_counts_from_sending():
    rule = {"trigger": TRIGGER_NOT_VIEWED, "offset_hours": 12}
    q = _q(STATUS_SENT, datetime(2026, 10, 27), sent_at=datetime(2026, 10, 28, 6, 0))
    assert not timers.rule_due(rule, q, datetime(2026, 10, 28, 17, 0))
    assert timers.rule_due(rule, q, datetime(2026, 10, 28, 18, 0))


def test_viewed_no_reply_stops_at_expiry():
    rule = {"trigger": TRIGGER_VIEWED_NO_REPLY, "offset_hours": 12}
    q = _q(
        STATUS_VIEWED,
        datetime(2026, 10, 28, 5, 0),
        sent_at=datetime(2026, 10, 28, 5, 0),
        viewed_at=datetime(2026, 10, 28, 6, 0),
        valid_until=date(2026, 10, 29),  # истекает 29.10 19:00 UTC
    )
    assert timers.rule_due(rule, q, datetime(2026, 10, 28, 18, 0))
    # после окончания срока вопрос уже «перевыпустить?», а не «есть вопросы?»
    assert not timers.rule_due(rule, q, datetime(2026, 10, 29, 19, 0))


def test_before_expiry_is_silent_when_offer_was_sent_inside_the_window():
    rule = {"trigger": TRIGGER_BEFORE_EXPIRY, "offset_hours": 6}
    vu = date(2026, 10, 28)  # конец — 28.10 19:00 UTC, окно с 13:00 UTC
    late = _q(
        STATUS_SENT, datetime(2026, 10, 28, 14), sent_at=datetime(2026, 10, 28, 14), valid_until=vu
    )
    assert not timers.rule_due(rule, late, datetime(2026, 10, 28, 15, 0))

    early = _q(
        STATUS_SENT, datetime(2026, 10, 27, 5), sent_at=datetime(2026, 10, 27, 5), valid_until=vu
    )
    assert not timers.rule_due(rule, early, datetime(2026, 10, 28, 12, 59))
    assert timers.rule_due(rule, early, datetime(2026, 10, 28, 13, 0))
    assert not timers.rule_due(rule, early, datetime(2026, 10, 28, 19, 0))


def test_expired_rule_ignores_offers_imported_already_expired():
    rule = {"trigger": TRIGGER_EXPIRED, "offset_hours": 72}
    vu = date(2026, 10, 10)
    imported_late = _q(STATUS_EXPIRED, datetime(2026, 10, 28), valid_until=vu)
    assert not timers.rule_due(rule, imported_late, datetime(2026, 11, 30))

    watched = _q(
        STATUS_EXPIRED, datetime(2026, 10, 8), sent_at=datetime(2026, 10, 8), valid_until=vu
    )
    assert not timers.rule_due(rule, watched, datetime(2026, 10, 13, 18, 0))
    assert timers.rule_due(rule, watched, datetime(2026, 10, 13, 19, 0))


def test_dedup_key_changes_when_offer_is_prolonged():
    assert timers.dedup_key(5, date(2026, 10, 30)) != timers.dedup_key(5, date(2026, 11, 2))


def test_render_keeps_link_placeholder_and_tolerates_unknown_keys():
    text = timers.render(
        "КП {number} до {valid_until}: {link} {unknown}",
        {"number": "КП-0042", "valid_until": "30.10.2026", "link": ""},
    )
    assert text == "КП КП-0042 до 30.10.2026: {link} "
    assert timers.render("кривой { шаблон", {}) == "кривой { шаблон"

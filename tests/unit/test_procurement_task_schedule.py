"""Расписание суточных задач procurement.

`TaskRegistry` крона не умеет, поэтому задачи сами считают, сколько спать до
нужного часа UTC. Ошибка тут не падает, а тихо сдвигает синк на сутки —
ровно так офферы поставщиков и простояли с 24.07 по 28.09.2026.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

from modules.procurement.tasks import _seconds_until


def _at(hour: int, minute: int, second: int = 0):
    """Подменяем utcnow: функция берёт время сама, аргумента у неё нет."""
    return patch(
        "modules.procurement.tasks.datetime",
        **{"utcnow.return_value": datetime(2026, 9, 28, hour, minute, second)},
    )


def test_waits_until_today_when_target_is_ahead():
    with _at(10, 0):
        assert _seconds_until(23, 50) == timedelta(hours=13, minutes=50).total_seconds()


def test_rolls_over_to_tomorrow_when_target_has_passed():
    with _at(23, 55):
        assert _seconds_until(23, 50) == timedelta(hours=23, minutes=55).total_seconds()


def test_exact_match_waits_a_full_day_not_zero():
    """Ровно в цель — ждём сутки: иначе задача крутилась бы в пустом цикле."""
    with _at(23, 50):
        assert _seconds_until(23, 50) == 24 * 3600


def test_supplier_sync_goes_after_the_catalog():
    """Оба источника пишут в одну таблицу — расходиться по времени дешевле."""
    with _at(0, 0):
        assert _seconds_until(23, 50) > _seconds_until(23, 30)

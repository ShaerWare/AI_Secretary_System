"""Tests for the numbered-choice registry (WhatsApp button emulation).

The self-hosted provider can't render interactive buttons, so menus go out as
numbered text and the reply has to be mapped back to the original ``reply_id``.
Getting this wrong either breaks the sales funnel or hijacks ordinary messages.
"""

import pytest

from whatsapp_bot.services import choices


PHONE = "79001234567"

BUTTONS = [
    {"id": "sales:quiz", "title": "Подобрать решение"},
    {"id": "sales:demo", "title": "Посмотреть демо"},
    {"id": "nav:menu", "title": "Меню"},
]


@pytest.fixture(autouse=True)
def _clean_registry():
    choices.reset()
    yield
    choices.reset()


def test_resolves_plain_number():
    choices.remember(PHONE, "button_reply", BUTTONS)
    assert choices.resolve(PHONE, "2") == ("button_reply", "sales:demo")


@pytest.mark.parametrize("text", ["1", "1)", "1.", "1 -", "№1", " 1 ", "вариант 1"])
def test_resolves_number_variants(text):
    choices.remember(PHONE, "button_reply", BUTTONS)
    assert choices.resolve(PHONE, text) == ("button_reply", "sales:quiz")


def test_resolves_by_title_case_insensitively():
    choices.remember(PHONE, "list_reply", BUTTONS)
    assert choices.resolve(PHONE, "  МЕНЮ ") == ("list_reply", "nav:menu")


def test_choice_is_consumed_once():
    choices.remember(PHONE, "button_reply", BUTTONS)
    assert choices.resolve(PHONE, "1") is not None
    # A second "1" is now an ordinary message, not a repeated button press.
    assert choices.resolve(PHONE, "1") is None


def test_number_outside_range_is_free_text():
    """ "Нужно 5 штук" must not be swallowed as a menu pick."""
    choices.remember(PHONE, "button_reply", BUTTONS)
    assert choices.resolve(PHONE, "5") is None
    # …and the menu stays open for a valid answer.
    assert choices.resolve(PHONE, "3") == ("button_reply", "nav:menu")


def test_unrelated_text_is_not_resolved():
    choices.remember(PHONE, "button_reply", BUTTONS)
    assert choices.resolve(PHONE, "а сколько стоит?") is None


def test_no_pending_menu_returns_none():
    assert choices.resolve(PHONE, "1") is None


def test_menus_are_per_phone():
    other = "79007654321"
    choices.remember(PHONE, "button_reply", BUTTONS)
    assert choices.resolve(other, "1") is None
    assert choices.resolve(PHONE, "1") == ("button_reply", "sales:quiz")


def test_later_menu_replaces_earlier_one():
    choices.remember(PHONE, "button_reply", BUTTONS)
    choices.remember(PHONE, "list_reply", [{"id": "faq:pricing", "title": "Цены"}])
    assert choices.resolve(PHONE, "1") == ("list_reply", "faq:pricing")


def test_expired_menu_is_dropped(monkeypatch):
    choices.remember(PHONE, "button_reply", BUTTONS)
    entry = choices._pending[PHONE]
    entry.created_at -= choices.CHOICE_TTL_SECONDS + 1
    assert choices.resolve(PHONE, "1") is None
    assert PHONE not in choices._pending


def test_options_without_id_are_skipped():
    choices.remember(
        PHONE,
        "list_reply",
        [{"id": "", "title": "Заголовок секции"}, {"id": "faq:a", "title": "Ответ"}],
    )
    # Numbering follows what the user actually sees: the id-less row is dropped
    # before rendering, so the first visible option is number 1.
    assert choices.resolve(PHONE, "1") == ("list_reply", "faq:a")


def test_clear_forgets_menu():
    choices.remember(PHONE, "button_reply", BUTTONS)
    choices.clear(PHONE)
    assert choices.resolve(PHONE, "1") is None


def test_empty_option_list_leaves_no_pending_menu():
    choices.remember(PHONE, "button_reply", [])
    assert PHONE not in choices._pending

"""Tests for WhatsApp channel identity, session reuse and sender filtering.

The WhatsApp bot reuses ``LLMRouter`` from the Telegram bot, and that sharing
hid three defects: sessions were tagged ``telegram_bot`` (so the orchestrator
never resolved the WhatsApp instance's RAG collections), no conversation key
existed to cache on (so every message opened a fresh session and lost the
history), and the instance's allow/block lists were never read.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.llm_router import LLMRouter
from whatsapp_bot.services import access


def _client(existing_ok: bool = False) -> MagicMock:
    """HTTP client stub whose POST returns a fresh orchestrator session id."""
    client = MagicMock()
    client.get = AsyncMock(return_value=MagicMock(status_code=200 if existing_ok else 404))
    created = {"n": 0}

    async def _post(url, json=None):
        created["n"] += 1
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"session": {"id": f"chat_{created['n']}"}})
        resp.request_body = json
        return resp

    client.post = AsyncMock(side_effect=_post)
    return client


class TestSessionTagging:
    """Sessions must carry the channel that actually created them."""

    async def test_whatsapp_router_tags_sessions_as_whatsapp(self):
        router = LLMRouter(source="whatsapp", instance_id="wa-1")
        client = _client()

        await router._ensure_session(client, None, source_id="wa-1:77085442089")

        body = client.post.await_args.kwargs["json"]
        assert body["source"] == "whatsapp"
        assert body["source_id"] == "wa-1:77085442089"
        assert body["title"] == "WhatsApp Bot"

    async def test_telegram_default_is_unchanged(self):
        router = LLMRouter()
        client = _client()

        await router._ensure_session(client, None, source_id="bot-1:42")

        body = client.post.await_args.kwargs["json"]
        assert body["source"] == "telegram_bot"
        assert body["title"] == "Telegram Bot"


class TestSessionReuse:
    """One conversation must map to one orchestrator session."""

    async def test_same_conversation_key_reuses_the_session(self):
        router = LLMRouter(source="whatsapp", instance_id="wa-1")
        client = _client()

        first = await router._ensure_session(client, None, conversation_key="77085442089")
        second = await router._ensure_session(client, None, conversation_key="77085442089")

        assert first == second
        assert client.post.await_count == 1, "a second session means history was lost"

    async def test_different_conversations_get_different_sessions(self):
        router = LLMRouter(source="whatsapp", instance_id="wa-1")
        client = _client()

        a = await router._ensure_session(client, None, conversation_key="7708")
        b = await router._ensure_session(client, None, conversation_key="7709")

        assert a != b

    async def test_conversation_key_is_never_probed_as_an_orchestrator_id(self):
        # A phone is a local key; GETting it would always 404 and waste a call.
        router = LLMRouter(source="whatsapp", instance_id="wa-1")
        client = _client(existing_ok=True)

        await router._ensure_session(client, "77085442089", conversation_key="77085442089")

        client.get.assert_not_awaited()


class TestSenderFiltering:
    """Allow/block lists must work, including for '@lid' senders."""

    def test_everything_allowed_when_lists_are_empty(self):
        assert access.is_sender_allowed("77085442089", "77085442089", [], [])
        assert access.is_sender_allowed("77085442089", None, None, None)

    def test_block_wins_over_allow(self):
        assert not access.is_sender_allowed(
            "77085442089", "77085442089", ["77085442089"], ["77085442089"]
        )

    @pytest.mark.parametrize(
        "entry",
        ["+7 708 544-20-89", "77085442089", "8 (708) 544 20 89"],
    )
    def test_block_entry_formats_are_equivalent(self, entry):
        assert not access.is_sender_allowed("77085442089", None, [], [entry])

    def test_lid_sender_can_be_blocked_verbatim(self):
        # WhatsApp discloses no number for these, so digits cannot match —
        # this is the only way to silence an automated '@lid' broadcaster.
        assert not access.is_sender_allowed(
            "106334968131631@lid", None, [], ["106334968131631@lid"]
        )

    def test_allow_list_excludes_everyone_else(self):
        assert access.is_sender_allowed("7708", None, ["7708"], [])
        assert not access.is_sender_allowed("7709", None, ["7708"], [])

    def test_blank_allow_entries_do_not_lock_everyone_out(self):
        assert access.is_sender_allowed("7708", None, ["", "  "], [])


class TestStaleness:
    """Replayed offline messages must not be answered."""

    def test_fresh_message_passes(self):
        assert not access.is_stale(1_000_000, now=1_000_030)

    def test_old_message_is_stale(self):
        assert access.is_stale(1_000_000, now=1_000_000 + 3600)

    def test_missing_timestamp_is_treated_as_fresh(self):
        # Dropping what the bridge could not stamp is worse than a late reply.
        assert not access.is_stale(None)
        assert not access.is_stale(0)

    def test_check_can_be_disabled(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_MAX_MESSAGE_AGE", "0")
        assert not access.is_stale(1, now=10**9)

    def test_invalid_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_MAX_MESSAGE_AGE", "nonsense")
        assert access.max_message_age_seconds() == access.DEFAULT_MAX_MESSAGE_AGE_SECONDS

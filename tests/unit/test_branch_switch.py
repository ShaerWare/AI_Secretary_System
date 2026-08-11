"""Branch switching tests (ChatRepository.switch_branch).

The active branch is the set of messages with is_active=True. Switching must
leave exactly one root→tip chain active: target + its ancestors + the
most-recent-child chain forward, with every diverging branch deactivated.

Regression: switching to a node deep inside an inactive branch used to
deactivate only the target's own siblings, so the branch being switched away
from stayed active alongside the new one and the chat rendered both.
"""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from db.models import Base
from db.repositories.chat import ChatRepository
from modules.chat.models import ChatMessage, ChatSession
from modules.core.models import Workspace


BASE_TIME = datetime(2026, 1, 1)
SESSION_ID = "S"


@pytest_asyncio.fixture()
async def setup_db(test_engine, test_session_factory):
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return test_session_factory


async def _build(session, rows):
    """rows: (id, parent_id, is_active, minute_offset) — offset orders siblings."""
    session.add(Workspace(id=1, name="default", slug="default"))
    await session.flush()
    session.add(ChatSession(id=SESSION_ID, title="t", workspace_id=1))
    for mid, pid, active, offset in rows:
        session.add(
            ChatMessage(
                id=mid,
                session_id=SESSION_ID,
                role="user",
                content=mid,
                parent_id=pid,
                is_active=active,
                created=BASE_TIME + timedelta(minutes=offset),
            )
        )
    await session.commit()


async def _active_chain(session):
    result = await session.execute(
        select(ChatMessage.id, ChatMessage.is_active).order_by(ChatMessage.created)
    )
    return [mid for mid, active in result.all() if active]


async def _switch(SessionFactory, rows, target):
    async with SessionFactory() as session:
        await _build(session, rows)
        repo = ChatRepository(session)
        ok = await repo.switch_branch(SESSION_ID, target)
        await session.commit()
        session.expire_all()
        return ok, await _active_chain(session)


@pytest.mark.asyncio
async def test_switch_to_deep_node_of_inactive_branch(setup_db):
    """The branch we switch away from must not stay active."""
    ok, chain = await _switch(
        setup_db,
        [
            ("root", None, True, 0),
            ("A", "root", True, 1),
            ("A1", "A", True, 2),
            ("B", "root", False, 3),
            ("B1", "B", False, 4),
            ("B2", "B1", False, 5),
        ],
        "B2",
    )
    assert ok
    assert chain == ["root", "B", "B1", "B2"]


@pytest.mark.asyncio
async def test_switch_to_direct_sibling(setup_db):
    ok, chain = await _switch(
        setup_db,
        [
            ("root", None, True, 0),
            ("A", "root", True, 1),
            ("A1", "A", True, 2),
            ("B", "root", False, 3),
        ],
        "B",
    )
    assert ok
    assert chain == ["root", "B"]


@pytest.mark.asyncio
async def test_switch_to_ancestor_follows_most_recent_child(setup_db):
    """Switching to a fork point continues down the newest child chain."""
    ok, chain = await _switch(
        setup_db,
        [
            ("root", None, True, 0),
            ("A", "root", False, 1),
            ("B", "root", True, 2),
        ],
        "root",
    )
    assert ok
    assert chain == ["root", "B"]


@pytest.mark.asyncio
async def test_switch_between_separate_root_chains(setup_db):
    """start_new_branch creates a second root — the old one must deactivate."""
    ok, chain = await _switch(
        setup_db,
        [
            ("r1", None, True, 0),
            ("r1a", "r1", True, 1),
            ("r2", None, False, 2),
            ("r2a", "r2", False, 3),
        ],
        "r2a",
    )
    assert ok
    assert chain == ["r2", "r2a"]


@pytest.mark.asyncio
async def test_switch_to_already_active_message_is_noop(setup_db):
    ok, chain = await _switch(
        setup_db,
        [("root", None, True, 0), ("A", "root", True, 1)],
        "A",
    )
    assert ok
    assert chain == ["root", "A"]


@pytest.mark.asyncio
async def test_switch_to_unknown_message_returns_false(setup_db):
    ok, chain = await _switch(
        setup_db,
        [("root", None, True, 0), ("A", "root", True, 1)],
        "nope",
    )
    assert ok is False
    assert chain == ["root", "A"]

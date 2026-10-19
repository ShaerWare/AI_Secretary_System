"""A slow LLM stream must not freeze the event loop.

Providers stream through a sync httpx client. Iterated directly inside an async
handler, every socket read parked the loop: a bridge answer that took minutes
left /health and /admin/auth/login unanswered ("connection error" on login).
"""

import asyncio
import time

from modules.chat.facade import _iterate_in_thread


def _slow_stream():
    for chunk in ("a", "b", "c"):
        time.sleep(0.2)  # blocking read, like httpx iter_lines()
        yield chunk


async def test_slow_stream_leaves_loop_responsive():
    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    hb = asyncio.create_task(heartbeat())
    chunks = [c async for c in _iterate_in_thread(_slow_stream())]
    hb.cancel()

    assert chunks == ["a", "b", "c"]
    # ~0.6 s of blocking reads; a frozen loop would tick 0-1 times.
    assert ticks >= 10

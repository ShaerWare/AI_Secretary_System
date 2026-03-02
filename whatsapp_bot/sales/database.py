"""SQLite persistence for WhatsApp sales funnel data via aiosqlite.

Fork of telegram_bot/sales/database.py adapted for WhatsApp:
- user_id is TEXT (phone number) instead of INTEGER
- Added funnel_state column for free-text input state machine
- Dropped Telegram-specific tables (payments, testimonials, news_cache, etc.)
"""

import json
import logging

import aiosqlite


logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    segment TEXT DEFAULT 'unknown',
    quiz_tech TEXT,
    quiz_infra TEXT,
    sub_segment TEXT,
    funnel_state TEXT,
    funnel_completed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    last_activity TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_data TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS custom_discovery (
    user_id TEXT PRIMARY KEY,
    step_1_task TEXT,
    step_2_volume TEXT,
    step_3_integrations TEXT,
    step_4_timeline TEXT,
    step_5_budget TEXT,
    completed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
"""


class SalesDatabase:
    """Async SQLite wrapper for WhatsApp sales funnel data."""

    def __init__(self, db_path: str = "wa_sales.db") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        logger.info("WhatsApp sales database initialized: %s", self._db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    # ── Users ──────────────────────────────────────────────

    async def upsert_user(self, user_id: str) -> None:
        await self._db.execute(
            """INSERT INTO users (user_id)
               VALUES (?)
               ON CONFLICT(user_id) DO UPDATE SET
                 last_activity = datetime('now')""",
            (user_id,),
        )
        await self._db.commit()

    async def get_user(self, user_id: str) -> dict | None:
        cursor = await self._db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def update_user(self, user_id: str, **kwargs: str | int | None) -> None:
        if not kwargs:
            return
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [user_id]
        await self._db.execute(
            f"UPDATE users SET {sets}, last_activity = datetime('now') WHERE user_id = ?",
            vals,
        )
        await self._db.commit()

    # ── State helpers ──────────────────────────────────────

    async def get_user_state(self, user_id: str) -> str | None:
        cursor = await self._db.execute(
            "SELECT funnel_state FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def set_user_state(self, user_id: str, state: str | None) -> None:
        await self._db.execute(
            "UPDATE users SET funnel_state = ?, last_activity = datetime('now') WHERE user_id = ?",
            (state, user_id),
        )
        await self._db.commit()

    # ── Events ─────────────────────────────────────────────

    async def log_event(self, user_id: str, event_type: str, data: dict | None = None) -> None:
        await self._db.execute(
            "INSERT INTO events (user_id, event_type, event_data) VALUES (?, ?, ?)",
            (user_id, event_type, json.dumps(data) if data else None),
        )
        await self._db.commit()

    async def count_events(self, event_type: str, days: int = 30) -> int:
        cursor = await self._db.execute(
            """SELECT COUNT(*) FROM events
               WHERE event_type = ?
                 AND created_at >= datetime('now', ?)""",
            (event_type, f"-{days} days"),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    # ── Custom Discovery ───────────────────────────────────

    async def save_discovery_step(self, user_id: str, step: int, value: str) -> None:
        col = f"step_{step}_{'task' if step == 1 else ['volume', 'integrations', 'timeline', 'budget'][step - 2]}"
        await self._db.execute(
            "INSERT OR IGNORE INTO custom_discovery (user_id) VALUES (?)",
            (user_id,),
        )
        await self._db.execute(
            f"UPDATE custom_discovery SET {col} = ? WHERE user_id = ?",
            (value, user_id),
        )
        if step == 5:
            await self._db.execute(
                "UPDATE custom_discovery SET completed = 1 WHERE user_id = ?",
                (user_id,),
            )
        await self._db.commit()

    async def get_discovery(self, user_id: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT * FROM custom_discovery WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def reset_discovery(self, user_id: str) -> None:
        await self._db.execute("DELETE FROM custom_discovery WHERE user_id = ?", (user_id,))
        await self._db.commit()

    # ── Analytics ──────────────────────────────────────────

    async def get_funnel_report(self, days: int = 30) -> dict:
        stages = [
            "start",
            "quiz_started",
            "quiz_completed",
            "diy_path_entered",
            "basic_path_entered",
            "custom_path_entered",
        ]
        report: dict[str, int] = {}
        for stage in stages:
            report[stage] = await self.count_events(stage, days)
        return report

    async def get_user_count(self) -> int:
        cursor = await self._db.execute("SELECT COUNT(*) FROM users")
        row = await cursor.fetchone()
        return row[0] if row else 0


# ── Singleton ──────────────────────────────────────────────

_db: SalesDatabase | None = None


async def get_sales_db() -> SalesDatabase:
    global _db
    if _db is None:
        from ..state import get_bot_config

        bot_config = get_bot_config()
        if bot_config is not None:
            db_path = f"data/wa_sales_{bot_config.instance_id}.db"
        else:
            db_path = "wa_sales.db"
        _db = SalesDatabase(db_path)
        await _db.init()
    return _db


async def close_sales_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None

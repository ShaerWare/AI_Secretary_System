"""SQLite persistence for sales funnel data via aiosqlite."""

import json
import logging

import aiosqlite


logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    segment TEXT DEFAULT 'unknown',
    quiz_tech TEXT,
    quiz_infra TEXT,
    sub_segment TEXT,
    funnel_completed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    last_activity TEXT DEFAULT (datetime('now')),
    subscribed INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_data TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS custom_discovery (
    user_id INTEGER PRIMARY KEY,
    step_1_task TEXT,
    step_2_volume TEXT,
    step_3_integrations TEXT,
    step_4_timeline TEXT,
    step_5_budget TEXT,
    completed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    telegram_charge_id TEXT UNIQUE,
    provider_charge_id TEXT,
    amount INTEGER NOT NULL,
    currency TEXT DEFAULT 'RUB',
    product TEXT DEFAULT 'basic_install',
    status TEXT DEFAULT 'completed',
    customer_name TEXT,
    customer_phone TEXT,
    customer_email TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS testimonials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    author TEXT NOT NULL,
    role TEXT,
    rating INTEGER DEFAULT 5,
    approved INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS news_cache (
    pr_number INTEGER PRIMARY KEY,
    pr_title TEXT,
    post_text TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS news_broadcasts (
    pr_number INTEGER PRIMARY KEY,
    broadcast_at TEXT DEFAULT (datetime('now')),
    recipients_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS commit_news_cache (
    sha TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    message TEXT,
    post_text TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS commit_news_broadcasts (
    sha TEXT PRIMARY KEY,
    broadcast_at TEXT DEFAULT (datetime('now')),
    recipients_count INTEGER DEFAULT 0
);
"""


class SalesDatabase:
    """Async SQLite wrapper for sales funnel data."""

    def __init__(self, db_path: str = "sales.db") -> None:
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
        logger.info("Sales database initialized: %s", self._db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    # ── Users ──────────────────────────────────────────────

    async def upsert_user(self, user_id: int, **kwargs: str | None) -> None:
        username = kwargs.get("username")
        first_name = kwargs.get("first_name")
        await self._db.execute(
            """INSERT INTO users (user_id, username, first_name)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 username = COALESCE(excluded.username, users.username),
                 first_name = COALESCE(excluded.first_name, users.first_name),
                 last_activity = datetime('now')""",
            (user_id, username, first_name),
        )
        await self._db.commit()

    async def get_user(self, user_id: int) -> dict | None:
        cursor = await self._db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def update_user(self, user_id: int, **kwargs: str | int | None) -> None:
        if not kwargs:
            return
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [user_id]
        await self._db.execute(
            f"UPDATE users SET {sets}, last_activity = datetime('now') WHERE user_id = ?",
            vals,
        )
        await self._db.commit()

    # ── Events ─────────────────────────────────────────────

    async def log_event(self, user_id: int, event_type: str, data: dict | None = None) -> None:
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

    async def save_discovery_step(self, user_id: int, step: int, value: str) -> None:
        col = f"step_{step}_{'task' if step == 1 else ['volume', 'integrations', 'timeline', 'budget'][step - 2]}"
        # Ensure row exists
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

    async def get_discovery(self, user_id: int) -> dict | None:
        cursor = await self._db.execute(
            "SELECT * FROM custom_discovery WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    # ── Analytics ──────────────────────────────────────────

    async def get_funnel_report(self, days: int = 30) -> dict:
        stages = [
            "start",
            "quiz_started",
            "quiz_completed",
            "value_shown",
            "cta_clicked",
            "checkout_started",
        ]
        report: dict[str, int] = {}
        for stage in stages:
            report[stage] = await self.count_events(stage, days)
        return report

    async def get_user_count(self) -> int:
        cursor = await self._db.execute("SELECT COUNT(*) FROM users")
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def get_subscribed_users(self) -> list[int]:
        """Get list of user_ids who are subscribed to news."""
        cursor = await self._db.execute("SELECT user_id FROM users WHERE subscribed = 1")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def get_subscribers_count(self) -> int:
        """Get count of subscribed users."""
        cursor = await self._db.execute("SELECT COUNT(*) FROM users WHERE subscribed = 1")
        row = await cursor.fetchone()
        return row[0] if row else 0

    # ── Payments ──────────────────────────────────────────────

    async def save_payment(
        self,
        user_id: int,
        telegram_charge_id: str,
        provider_charge_id: str,
        amount: int,
        currency: str = "RUB",
        product: str = "basic_install",
        customer_name: str | None = None,
        customer_phone: str | None = None,
        customer_email: str | None = None,
    ) -> None:
        """Save payment record."""
        await self._db.execute(
            """INSERT INTO payments
               (user_id, telegram_charge_id, provider_charge_id, amount, currency,
                product, customer_name, customer_phone, customer_email)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                telegram_charge_id,
                provider_charge_id,
                amount,
                currency,
                product,
                customer_name,
                customer_phone,
                customer_email,
            ),
        )
        await self._db.commit()

    async def get_payments_count(self, days: int = 30) -> int:
        """Get count of payments in last N days."""
        cursor = await self._db.execute(
            """SELECT COUNT(*) FROM payments
               WHERE created_at >= datetime('now', ?)""",
            (f"-{days} days",),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    # ── Testimonials ──────────────────────────────────────────

    async def get_random_testimonial(self) -> dict | None:
        """Get a random approved testimonial."""
        cursor = await self._db.execute(
            """SELECT text, author, role FROM testimonials
               WHERE approved = 1
               ORDER BY RANDOM() LIMIT 1"""
        )
        row = await cursor.fetchone()
        if row:
            return {"text": row[0], "author": row[1], "role": row[2]}
        return None

    async def add_testimonial(
        self, text: str, author: str, role: str | None = None, rating: int = 5
    ) -> None:
        """Add a new testimonial."""
        await self._db.execute(
            """INSERT INTO testimonials (text, author, role, rating)
               VALUES (?, ?, ?, ?)""",
            (text, author, role, rating),
        )
        await self._db.commit()

    # ── News Cache ──────────────────────────────────────────────

    async def get_cached_news(self, pr_number: int) -> str | None:
        """Get cached SMM post for a PR."""
        cursor = await self._db.execute(
            "SELECT post_text FROM news_cache WHERE pr_number = ?",
            (pr_number,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def save_news_cache(self, pr_number: int, pr_title: str, post_text: str) -> None:
        """Save generated SMM post to cache."""
        await self._db.execute(
            """INSERT INTO news_cache (pr_number, pr_title, post_text)
               VALUES (?, ?, ?)
               ON CONFLICT(pr_number) DO UPDATE SET
                 post_text = excluded.post_text,
                 created_at = datetime('now')""",
            (pr_number, pr_title, post_text),
        )
        await self._db.commit()

    async def get_all_cached_news(self, pr_numbers: list[int]) -> dict[int, str]:
        """Get all cached posts for given PR numbers.

        Returns:
            Dict mapping pr_number -> post_text
        """
        if not pr_numbers:
            return {}

        placeholders = ",".join("?" * len(pr_numbers))
        cursor = await self._db.execute(
            f"SELECT pr_number, post_text FROM news_cache WHERE pr_number IN ({placeholders})",
            pr_numbers,
        )
        rows = await cursor.fetchall()
        return {row[0]: row[1] for row in rows}

    # ── News Broadcasts ──────────────────────────────────────────

    async def is_pr_broadcast(self, pr_number: int) -> bool:
        """Check if PR was already broadcast to subscribers."""
        cursor = await self._db.execute(
            "SELECT 1 FROM news_broadcasts WHERE pr_number = ?",
            (pr_number,),
        )
        row = await cursor.fetchone()
        return row is not None

    async def mark_pr_broadcast(self, pr_number: int, recipients_count: int) -> None:
        """Mark PR as broadcast."""
        await self._db.execute(
            """INSERT INTO news_broadcasts (pr_number, recipients_count)
               VALUES (?, ?)
               ON CONFLICT(pr_number) DO UPDATE SET
                 broadcast_at = datetime('now'),
                 recipients_count = excluded.recipients_count""",
            (pr_number, recipients_count),
        )
        await self._db.commit()

    async def get_unbroadcast_pr_numbers(self, pr_numbers: list[int]) -> list[int]:
        """Filter PR numbers to get only those not yet broadcast."""
        if not pr_numbers:
            return []

        placeholders = ",".join("?" * len(pr_numbers))
        cursor = await self._db.execute(
            f"SELECT pr_number FROM news_broadcasts WHERE pr_number IN ({placeholders})",
            pr_numbers,
        )
        rows = await cursor.fetchall()
        broadcast_set = {row[0] for row in rows}
        return [n for n in pr_numbers if n not in broadcast_set]

    async def has_any_broadcasts(self) -> bool:
        """Check if there are any broadcast records at all (for first-run detection)."""
        cursor = await self._db.execute("SELECT 1 FROM news_broadcasts LIMIT 1")
        return await cursor.fetchone() is not None

    # ── Commit News Cache ──────────────────────────────────────────

    async def get_cached_commit_news(self, sha: str) -> str | None:
        """Get cached news post for a commit."""
        cursor = await self._db.execute(
            "SELECT post_text FROM commit_news_cache WHERE sha = ?",
            (sha,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def save_commit_news_cache(
        self, sha: str, repo: str, message: str, post_text: str
    ) -> None:
        """Save commit news post to cache."""
        await self._db.execute(
            """INSERT INTO commit_news_cache (sha, repo, message, post_text)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(sha) DO UPDATE SET
                 post_text = excluded.post_text,
                 created_at = datetime('now')""",
            (sha, repo, message, post_text),
        )
        await self._db.commit()

    async def get_all_cached_commit_news(self, shas: list[str]) -> dict[str, str]:
        """Get all cached posts for given commit SHAs.

        Returns:
            Dict mapping sha -> post_text
        """
        if not shas:
            return {}

        placeholders = ",".join("?" * len(shas))
        cursor = await self._db.execute(
            f"SELECT sha, post_text FROM commit_news_cache WHERE sha IN ({placeholders})",
            shas,
        )
        rows = await cursor.fetchall()
        return {row[0]: row[1] for row in rows}

    # ── Commit News Broadcasts ──────────────────────────────────────

    async def get_unbroadcast_commit_shas(self, shas: list[str]) -> list[str]:
        """Filter commit SHAs to get only those not yet broadcast."""
        if not shas:
            return []

        placeholders = ",".join("?" * len(shas))
        cursor = await self._db.execute(
            f"SELECT sha FROM commit_news_broadcasts WHERE sha IN ({placeholders})",
            shas,
        )
        rows = await cursor.fetchall()
        broadcast_set = {row[0] for row in rows}
        return [s for s in shas if s not in broadcast_set]

    async def has_any_commit_broadcasts(self) -> bool:
        """Check if there are any commit broadcast records (for first-run detection)."""
        cursor = await self._db.execute("SELECT 1 FROM commit_news_broadcasts LIMIT 1")
        return await cursor.fetchone() is not None

    async def mark_commit_broadcast(self, sha: str, recipients_count: int) -> None:
        """Mark commit as broadcast."""
        await self._db.execute(
            """INSERT INTO commit_news_broadcasts (sha, recipients_count)
               VALUES (?, ?)
               ON CONFLICT(sha) DO UPDATE SET
                 broadcast_at = datetime('now'),
                 recipients_count = excluded.recipients_count""",
            (sha, recipients_count),
        )
        await self._db.commit()


# ── Singleton ──────────────────────────────────────────────

_db: SalesDatabase | None = None


async def get_sales_db() -> SalesDatabase:
    global _db
    if _db is None:
        # Multi-instance mode: get db_path from BotConfig
        from ..state import get_bot_config

        bot_config = get_bot_config()
        if bot_config is not None:
            db_path = bot_config.sales_db_path
        else:
            from ..config import get_telegram_settings

            settings = get_telegram_settings()
            db_path = getattr(settings, "sales_db_path", "sales.db")
        _db = SalesDatabase(db_path)
        await _db.init()
    return _db

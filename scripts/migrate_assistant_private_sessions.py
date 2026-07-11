"""
Migrate default assistants from "one shared conversation for everyone" to a
PRIVATE per-user session per assistant.

Background
----------
Default assistants (Юрист РФ/РК, Бухгалтер РФ/РК, …) are `MobileAppInstance`
rows assigned to users via `ResourceShare`. The instance holds the shared
config (system_prompt + RAG collections). Historically the mobile/admin UIs
pointed every assigned user at a SINGLE `ChatSession` shared via
`ChatSessionShare` (often flagged `is_default_mobile`), so everyone typed into
the same conversation.

The new model: each user gets their own `ChatSession`
(owner_id=user, source="mobile", source_id=<instance_id>) that inherits the
instance's prompt + RAG. Config stays shared; the dialogue is private.

This migration:
  1. Pre-creates the private (user, assistant) session for every existing
     ResourceShare that doesn't have one yet (so users land in their own chat
     immediately, not on first open).
  2. Removes `ChatSessionShare` rows on assistant sessions (source="mobile"),
     which is what made a conversation common to several users. Owner copies
     are kept; only the cross-user shares are dropped.

It does NOT touch shares of regular (non-mobile) chats — those are legitimate
user-to-user shares.

Idempotent. Safe to re-run.

Usage:
    python scripts/migrate_assistant_private_sessions.py --dry-run
    python scripts/migrate_assistant_private_sessions.py
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("migrate_assistant_private_sessions")


async def run(dry_run: bool = False) -> None:
    from sqlalchemy import delete, select

    from db.database import AsyncSessionLocal
    from db.models import (
        ChatSession,
        ChatSessionShare,
        MobileAppInstance,
        ResourceShare,
    )
    from modules.chat.service import chat_service

    # ---- Step 1: pre-create private sessions for each (user, assistant) ----
    created = 0
    skipped = 0
    async with AsyncSessionLocal() as session:
        instances = (
            (await session.execute(select(MobileAppInstance))).scalars().all()
        )
        inst_by_id = {i.id: i for i in instances}

        shares = (
            (
                await session.execute(
                    select(ResourceShare).where(
                        ResourceShare.resource_type == "mobile_app_instance"
                    )
                )
            )
            .scalars()
            .all()
        )
        log.info("Assistants: %d, assignments: %d", len(instances), len(shares))

        for share in shares:
            inst = inst_by_id.get(share.resource_id)
            if not inst:
                continue

            existing = await chat_service.find_user_instance_session(
                share.user_id, "mobile", inst.id
            )
            if existing:
                skipped += 1
                continue

            if dry_run:
                log.info(
                    "  [dry] would create session: user=%d assistant=%s",
                    share.user_id,
                    inst.id,
                )
                created += 1
                continue

            new_session = await chat_service.create_session(
                inst.name,
                inst.system_prompt,
                "mobile",
                inst.id,
                owner_id=share.user_id,
                rag_mode=inst.rag_mode,
            )
            collection_ids = inst.get_knowledge_collection_ids()
            if collection_ids:
                await chat_service.update_session(
                    new_session["id"], knowledge_collection_ids=collection_ids
                )
            created += 1

        log.info("Private sessions — created: %d, already existed: %d", created, skipped)

    # ---- Step 2: drop cross-user shares on assistant (mobile) sessions ----
    async with AsyncSessionLocal() as session:
        mobile_session_ids = (
            select(ChatSession.id).where(ChatSession.source == "mobile").scalar_subquery()
        )
        shares_to_delete = (
            (
                await session.execute(
                    select(ChatSessionShare).where(
                        ChatSessionShare.session_id.in_(mobile_session_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        log.info("Assistant-session shares to remove: %d", len(shares_to_delete))
        for s in shares_to_delete:
            log.info(
                "  %s session=%s user=%d default_mobile=%s",
                "[dry] would remove" if dry_run else "remove",
                s.session_id,
                s.user_id,
                s.is_default_mobile,
            )

        if not dry_run and shares_to_delete:
            await session.execute(
                delete(ChatSessionShare).where(
                    ChatSessionShare.session_id.in_(mobile_session_ids)
                )
            )
            await session.commit()

    if dry_run:
        log.info("dry-run: no changes written")
    else:
        log.info("migration committed")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate default assistants to private per-user sessions"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show planned changes only")
    args = parser.parse_args()

    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()

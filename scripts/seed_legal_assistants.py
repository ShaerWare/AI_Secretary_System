"""Seed default assistants and backfill shares for all existing users.

Ensures the default assistant instances exist (marketer, programmer, lawyer-ru,
accountant-ru, lawyer-kz, accountant-kz — see
``modules/channels/mobile/provisioning.ASSISTANT_CATALOG``) and shares the
appropriate set with every active user based on ``User.country`` (ru/kz).

New users get provisioned automatically at registration
(``WorkspaceService.accept_invite`` and ``scripts/manage_users.py``); this
script is the one-shot backfill for users that already existed.

Idempotent and additive: re-running updates instance prompts/collections from
``prompts/*.md`` and adds only missing shares — it never duplicates or revokes.

Usage:
  venv/bin/python scripts/seed_legal_assistants.py
  venv/bin/python scripts/seed_legal_assistants.py --dry-run
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
log = logging.getLogger("seed_legal_assistants")


async def run(dry_run: bool = False) -> None:
    from sqlalchemy import select

    from db.database import AsyncSessionLocal
    from db.models import User
    from modules.channels.mobile.provisioning import (
        ensure_default_instances,
        provision_default_assistants,
        target_instance_ids,
    )

    async with AsyncSessionLocal() as session:
        log.info("Ensuring default assistant instances exist / are up to date…")
        await ensure_default_instances(session)

        users = (
            (await session.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
        )
        log.info("Active users: %d", len(users))

        total_shares = 0
        for user in users:
            country = getattr(user, "country", "ru") or "ru"
            ids = target_instance_ids(country)
            if dry_run:
                log.info("[dry] %s (country=%s) → %s", user.username, country, ", ".join(ids))
                continue
            n = await provision_default_assistants(session, user.id, country, ensure=False)
            total_shares += n
            log.info("%s (country=%s): %d assistants", user.username, country, n)

        if dry_run:
            log.info("dry-run: rolling back")
            await session.rollback()
        else:
            await session.commit()
            log.info("committed — %d user-assistant shares ensured", total_shares)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed default assistants + backfill user shares")
    parser.add_argument("--dry-run", action="store_true", help="Show planned changes only")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()

"""
Seed 4 mobile-app-instance assistants and share them with users:

  - lawyer-ru        (РФ-юрист, кодексы РФ)
  - lawyer-kz        (РК-юрист, кодексы РК)
  - accountant-ru    (РФ-бухгалтер, УСН-набор)
  - accountant-kz    (РК-бухгалтер, НК РК + практика)

KZ variants are shared only with admins and the username `stalkerelectric`
("пока нет языка"). RU variants are shared with every active user.

Idempotent: re-running updates existing instances and skips duplicate shares.

Usage:
  venv/bin/python scripts/seed_legal_assistants.py
  venv/bin/python scripts/seed_legal_assistants.py --dry-run
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path


# Project root on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("seed_legal_assistants")


def _read_prompt(filename: str, fallback: str) -> str:
    path = PROJECT_ROOT / "prompts" / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    log.warning("prompts/%s not found, using inline fallback", filename)
    return fallback


# ---------------------------------------------------------------------------
# Assistant catalog
# ---------------------------------------------------------------------------

# Slug → (display name, prompt-file or fallback, knowledge-collection slugs, kazakh?)
ACCOUNTANT_RU_FALLBACK = (
    "Ты — бухгалтерский ассистент по Российской Федерации. Объясняй нормы НК РФ "
    "и УСН со ссылками на статьи, не давай налоговых заключений."
)

ASSISTANTS: list[dict] = [
    {
        "id": "lawyer-ru",
        "name": "Юрист РФ",
        "description": "Юридический ассистент по праву РФ (УК, КоАП, УПК, ГК, ТК, СК, ЖК).",
        "prompt_file": "lawyer-ru.md",
        "prompt_fallback": "Ты — юридический ассистент по праву РФ. Цитируй статьи кодексов.",
        "collection_slugs": [
            "ru-uk-rf",
            "ru-koap-rf",
            "ru-upk-rf",
            "ru-gk-rf-1",
            "ru-gk-rf-2",
            "ru-gk-rf-3",
            "ru-gk-rf-4",
            "ru-tk-rf",
            "ru-sk-rf",
            "ru-zhk-rf",
            "ru-nk-rf-glava-26-2",
        ],
        "kazakh": False,
    },
    {
        "id": "lawyer-kz",
        "name": "Юрист РК",
        "description": "Юридический ассистент по праву РК (УК, КоАП, УПК, ГК, ТК, НК).",
        "prompt_file": "lawyer-kz.md",
        "prompt_fallback": "Ты — юридический ассистент по праву РК. Цитируй статьи кодексов РК.",
        "collection_slugs": [
            "kz-uk-rk",
            "kz-koap-rk",
            "kz-upk-rk",
            "kz-gk-rk-general",
            "kz-gk-rk-special",
            "kz-tk-rk",
            "kz-nk-rk",
        ],
        "kazakh": True,
    },
    {
        "id": "accountant-ru",
        "name": "Бухгалтер РФ",
        "description": "Бухгалтерский ассистент по РФ (УСН + НК РФ глава 26.2).",
        "prompt_file": "accountant-ru.md",
        "prompt_fallback": ACCOUNTANT_RU_FALLBACK,
        "collection_slugs": ["ru-fns-usn", "ru-nk-rf-glava-26-2", "ru-moedelo-usn"],
        "kazakh": False,
    },
    {
        "id": "accountant-kz",
        "name": "Бухгалтер РК",
        "description": "Бухгалтерский ассистент по РК (НК РК + практика КГД).",
        "prompt_file": "accountant-kz.md",
        "prompt_fallback": "Ты — бухгалтерский ассистент по РК. Используй НК РК.",
        "collection_slugs": ["kz-nk-rk", "kz-tk-rk"],
        "kazakh": True,
    },
]


# ---------------------------------------------------------------------------
# Logic
# ---------------------------------------------------------------------------


async def run(dry_run: bool = False) -> None:
    from sqlalchemy import select

    from db.database import AsyncSessionLocal
    from db.models import (
        KnowledgeCollection,
        MobileAppInstance,
        ResourceShare,
        User,
    )

    async with AsyncSessionLocal() as session:
        # Map collection slug → id
        rows = (await session.execute(select(KnowledgeCollection))).scalars().all()
        slug_to_id = {c.slug: c.id for c in rows}

        # Eligible users: admin role gets everything; others get RU only,
        # kz also goes to user `stalkerelectric` (until language preference lands).
        users = (
            (await session.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
        )
        users = [u for u in users if u.role in ("admin", "user", "web", "guest")]

        log.info("Eligible users: %d", len(users))

        for spec in ASSISTANTS:
            instance_id = spec["id"]
            log.info("=== %s (%s) ===", spec["name"], instance_id)

            # Resolve collection IDs
            collection_ids: list[int] = []
            for slug in spec["collection_slugs"]:
                cid = slug_to_id.get(slug)
                if cid:
                    collection_ids.append(cid)
                else:
                    log.warning("  skip missing collection: %s", slug)

            # Read system prompt
            prompt_text = _read_prompt(spec["prompt_file"], spec["prompt_fallback"])

            # Upsert instance
            existing = await session.get(MobileAppInstance, instance_id)
            now = datetime.utcnow()
            payload = {
                "name": spec["name"],
                "description": spec["description"],
                "enabled": True,
                "system_prompt": prompt_text,
                "rag_mode": "selected" if collection_ids else "all",
                "knowledge_collection_ids": json.dumps(collection_ids) if collection_ids else None,
                "updated": now,
            }

            if existing:
                if dry_run:
                    log.info("  [dry] would update instance %s", instance_id)
                else:
                    for k, v in payload.items():
                        setattr(existing, k, v)
                    log.info("  updated instance (%d collections)", len(collection_ids))
            elif dry_run:
                log.info("  [dry] would create instance %s", instance_id)
            else:
                instance = MobileAppInstance(
                    id=instance_id,
                    created=now,
                    # Keep defaults the orchestrator's chat facade tolerates;
                    # admin can refine LLM/TTS later via the Mobile-App view.
                    llm_backend="cloud",
                    llm_persona="anna",
                    tts_engine="xtts",
                    tts_voice="anna",
                    **payload,
                )
                session.add(instance)
                log.info("  created instance (%d collections)", len(collection_ids))

            # Decide who should see this assistant
            if spec["kazakh"]:
                target_users = [
                    u for u in users if u.role == "admin" or u.username == "stalkerelectric"
                ]
            else:
                target_users = list(users)

            log.info("  share targets: %d users", len(target_users))

            # Existing shares for this resource
            existing_shares = (
                (
                    await session.execute(
                        select(ResourceShare).where(
                            ResourceShare.resource_type == "mobile_app_instance",
                            ResourceShare.resource_id == instance_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            shared_user_ids = {s.user_id for s in existing_shares}

            new_shares = 0
            for u in target_users:
                if u.id in shared_user_ids:
                    continue
                if dry_run:
                    log.info("  [dry] would share with %s (id=%d)", u.username, u.id)
                else:
                    session.add(
                        ResourceShare(
                            resource_type="mobile_app_instance",
                            resource_id=instance_id,
                            user_id=u.id,
                            permission="view",
                            shared_by=None,
                            shared_at=now,
                        )
                    )
                new_shares += 1

            log.info("  +%d new shares (skipped %d existing)", new_shares, len(shared_user_ids))

        if dry_run:
            log.info("dry-run: rolling back")
            await session.rollback()
        else:
            await session.commit()
            log.info("committed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed legal/accountant mobile assistants")
    parser.add_argument("--dry-run", action="store_true", help="Show planned changes only")
    args = parser.parse_args()

    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()

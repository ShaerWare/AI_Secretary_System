"""Default-assistant provisioning.

Every user gets a default set of mobile-app assistants at registration:

  - marketer, programmer      — country-agnostic (shared with everyone)
  - lawyer-ru, accountant-ru  — for country="ru" users
  - lawyer-kz, accountant-kz  — for country="kz" users

Assistants are `MobileAppInstance` rows; access is a `ResourceShare`
(resource_type="mobile_app_instance", permission="view"). This module owns:

  - ``ASSISTANT_CATALOG``          — the catalog (id, name, prompt, collections, scope)
  - ``ensure_default_instances``   — idempotent upsert of the instance rows
  - ``provision_default_assistants`` — idempotent share creation for one user
  - ``provision_for_username``     — standalone entrypoint (opens its own session)

Called from the user-creation paths (``WorkspaceService.accept_invite``,
``scripts/manage_users.py``) and from the backfill script
(``scripts/seed_legal_assistants.py``). All operations are idempotent and
additive — re-running never duplicates instances or shares and never revokes.

Provisioning is best-effort at registration: a failure here must never block
account creation (the caller wraps the call in try/except).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = PROJECT_ROOT / "prompts"

RESOURCE_TYPE = "mobile_app_instance"
VALID_COUNTRIES = ("ru", "kz")


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------
# scope: "all" → every user; "ru"/"kz" → only users with that country.
ASSISTANT_CATALOG: list[dict] = [
    {
        "id": "marketer",
        "name": "Маркетолог",
        "description": "Маркетолог-сеошник: продвижение сайтов, SEO, контент, аналитика.",
        "prompt_file": "marketer-ru.md",
        "prompt_fallback": (
            "Ты — ассистент по интернет-маркетингу и SEO. Помогай продвигать сайты "
            "в поиске (Яндекс, Google): семантика, контент, техническое SEO, ссылки, "
            "аналитика. Не гарантируй позиции, отказывайся от «серых» методов."
        ),
        "collection_slugs": ["ru-sbup-seo"],
        "scope": "all",
    },
    {
        "id": "programmer",
        "name": "Программист",
        "description": "Цифровой партнёр по разработке (PHP/Laravel по умолчанию, стек редактируется).",
        "prompt_file": "programmer-ru.md",
        "prompt_fallback": (
            "Ты — цифровой партнёр по разработке. Анализируй задачу, предлагай "
            "архитектуру и только затем реализуй. Стек по умолчанию — PHP/Laravel; "
            "если у пользователя другой стек, он редактирует этот промпт под себя."
        ),
        "collection_slugs": [],
        "scope": "all",
    },
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
        "scope": "ru",
    },
    {
        "id": "accountant-ru",
        "name": "Бухгалтер РФ",
        "description": "Бухгалтерский ассистент по РФ (УСН + НК РФ глава 26.2).",
        "prompt_file": "accountant-ru.md",
        "prompt_fallback": (
            "Ты — бухгалтерский ассистент по РФ. Объясняй нормы УСН и НК РФ со "
            "ссылками на статьи, не давай налоговых заключений."
        ),
        "collection_slugs": ["ru-fns-usn", "ru-nk-rf-glava-26-2", "ru-moedelo-usn"],
        "scope": "ru",
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
        "scope": "kz",
    },
    {
        "id": "accountant-kz",
        "name": "Бухгалтер РК",
        "description": "Бухгалтерский ассистент по РК (НК РК + практика КГД).",
        "prompt_file": "accountant-kz.md",
        "prompt_fallback": "Ты — бухгалтерский ассистент по РК. Используй НК РК.",
        "collection_slugs": ["kz-nk-rk", "kz-tk-rk"],
        "scope": "kz",
    },
]


def _read_prompt(filename: str, fallback: str) -> str:
    path = PROMPTS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning("prompts/%s not found, using inline fallback", filename)
    return fallback


def target_instance_ids(country: Optional[str]) -> list[str]:
    """Default-assistant ids for a user's country (country-agnostic + matching)."""
    country = (country or "ru").lower()
    if country not in VALID_COUNTRIES:
        country = "ru"
    return [spec["id"] for spec in ASSISTANT_CATALOG if spec["scope"] in ("all", country)]


async def ensure_default_instances(session) -> None:
    """Idempotently create/update the default assistant instances.

    Resolves collection slugs → ids against the current DB (missing collections
    are skipped with a warning — e.g. ru-sbup-seo may be absent in dev). Safe to
    call on every registration; it only touches the six catalog rows.
    """
    from sqlalchemy import select

    from db.models import KnowledgeCollection, MobileAppInstance

    rows = (await session.execute(select(KnowledgeCollection))).scalars().all()
    slug_to_id = {c.slug: c.id for c in rows}

    for spec in ASSISTANT_CATALOG:
        collection_ids: list[int] = []
        for slug in spec["collection_slugs"]:
            cid = slug_to_id.get(slug)
            if cid:
                collection_ids.append(cid)
            else:
                logger.warning("ensure_default_instances: missing collection %s", slug)

        prompt_text = _read_prompt(spec["prompt_file"], spec["prompt_fallback"])
        rag_mode = "selected" if collection_ids else "all"
        collection_ids_json = json.dumps(collection_ids) if collection_ids else None

        existing = await session.get(MobileAppInstance, spec["id"])
        if existing:
            existing.name = spec["name"]
            existing.description = spec["description"]
            existing.enabled = True
            existing.system_prompt = prompt_text
            existing.rag_mode = rag_mode
            existing.knowledge_collection_ids = collection_ids_json
        else:
            session.add(
                MobileAppInstance(
                    id=spec["id"],
                    name=spec["name"],
                    description=spec["description"],
                    enabled=True,
                    system_prompt=prompt_text,
                    rag_mode=rag_mode,
                    knowledge_collection_ids=collection_ids_json,
                    # Cloud-friendly defaults; admin can refine LLM/TTS in the
                    # Mobile-App view later.
                    llm_backend="cloud",
                    llm_persona="anna",
                    tts_engine="xtts",
                    tts_voice="anna",
                )
            )
    await session.flush()


async def provision_default_assistants(
    session,
    user_id: int,
    country: Optional[str] = "ru",
    *,
    ensure: bool = True,
) -> int:
    """Share the default assistant set with one user. Idempotent and additive.

    Returns the number of instances the user ends up sharing (existing + new).
    Never revokes shares (a country change that should drop the other country's
    assistants is handled separately). Caller owns the transaction/commit.
    """
    from db.repositories.resource_share import ResourceShareRepository

    if ensure:
        await ensure_default_instances(session)

    repo = ResourceShareRepository(session)
    shared = 0
    for instance_id in target_instance_ids(country):
        await repo.add_share(
            resource_type=RESOURCE_TYPE,
            resource_id=instance_id,
            user_id=user_id,
            permission="view",
            shared_by=None,
        )
        shared += 1
    return shared


async def provision_for_username(username: str) -> int:
    """Standalone entrypoint (opens/commits its own session). Best-effort.

    Used by the CLI (scripts/manage_users.py) which otherwise talks raw sqlite.
    Returns number of assistants shared, or 0 if the user is not found.
    """
    from sqlalchemy import select

    from db.database import AsyncSessionLocal
    from db.models import User

    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if not user:
            logger.warning("provision_for_username: user %s not found", username)
            return 0
        count = await provision_default_assistants(session, user.id, getattr(user, "country", "ru"))
        await session.commit()
        return count

"""Assistant preset templates for new chat session creation.

When the user clicks "new assistant" in the mobile app or the admin panel,
they pick from a small set of pre-baked thematic templates. Each template
ships a system prompt + a list of knowledge-collection slugs. The factory
endpoint (``GET /admin/chat/assistant-presets``) resolves slugs against the
live DB and loads prompt-file content from disk, so unknown collections /
missing prompt files degrade gracefully (the preset still appears, just
without those particular collections / with the platform-agent fallback
prompt).

Adding a new preset = appending one entry to ``PRESETS``; no DB schema
changes required.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", "/opt/ai-secretary/prompts"))


@dataclass(frozen=True)
class AssistantPreset:
    """One thematic assistant template.

    ``prompt_file`` is resolved against ``PROMPTS_DIR``; ``None`` means the
    preset does not ship its own system prompt and the chat will fall back
    to ``platform-agent.md`` at conversation time.

    ``collection_slugs`` are resolved against the live DB; any slug not
    matching an existing collection is silently dropped (so presets can
    reference future / in-progress collections without hard-failing).
    """

    slug: str
    name: str
    description: str
    icon: str  # lucide-vue-next icon name
    prompt_file: str | None
    collection_slugs: list[str] = field(default_factory=list)
    rag_mode: str | None = "auto"


# Order matters — frontends render presets in this order.
PRESETS: list[AssistantPreset] = [
    AssistantPreset(
        slug="lawyer-ru",
        name="Юрист РФ",
        description="Российское право: Конституция, кодексы (УК, УПК, КоАП, ГК ч.1–4, ТК, СК, ЖК, НК, БК, ГПК, АПК, КАС, ЗК, ЛК, ВК, ГсК), ФЗ, ФКЗ.",
        icon="scale",
        prompt_file="lawyer-ru.md",
        collection_slugs=[
            # Already scraped codes
            "ru-uk-rf",
            "ru-upk-rf",
            "ru-koap-rf",
            "ru-gk-rf-1",
            "ru-gk-rf-2",
            "ru-gk-rf-3",
            "ru-gk-rf-4",
            "ru-tk-rf",
            "ru-sk-rf",
            "ru-zhk-rf",
            "ru-fz-273",
            "ru-pravo-news",
            # Pending batch scrape (silently skipped until they exist)
            "ru-konstitutsiya",
            "ru-nk-rf-1",
            "ru-nk-rf-2",
            "ru-bk-rf",
            "ru-gpk-rf",
            "ru-apk-rf",
            "ru-kas-rf",
            "ru-zk-rf",
            "ru-lk-rf",
            "ru-vk-rf",
            "ru-gsk-rf",
            "ru-fz-14",
            "ru-fz-208",
            "ru-fz-7",
            "ru-fz-127",
            "ru-fz-129",
            "ru-fz-79",
            "ru-fz-131",
            "ru-fz-414",
            "ru-fz-59",
            "ru-fz-99",
            "ru-fz-248",
            "ru-fz-3",
            "ru-fz-53",
            "ru-fz-prokuratura",
            "ru-fz-323",
            "ru-fz-326",
            "ru-fz-181",
            "ru-fz-255",
            "ru-fz-400",
            "ru-fz-44",
            "ru-fz-223",
            "ru-fz-115",
            "ru-fz-422",
            "ru-fz-152",
            "ru-fz-149",
            "ru-fkz-pravitelstvo",
            "ru-fkz-ks",
            "ru-fkz-sudsystem",
            "ru-fkz-vs",
            "ru-fkz-ombudsman",
            "ru-fkz-arbitr",
            "ru-fkz-voennoe",
            "ru-fkz-cs",
            "ru-fkz-referendum",
            "ru-fkz-sou",
            "ru-fkz-voensud",
        ],
    ),
    AssistantPreset(
        slug="lawyer-kz",
        name="Юрист РК",
        description="Право Республики Казахстан: УК, УПК, КоАП, ГК (общая + особенная), ТК + новостная лента.",
        icon="scale",
        prompt_file="lawyer-kz.md",
        collection_slugs=[
            "kz-uk-rk",
            "kz-upk-rk",
            "kz-koap-rk",
            "kz-gk-rk-general",
            "kz-gk-rk-special",
            "kz-tk-rk",
            "kz-news",
        ],
    ),
    AssistantPreset(
        slug="accountant-ru",
        name="Бухгалтер РФ (УСН)",
        description="Упрощённая система налогообложения: НК РФ глава 26.2, ФНС, МоёДело, новости.",
        icon="calculator",
        prompt_file="accountant-ru.md",
        collection_slugs=[
            "ru-fns-usn",
            "ru-nk-rf-glava-26-2",
            "ru-bukh-news",
            "ru-moedelo-usn",
        ],
    ),
    AssistantPreset(
        slug="accountant-kz",
        name="Бухгалтер РК",
        description="Налоговое и бухгалтерское право Казахстана: НК РК + новости.",
        icon="calculator",
        prompt_file="accountant-kz.md",
        collection_slugs=[
            "kz-nk-rk",
            "kz-news",
        ],
    ),
    AssistantPreset(
        slug="accountant-ie",
        name="Accountant Ireland",
        description="Irish tax & accountancy: revenue.ie, ICAEW, CAI, CPA, ATI, professional forums (English).",
        icon="calculator",
        prompt_file=None,  # No EN prompt yet — falls back to platform-agent
        collection_slugs=[
            "irish-tax",
            "accountant-forums-ireland",
            "accounting-technicians-ie",
            "boards-ie-accountancy",
            "chartered-accountants-ie",
            "cpa-ireland",
            "icaew-ireland",
        ],
    ),
    AssistantPreset(
        slug="seo-marketing",
        name="SEO / Маркетинг",
        description="Поисковая оптимизация, реклама, продвижение в Яндексе и Google. По материалам sbup.com.",
        icon="search",
        prompt_file="seo-ru.md",  # Lands after PR #772 merges
        collection_slugs=[
            "ru-sbup-seo",
        ],
    ),
    AssistantPreset(
        slug="secretary24",
        name="Секретарь24",
        description="Универсальный ассистент платформы Секретарь24 — помогает настроить персонального помощника.",
        icon="bot",
        prompt_file="platform-agent.md",
        collection_slugs=["default"],
    ),
    AssistantPreset(
        slug="custom",
        name="Свой ассистент",
        description="Пустой чат без коллекций. Промпт и базу знаний можно настроить позже.",
        icon="edit",
        prompt_file=None,
        collection_slugs=[],
        rag_mode=None,
    ),
]


def _load_prompt(filename: str | None) -> str | None:
    """Read prompt file from PROMPTS_DIR, return None if missing."""
    if not filename:
        return None
    path = PROMPTS_DIR / filename
    try:
        text = path.read_text(encoding="utf-8").strip()
        return text or None
    except OSError as exc:
        logger.warning("Preset prompt file not found (%s): %s", path, exc)
        return None


async def resolve_presets(
    knowledge_collection_service: Any,
) -> list[dict[str, Any]]:
    """Materialize PRESETS into JSON-ready dicts.

    For each preset:
      * Load system_prompt from disk (None if file is missing).
      * Resolve collection_slugs against the live DB; keep only existing
        collections, return ``[{id, slug, name}, ...]`` so the frontend can
        show what will actually be attached.
      * Compute ``ready`` flag — true if the preset has at least one
        collection OR is the explicit "custom" no-collections card.

    The endpoint owns DB session injection and just hands us the service.
    """
    # Build a slug → record lookup once.
    all_collections = await knowledge_collection_service.get_all(enabled_only=True)
    by_slug = {c["slug"]: c for c in all_collections if c.get("slug")}

    out: list[dict[str, Any]] = []
    for preset in PRESETS:
        resolved: list[dict[str, Any]] = []
        for slug in preset.collection_slugs:
            rec = by_slug.get(slug)
            if rec:
                resolved.append(
                    {
                        "id": rec["id"],
                        "slug": rec["slug"],
                        "name": rec["name"],
                    }
                )
        out.append(
            {
                "slug": preset.slug,
                "name": preset.name,
                "description": preset.description,
                "icon": preset.icon,
                "system_prompt": _load_prompt(preset.prompt_file),
                "rag_mode": preset.rag_mode,
                "collections": resolved,
                "knowledge_collection_ids": [c["id"] for c in resolved],
                "ready": preset.slug == "custom" or bool(resolved),
            }
        )
    return out

#!/usr/bin/env python3
"""Seed initial RSS feed subscriptions into the knowledge base.

Idempotent: skips collections/feeds that already exist (by slug/url).

Creates 3 news-flow collections:
  - ru-bukh-news    — Russian accountant news (federal codes updates,
                       Минфин letters, КонсультантПлюс bulletins, Главбух)
  - ru-pravo-news   — Russian lawyer news (court practice, federal-law
                       hot-docs, ПРАВО.RU)
  - kz-news         — Kazakhstan news (adilet НПА updates, mybuh.kz,
                       digitalbusiness.kz)

Run:
  venv/bin/python scripts/seed_rss_feeds.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import AsyncSessionLocal
from db.repositories.rss_feed import RSSFeedRepository
from modules.knowledge.service import knowledge_collection_service


COLLECTIONS = [
    {
        "name": "RU Бухгалтер — новости",
        "slug": "ru-bukh-news",
        "description": (
            "Свежие новости для российских бухгалтеров: горячие документы "
            "КонсультантПлюс, обновления федерального законодательства, "
            "письма Минфина, журнал «Главбух»."
        ),
    },
    {
        "name": "RU Юрист — новости",
        "slug": "ru-pravo-news",
        "description": (
            "Юридические новости и обновления законодательства РФ: "
            "ПРАВО.RU, горячие документы КонсультантПлюс, Гарант "
            "(новое в фед.зак-ве)."
        ),
    },
    {
        "name": "KZ — новости",
        "slug": "kz-news",
        "description": (
            "Казахстан: НПА Республики Казахстан (adilet.zan.kz), "
            "бухгалтерские новости (mybuh.kz), бизнес-новости "
            "(digitalbusiness.kz)."
        ),
    },
]


FEEDS = [
    # ---------------- RU bookkeeper ----------------
    {
        "name": "КонсультантПлюс — Новости для бухгалтера",
        "url": "https://www.consultant.ru/rss/db.xml",
        "collection_slug": "ru-bukh-news",
        "fetch_full_text": True,
    },
    {
        "name": "Главбух — новости журнала",
        "url": "https://www.glavbukh.ru/rss/news.xml",
        "collection_slug": "ru-bukh-news",
        "fetch_full_text": True,
    },
    {
        "name": "Гарант — Бухучёт (консультации)",
        "url": "https://rss.garant.ru/consult/account/",
        "collection_slug": "ru-bukh-news",
        "fetch_full_text": True,
    },
    {
        "name": "Гарант — Налоги (консультации)",
        "url": "https://rss.garant.ru/consult/nalog/",
        "collection_slug": "ru-bukh-news",
        "fetch_full_text": True,
    },
    {
        "name": "Гарант — Письма Минфина",
        "url": "https://rss.garant.ru/hotlaw/minfin/",
        "collection_slug": "ru-bukh-news",
        "fetch_full_text": True,
    },
    # ---------------- RU lawyer ----------------
    {
        "name": "ПРАВО.RU — новости",
        "url": "https://pravo.ru/rss/",
        "collection_slug": "ru-pravo-news",
        "fetch_full_text": True,
    },
    {
        "name": "КонсультантПлюс — Горячие документы",
        "url": "https://www.consultant.ru/rss/hotdocs.xml",
        "collection_slug": "ru-pravo-news",
        "fetch_full_text": True,
    },
    {
        "name": "КонсультантПлюс — Новое в законодательстве",
        "url": "https://www.consultant.ru/rss/nw.xml",
        "collection_slug": "ru-pravo-news",
        "fetch_full_text": True,
    },
    {
        "name": "КонсультантПлюс — Федеральное законодательство",
        "url": "https://www.consultant.ru/rss/fd.xml",
        "collection_slug": "ru-pravo-news",
        "fetch_full_text": True,
    },
    {
        "name": "Гарант — Новое в фед. законодательстве",
        "url": "https://rss.garant.ru/hotlaw/federal/",
        "collection_slug": "ru-pravo-news",
        "fetch_full_text": True,
    },
    # ---------------- KZ ----------------
    {
        "name": "Әділет — Последние НПА РК",
        "url": "https://adilet.zan.kz/rus/docs/rss",
        "collection_slug": "kz-news",
        "fetch_full_text": False,  # adilet uses non-standard SSL CA — keep light
        "verify_ssl": False,
    },
    {
        "name": "MyBuh.kz — Бухгалтерия Казахстана",
        "url": "https://mybuh.kz/rss",
        "collection_slug": "kz-news",
        "fetch_full_text": True,
    },
    {
        "name": "DigitalBusiness.kz — бизнес-новости",
        "url": "https://digitalbusiness.kz/feed",
        "collection_slug": "kz-news",
        "fetch_full_text": True,
    },
]


async def main() -> None:
    # Ensure collections exist
    slug_to_id: dict[str, int] = {}
    for col in COLLECTIONS:
        existing = await knowledge_collection_service.get_by_slug(col["slug"])
        if existing:
            print(f"  collection ✓ {col['slug']} (id={existing['id']})")
            slug_to_id[col["slug"]] = existing["id"]
            continue
        created = await knowledge_collection_service.create(
            name=col["name"],
            slug=col["slug"],
            description=col["description"],
            enabled=True,
        )
        print(f"  collection + {col['slug']} (id={created['id']})")
        slug_to_id[col["slug"]] = created["id"]

    # Ensure feeds exist
    async with AsyncSessionLocal() as session:
        repo = RSSFeedRepository(session)
        for feed in FEEDS:
            existing = await repo.get_by_url(feed["url"])
            if existing:
                print(f"  feed ✓ {feed['name']}")
                continue
            collection_id = slug_to_id.get(feed["collection_slug"])
            if not collection_id:
                print(f"  feed ✗ {feed['name']} — collection missing")
                continue
            await repo.create_feed(
                name=feed["name"],
                url=feed["url"],
                collection_id=collection_id,
                fetch_full_text=feed.get("fetch_full_text", True),
                verify_ssl=feed.get("verify_ssl", True),
                enabled=True,
                workspace_id=1,
            )
            print(f"  feed + {feed['name']}")
        await session.commit()

    print("\nDone. Run sync via admin UI or:")
    print("  curl -XPOST <url>/admin/rss/sync-all -H 'Authorization: Bearer <token>'")


if __name__ == "__main__":
    asyncio.run(main())

"""RSS knowledge ingestion service.

Each enabled `RSSFeed` row points to a URL and a `KnowledgeCollection`. On
sync, we fetch the feed, deduplicate items by `guid`, optionally fetch the
full article HTML and convert it to markdown, and store the result as a
`KnowledgeDocument`. After processing all new items we publish a single
`DatasetSynced` event so the existing pipeline (BM25 reload + Vector Search
upsert) picks up the new documents.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from time import mktime
from typing import Any, Optional

from db.database import AsyncSessionLocal
from db.repositories.rss_feed import RSSFeedItemRepository, RSSFeedRepository


logger = logging.getLogger(__name__)

USER_AGENT = "AISecretary-RSS/1.0 (+https://ai-sekretar24.ru)"
WIKI_PAGES_DIR = Path("wiki-pages")
REQUEST_TIMEOUT = 25
MAX_FULL_TEXT_BYTES = 1_500_000  # 1.5 MB — abort fetch if response is larger
MAX_ITEMS_PER_FEED = 50  # cap per sync to avoid surprise spikes


def _slugify(text: str, max_len: int = 80) -> str:
    """Build a filesystem-safe slug from arbitrary text."""
    text = text.lower().strip()
    # Drop everything that's not letters/digits/dash/underscore (keep cyrillic)
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text[:max_len] or "item"


def _filename_for(feed_slug: str, guid: str, title: str) -> str:
    """Generate stable, unique filename for an RSS item."""
    h = hashlib.md5(guid.encode("utf-8")).hexdigest()[:10]
    title_slug = _slugify(title, max_len=60)
    return f"rss-{feed_slug}-{title_slug}-{h}.md"


def _strip_html_to_markdown(html_text: str) -> str:
    """Best-effort HTML → plain markdown via lxml. Falls back to text-only."""
    if not html_text:
        return ""
    try:
        from lxml import html as lxml_html

        tree = lxml_html.fromstring(html_text)
        # Remove obvious chrome
        for bad in tree.xpath(
            ".//script | .//style | .//noscript | .//nav | .//header | .//footer"
            "| .//aside | .//form | .//iframe"
            '| .//*[contains(@class, "share")]'
            '| .//*[contains(@class, "social")]'
            '| .//*[contains(@class, "advert")]'
            '| .//*[contains(@class, "banner")]'
            '| .//*[contains(@class, "cookie")]'
            '| .//*[contains(@class, "newsletter")]'
            '| .//*[contains(@id, "cookie")]'
        ):
            parent = bad.getparent()
            if parent is not None:
                parent.remove(bad)

        lines: list[str] = []
        _walk(tree, lines)
        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    except Exception as e:
        logger.debug("lxml conversion failed, falling back to text: %s", e)
        return re.sub(r"<[^>]+>", " ", html_text).strip()


def _walk(el: Any, lines: list[str], depth: int = 0) -> None:
    tag = el.tag if isinstance(el.tag, str) else ""
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(tag[1])
        text = (el.text_content() or "").strip()
        if text:
            lines.append(f"\n{'#' * level} {text}\n")
        return
    if tag == "li":
        text = (el.text_content() or "").strip()
        if text:
            indent = "  " * max(0, depth - 1)
            lines.append(f"{indent}- {text}")
        return
    if tag == "p":
        text = (el.text_content() or "").strip()
        if text:
            lines.append(f"\n{text}\n")
        return
    if tag == "blockquote":
        text = (el.text_content() or "").strip()
        if text:
            for line in text.split("\n"):
                line = line.strip()
                if line:
                    lines.append(f"> {line}")
            lines.append("")
        return
    for child in el:
        if isinstance(child.tag, str):
            _walk(child, lines, depth + 1)


def _entry_guid(entry: Any) -> Optional[str]:
    """Build a stable GUID for an RSS entry."""
    raw = (
        getattr(entry, "id", None)
        or getattr(entry, "guid", None)
        or getattr(entry, "link", None)
        or entry.get("title")
    )
    if not raw:
        return None
    return str(raw)[:500]


def _entry_pub_date(entry: Any) -> Optional[datetime]:
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = getattr(entry, attr, None) or entry.get(attr)
        if parsed:
            try:
                return datetime.fromtimestamp(mktime(parsed))
            except Exception:
                continue
    return None


def _entry_summary(entry: Any) -> str:
    """Pick the richest content block available from a feedparser entry."""
    contents = entry.get("content") or []
    if contents:
        best = max(contents, key=lambda c: len(c.get("value", "") or ""))
        if best.get("value"):
            return str(best["value"])
    summary = entry.get("summary") or entry.get("description") or ""
    return str(summary)


def _fetch_feed_sync(
    url: str, etag: Optional[str], modified: Optional[str], verify_ssl: bool
) -> Any:
    """Sync feedparser call — must run in a thread pool."""
    import feedparser

    request_headers = {"User-Agent": USER_AGENT}
    if not verify_ssl:
        # feedparser passes through to urllib; pre-disable certifi verification
        import ssl

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return feedparser.parse(
            url,
            etag=etag,
            modified=modified,
            request_headers=request_headers,
            handlers=[],
            ssl_context=ctx,
        )
    return feedparser.parse(
        url,
        etag=etag,
        modified=modified,
        request_headers=request_headers,
    )


def _fetch_article_sync(url: str, verify_ssl: bool) -> Optional[str]:
    """Fetch full article HTML. Returns None on any error."""
    import requests

    try:
        if not verify_ssl:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "ru,en;q=0.8"},
            timeout=REQUEST_TIMEOUT,
            verify=verify_ssl,
            stream=True,
        )
        if resp.status_code >= 400:
            return None
        ctype = resp.headers.get("content-type", "")
        if "html" not in ctype.lower():
            return None
        # Read at most MAX_FULL_TEXT_BYTES to avoid pulling huge pages
        chunks: list[bytes] = []
        size = 0
        for chunk in resp.iter_content(chunk_size=16384):
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_FULL_TEXT_BYTES:
                break
        body = b"".join(chunks)
        # feedparser-style charset detection: prefer apparent_encoding
        encoding = resp.encoding or resp.apparent_encoding or "utf-8"
        return body.decode(encoding, errors="replace")
    except Exception as e:
        logger.debug("Full-text fetch failed for %s: %s", url, e)
        return None


def _build_document_body(entry: Any, full_html: Optional[str]) -> str:
    """Compose the markdown body to write to disk."""
    title = entry.get("title", "").strip()
    link = entry.get("link", "").strip()
    pub = entry.get("published", "") or entry.get("updated", "") or ""
    author = entry.get("author", "")

    lines = [f"# {title}", ""]
    meta = []
    if pub:
        meta.append(f"**Дата:** {pub}")
    if author:
        meta.append(f"**Автор:** {author}")
    if link:
        meta.append(f"**Источник:** [{link}]({link})")
    if meta:
        lines.extend(meta)
        lines.append("")

    if full_html:
        body_md = _strip_html_to_markdown(full_html)
    else:
        body_md = _strip_html_to_markdown(_entry_summary(entry))

    if body_md:
        lines.append(body_md)
    elif _entry_summary(entry):
        lines.append(_strip_html_to_markdown(_entry_summary(entry)))

    return "\n".join(lines).strip() + "\n"


async def sync_feed(feed_id: int) -> dict:
    """Sync a single feed; return stats dict."""
    from modules.knowledge.service import knowledge_collection_service, knowledge_doc_service

    stats = {"feed_id": feed_id, "new_items": 0, "errors": 0, "total_items": 0}

    async with AsyncSessionLocal() as session:
        feed_repo = RSSFeedRepository(session)
        feed = await feed_repo.get_feed(feed_id)
        if not feed:
            stats["error"] = "feed_not_found"
            return stats
        feed_url = feed.url
        feed_collection_id = feed.collection_id
        feed_etag = feed.last_etag
        feed_modified = feed.last_modified
        feed_fetch_full = feed.fetch_full_text
        feed_verify_ssl = feed.verify_ssl
        feed_workspace_id = feed.workspace_id
        feed_name = feed.name

    if not feed_collection_id:
        logger.warning("RSS feed %s has no collection, skipping", feed_id)
        return stats

    # Mark as syncing
    async with AsyncSessionLocal() as session:
        feed_repo = RSSFeedRepository(session)
        await feed_repo.update_sync_status(feed_id, status="syncing", error=None)
        await session.commit()

    try:
        parsed = await asyncio.to_thread(
            _fetch_feed_sync, feed_url, feed_etag, feed_modified, feed_verify_ssl
        )
    except Exception as e:
        logger.warning("RSS feed %s fetch failed: %s", feed_id, e)
        async with AsyncSessionLocal() as session:
            feed_repo = RSSFeedRepository(session)
            await feed_repo.update_sync_status(feed_id, status="error", error=str(e)[:500])
            await session.commit()
        stats["error"] = str(e)
        return stats

    bozo_exception = getattr(parsed, "bozo_exception", None)
    if parsed.get("status") in (304, "304"):
        logger.info("RSS feed %s: not modified", feed_id)
        async with AsyncSessionLocal() as session:
            feed_repo = RSSFeedRepository(session)
            await feed_repo.update_sync_status(feed_id, status="idle", error=None)
            await session.commit()
        return stats

    entries = list(getattr(parsed, "entries", []) or [])[:MAX_ITEMS_PER_FEED]
    stats["total_items"] = len(entries)

    if not entries and bozo_exception:
        msg = f"feed parse error: {bozo_exception}"
        logger.warning("RSS feed %s: %s", feed_id, msg)
        async with AsyncSessionLocal() as session:
            feed_repo = RSSFeedRepository(session)
            await feed_repo.update_sync_status(feed_id, status="error", error=msg[:500])
            await session.commit()
        stats["error"] = msg
        return stats

    # Resolve collection metadata
    collection = await knowledge_collection_service.get_by_id(feed_collection_id)
    if not collection:
        logger.warning("RSS feed %s collection %s missing", feed_id, feed_collection_id)
        async with AsyncSessionLocal() as session:
            feed_repo = RSSFeedRepository(session)
            await feed_repo.update_sync_status(feed_id, status="error", error="collection missing")
            await session.commit()
        stats["error"] = "collection missing"
        return stats

    base_dir = Path(collection.get("base_dir") or "wiki-pages")
    base_dir.mkdir(parents=True, exist_ok=True)
    feed_slug = _slugify(feed_name, max_len=40)

    # Determine which guids are new
    async with AsyncSessionLocal() as session:
        item_repo = RSSFeedItemRepository(session)
        known = await item_repo.get_known_guids(feed_id)

    new_documents: list[dict] = []
    for entry in entries:
        guid = _entry_guid(entry)
        if not guid or guid in known:
            continue
        title = (entry.get("title") or "untitled").strip()[:500]
        link = (entry.get("link") or "").strip() or None
        pub = _entry_pub_date(entry)

        full_html: Optional[str] = None
        if feed_fetch_full and link:
            full_html = await asyncio.to_thread(_fetch_article_sync, link, feed_verify_ssl)

        body = _build_document_body(entry, full_html)
        if not body.strip():
            stats["errors"] += 1
            continue

        filename = _filename_for(feed_slug, guid, title)
        path = base_dir / filename
        try:
            path.write_text(body, encoding="utf-8")
        except Exception as e:
            logger.warning("RSS write failed for %s: %s", filename, e)
            stats["errors"] += 1
            continue

        # Section count is rough — count headings + 1
        section_count = max(1, body.count("\n# ") + body.count("\n## "))

        # Create knowledge document + persisted RSS item
        try:
            doc = await knowledge_doc_service.create(
                filename=filename,
                title=title,
                source_type="rss",
                file_size_bytes=len(body.encode("utf-8")),
                section_count=section_count,
                collection_id=feed_collection_id,
                workspace_id=feed_workspace_id,
            )
        except Exception as e:
            logger.warning("RSS doc create failed: %s", e)
            stats["errors"] += 1
            continue

        async with AsyncSessionLocal() as session:
            item_repo = RSSFeedItemRepository(session)
            await item_repo.add_item(
                feed_id=feed_id,
                guid=guid,
                title=title,
                link=link,
                document_id=doc["id"],
                pub_date=pub,
            )
            await session.commit()

        new_documents.append(
            {
                "filename": filename,
                "title": title,
                "source_type": "rss",
                "file_size_bytes": doc["file_size_bytes"],
                "section_count": section_count,
            }
        )
        stats["new_items"] += 1

    # Update feed status + counters + ETag
    new_etag = parsed.get("etag")
    new_modified = parsed.get("modified")
    item_count_total = len(known) + stats["new_items"]
    async with AsyncSessionLocal() as session:
        feed_repo = RSSFeedRepository(session)
        await feed_repo.update_sync_status(
            feed_id,
            status="idle",
            error=None,
            item_count=item_count_total,
            etag=new_etag,
            last_modified=new_modified,
        )
        await session.commit()

    # Reload BM25 + sync to Vector Search directly (no DatasetSynced event,
    # since its handler deletes-and-recreates documents which would orphan
    # our rss_feed_items.document_id FKs).
    if new_documents:
        try:
            from app.dependencies import get_container

            container = get_container()
            wiki_rag = getattr(container, "wiki_rag_service", None)
            if wiki_rag:
                existing = await knowledge_doc_service.get_by_collection(feed_collection_id)
                filenames = [d["filename"] for d in existing]
                wiki_rag.reload_collection(
                    feed_collection_id, filenames, base_dir, slug=collection["slug"]
                )

                vs_client = getattr(container, "vector_search_client", None)
                if vs_client:
                    from modules.knowledge.tasks import sync_collection_to_vector_search

                    await sync_collection_to_vector_search(
                        wiki_rag, vs_client, feed_collection_id, collection["slug"]
                    )
        except Exception as e:
            logger.warning("RSS feed %s reload failed: %s", feed_id, e)

    logger.info(
        "RSS feed sync done: feed_id=%s name=%s new=%d total=%d",
        feed_id,
        feed_name,
        stats["new_items"],
        stats["total_items"],
    )
    return stats


async def sync_all_feeds() -> dict:
    """Periodic task body: iterate over enabled feeds and sync each in turn."""
    async with AsyncSessionLocal() as session:
        feed_repo = RSSFeedRepository(session)
        feeds = await feed_repo.list_feed_orms(enabled_only=True)

    aggregate = {"feeds": 0, "new_items": 0, "errors": 0}
    for feed in feeds:
        aggregate["feeds"] += 1
        try:
            stats = await sync_feed(feed.id)
        except Exception as e:
            logger.exception("RSS feed %s sync errored: %s", feed.id, e)
            aggregate["errors"] += 1
            continue
        aggregate["new_items"] += stats.get("new_items", 0)
        aggregate["errors"] += stats.get("errors", 0)
    if aggregate["feeds"]:
        logger.info(
            "RSS sync round done: feeds=%d new=%d errors=%d",
            aggregate["feeds"],
            aggregate["new_items"],
            aggregate["errors"],
        )
    return aggregate

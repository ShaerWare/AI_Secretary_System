#!/usr/bin/env python3
"""
Step 1: Download raw HTML from Irish accountancy websites.

BFS crawler with per-site link extraction, rate limiting, and dedup.

Usage:
  python scripts/scrape_digitax/scrape.py                     # all sites
  python scripts/scrape_digitax/scrape.py --site icaew-ireland # single site
  python scripts/scrape_digitax/scrape.py --site boards-ie-accountancy --max-pages 10
  python scripts/scrape_digitax/scrape.py --stats              # show file counts
"""

import argparse
import re
from collections import deque
from urllib.parse import urlparse

from config import (
    SITES,
    fetch_page,
    get_site_raw_dir,
    log,
    setup_session,
    url_to_filename,
)
from lxml import html as lxml_html


# ---------------------------------------------------------------------------
# Generic BFS crawler
# ---------------------------------------------------------------------------


def crawl_site(
    session,
    slug: str,
    site_cfg: dict,
    max_pages: int | None = None,
) -> dict:
    """
    BFS crawl a site. Returns stats dict.

    Uses per-site `extract_links` and `should_follow` functions.
    """
    raw_dir = get_site_raw_dir(slug)
    limit = max_pages or site_cfg["max_pages"]
    base_url = site_cfg["base_url"]

    # Build seed URLs
    seeds = [base_url.rstrip("/") + p for p in site_cfg["seed_paths"]]

    visited: set[str] = set()
    queue: deque[str] = deque(seeds)
    stats = {"downloaded": 0, "skipped": 0, "errors": 0, "pages_visited": 0}

    # Get site-specific link extractor
    extract_fn = LINK_EXTRACTORS.get(slug, extract_links_generic)
    filter_fn = LINK_FILTERS.get(slug)

    while queue and stats["pages_visited"] < limit:
        url = queue.popleft()
        url = _normalize_url(url)

        if url in visited:
            continue
        visited.add(url)

        # Check if already downloaded
        fname = url_to_filename(url) + ".html"
        filepath = raw_dir / fname
        if filepath.exists() and filepath.stat().st_size > 0:
            stats["skipped"] += 1
            # Still parse for links if we haven't hit the limit
            html_text = filepath.read_text(encoding="utf-8", errors="ignore")
            new_links = extract_fn(url, html_text, base_url)
            for link in new_links:
                link = _normalize_url(link)
                if link not in visited and _is_same_domain(link, base_url):
                    if not filter_fn or filter_fn(link, site_cfg):
                        queue.append(link)
            continue

        # Fetch
        html_text = fetch_page(session, url)
        if html_text is None:
            stats["errors"] += 1
            stats["pages_visited"] += 1
            continue

        # Save
        filepath.write_text(html_text, encoding="utf-8")
        stats["downloaded"] += 1
        stats["pages_visited"] += 1

        # Extract links
        new_links = extract_fn(url, html_text, base_url)
        for link in new_links:
            link = _normalize_url(link)
            if link not in visited and _is_same_domain(link, base_url):
                if not filter_fn or filter_fn(link, site_cfg):
                    queue.append(link)

        if stats["downloaded"] % 20 == 0:
            log.info(
                "[%s] Progress: %d downloaded, %d skipped, %d errors, queue=%d",
                slug,
                stats["downloaded"],
                stats["skipped"],
                stats["errors"],
                len(queue),
            )

    log.info(
        "[%s] Done: %d downloaded, %d skipped, %d errors",
        slug,
        stats["downloaded"],
        stats["skipped"],
        stats["errors"],
    )
    return stats


def _normalize_url(url: str) -> str:
    """Drop the fragment, preserve a trailing slash on directory-looking paths.

    Some servers (e.g. nalog.gov.ru) return 404 without the trailing slash on
    directory URLs. Others (e.g. GitHub) return a redirect. Stripping the
    slash blindly (as the older implementation did) broke the former. The
    heuristic used here: keep the trailing slash if the last path segment
    does not look like a file (no dot) and the URL originally had one;
    strip it otherwise so `/foo.html/` and `/foo.html` don't diverge.
    """
    parsed = urlparse(url)
    path = parsed.path or "/"
    had_trailing = path.endswith("/") and path != "/"
    stripped = path.rstrip("/") or "/"
    last_seg = stripped.rsplit("/", 1)[-1]
    looks_like_file = "." in last_seg
    if had_trailing and not looks_like_file:
        path = stripped + "/"
    else:
        path = stripped
    query = parsed.query
    normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
    if query:
        normalized += f"?{query}"
    return normalized


def _is_same_domain(url: str, base_url: str) -> bool:
    """Check if URL is on the same domain (or www variant)."""
    url_host = urlparse(url).netloc.lower().replace("www.", "")
    base_host = urlparse(base_url).netloc.lower().replace("www.", "")
    return url_host == base_host


# ---------------------------------------------------------------------------
# Generic link extractor
# ---------------------------------------------------------------------------


def extract_links_generic(url: str, html_text: str, base_url: str) -> list[str]:
    """Extract all internal links from a page."""
    try:
        tree = lxml_html.fromstring(html_text)
        tree.make_links_absolute(url)
    except Exception:
        return []

    links = []
    for el, _attr, link, _pos in tree.iterlinks():
        if not link:
            continue
        parsed = urlparse(link)
        # Skip non-HTTP, files, anchors
        if parsed.scheme not in ("http", "https"):
            continue
        if re.search(
            r"\.(pdf|jpg|jpeg|png|gif|svg|css|js|zip|doc|docx|xls|xlsx|ppt|pptx)$",
            parsed.path,
            re.IGNORECASE,
        ):
            continue
        links.append(link)
    return links


# ---------------------------------------------------------------------------
# Site-specific link extractors
# ---------------------------------------------------------------------------


def extract_links_boards_ie(url: str, html_text: str, base_url: str) -> list[str]:
    """Extract thread links and pagination from boards.ie."""
    try:
        tree = lxml_html.fromstring(html_text)
        tree.make_links_absolute(url)
    except Exception:
        return []

    links = []
    for a in tree.xpath("//a[@href]"):
        href = a.get("href", "")
        if not href:
            continue
        # Thread links: /discussion/NNNNN/...
        if "/discussion/" in href or "/categories/accountancy" in href:
            links.append(href)

    return links


def filter_boards_ie(url: str, cfg: dict) -> bool:
    """Only follow accountancy category and discussion pages."""
    path = urlparse(url).path
    return "/categories/accountancy" in path or "/discussion/" in path


def extract_links_accountant_forums(url: str, html_text: str, base_url: str) -> list[str]:
    """Extract thread links from accountantforums.com search results."""
    try:
        tree = lxml_html.fromstring(html_text)
        tree.make_links_absolute(url)
    except Exception:
        return []

    links = []
    for a in tree.xpath("//a[@href]"):
        href = a.get("href", "")
        if not href:
            continue
        # Thread links: /threads/...
        if "/threads/" in href or ("/search/" in href and "q=Ireland" in href):
            links.append(href)

    return links


def filter_accountant_forums(url: str, cfg: dict) -> bool:
    """Only follow search results and thread pages."""
    path = urlparse(url).path
    return "/threads/" in path or "/search/" in path


def extract_links_icaew(url: str, html_text: str, base_url: str) -> list[str]:
    """Extract links from ICAEW. Scope is enforced by filter_icaew, which reads
    `stay_under` and `ireland_keywords` from site config — we pass everything
    through here and let the filter reject unrelated pages."""
    return extract_links_generic(url, html_text, base_url)


def filter_icaew(url: str, cfg: dict) -> bool:
    """Stay within Ireland-related content on icaew.com.

    Prefer `ireland_keywords` (matched against URL path) when configured —
    lets the crawler follow Ireland-relevant pages that live outside the
    small /technical/by-country/europe/ireland subsection. Fall back to
    `stay_under` (legacy behaviour) otherwise.
    """
    path = urlparse(url).path.lower()
    # Global skip — avoid obvious junk
    skip_patterns = ["/login", "/register", "/search", "/media/", "/assets/", "/my-account"]
    if any(p in path for p in skip_patterns):
        return False

    ireland_keywords = cfg.get("ireland_keywords")
    if ireland_keywords:
        return any(kw.lower() in path for kw in ireland_keywords)

    # `path` is already lower-cased; lower the prefix too so mixed-case
    # document IDs (e.g. consultant.ru `/document/cons_doc_LAW_28165/`) match.
    stay_under = cfg.get("stay_under", "/technical/by-country/europe/ireland").lower()
    return stay_under in path


def filter_professional_site(url: str, cfg: dict) -> bool:
    """Filter for professional body sites — skip login, search, media."""
    path = urlparse(url).path.lower()
    skip_patterns = [
        "/login",
        "/register",
        "/search",
        "/cart",
        "/checkout",
        "/my-account",
        "/wp-admin",
        "/wp-content",
        "/feed",
        "/tag/",
        "/author/",
        "/comment",
        "/print/",
        "/media/",
        "/uploads/",
        "/assets/",
    ]
    return not any(p in path for p in skip_patterns)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

LINK_EXTRACTORS: dict[str, callable] = {
    "boards-ie-accountancy": extract_links_boards_ie,
    "accountant-forums-ireland": extract_links_accountant_forums,
    "icaew-ireland": extract_links_icaew,
}

LINK_FILTERS: dict[str, callable] = {
    "boards-ie-accountancy": filter_boards_ie,
    "accountant-forums-ireland": filter_accountant_forums,
    "icaew-ireland": filter_icaew,
    "chartered-accountants-ie": filter_professional_site,
    "cpa-ireland": filter_professional_site,
    "accounting-technicians-ie": filter_professional_site,
    "iafa": filter_professional_site,
    # Russian accountant assistant sites — all three rely on the `stay_under`
    # path prefix to keep the crawler inside the relevant section.
    # filter_icaew reads `stay_under` from cfg, so it works as a generic
    # stay-under filter when `ireland_keywords` is absent.
    "ru-fns-usn": filter_icaew,
    "ru-nk-rf-glava-26-2": filter_icaew,
    "ru-moedelo-usn": filter_icaew,
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def show_stats():
    """Show downloaded file counts per site."""
    from config import RAW_DIR

    print("\n=== Scrape Stats ===\n")
    total = 0
    for slug in SITES:
        d = RAW_DIR / slug
        count = len(list(d.glob("*.html"))) if d.exists() else 0
        total += count
        print(f"  {slug:30s} {count:5d} files")
    print(f"\n  {'TOTAL':30s} {total:5d} files\n")


def main():
    parser = argparse.ArgumentParser(description="Scrape Irish accountancy websites")
    parser.add_argument(
        "--site",
        choices=list(SITES.keys()),
        help="Scrape single site (default: all)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Override max pages per site (0=use config)",
    )
    parser.add_argument("--stats", action="store_true", help="Show file counts")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    session = setup_session()
    sites_to_scrape = {args.site: SITES[args.site]} if args.site else SITES

    all_stats = {}
    for slug, cfg in sites_to_scrape.items():
        log.info("=" * 60)
        log.info("Scraping: %s (%s)", cfg["name"], cfg["base_url"])
        log.info("=" * 60)

        site_stats = crawl_site(
            session,
            slug,
            cfg,
            max_pages=args.max_pages or None,
        )
        all_stats[slug] = site_stats

    # Summary
    print("\n=== Scrape Summary ===\n")
    total_dl = 0
    for slug, s in all_stats.items():
        print(
            f"  {slug:30s}  downloaded={s['downloaded']:4d}  "
            f"skipped={s['skipped']:4d}  errors={s['errors']:3d}"
        )
        total_dl += s["downloaded"]
    print(f"\n  Total new downloads: {total_dl}\n")


if __name__ == "__main__":
    main()

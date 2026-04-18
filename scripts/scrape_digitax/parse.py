#!/usr/bin/env python3
"""
Step 2: Parse downloaded HTML into clean markdown documents.

Per-site content selectors, forum post merging, metadata headers.

Usage:
  python scripts/scrape_digitax/parse.py                        # all sites
  python scripts/scrape_digitax/parse.py --site icaew-ireland   # single site
  python scripts/scrape_digitax/parse.py --stats                # show counts
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path

from config import (
    MIN_CONTENT_LENGTH,
    SITES,
    get_site_parsed_dir,
    get_site_raw_dir,
    log,
)
from lxml import html as lxml_html


TODAY = date.today().isoformat()

# ---------------------------------------------------------------------------
# Filename filters — skip garbage before parsing
# ---------------------------------------------------------------------------

# Files that should never be parsed (listing pages, search, cdn, etc.)
SKIP_FILENAMES = {
    "boards-ie-accountancy": [
        # Category listing / sort / filter pages — no article content
        re.compile(r"^categories__"),
        # Individual comment permalink pages (duplicate content from full threads)
        re.compile(r"comment__\d+"),
    ],
    "accountant-forums-ireland": [
        # Search result listing pages
        re.compile(r"^search__"),
    ],
    "accounting-technicians-ie": [
        # Cloudflare email protection pages
        re.compile(r"cdn-cgi"),
    ],
}

# Content patterns that indicate a garbage page (check after parsing)
GARBAGE_CONTENT_PATTERNS = [
    re.compile(r"Please login below", re.IGNORECASE),
    re.compile(r"^# 404 error", re.MULTILINE),
    re.compile(r"Page not found", re.IGNORECASE),
    re.compile(r"<div id=\"app\"></div>"),  # SPA shell
    re.compile(r"^# Welcome to the CPA Ireland website\s*$", re.MULTILINE),
]


def should_skip_file(filename: str, slug: str) -> bool:
    """Check if a file should be skipped based on filename patterns."""
    patterns = SKIP_FILENAMES.get(slug, [])
    return any(pat.search(filename) for pat in patterns)


def is_garbage_content(raw_html: str, content: str) -> bool:
    """Check if parsed content is garbage (login forms, 404s, SPA shells)."""
    for pat in GARBAGE_CONTENT_PATTERNS:
        if pat.search(raw_html[:2000]) or pat.search(content[:1000]):
            return True
    return False


# ---------------------------------------------------------------------------
# HTML → Markdown conversion (adapted from tax_data/02_parse_to_markdown.py)
# ---------------------------------------------------------------------------


def strip_boilerplate(tree, slug: str = ""):
    """Remove nav, header, footer, sidebar, scripts, ads from lxml tree."""
    # Universal removals
    for bad in tree.xpath(
        ".//nav | .//header | .//footer | .//aside"
        "| .//script | .//style | .//noscript"
        '| .//*[contains(@class, "breadcrumb")]'
        '| .//*[contains(@class, "sidebar")]'
        '| .//*[contains(@class, "cookie")]'
        '| .//*[contains(@class, "pagination")]'
        '| .//*[contains(@class, "advert")]'
        '| .//*[contains(@class, "ad-")]'
        '| .//*[contains(@class, "banner")]'
        '| .//*[contains(@class, "signup")]'
        '| .//*[contains(@class, "newsletter")]'
        '| .//*[contains(@class, "social-share")]'
        '| .//*[contains(@class, "share-")]'
        '| .//*[contains(@id, "cookie")]'
        '| .//*[contains(@id, "gdpr")]'
    ):
        parent = bad.getparent()
        if parent is not None:
            parent.remove(bad)

    # CAI-specific: remove Sitefinity mega-menu, top nav, footer blocks
    if slug == "chartered-accountants-ie":
        for bad in tree.xpath(
            './/*[contains(@class, "sfNavWrp")]'
            '| .//*[contains(@class, "main-nav")]'
            '| .//*[contains(@class, "util-nav")]'
            '| .//*[contains(@class, "level-2-nav")]'
            '| .//*[contains(@class, "topnav")]'
            '| .//*[contains(@class, "header__wrapper")]'
            '| .//*[contains(@class, "newsletter-wrapper")]'
            '| .//*[contains(@class, "hide-it")]'
            '| .//*[contains(@class, "footer")]'
            '| .//*[contains(@class, "utils")]'
            '| .//*[contains(@class, "nav-wrap")]'
            '| .//*[contains(@class, "top-row")]'
            '| .//*[contains(@class, "bottom-row")]'
            '| .//*[contains(@class, "footer-nav")]'
        ):
            parent = bad.getparent()
            if parent is not None:
                parent.remove(bad)

    # CPA-specific: remove login forms + Kentico chrome (header, search
    # modal, cookie bar, breadcrumbs, banners, hidden aspnet fields, scripts).
    # The page is one big <form id="form">, so without this strip the parser
    # was picking up navigation menus as "content".
    if slug == "cpa-ireland":
        for bad in tree.xpath(
            './/form[contains(@action, "login")]'
            '| .//*[contains(@class, "login")]'
            '| .//*[contains(@class, "header__wrapper")]'
            '| .//*[contains(@class, "search_modal")]'
            '| .//*[contains(@class, "aspNetHidden")]'
            '| .//*[contains(@class, "cookie_bar")]'
            '| .//*[contains(@class, "m16_breadcrumbs")]'
            '| .//*[contains(@class, "m01_banner")]'
            "| .//header"
            "| .//footer"
            "| .//input"
            "| .//script"
            "| .//noscript"
        ):
            parent = bad.getparent()
            if parent is not None:
                parent.remove(bad)


def extract_text_recursive(el, lines: list, depth: int = 0):
    """Recursively extract text from HTML element, preserving structure."""
    tag = el.tag if isinstance(el.tag, str) else ""

    # Headings
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(tag[1])
        text = (el.text_content() or "").strip()
        if text:
            lines.append(f"\n{'#' * level} {text}\n")
        return

    # Lists
    if tag == "li":
        text = (el.text or "").strip()
        children_text = []
        for child in el:
            if isinstance(child.tag, str) and child.tag not in ("ul", "ol"):
                children_text.append((child.text_content() or "").strip())
        full_text = " ".join(filter(None, [text] + children_text))
        if full_text:
            indent = "  " * max(0, depth - 1)
            lines.append(f"{indent}- {full_text}")
        for child in el:
            if isinstance(child.tag, str) and child.tag in ("ul", "ol"):
                extract_text_recursive(child, lines, depth + 1)
        return

    # Tables
    if tag == "table":
        _table_to_markdown(el, lines)
        return

    # Paragraphs
    if tag == "p":
        text = (el.text_content() or "").strip()
        if text:
            lines.append(f"\n{text}\n")
        return

    # Blockquotes
    if tag == "blockquote":
        text = (el.text_content() or "").strip()
        if text:
            for line in text.split("\n"):
                line = line.strip()
                if line:
                    lines.append(f"> {line}")
            lines.append("")
        return

    # Links with href (standalone, e.g. PDF links)
    if tag == "a":
        text = (el.text_content() or "").strip()
        href = el.get("href", "")
        if text and href and href.endswith(".pdf"):
            lines.append(f"- [{text}]({href})")
            return

    # Recurse into children
    for child in el:
        if isinstance(child.tag, str):
            extract_text_recursive(child, lines, depth)


def _table_to_markdown(table_el, lines: list):
    """Convert HTML table to markdown table."""
    rows = []
    for tr in table_el.xpath(".//tr"):
        cells = []
        for td in tr.xpath("./td | ./th"):
            text = (td.text_content() or "").strip()
            text = text.replace("|", "/").replace("\n", " ")
            cells.append(text)
        if cells:
            rows.append(cells)

    if not rows:
        return

    max_cols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < max_cols:
            r.append("")

    lines.append("")
    lines.append("| " + " | ".join(rows[0]) + " |")
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")


def html_to_markdown(tree) -> str:
    """Convert an lxml tree (after boilerplate removal) to markdown text."""
    lines: list[str] = []
    extract_text_recursive(tree, lines)
    content = "\n".join(lines)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


# ---------------------------------------------------------------------------
# Content extractors (per site type)
# ---------------------------------------------------------------------------


def find_content_element(tree, selectors: list[str]):
    """Try multiple XPath selectors, return first match."""
    for selector in selectors:
        els = tree.xpath(selector)
        if els:
            return els[0]
    return None


# Per-site content area selectors
CONTENT_SELECTORS = {
    "boards-ie-accountancy": [
        '//div[contains(@class, "MessageList")]',
        '//div[contains(@class, "DataList")]',
        '//div[@id="content"]',
        "//main",
        "//body",
    ],
    "chartered-accountants-ie": [
        '//div[contains(@class, "main-wrapper")]',
        '//div[@class="wrapper"]',
        "//main",
        "//body",
    ],
    "cpa-ireland": [
        # The site is ASP.NET Web Forms / Kentico; there is no <main> or
        # <article>, everything lives inside <form id="form">. Old selectors
        # (content-wysiwyg, m07_three_col) no longer match — the site was
        # redesigned and the content is now in Kentico-generated divs with
        # dynamic IDs like p_lt_WebPartZone*_pageplaceholder_*_m02div.
        # Using the form as root + strip_boilerplate gives us the real page.
        '//form[@id="form"]',
        '//div[contains(@class, "content-wysiwyg")]',
        '//div[contains(@class, "m07_three_col")]',
        "//main",
        "//article",
        "//body",
    ],
    "accounting-technicians-ie": [
        "//main",
        "//article",
        '//div[contains(@class, "content")]',
        "//body",
    ],
    "iafa": [
        "//main",
        "//article",
        '//div[contains(@class, "content")]',
        '//div[contains(@class, "entry")]',
        "//body",
    ],
    "accountant-forums-ireland": [
        '//div[contains(@class, "MessageList")]',
        '//div[contains(@class, "message-threadStarterPost")]',
        '//ol[contains(@class, "block-body")]',
        '//div[@id="content"]',
        "//main",
        "//article",
        "//body",
    ],
    "icaew-ireland": [
        "//main",
        "//article",
        '//div[contains(@class, "content-body")]',
        '//div[contains(@class, "article")]',
        '//div[@id="content"]',
        "//body",
    ],
}

# Per-site title selectors
TITLE_SELECTORS = {
    "boards-ie-accountancy": [
        '//h1[contains(@class, "discussionTitle")]/text()',
        "//h1/text()",
        "//title/text()",
    ],
    "default": [
        '//meta[@property="og:title"]/@content',
        "//h1/text()",
        "//title/text()",
    ],
}


def extract_title(tree, slug: str) -> str:
    """Extract page title using site-specific selectors."""
    selectors = TITLE_SELECTORS.get(slug, TITLE_SELECTORS["default"])
    for sel in selectors:
        result = tree.xpath(sel)
        if result:
            title = result[0].strip()
            if title:
                return title[:500]
    return ""


# ---------------------------------------------------------------------------
# Forum parsers
# ---------------------------------------------------------------------------


def _clean_forum_post(text: str) -> str:
    """Remove common forum noise from post body text."""
    # Tabs → single space (XenForo leaves huge tab runs from column layout)
    text = text.replace("\t", " ")
    # Remove multi-line whitespace runs (broken HTML extraction)
    text = re.sub(r"(\s*\n){3,}", "\n\n", text)
    # Remove "Registered Users, Registered Users 2 Posts: N,NNN ✭✭✭" etc.
    text = re.sub(r"Registered Users.*?Posts:\s*[\d,]+\s*✭*", "", text)
    # Remove "Join Date: ..." lines
    text = re.sub(r"Join\s*\n?\s*Date:.*", "", text)
    # XenForo profile boilerplate: "Joined\nJun 8, 2017", "Messages\n42",
    # "Reaction score\n10", "Location\nDublin" — strip the label + its value.
    text = re.sub(
        r"^\s*(Joined|Messages|Reaction score|Location|Likes Received|Trophy Points)\s*\n"
        r"[^\n]{0,80}\n",
        "",
        text,
        flags=re.MULTILINE,
    )
    # Remove post numbers "#1", "#23"
    text = re.sub(r"^\s*#\d+\s*$", "", text, flags=re.MULTILINE)
    # Remove "Help Keep Boards Alive" promos
    text = re.sub(r"Help Keep Boards Alive.*", "", text)
    # Remove boards.ie subscription promos
    text = re.sub(r"https://subscriptions\.boards\.ie[^\s]*", "", text)
    # Remove "Private Group for paid up members" blurbs
    text = re.sub(r"Private Group for paid up members.*", "", text)
    # Remove "please see this major site announcement" blurbs
    text = re.sub(r"please see this major site announcement.*", "", text, flags=re.IGNORECASE)
    # Accountantforums.com footer/sidebar promos (appear under every post)
    text = re.sub(
        r"(What Are the Key Benefits of Payroll Outsourcing\?.*?Started by Mika[^\n]*)",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"Similar threads.*", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"(You must log in|Register a new account).*", "", text, flags=re.IGNORECASE)
    # Drop isolated single-letter avatar initials on their own line
    text = re.sub(r"^\s*[A-Z]\s*$", "", text, flags=re.MULTILINE)
    # Collapse leading whitespace on every line
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[ \t]+", "", text, flags=re.MULTILINE)
    # Collapse blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_forum_boards_ie(filepath: Path, slug: str) -> dict | None:
    """Parse a boards.ie discussion thread into a single markdown document."""
    try:
        raw = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    if not raw.strip():
        return None

    try:
        tree = lxml_html.fromstring(raw)
    except Exception:
        return None

    title = extract_title(tree, slug) or filepath.stem

    # Extract individual posts
    posts = []
    for post_el in tree.xpath(
        '//div[contains(@class, "Message")]'
        '| //li[contains(@class, "Item")]'
        '| //article[contains(@class, "message")]'
    ):
        # Author
        author_els = post_el.xpath(
            './/*[contains(@class, "username")]//text()| .//*[contains(@class, "Author")]//a/text()'
        )
        author = ""
        for a in author_els:
            a = a.strip()
            if a and len(a) > 1 and a not in ("Unknown",):
                author = a
                break
        if not author:
            author = "Anonymous"

        # Date
        date_els = post_el.xpath(
            './/time/@datetime| .//*[contains(@class, "DateCreated")]//time/text()'
        )
        post_date = date_els[0].strip() if date_els else ""

        # Body — prefer the actual message content div
        body_els = post_el.xpath(
            './/*[contains(@class, "Message") and not(contains(@class, "MessageList"))]'
            '| .//*[contains(@class, "message-body")]//div[contains(@class, "bbWrapper")]'
            '| .//*[contains(@class, "message-body")]'
        )
        if body_els:
            strip_boilerplate(body_els[0])
            # Remove signature blocks
            for sig in body_els[0].xpath(
                './/*[contains(@class, "signature")]| .//*[contains(@class, "Signature")]'
            ):
                parent = sig.getparent()
                if parent is not None:
                    parent.remove(sig)
            body = (body_els[0].text_content() or "").strip()
        else:
            body = ""

        body = _clean_forum_post(body)

        # Skip empty, promo-only, or very short posts
        if body and len(body) > 50:
            posts.append({"author": author, "date": post_date, "body": body})

    if not posts:
        return None

    # Combine posts into single document
    parts = []
    for post in posts:
        header = f"### Post by {post['author']}"
        if post["date"]:
            header += f" ({post['date']})"
        parts.append(header)
        parts.append(post["body"])
        parts.append("")

    content = "\n\n".join(parts)

    if len(content) < MIN_CONTENT_LENGTH:
        return None

    return {
        "title": title,
        "content": content,
        "post_count": len(posts),
    }


def parse_forum_accountant_forums(
    filepath: Path,
    slug: str,
    ireland_keywords: list[str],
) -> dict | None:
    """Parse accountantforums.com thread, filtering for Ireland relevance."""
    try:
        raw = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    if not raw.strip():
        return None

    try:
        tree = lxml_html.fromstring(raw)
    except Exception:
        return None

    title = extract_title(tree, slug) or filepath.stem

    # Check Ireland relevance in title
    combined_text = title.lower()

    # Extract posts. XPath may return nested matches (a message inside a
    # message container also has class "message"), so dedupe by element id.
    posts = []
    seen_elements = set()
    for post_el in tree.xpath(
        '//article[contains(@class, "message")]'
        '| //div[contains(@class, "message")]'
        '| //li[contains(@class, "block-row")]'
    ):
        el_id = id(post_el)
        if el_id in seen_elements:
            continue
        seen_elements.add(el_id)
        # Also skip if this element contains a nested article.message child
        # (i.e. this is the outer wrapper, not the leaf post).
        if post_el.xpath('.//article[contains(@class, "message")]'):
            continue
        author_els = post_el.xpath(
            './/*[contains(@class, "username")]//text()| .//a[@class="username"]//text()'
        )
        author = author_els[0].strip() if author_els else "Unknown"

        date_els = post_el.xpath('.//time/@datetime| .//*[contains(@class, "u-dt")]//text()')
        post_date = date_els[0].strip() if date_els else ""

        # Prefer bbWrapper (innermost XenForo message container — just the
        # user text, no avatar/profile chrome). Fall back to message-body.
        body_els = post_el.xpath(
            './/*[contains(@class, "bbWrapper")]| .//*[contains(@class, "message-body")]'
        )
        if body_els:
            strip_boilerplate(body_els[0])
            # XenForo bbWrapper holds free-flowing text separated by <br>,
            # which extract_text_recursive (paragraph-based) silently drops.
            # text_content() + _clean_forum_post is the right tool here.
            body = (body_els[0].text_content() or "").strip()
        else:
            body = (post_el.text_content() or "").strip()

        body = _clean_forum_post(body)

        if body and len(body) > 20:
            posts.append({"author": author, "date": post_date, "body": body})
            combined_text += " " + body.lower()

    if not posts:
        return None

    # Filter: must mention Ireland-related keywords
    if not any(kw in combined_text for kw in ireland_keywords):
        return None

    parts = []
    for post in posts:
        header = f"### Post by {post['author']}"
        if post["date"]:
            header += f" ({post['date']})"
        parts.append(header)
        parts.append(post["body"])
        parts.append("")

    content = "\n\n".join(parts)

    return {
        "title": title,
        "content": content,
        "post_count": len(posts),
    }


# ---------------------------------------------------------------------------
# Generic page parser
# ---------------------------------------------------------------------------


def parse_generic_page(filepath: Path, slug: str) -> dict | None:
    """Parse a generic professional/academic page to markdown."""
    try:
        raw = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    if not raw.strip():
        return None

    # Early check for SPA shells / garbage
    if is_garbage_content(raw, ""):
        return None

    try:
        tree = lxml_html.fromstring(raw)
    except Exception:
        return None

    title = extract_title(tree, slug) or filepath.stem

    # Skip 404 pages
    if "404" in title and ("error" in title.lower() or "not found" in title.lower()):
        return None

    selectors = CONTENT_SELECTORS.get(slug, CONTENT_SELECTORS["icaew-ireland"])
    content_el = find_content_element(tree, selectors)
    if content_el is None:
        return None

    strip_boilerplate(content_el, slug=slug)
    content = html_to_markdown(content_el)

    # Post-parse garbage check
    if is_garbage_content("", content):
        return None

    if len(content) < MIN_CONTENT_LENGTH:
        return None

    word_count = len(content.split())

    return {
        "title": title,
        "content": content,
        "word_count": word_count,
    }


# ---------------------------------------------------------------------------
# Site dispatcher
# ---------------------------------------------------------------------------


def parse_file(filepath: Path, slug: str, site_cfg: dict) -> dict | None:
    """Parse a single HTML file based on site type."""
    if slug == "boards-ie-accountancy":
        return parse_forum_boards_ie(filepath, slug)
    elif slug == "accountant-forums-ireland":
        return parse_forum_accountant_forums(
            filepath,
            slug,
            site_cfg.get("ireland_keywords", []),
        )
    else:
        return parse_generic_page(filepath, slug)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_site(slug: str, site_cfg: dict) -> dict:
    """Parse all HTML files for a site. Returns stats."""
    raw_dir = get_site_raw_dir(slug)
    parsed_dir = get_site_parsed_dir(slug)
    site_name = site_cfg["name"]

    html_files = sorted(raw_dir.glob("*.html"))
    if not html_files:
        log.info("[%s] No HTML files found in %s", slug, raw_dir)
        return {"parsed": 0, "skipped": 0, "errors": 0}

    log.info("[%s] Parsing %d HTML files...", slug, len(html_files))

    manifest = []
    stats = {"parsed": 0, "skipped": 0, "errors": 0}

    for i, filepath in enumerate(html_files):
        # Skip garbage filenames (listing pages, search, cdn)
        if should_skip_file(filepath.name, slug):
            stats["skipped"] += 1
            continue

        try:
            result = parse_file(filepath, slug, site_cfg)
        except Exception as e:
            log.warning("[%s] Error parsing %s: %s", slug, filepath.name, e)
            stats["errors"] += 1
            continue

        if result is None:
            stats["skipped"] += 1
            continue

        # Write markdown
        out_name = filepath.stem + ".md"
        out_path = parsed_dir / out_name

        md_content = (
            f"# {result['title']}\n\n"
            f"> Source: {site_cfg['base_url']}\n"
            f"> Site: {site_name}\n"
            f"> Scraped: {TODAY}\n\n"
            f"{result['content']}"
        )
        out_path.write_text(md_content, encoding="utf-8")

        manifest.append(
            {
                "file": out_name,
                "title": result["title"],
                "word_count": result.get("word_count", len(result["content"].split())),
                "post_count": result.get("post_count"),
            }
        )
        stats["parsed"] += 1

        if (i + 1) % 50 == 0:
            log.info("[%s] Progress: %d/%d parsed", slug, stats["parsed"], i + 1)

    # Save manifest
    manifest_path = parsed_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    log.info(
        "[%s] Done: %d parsed, %d skipped, %d errors",
        slug,
        stats["parsed"],
        stats["skipped"],
        stats["errors"],
    )
    return stats


def show_stats():
    """Show parsed file counts per site."""
    from config import PARSED_DIR

    print("\n=== Parse Stats ===\n")
    total = 0
    for slug in SITES:
        d = PARSED_DIR / slug
        count = len(list(d.glob("*.md"))) if d.exists() else 0
        total += count
        print(f"  {slug:30s} {count:5d} markdown files")
    print(f"\n  {'TOTAL':30s} {total:5d} files\n")


def main():
    parser = argparse.ArgumentParser(description="Parse scraped HTML to markdown")
    parser.add_argument(
        "--site",
        choices=list(SITES.keys()),
        help="Parse single site (default: all)",
    )
    parser.add_argument("--stats", action="store_true", help="Show file counts")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    sites_to_parse = {args.site: SITES[args.site]} if args.site else SITES

    all_stats = {}
    for slug, cfg in sites_to_parse.items():
        log.info("=" * 60)
        log.info("Parsing: %s", cfg["name"])
        log.info("=" * 60)
        all_stats[slug] = parse_site(slug, cfg)

    # Summary
    print("\n=== Parse Summary ===\n")
    total_parsed = 0
    for slug, s in all_stats.items():
        print(
            f"  {slug:30s}  parsed={s['parsed']:4d}  "
            f"skipped={s['skipped']:4d}  errors={s['errors']:3d}"
        )
        total_parsed += s["parsed"]
    print(f"\n  Total markdown files: {total_parsed}\n")


if __name__ == "__main__":
    main()

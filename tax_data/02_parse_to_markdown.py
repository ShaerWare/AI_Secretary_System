#!/usr/bin/env python3
"""
Script 2: Parse downloaded revenue.ie HTML & PDF into clean markdown chunks.

Input:
  tax_data/raw_html/  — HTML pages from revenue.ie
  tax_data/raw_pdf/   — PDF documents

Output:
  tax_data/parsed/    — One .md file per source document, cleaned and structured
  tax_data/parsed/manifest.json — Index of all parsed documents with metadata

Usage:
  python tax_data/02_parse_to_markdown.py [--html-only] [--pdf-only] [--stats]
"""

import argparse
import json
import logging
import re
from pathlib import Path

import pdfplumber
from lxml import html as lxml_html


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
RAW_HTML_DIR = BASE_DIR / "raw_html"
RAW_PDF_DIR = BASE_DIR / "raw_pdf"
PARSED_DIR = BASE_DIR / "parsed"
MANIFEST_PATH = PARSED_DIR / "manifest.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------


def parse_html_to_markdown(filepath: Path) -> dict | None:
    """
    Extract main content from revenue.ie HTML page.
    Returns {title, url, content, section, word_count} or None if empty.
    """
    try:
        raw = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        log.warning("Cannot read %s: %s", filepath.name, e)
        return None

    if not raw.strip():
        return None

    try:
        tree = lxml_html.fromstring(raw)
    except Exception as e:
        log.warning("Cannot parse HTML %s: %s", filepath.name, e)
        return None

    # Extract title
    title_el = tree.xpath("//title/text()")
    title = title_el[0].strip() if title_el else filepath.stem

    # Clean title — remove " - Revenue" suffix
    title = re.sub(r"\s*[-–—]\s*Revenue\s*$", "", title)

    # Extract main content area (revenue.ie uses <main> or <div class="main-content">)
    content_els = tree.xpath(
        '//main//div[contains(@class, "body-content")]'
        '|//main//div[contains(@class, "article")]'
        "|//main"
        '|//div[@id="content"]'
        '|//div[contains(@class, "main-content")]'
    )

    if not content_els:
        # Fallback: try body
        content_els = tree.xpath("//body")

    if not content_els:
        return None

    content_el = content_els[0]

    # Remove nav, header, footer, sidebar, scripts, styles
    for bad in content_el.xpath(
        ".//nav | .//header | .//footer | .//aside"
        "| .//script | .//style | .//noscript"
        '| .//*[contains(@class, "breadcrumb")]'
        '| .//*[contains(@class, "sidebar")]'
        '| .//*[contains(@class, "cookie")]'
        '| .//*[contains(@class, "pagination")]'
    ):
        bad.getparent().remove(bad)

    # Convert to markdown-like text
    lines = []
    _extract_text_recursive(content_el, lines, depth=0)

    content = "\n".join(lines)

    # Clean up
    content = re.sub(r"\n{3,}", "\n\n", content)
    content = content.strip()

    if len(content) < 50:
        return None

    # Reconstruct URL from filename
    url = _filename_to_url(filepath.name, ".html")

    # Detect section from URL
    section = _url_to_section(url)

    word_count = len(content.split())

    return {
        "title": title,
        "url": url,
        "section": section,
        "content": content,
        "word_count": word_count,
        "source_file": filepath.name,
        "source_type": "html",
    }


def _extract_text_recursive(el, lines: list, depth: int):
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
            lines.append(f"- {full_text}")
        # Process nested lists
        for child in el:
            if isinstance(child.tag, str) and child.tag in ("ul", "ol"):
                _extract_text_recursive(child, lines, depth + 1)
        return

    # Tables — convert to markdown table
    if tag == "table":
        _table_to_markdown(el, lines)
        return

    # Paragraphs and divs
    if tag in ("p", "div", "section", "article"):
        text = (el.text_content() or "").strip()
        if text and tag == "p":
            lines.append(f"\n{text}\n")
            return

    # Links with href
    if tag == "a":
        text = (el.text_content() or "").strip()
        href = el.get("href", "")
        if text and href and href.endswith(".pdf"):
            lines.append(f"- [{text}]({href})")
            return

    # Recurse into children
    for child in el:
        if isinstance(child.tag, str):
            _extract_text_recursive(child, lines, depth)


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

    # Normalize column count
    max_cols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < max_cols:
            r.append("")

    # Output markdown table
    lines.append("")
    lines.append("| " + " | ".join(rows[0]) + " |")
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")


# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------


def parse_pdf_to_markdown(filepath: Path) -> dict | None:
    """
    Extract text from PDF using pdfplumber.
    Returns {title, url, content, section, word_count, pages} or None if empty.
    """
    try:
        with pdfplumber.open(filepath) as pdf:
            pages_text = []
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if text.strip():
                    pages_text.append(f"<!-- Page {i + 1} -->\n{text}")

            if not pages_text:
                return None

            content = "\n\n---\n\n".join(pages_text)
            num_pages = len(pdf.pages)

    except Exception as e:
        log.warning("Cannot parse PDF %s: %s", filepath.name, e)
        return None

    # Clean up common PDF artifacts
    content = re.sub(r"(\n\s*){3,}", "\n\n", content)

    # Try to extract title from first page
    first_lines = content.split("\n")[:5]
    title = ""
    for line in first_lines:
        line = line.strip().strip("#").strip()
        if line and not line.startswith("<!--") and len(line) > 5:
            title = line[:120]
            break
    if not title:
        title = filepath.stem

    url = _filename_to_url(filepath.name, ".pdf")
    section = _url_to_section(url)
    word_count = len(content.split())

    return {
        "title": title,
        "url": url,
        "section": section,
        "content": content,
        "word_count": word_count,
        "pages": num_pages,
        "source_file": filepath.name,
        "source_type": "pdf",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _filename_to_url(filename: str, ext: str) -> str:
    """Reverse url_to_filename: restore approximate URL."""
    name = filename
    if ext == ".html":
        name = re.sub(r"\.html$", ".aspx", name)
    elif ext == ".pdf":
        name = re.sub(r"\.pdf$", ".pdf", name)
    path = name.replace("__", "/")
    return f"https://www.revenue.ie/{path}"


def _url_to_section(url: str) -> str:
    """Classify URL into a section for the manifest."""
    patterns = {
        "self-assessment": r"/self-assessment-and-self-employment/",
        "income-tax": r"/jobs-and-pensions/calculating-your-income-tax/",
        "usc": r"/jobs-and-pensions/usc/",
        "tax-credits": r"/personal-tax-credits-reliefs-and-exemptions/",
        "starting-business": r"/starting-a-business/",
        "vat": r"/vat/",
        "ros-help": r"/online-services/",
        "tdm-expenses": r"/tdm.*?/part-07/",
        "tdm-capital-allowances": r"/tdm.*?/part-09/",
        "tdm-self-assessment": r"/tdm.*?/part-41/",
        "tdm-credits": r"/tdm.*?/part-15/",
        "tdm-basis": r"/tdm.*?/part-04/",
        "tdm-allowances": r"/tdm.*?/part-23/",
        "tdm-capital-gains": r"/tdm.*?/part-11/",
        "tdm-vat": r"/tdm.*?/value-added-tax/",
        "statistics": r"/statistics/",
        "form11": r"/form[-_]?11/|form11",
    }

    for section, pattern in patterns.items():
        if re.search(pattern, url, re.IGNORECASE):
            return section

    return "other"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Parse revenue.ie HTML/PDF to markdown")
    parser.add_argument("--html-only", action="store_true")
    parser.add_argument("--pdf-only", action="store_true")
    parser.add_argument("--stats", action="store_true", help="Show stats only, don't parse")
    args = parser.parse_args()

    PARSED_DIR.mkdir(parents=True, exist_ok=True)

    manifest = []

    # Parse HTML
    if not args.pdf_only:
        html_files = sorted(RAW_HTML_DIR.glob("*.html")) if RAW_HTML_DIR.exists() else []
        log.info("Parsing %d HTML files...", len(html_files))

        for i, f in enumerate(html_files):
            result = parse_html_to_markdown(f)
            if result:
                out_name = f.stem + ".md"
                out_path = PARSED_DIR / out_name
                out_path.write_text(
                    f"# {result['title']}\n\n"
                    f"> Source: {result['url']}\n"
                    f"> Section: {result['section']}\n\n"
                    f"{result['content']}",
                    encoding="utf-8",
                )
                manifest.append(
                    {
                        "file": out_name,
                        "title": result["title"],
                        "url": result["url"],
                        "section": result["section"],
                        "type": "html",
                        "word_count": result["word_count"],
                    }
                )

            if (i + 1) % 100 == 0:
                log.info("  Parsed %d/%d HTML files", i + 1, len(html_files))

        log.info("HTML: %d documents parsed", len([m for m in manifest if m["type"] == "html"]))

    # Parse PDFs
    if not args.html_only:
        pdf_files = sorted(RAW_PDF_DIR.glob("*.pdf")) if RAW_PDF_DIR.exists() else []
        log.info("Parsing %d PDF files...", len(pdf_files))

        for i, f in enumerate(pdf_files):
            result = parse_pdf_to_markdown(f)
            if result:
                out_name = f.stem + ".md"
                out_path = PARSED_DIR / out_name
                out_path.write_text(
                    f"# {result['title']}\n\n"
                    f"> Source: {result['url']}\n"
                    f"> Section: {result['section']}\n"
                    f"> Pages: {result.get('pages', '?')}\n\n"
                    f"{result['content']}",
                    encoding="utf-8",
                )
                manifest.append(
                    {
                        "file": out_name,
                        "title": result["title"],
                        "url": result["url"],
                        "section": result["section"],
                        "type": "pdf",
                        "word_count": result["word_count"],
                        "pages": result.get("pages"),
                    }
                )

            if (i + 1) % 10 == 0:
                log.info("  Parsed %d/%d PDF files", i + 1, len(pdf_files))

        log.info("PDF: %d documents parsed", len([m for m in manifest if m["type"] == "pdf"]))

    # Save manifest
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Stats
    total_words = sum(m["word_count"] for m in manifest)
    sections = {}
    for m in manifest:
        s = m["section"]
        sections[s] = sections.get(s, 0) + 1

    log.info("=== DONE ===")
    log.info("Total documents: %d", len(manifest))
    log.info("Total words: %d (~%.1f MB text)", total_words, total_words * 5 / 1024 / 1024)
    log.info("Sections:")
    for s, c in sorted(sections.items(), key=lambda x: -x[1]):
        log.info("  %-25s %d docs", s, c)


if __name__ == "__main__":
    main()

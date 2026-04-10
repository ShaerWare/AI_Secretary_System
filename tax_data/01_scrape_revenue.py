#!/usr/bin/env python3
"""
Script 1: Download Irish Revenue self-employment tax data.

Steps:
  1. Download & parse sitemap.xml (14,662 URLs)
  2. Filter URLs relevant to self-employed tax filing
  3. Download HTML pages (self-assessment, tax credits, VAT, ROS help)
  4. Download PDF documents (Form 11, TDM manuals, guides)

Output:
  tax_data/raw_html/  — HTML pages
  tax_data/raw_pdf/   — PDF documents
  tax_data/sitemap_urls.json — parsed sitemap with metadata

Usage:
  python tax_data/01_scrape_revenue.py [--sitemap-only] [--pdf-only] [--html-only]

Revenue.ie: no robots.txt, CC-BY-4.0 license.
"""

import argparse
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import requests


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
RAW_HTML_DIR = BASE_DIR / "raw_html"
RAW_PDF_DIR = BASE_DIR / "raw_pdf"
SITEMAP_CACHE = BASE_DIR / "sitemap_urls.json"

SITEMAP_URL = "https://www.revenue.ie/sitemap.xml"

# Delay between requests (seconds) — be polite
REQUEST_DELAY = 0.3
TIMEOUT = 30

# URL filters for self-employed relevant content
RELEVANT_URL_PATTERNS = [
    # Core self-employment & self-assessment
    r"/self-assessment-and-self-employment/",
    # Tax credits and reliefs (personal)
    r"/personal-tax-credits-reliefs-and-exemptions/",
    # Income tax calculation
    r"/jobs-and-pensions/calculating-your-income-tax/",
    r"/jobs-and-pensions/usc/",
    # Starting a business
    r"/starting-a-business/",
    # VAT (thresholds, registration, VAT3, accounting)
    r"/vat/vat-registration/",
    r"/vat/vat-rates/what-are-vat-rates/",
    r"/vat/vat-rates/historical-vat-rates/",
    r"/vat/accounting-for-vat/",
    # ROS help
    r"/online-services/services/ros/",
    r"/online-services/support/ros-help/",
    # TDM — Tax and Duty Manuals (key parts for self-employed)
    r"/tax-professionals/tdm/income-tax-capital-gains-tax-corporation-tax/part-04/",  # Basis of assessment
    r"/tax-professionals/tdm/income-tax-capital-gains-tax-corporation-tax/part-07/",  # Expenses
    r"/tax-professionals/tdm/income-tax-capital-gains-tax-corporation-tax/part-09/",  # Capital allowances
    r"/tax-professionals/tdm/income-tax-capital-gains-tax-corporation-tax/part-11/",  # Capital gains
    r"/tax-professionals/tdm/income-tax-capital-gains-tax-corporation-tax/part-15/",  # Tax credits
    r"/tax-professionals/tdm/income-tax-capital-gains-tax-corporation-tax/part-23/",  # Allowances for expenses
    r"/tax-professionals/tdm/income-tax-capital-gains-tax-corporation-tax/part-41/",  # Self-assessment
    r"/tax-professionals/tdm/value-added-tax/",  # VAT manual
    # Statistics (rates, reckoner)
    r"/corporate/information-about-revenue/statistics/personal-taxes/",
    r"/corporate/documents/statistics/ready-reckoner",
]

# Direct PDF URLs to always include (Form 11, guides)
DIRECT_PDFS = [
    # Form 11 (current + historical)
    "https://www.revenue.ie/en/self-assessment-and-self-employment/documents/form11.pdf",
    "https://www.revenue.ie/en/self-assessment-and-self-employment/documents/form11-2024.pdf",
    "https://www.revenue.ie/en/self-assessment-and-self-employment/documents/form11-2023.pdf",
    "https://www.revenue.ie/en/self-assessment-and-self-employment/documents/form11-2022.pdf",
    "https://www.revenue.ie/en/self-assessment-and-self-employment/documents/form11-2021.pdf",
    # Helpsheets
    "https://www.revenue.ie/en/self-assessment-and-self-employment/documents/form11-helpsheet.pdf",
    "https://www.revenue.ie/en/self-assessment-and-self-employment/documents/form11-helpsheet-2024.pdf",
    "https://www.revenue.ie/en/self-assessment-and-self-employment/documents/form11-helpsheet-2023.pdf",
    "https://www.revenue.ie/en/self-assessment-and-self-employment/documents/form11-helpsheet-2022.pdf",
    "https://www.revenue.ie/en/self-assessment-and-self-employment/documents/form11-helpsheet-2021.pdf",
    # Form 11S (short)
    "https://www.revenue.ie/en/self-assessment-and-self-employment/documents/form-11s.pdf",
    "https://www.revenue.ie/en/self-assessment-and-self-employment/documents/form-11s-2024.pdf",
    "https://www.revenue.ie/en/self-assessment-and-self-employment/documents/form-11s-2023.pdf",
    # Guides
    "https://www.revenue.ie/en/self-assessment-and-self-employment/documents/guide-pay-file.pdf",
    # Ready Reckoner
    "https://www.revenue.ie/en/corporate/documents/statistics/ready-reckoner.pdf",
]

# Skip these URL patterns (noise: individual VAT rate lookups, etc.)
SKIP_PATTERNS = [
    r"/vat/vat-rates/search-vat-rates/",  # 2,119 individual product rate pages
    r"/vat/vat-rates/changes-to-vat-rates/",  # Historical rate changes by date
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sitemap parsing
# ---------------------------------------------------------------------------


def download_sitemap(client: requests.Session) -> list[dict]:
    """Download and parse sitemap.xml, return list of {url, lastmod}."""
    if SITEMAP_CACHE.exists():
        log.info("Loading cached sitemap from %s", SITEMAP_CACHE)
        with open(SITEMAP_CACHE) as f:
            return json.load(f)

    # Check for locally downloaded sitemap.xml first
    local_sitemap = BASE_DIR / "sitemap.xml"
    if local_sitemap.exists():
        log.info("Loading local sitemap.xml (%d KB)", local_sitemap.stat().st_size // 1024)
        xml_content = local_sitemap.read_bytes()
    else:
        log.info("Downloading sitemap from %s ...", SITEMAP_URL)
        resp = client.get(SITEMAP_URL, timeout=120)
        resp.raise_for_status()
        # Save locally for reuse
        local_sitemap.write_bytes(resp.content)
        log.info("Sitemap downloaded: %.1f MB", len(resp.content) / 1_048_576)
        xml_content = resp.content

    # Parse XML — namespace handling
    root = ET.fromstring(xml_content)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    urls = []
    for url_elem in root.findall("sm:url", ns):
        loc = url_elem.findtext("sm:loc", default="", namespaces=ns)
        lastmod = url_elem.findtext("sm:lastmod", default="", namespaces=ns)
        if loc:
            urls.append({"url": loc, "lastmod": lastmod})

    log.info("Parsed %d URLs from sitemap", len(urls))

    # Cache parsed result
    with open(SITEMAP_CACHE, "w") as f:
        json.dump(urls, f, indent=2)

    return urls


def filter_relevant_urls(all_urls: list[dict]) -> tuple[list[str], list[str]]:
    """Split relevant URLs into HTML pages and PDF links."""
    html_urls = []
    pdf_urls = set(DIRECT_PDFS)  # Start with known PDFs

    compiled_patterns = [re.compile(p) for p in RELEVANT_URL_PATTERNS]
    compiled_skip = [re.compile(p) for p in SKIP_PATTERNS]

    for entry in all_urls:
        url = entry["url"]

        # Skip noise
        if any(sp.search(url) for sp in compiled_skip):
            continue

        # Check relevance
        if any(rp.search(url) for rp in compiled_patterns):
            if url.lower().endswith(".pdf"):
                pdf_urls.add(url)
            else:
                html_urls.append(url)

    return sorted(set(html_urls)), sorted(pdf_urls)


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------


def url_to_filename(url: str, ext: str = "") -> str:
    """Convert URL to safe filename preserving structure."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    name = path.replace("/", "__")
    if ext:
        name = re.sub(r"\.(aspx|html|htm)$", "", name, flags=re.IGNORECASE)
        name = re.sub(r"\.pdf$", "", name, flags=re.IGNORECASE)
        name = f"{name}.{ext}"
    return name


def download_html_pages(client: requests.Session, urls: list[str]) -> dict:
    """Download HTML pages, save to raw_html/. Returns stats."""
    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)
    stats = {"downloaded": 0, "skipped": 0, "errors": 0}

    for i, url in enumerate(urls):
        filename = url_to_filename(url, "html")
        filepath = RAW_HTML_DIR / filename

        if filepath.exists() and filepath.stat().st_size > 0:
            stats["skipped"] += 1
            continue

        try:
            log.info("[%d/%d] HTML: %s", i + 1, len(urls), url.split("revenue.ie")[-1])
            resp = client.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            filepath.write_text(resp.text, encoding="utf-8")
            stats["downloaded"] += 1
            time.sleep(REQUEST_DELAY)
        except Exception as e:
            log.warning("Failed %s: %s", url, e)
            stats["errors"] += 1

    return stats


def download_pdfs(client: requests.Session, urls: list[str]) -> dict:
    """Download PDFs, save to raw_pdf/. Returns stats."""
    RAW_PDF_DIR.mkdir(parents=True, exist_ok=True)
    stats = {"downloaded": 0, "skipped": 0, "errors": 0}

    for i, url in enumerate(urls):
        filename = url_to_filename(url, "pdf")
        filepath = RAW_PDF_DIR / filename

        if filepath.exists() and filepath.stat().st_size > 0:
            stats["skipped"] += 1
            continue

        try:
            log.info("[%d/%d] PDF: %s", i + 1, len(urls), url.split("revenue.ie")[-1])
            resp = client.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
            stats["downloaded"] += 1
            time.sleep(REQUEST_DELAY)
        except Exception as e:
            log.warning("Failed %s: %s", url, e)
            stats["errors"] += 1

    return stats


# ---------------------------------------------------------------------------
# PDF discovery from HTML pages (find linked PDFs we missed)
# ---------------------------------------------------------------------------


def discover_pdfs_in_html(html_dir: Path) -> list[str]:
    """Scan downloaded HTML for PDF links on revenue.ie."""
    pdf_urls = set()
    pdf_pattern = re.compile(
        r'href=["\']' r'((?:https?://(?:www\.)?revenue\.ie)?/en/[^"\']+\.pdf)' r'["\']',
        re.IGNORECASE,
    )

    for html_file in html_dir.glob("*.html"):
        content = html_file.read_text(encoding="utf-8", errors="ignore")
        for match in pdf_pattern.finditer(content):
            href = match.group(1)
            if href.startswith("/"):
                href = f"https://www.revenue.ie{href}"
            pdf_urls.add(href)

    return sorted(pdf_urls)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Scrape revenue.ie for self-employed tax data")
    parser.add_argument("--sitemap-only", action="store_true", help="Only download & parse sitemap")
    parser.add_argument("--html-only", action="store_true", help="Only download HTML pages")
    parser.add_argument("--pdf-only", action="store_true", help="Only download PDFs")
    parser.add_argument(
        "--discover-pdfs", action="store_true", help="Discover PDFs linked from HTML"
    )
    args = parser.parse_args()

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; TaxResearchBot/1.0)",
        "Accept-Language": "en-IE,en;q=0.9",
    }

    session = requests.Session()
    session.headers.update(headers)

    with session as client:
        # Step 1: Sitemap
        all_urls = download_sitemap(client)
        html_urls, pdf_urls = filter_relevant_urls(all_urls)

        log.info(
            "Filtered: %d HTML pages, %d PDFs (from %d total sitemap URLs)",
            len(html_urls),
            len(pdf_urls),
            len(all_urls),
        )

        if args.sitemap_only:
            print(f"\nTotal sitemap URLs: {len(all_urls)}")
            print(f"Relevant HTML pages: {len(html_urls)}")
            print(f"Relevant PDFs: {len(pdf_urls)}")
            print("\nSample HTML URLs:")
            for u in html_urls[:20]:
                print(f"  {u}")
            print("\nSample PDF URLs:")
            for u in pdf_urls[:20]:
                print(f"  {u}")
            return

        # Step 2: Download HTML
        if not args.pdf_only:
            log.info("=== Downloading %d HTML pages ===", len(html_urls))
            html_stats = download_html_pages(client, html_urls)
            log.info(
                "HTML done: %d downloaded, %d skipped, %d errors",
                html_stats["downloaded"],
                html_stats["skipped"],
                html_stats["errors"],
            )

        # Step 3: Discover additional PDFs from downloaded HTML
        if not args.pdf_only and not args.html_only:
            log.info("=== Discovering PDFs linked in HTML pages ===")
            discovered = discover_pdfs_in_html(RAW_HTML_DIR)
            new_pdfs = [u for u in discovered if u not in pdf_urls]
            if new_pdfs:
                log.info("Found %d additional PDFs linked from HTML", len(new_pdfs))
                pdf_urls = sorted(set(pdf_urls) | set(new_pdfs))

        # Step 4: Download PDFs
        if not args.html_only:
            log.info("=== Downloading %d PDFs ===", len(pdf_urls))
            pdf_stats = download_pdfs(client, pdf_urls)
            log.info(
                "PDF done: %d downloaded, %d skipped, %d errors",
                pdf_stats["downloaded"],
                pdf_stats["skipped"],
                pdf_stats["errors"],
            )

        # Step 5: Discover PDFs mode (for second pass)
        if args.discover_pdfs:
            discovered = discover_pdfs_in_html(RAW_HTML_DIR)
            print(f"\nDiscovered {len(discovered)} PDF URLs in HTML pages:")
            for u in discovered:
                print(f"  {u}")

    # Summary
    html_count = len(list(RAW_HTML_DIR.glob("*.html"))) if RAW_HTML_DIR.exists() else 0
    pdf_count = len(list(RAW_PDF_DIR.glob("*.pdf"))) if RAW_PDF_DIR.exists() else 0
    log.info("=== DONE === %d HTML files, %d PDFs on disk", html_count, pdf_count)


if __name__ == "__main__":
    main()

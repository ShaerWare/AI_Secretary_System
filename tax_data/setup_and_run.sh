#!/bin/bash
# Setup and run tax data scraping on server
# Usage: bash tax_data/setup_and_run.sh

set -e
cd "$(dirname "$0")"

echo "=== Irish Tax Data Scraper ==="
echo "Directory: $(pwd)"

# Create venv if not exists
if [ ! -d ".venv" ]; then
    echo "Creating virtualenv..."
    python3 -m venv .venv
fi

source .venv/bin/activate
echo "Python: $(python3 --version)"

# Install deps
pip install -q -r requirements.txt

# Create output dirs
mkdir -p raw_html raw_pdf parsed datasets

# Step 1: Scrape revenue.ie
echo ""
echo "=== Step 1: Scraping revenue.ie ==="
python3 01_scrape_revenue.py

# Step 2: Parse to markdown
echo ""
echo "=== Step 2: Parsing to markdown ==="
python3 02_parse_to_markdown.py

echo ""
echo "=== Done ==="
echo "HTML files: $(ls raw_html/*.html 2>/dev/null | wc -l)"
echo "PDF files:  $(ls raw_pdf/*.pdf 2>/dev/null | wc -l)"
echo "Parsed:     $(ls parsed/*.md 2>/dev/null | wc -l)"

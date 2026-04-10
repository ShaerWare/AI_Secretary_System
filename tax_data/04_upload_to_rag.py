#!/usr/bin/env python3
"""
Script 4: Upload parsed tax documents directly to Wiki RAG knowledge base.

Works directly with the database and filesystem — no HTTP API, no auth needed.
Must be run from the project root (where orchestrator.py is).

Steps:
  1. Creates "Irish Tax" knowledge collection in DB
  2. Copies markdown files to the collection's base_dir
  3. Creates document records in DB
  4. Prints instructions to reload the index via admin panel

Usage:
  python tax_data/04_upload_to_rag.py
  python tax_data/04_upload_to_rag.py --max-files 10     # test run
  python tax_data/04_upload_to_rag.py --stats             # show stats
  python tax_data/04_upload_to_rag.py --dry-run           # show what would be uploaded
"""

import argparse
import asyncio
import logging
import re
import shutil
import sys
from pathlib import Path


# Ensure project root is in path (for imports)
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
PARSED_DIR = BASE_DIR / "parsed"
MANIFEST_PATH = PARSED_DIR / "manifest.json"

COLLECTION_NAME = "Irish Tax (Revenue.ie)"
COLLECTION_SLUG = "irish-tax"
COLLECTION_BASE_DIR = "wiki-pages/irish-tax"
COLLECTION_DESCRIPTION = (
    "Irish Revenue self-employment tax documentation from revenue.ie. "
    "Covers self-assessment, income tax, USC, PRSI, VAT, tax credits, "
    "Form 11, TDM manuals, and ROS help. CC-BY-4.0."
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB operations
# ---------------------------------------------------------------------------


async def ensure_collection() -> int:
    """Create or get the Irish Tax collection. Returns collection_id."""
    from modules.knowledge.service import knowledge_collection_service

    # Check if exists
    existing = await knowledge_collection_service.get_by_slug(COLLECTION_SLUG)
    if existing:
        log.info("Collection '%s' exists (id=%d)", COLLECTION_NAME, existing["id"])
        return existing["id"]

    # Create
    col = await knowledge_collection_service.create(
        name=COLLECTION_NAME,
        slug=COLLECTION_SLUG,
        description=COLLECTION_DESCRIPTION,
        enabled=True,
        base_dir=COLLECTION_BASE_DIR,
    )
    log.info(
        "Created collection '%s' (id=%d, base_dir=%s)",
        COLLECTION_NAME,
        col["id"],
        COLLECTION_BASE_DIR,
    )
    return col["id"]


async def get_existing_filenames(collection_id: int) -> set[str]:
    """Get set of filenames already in the collection."""
    from modules.knowledge.service import knowledge_doc_service

    docs = await knowledge_doc_service.get_by_collection(collection_id)
    return {d["filename"] for d in docs}


async def create_document_record(
    filename: str,
    title: str,
    file_size: int,
    section_count: int,
    collection_id: int,
) -> dict:
    """Create a knowledge document record in DB."""
    from modules.knowledge.service import knowledge_doc_service

    return await knowledge_doc_service.create(
        filename=filename,
        title=title,
        source_type="import",
        file_size_bytes=file_size,
        section_count=section_count,
        collection_id=collection_id,
    )


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------


def extract_title(content: str, filename: str) -> str:
    """Extract title from markdown content."""
    first_header = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if first_header:
        return first_header.group(1).strip()[:500]
    return Path(filename).stem.replace("-", " ").replace("_", " ")[:500]


def count_sections(content: str) -> int:
    """Count ## and ### headers."""
    return len(re.findall(r"^#{2,3}\s+.+$", content, re.MULTILINE))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run(args):
    # Get files
    if not PARSED_DIR.exists():
        log.error("Parsed directory not found: %s. Run 02_parse_to_markdown.py first.", PARSED_DIR)
        return

    md_files = sorted(f for f in PARSED_DIR.glob("*.md") if not f.name.startswith("_"))
    log.info("Found %d markdown files in %s", len(md_files), PARSED_DIR)

    if not md_files:
        log.error("No markdown files found")
        return

    if args.max_files:
        md_files = md_files[: args.max_files]

    # Ensure collection
    collection_id = await ensure_collection()

    # Target directory
    target_dir = PROJECT_ROOT / COLLECTION_BASE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    log.info("Target directory: %s", target_dir)

    if args.stats:
        existing = await get_existing_filenames(collection_id)
        print(f"Collection: {COLLECTION_NAME} (id={collection_id})")
        print(f"Documents in DB: {len(existing)}")
        print(f"Files in target dir: {len(list(target_dir.glob('*.md')))}")
        print(f"Files in parsed dir: {len(md_files)}")
        return

    # Get already uploaded
    existing = await get_existing_filenames(collection_id)
    log.info("Already in DB: %d documents", len(existing))

    # Upload
    stats = {"uploaded": 0, "skipped": 0, "errors": 0}

    for i, filepath in enumerate(md_files):
        if filepath.name in existing:
            stats["skipped"] += 1
            continue

        if args.dry_run:
            log.info("  [DRY] %s", filepath.name)
            stats["uploaded"] += 1
            continue

        try:
            content = filepath.read_text(encoding="utf-8")
            title = extract_title(content, filepath.name)
            sections = count_sections(content)
            file_size = filepath.stat().st_size

            # Copy file to collection directory
            target = target_dir / filepath.name
            shutil.copy2(filepath, target)

            # Create DB record
            await create_document_record(
                filename=filepath.name,
                title=title,
                file_size=file_size,
                section_count=sections,
                collection_id=collection_id,
            )
            stats["uploaded"] += 1

        except Exception as e:
            log.warning("Error uploading %s: %s", filepath.name, e)
            stats["errors"] += 1

        if (i + 1) % 100 == 0:
            log.info(
                "Progress: %d/%d (uploaded=%d, skipped=%d)",
                i + 1,
                len(md_files),
                stats["uploaded"],
                stats["skipped"],
            )

    log.info("=== Upload complete ===")
    log.info("Uploaded: %d", stats["uploaded"])
    log.info("Skipped (already in DB): %d", stats["skipped"])
    log.info("Errors: %d", stats["errors"])

    if stats["uploaded"] > 0 and not args.dry_run:
        log.info("")
        log.info("Files copied to: %s", target_dir)
        log.info("DB records created for %d documents", stats["uploaded"])
        log.info("")
        log.info("=== Next: reload the Wiki RAG index ===")
        log.info("Option 1: Restart orchestrator (auto-loads on startup)")
        log.info("Option 2: Admin panel → Знания → коллекция → Переиндексировать")
        log.info(
            "Option 3: curl -X POST http://localhost:8002/admin/wiki-rag/collections/%d/reload",
            collection_id,
        )


def main():
    parser = argparse.ArgumentParser(description="Upload parsed tax docs to Wiki RAG")
    parser.add_argument("--max-files", type=int, default=0, help="Limit files (0=all)")
    parser.add_argument("--stats", action="store_true", help="Show stats")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be uploaded")
    args = parser.parse_args()

    asyncio.run(run(args))


if __name__ == "__main__":
    main()

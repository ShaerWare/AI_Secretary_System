#!/usr/bin/env python3
"""
Step 3: Upload parsed markdown to Wiki RAG as 7 separate knowledge collections.

Works directly with the database and filesystem — no HTTP API, no auth needed.
Must be run from the project root (where orchestrator.py is).

Usage:
  python scripts/scrape_digitax/upload.py --all                    # all sites
  python scripts/scrape_digitax/upload.py --site icaew-ireland     # single site
  python scripts/scrape_digitax/upload.py --site icaew-ireland --dry-run
  python scripts/scrape_digitax/upload.py --stats                  # show counts
"""

import argparse
import asyncio
import logging
import re
import shutil
import sys
from pathlib import Path


# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.scrape_digitax.config import SITES, get_site_parsed_dir  # noqa: E402


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB operations
# ---------------------------------------------------------------------------


async def ensure_collection(slug: str, name: str, description: str, base_dir: str) -> int:
    """Create or get a knowledge collection. Returns collection_id."""
    from modules.knowledge.service import knowledge_collection_service

    existing = await knowledge_collection_service.get_by_slug(slug)
    if existing:
        log.info("Collection '%s' exists (id=%d)", name, existing["id"])
        return existing["id"]

    col = await knowledge_collection_service.create(
        name=name,
        slug=slug,
        description=description,
        enabled=True,
        base_dir=base_dir,
    )
    log.info("Created collection '%s' (id=%d, base_dir=%s)", name, col["id"], base_dir)
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
# Helpers
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
# Upload logic
# ---------------------------------------------------------------------------


async def upload_site(slug: str, cfg: dict, dry_run: bool = False) -> dict:
    """Upload all parsed markdown for one site to its collection."""
    parsed_dir = get_site_parsed_dir(slug)
    base_dir = f"wiki-pages/{slug}"
    collection_name = cfg["name"]
    description = cfg.get("description", "")

    md_files = sorted(f for f in parsed_dir.glob("*.md") if not f.name.startswith("_"))
    # Skip manifest.json (it's .json, not .md, but be safe)
    md_files = [f for f in md_files if f.name != "manifest.json"]

    if not md_files:
        log.info("[%s] No markdown files found in %s", slug, parsed_dir)
        return {"uploaded": 0, "skipped": 0, "errors": 0}

    log.info("[%s] Found %d markdown files", slug, len(md_files))

    # Ensure collection
    collection_id = await ensure_collection(slug, collection_name, description, base_dir)

    # Target directory
    target_dir = PROJECT_ROOT / base_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    # Get already uploaded
    existing = await get_existing_filenames(collection_id)
    log.info("[%s] Already in DB: %d documents", slug, len(existing))

    stats = {"uploaded": 0, "skipped": 0, "errors": 0}

    for i, filepath in enumerate(md_files):
        if filepath.name in existing:
            stats["skipped"] += 1
            continue

        if dry_run:
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
            log.warning("[%s] Error uploading %s: %s", slug, filepath.name, e)
            stats["errors"] += 1

        if (i + 1) % 100 == 0:
            log.info(
                "[%s] Progress: %d/%d (uploaded=%d, skipped=%d)",
                slug,
                i + 1,
                len(md_files),
                stats["uploaded"],
                stats["skipped"],
            )

    log.info(
        "[%s] Done: uploaded=%d, skipped=%d, errors=%d",
        slug,
        stats["uploaded"],
        stats["skipped"],
        stats["errors"],
    )
    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run(args):
    if args.stats:
        print("\n=== Upload Stats ===\n")
        for slug, cfg in SITES.items():
            parsed_dir = get_site_parsed_dir(slug)
            parsed_count = len(list(parsed_dir.glob("*.md"))) if parsed_dir.exists() else 0
            target_dir = PROJECT_ROOT / f"wiki-pages/{slug}"
            uploaded_count = len(list(target_dir.glob("*.md"))) if target_dir.exists() else 0
            print(f"  {slug:30s}  parsed={parsed_count:4d}  uploaded={uploaded_count:4d}")
        return

    if not args.site and not args.all:
        print("Error: specify --site <slug> or --all")
        print("Available sites:", ", ".join(SITES.keys()))
        return

    sites_to_upload = {args.site: SITES[args.site]} if args.site else SITES

    all_stats = {}

    for slug, cfg in sites_to_upload.items():
        log.info("=" * 60)
        log.info("Uploading: %s", cfg["name"])
        log.info("=" * 60)
        site_stats = await upload_site(slug, cfg, dry_run=args.dry_run)
        all_stats[slug] = site_stats

    # Summary
    print("\n=== Upload Summary ===\n")
    total_uploaded = 0
    for slug, s in all_stats.items():
        print(
            f"  {slug:30s}  uploaded={s['uploaded']:4d}  "
            f"skipped={s['skipped']:4d}  errors={s['errors']:3d}"
        )
        total_uploaded += s["uploaded"]
    print(f"\n  Total new uploads: {total_uploaded}\n")

    if total_uploaded > 0 and not args.dry_run:
        print("=== Next: reload the Wiki RAG indexes ===")
        print("Option 1: Restart orchestrator (auto-loads on startup)")
        print("Option 2: Admin panel -> Knowledge -> collection -> Reindex")
        print("Option 3: curl -X POST http://localhost:8002/admin/wiki-rag/reload")


def main():
    parser = argparse.ArgumentParser(description="Upload parsed docs to Wiki RAG collections")
    parser.add_argument(
        "--site",
        choices=list(SITES.keys()),
        help="Upload single site",
    )
    parser.add_argument("--all", action="store_true", help="Upload all sites")
    parser.add_argument("--stats", action="store_true", help="Show counts")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be uploaded")
    args = parser.parse_args()

    asyncio.run(run(args))


if __name__ == "__main__":
    main()

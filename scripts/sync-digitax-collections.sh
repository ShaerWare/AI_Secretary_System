#!/usr/bin/env bash
# Sync DigiTax RAG collections from the AI-Agents submodule into wiki-pages/.
# The RAG upload pipeline reads from wiki-pages/<slug>/ so collections need
# to live there at runtime. The source of truth is the AI-Agents repo.
#
# Usage:
#   bash scripts/sync-digitax-collections.sh           # sync all 7 collections
#   bash scripts/sync-digitax-collections.sh --check   # show what would change

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/external/ai-agents/digitax/collections"
DST="$ROOT/wiki-pages"

SLUGS=(
  irish-tax
  boards-ie-accountancy
  chartered-accountants-ie
  cpa-ireland
  accounting-technicians-ie
  accountant-forums-ireland
  icaew-ireland
)

if [ ! -d "$SRC" ]; then
  echo "✗ Submodule not initialised: $SRC"
  echo "  Run: git submodule update --init --recursive"
  exit 1
fi

mode="copy"
if [ "${1:-}" = "--check" ]; then
  mode="check"
fi

for slug in "${SLUGS[@]}"; do
  src_dir="$SRC/$slug"
  dst_dir="$DST/$slug"

  if [ ! -d "$src_dir" ]; then
    echo "! $slug: missing in submodule, skipping"
    continue
  fi

  src_count=$(find "$src_dir" -type f | wc -l)

  if [ "$mode" = "check" ]; then
    dst_count=0
    [ -d "$dst_dir" ] && dst_count=$(find "$dst_dir" -type f | wc -l)
    echo "= $slug: src=$src_count dst=$dst_count"
  else
    rsync -a --delete "$src_dir/" "$dst_dir/"
    echo "+ $slug: $src_count files → $dst_dir"
  fi
done

if [ "$mode" != "check" ]; then
  echo
  echo "Done. Reindex with:"
  echo "  curl -X POST http://localhost:8002/admin/wiki-rag/reload"
fi

#!/bin/bash
# Bootstrap script for the "dev-architecture" RAG collection.
#
# Provides the assistant with project-specific architecture context
# (CLAUDE.md + Code-Patterns.md) so dev chat sessions get accurate
# answers about file paths, modular layout, RBAC, EventBus, etc.
#
# Idempotent: safe to re-run after CLAUDE.md or Code-Patterns.md change.
# After running, restart orchestrator to reindex:
#   systemctl restart ai-secretary
#
# Run from repo root: bash scripts/setup_dev_architecture_rag.sh

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(pwd)}"
DB="${REPO_ROOT}/data/secretary.db"
SLUG=dev-architecture
DIR="${REPO_ROOT}/wiki-pages/${SLUG}"

if [ ! -f "$DB" ]; then
  echo "ERROR: DB not found at $DB"
  echo "Set REPO_ROOT or run from /opt/ai-secretary"
  exit 1
fi

mkdir -p "$DIR"

# 1. Copy current CLAUDE.md into the collection dir (refresh on every run).
cp "${REPO_ROOT}/CLAUDE.md" "${DIR}/CLAUDE.md"
echo "Refreshed CLAUDE.md copy in ${DIR}"

# Code-Patterns.md is committed to git directly in $DIR — no copy needed.
if [ ! -f "${DIR}/Code-Patterns.md" ]; then
  echo "WARNING: ${DIR}/Code-Patterns.md missing — pull from git first"
fi

# 2. Ensure KnowledgeCollection row exists with correct base_dir.
COLL_ID=$(sqlite3 "$DB" "SELECT id FROM knowledge_collections WHERE slug='${SLUG}';")
if [ -z "$COLL_ID" ]; then
  sqlite3 "$DB" <<SQL
INSERT INTO knowledge_collections(name, slug, description, enabled, base_dir, workspace_id)
VALUES('AI Secretary — Dev Architecture', '${SLUG}',
       'Архитектурный контекст для дев-сессий: CLAUDE.md, Code-Patterns.md (паттерны кода, anti-patterns).',
       1, 'wiki-pages/${SLUG}', 1);
SQL
  COLL_ID=$(sqlite3 "$DB" "SELECT id FROM knowledge_collections WHERE slug='${SLUG}';")
  echo "Created collection id=${COLL_ID}"
else
  # Ensure base_dir is correct (in case of earlier misconfig).
  sqlite3 "$DB" "UPDATE knowledge_collections SET base_dir='wiki-pages/${SLUG}' WHERE id=${COLL_ID};"
  echo "Collection already exists id=${COLL_ID} (base_dir verified)"
fi

# 3. Re-register KnowledgeDocument rows (idempotent: wipe + reinsert).
sqlite3 "$DB" "DELETE FROM knowledge_documents WHERE collection_id=${COLL_ID};"
for f in "$DIR"/*.md; do
  [ -f "$f" ] || continue
  fname=$(basename "$f")
  title=$(head -1 "$f" | sed 's/^# //' | sed "s/'/''/g")
  size=$(stat -c %s "$f" 2>/dev/null || wc -c < "$f")
  sections=$(grep -c '^## ' "$f" || echo 1)
  sqlite3 "$DB" "INSERT INTO knowledge_documents(filename, title, source_type, file_size_bytes, section_count, collection_id, workspace_id) VALUES('${fname}','${title}','dev-architecture',${size},${sections},${COLL_ID},1);"
  echo "  registered: ${fname} (${size}b)"
done

echo ""
echo "Done. Restart orchestrator to load the index:"
echo "  systemctl restart ai-secretary"
echo ""
echo "To attach this collection to a chat session (admin UI):"
echo "  chat session settings → Knowledge Collections → add 'AI Secretary — Dev Architecture'"

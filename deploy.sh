#!/bin/bash
# Production deploy: pull main, install deps, rebuild admin, restart orchestrator.
#
#   ssh root@<server> "bash /opt/ai-secretary/deploy.sh"
#
# Safe to re-run. Aborts before the restart if any step fails, so a broken
# build or a failed pip install never takes the running service down.
#
# Optional env:
#   DEPLOY_SKIP_ADMIN=1     backend-only change — skip the admin build
#   APPLY_CLOUD_PATCHES=1   run apply_patches.py (legacy; only the OLD server
#                           needed it — on the current one it writes
#                           VITE_BASE_PATH=/ and breaks the panel at /admin/)

set -euo pipefail

REPO_DIR="/opt/ai-secretary"
LOG_FILE="/var/log/ai-secretary-deploy.log"
ADMIN_WWW="/var/www/admin-ai-sekretar24"   # old layout: nginx served admin from here
HEALTH_URL="http://localhost:8002/health"
HEALTH_TIMEOUT=300                         # RAG collections take ~2.5 min to load
BUILD_MEMORY_MAX="2500M"                   # no swap on prod — keep vite from OOM-ing the orchestrator

# `git reset --hard` below rewrites this very file while bash is still reading
# it; run from a private copy so the rest of the script is the version we started.
if [ "${DEPLOY_SELF_COPY:-}" != "1" ]; then
    tmp="$(mktemp /tmp/ai-secretary-deploy.XXXXXX.sh)"
    cp "$0" "$tmp"
    DEPLOY_SELF_COPY=1 exec bash "$tmp" "$@"
fi
trap 'rm -f "$0"' EXIT

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}
fail() {
    log "ERROR: $*"
    log "=== Deploy FAILED — service not restarted, previous version still running ==="
    exit 1
}
run() {  # run a command, mirror its output to the log, keep its exit status
    "$@" 2>&1 | tee -a "$LOG_FILE"
}
bump_sw_cache() {  # new cache name → browsers drop the old service-worker cache
    if [ -f "$1/sw.js" ]; then
        sed -i "s/ai-admin-v[0-9a-z]*/ai-admin-v$(date +%s)/" "$1/sw.js"
    fi
}

exec 9>/var/lock/ai-secretary-deploy.lock
flock -n 9 || { echo "Another deploy is already running"; exit 1; }

log "=== Deploy started ==="
cd "$REPO_DIR"

# ── Code ────────────────────────────────────────────────────────────────────
# .env, data/, backups and other untracked/ignored files survive reset --hard;
# only edits to tracked files are lost, so name them before throwing them away.
dirty="$(git status --porcelain --untracked-files=no)"
if [ -n "$dirty" ]; then
    log "WARNING: discarding local edits to tracked files:"
    echo "$dirty" | tee -a "$LOG_FILE"
fi
old_rev="$(git rev-parse --short HEAD)"
run git fetch origin main || fail "git fetch"
run git reset --hard origin/main || fail "git reset"
log "Code: $old_rev -> $(git rev-parse --short HEAD)"

if [ "${APPLY_CLOUD_PATCHES:-}" = "1" ] && [ -f "$REPO_DIR/apply_patches.py" ]; then
    log "Applying legacy cloud-mode patches..."
    run python3 "$REPO_DIR/apply_patches.py" || fail "apply_patches.py"
fi

# ── Python deps ─────────────────────────────────────────────────────────────
# A cloud server (no GPU, Python 3.12) cannot install the full requirements.txt:
# TTS/whisper/vosk need torch + audio devices, and numpy==1.24.3 has no 3.12
# wheel. Install the same list minus those, with numpy/transformers re-pinned —
# derived on every run, so deps added to requirements.txt are never missed.
deployment_mode="$( (grep -E '^DEPLOYMENT_MODE=' "$REPO_DIR/.env" || true) | tail -1 | cut -d= -f2- | tr -d "\"' ")"
req_file="$REPO_DIR/requirements.txt"
if [ "${deployment_mode:-full}" = "cloud" ]; then
    req_file="$(mktemp /tmp/requirements-cloud.XXXXXX.txt)"
    grep -viE '^(TTS|openai-whisper|faster-whisper|vosk|sounddevice)([=<>~ ]|$)' "$REPO_DIR/requirements.txt" \
        | sed -E 's/^numpy==.*/numpy>=1.26,<2.0/; s/^(transformers>=[^,]*),<[^ ]*/\1/' > "$req_file"
    log "Installing Python dependencies (cloud subset of requirements.txt)..."
else
    log "Installing Python dependencies..."
fi
run "$REPO_DIR/venv/bin/pip" install -q -r "$req_file" || fail "pip install (main)"
log "Installing bridge dependencies..."
run "$REPO_DIR/venv/bin/pip" install -q -r "$REPO_DIR/services/bridge/requirements.txt" \
    || fail "pip install (bridge)"

# ── Admin panel ─────────────────────────────────────────────────────────────
if [ "${DEPLOY_SKIP_ADMIN:-}" = "1" ]; then
    log "Skipping admin build (DEPLOY_SKIP_ADMIN=1)"
else
    if [ "${VITE_DEMO_MODE:-}" = "true" ]; then
        fail "VITE_DEMO_MODE=true in shell env — production build unsafe"
    fi

    log "Building admin panel..."
    build_cmd="cd '$REPO_DIR/admin' && npm ci --include=dev --silent && rm -rf dist node_modules/.vite && VITE_DEMO_MODE= npm run build"
    if command -v systemd-run >/dev/null 2>&1; then
        run systemd-run --quiet --wait --collect --pipe -p MemoryMax="$BUILD_MEMORY_MAX" \
            /bin/bash -c "$build_cmd" || fail "admin build"
    else
        run /bin/bash -c "$build_cmd" || fail "admin build"
    fi

    # The orchestrator serves the panel at /admin/. A build with any other base
    # (demo build, or a leftover VITE_BASE_PATH=/ from the old server) would
    # ship a panel whose asset URLs all 404 — refuse it unless the base was
    # overridden on purpose in admin/.env.production.local.
    index="$REPO_DIR/admin/dist/index.html"
    [ -s "$index" ] || fail "admin build produced no index.html"
    if ! grep -q '/admin/assets/' "$index"; then
        if grep -qs '^VITE_BASE_PATH=' "$REPO_DIR/admin/.env.production.local"; then
            log "WARNING: admin built with a custom VITE_BASE_PATH from admin/.env.production.local"
        else
            fail "admin build does not use the /admin/ base path (demo build?)"
        fi
    fi

    bump_sw_cache "$REPO_DIR/admin/dist"
    if [ -d "$ADMIN_WWW" ]; then
        log "Copying admin build to $ADMIN_WWW..."
        run rsync -a --delete "$REPO_DIR/admin/dist/" "$ADMIN_WWW/" || fail "rsync admin"
    fi
fi

# ── Restart ─────────────────────────────────────────────────────────────────
log "Restarting orchestrator..."
systemctl restart ai-secretary

log "Waiting for health (up to ${HEALTH_TIMEOUT}s)..."
elapsed=0
until curl -sf --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; do
    if [ "$elapsed" -ge "$HEALTH_TIMEOUT" ]; then
        log "=== WARNING: orchestrator not healthy after ${HEALTH_TIMEOUT}s — check: journalctl -u ai-secretary -n 100 ==="
        exit 1
    fi
    sleep 5
    elapsed=$((elapsed + 5))
done
log "=== Deploy completed successfully at $(git rev-parse --short HEAD) (healthy after ${elapsed}s) ==="

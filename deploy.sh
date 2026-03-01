#!/bin/bash
# Auto-deploy script for admin.ai-sekretar24.ru
# Pulls latest code, rebuilds admin panel, restarts orchestrator

set -e

REPO_DIR="/opt/ai-secretary"
LOG_FILE="/var/log/ai-secretary-deploy.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== Deploy started ==="

cd "$REPO_DIR"

# Backup local-only files (not in git)
log "Backing up local files..."
cp "$REPO_DIR/apply_patches.py" /tmp/apply_patches.py.bak
cp "$REPO_DIR/deploy.sh" /tmp/deploy.sh.bak
cp "$REPO_DIR/webhook_server.py" /tmp/webhook_server.py.bak
cp "$REPO_DIR/.env" /tmp/ai-secretary-env.bak
[ -f "$REPO_DIR/admin/.env.production.local" ] && cp "$REPO_DIR/admin/.env.production.local" /tmp/env-production-local.bak

# Pull latest changes
log "Pulling latest changes..."
git fetch origin 2>&1 | tee -a "$LOG_FILE"
git reset --hard origin/main 2>&1 | tee -a "$LOG_FILE"

# Restore local-only files
log "Restoring local files..."
cp /tmp/apply_patches.py.bak "$REPO_DIR/apply_patches.py"
cp /tmp/deploy.sh.bak "$REPO_DIR/deploy.sh"
cp /tmp/webhook_server.py.bak "$REPO_DIR/webhook_server.py"
cp /tmp/ai-secretary-env.bak "$REPO_DIR/.env"
[ -f /tmp/env-production-local.bak ] && cp /tmp/env-production-local.bak "$REPO_DIR/admin/.env.production.local"

# Re-apply local patches for cloud/web mode
log "Re-applying cloud-mode patches..."
# These patches make TTS/STT/XTTS imports optional for servers without GPU/torch
python3 "$REPO_DIR/apply_patches.py" 2>&1 | tee -a "$LOG_FILE"

# Install/update Python deps (bridge)
log "Installing bridge dependencies..."
"$REPO_DIR/venv/bin/pip" install -q -r "$REPO_DIR/services/bridge/requirements.txt" 2>&1 | tee -a "$LOG_FILE"

# Install/update npm deps
log "Installing npm dependencies..."
cd "$REPO_DIR/admin"
npm ci --include=dev 2>&1 | tee -a "$LOG_FILE"

# Ensure .env.production.local exists (base path override)
if [ ! -f "$REPO_DIR/admin/.env.production.local" ]; then
    echo "VITE_BASE_PATH=/" > "$REPO_DIR/admin/.env.production.local"
    log "Created .env.production.local"
fi

# Build admin panel (production mode)
# Clean dist/ and Vite cache to prevent stale demo build artifacts
rm -rf "$REPO_DIR/admin/dist" "$REPO_DIR/admin/node_modules/.vite"
log "Building admin panel..."
VITE_DEMO_MODE= npm run build 2>&1 | tee -a "$LOG_FILE"

# Verify no demo interceptor leaked into production build
if grep -q 'setupDemoInterceptor' "$REPO_DIR/admin/dist/assets/"*.js 2>/dev/null; then
    log "ERROR: Demo interceptor found in production build! Aborting deploy."
    exit 1
fi

# Deploy static files to nginx root
log "Copying dist to /var/www/admin-ai-sekretar24/..."
rsync -a --delete "$REPO_DIR/admin/dist/" /var/www/admin-ai-sekretar24/

# Restart orchestrator
log "Restarting orchestrator..."
systemctl restart ai-secretary 2>&1 | tee -a "$LOG_FILE"

# Wait and verify (20s to allow orchestrator full startup)
sleep 20
if curl -sf http://localhost:8002/health > /dev/null 2>&1; then
    log "=== Deploy completed successfully ==="
else
    log "=== WARNING: Orchestrator may not have started correctly ==="
fi

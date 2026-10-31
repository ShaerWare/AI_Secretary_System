# Deployment

> Part of the project map in [CLAUDE.md](../../CLAUDE.md). Split out of CLAUDE.md verbatim on 2026-10-31; update it in the same PR as the code it describes.

> ⚠️ Production moved to `178.208.81.231` (Ubuntu 24.04, systemd, cloud mode). Deploy: `ssh root@178.208.81.231 "bash /opt/ai-secretary/deploy.sh"`; run pending migrations by hand afterwards. The `155.212.231.7` host below is the old server.

## Server Deployment (Production)

Server: `root@155.212.231.7`, systemd service (not Docker Compose).

```bash
ssh root@155.212.231.7
cd /opt/ai-secretary
git pull origin main
cd admin && npm ci && npm run build
rsync -av --delete admin/dist/ /var/www/admin-ai-sekretar24/  # REQUIRED: nginx serves from /var/www/
sed -i "s/ai-admin-v[0-9a-z]*/ai-admin-v$(date +%s)/" /var/www/admin-ai-sekretar24/sw.js  # bust SW cache
systemctl restart ai-secretary               # restart orchestrator
curl -s http://localhost:8002/health         # health check
```

**IMPORTANT**: Nginx serves frontend from `/var/www/admin-ai-sekretar24/`, NOT from `/opt/ai-secretary/admin/dist/`. Always rsync after build.

Webhook auto-deploy: `ai-secretary-webhook.service` triggers on GitHub push.

**Local-only files** (not in git): `.env`, `docker-compose.override.yml`, modified `Dockerfile`

## Deployment Checklist

1. Run lint locally — `ruff check . && cd admin && npm run lint:check`
2. Check for pending DB migrations
3. Kill stale processes — `lsof -i :8002`
4. Clean build artifacts — `rm -rf admin/dist admin/node_modules/.vite`
5. Build — `npm run build` (verify `VITE_DEMO_MODE` is NOT set)
6. Restart — `docker compose restart ai-secretary`
7. Verify — `curl http://localhost:8002/health` + test `/admin/auth/login`

## Automated Deployment

```bash
./deploy.sh                # git pull, re-apply patches, build admin, restart orchestrator
./test_system.sh           # Quick health checks and API smoke tests
```

## Demo Sites

Fully offline demo builds at `demo.ai-sekretar24.ru`:
- Full demo (`/full/`): `npm run build -- --mode demo` (admin role, all features)
- Cloud demo (`/cloud/`): `npm run build -- --mode demo-web` (web role, customer-facing)
- Deploy: `bash /root/deploy-demo.sh`

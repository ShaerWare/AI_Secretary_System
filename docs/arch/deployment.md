# Deployment

> Part of the project map in [CLAUDE.md](../../CLAUDE.md). Split out of CLAUDE.md verbatim on 2026-10-31; update it in the same PR as the code it describes.

## Server Deployment (Production)

Server: `root@178.208.81.231` (Ubuntu 24.04, `DEPLOYMENT_MODE=cloud`, systemd service `ai-secretary`, not Docker Compose). RAM 7,8 GB without swap — run anything heavy under `systemd-run -p MemoryMax=…` or the OOM killer takes the orchestrator. The old server `155.212.231.7` is down.

```bash
ssh root@178.208.81.231 "bash /opt/ai-secretary/deploy.sh"
# then apply pending migrations by hand:
ssh root@178.208.81.231 "cd /opt/ai-secretary && venv/bin/alembic upgrade head"
```

`deploy.sh` (in the repo root, safe to re-run, flock-guarded, log in `/var/log/ai-secretary-deploy.log`): `git fetch` + `reset --hard origin/main` (warns about discarded local edits) → `pip install` of `requirements.txt` (cloud mode filters out TTS/whisper/vosk) and `services/bridge/requirements.txt` → admin build under `systemd-run MemoryMax=2500M` with `VITE_DEMO_MODE=` forced empty → checks `index.html` references `/admin/assets/` → `rsync` to `/var/www/admin-ai-sekretar24/` + service-worker cache bump → `systemctl restart ai-secretary` → waits for `/health` up to 300 s (RAG collections take ~2.5 min to load). Any failure before the restart aborts it, so the running version stays up. `DEPLOY_SKIP_ADMIN=1` for backend-only changes. **Do not** set `APPLY_CLOUD_PATCHES=1` / run `apply_patches.py` — it writes `VITE_BASE_PATH=/` and breaks the panel at `/admin/`.

**IMPORTANT**: Nginx serves the admin panel from `/var/www/admin-ai-sekretar24/`, NOT from `/opt/ai-secretary/admin/dist/` (the architecture diagram shows the FastAPI fallback). A manual build must be rsynced there.

**Production vs demo build.** Do **not** check with `grep setupDemoInterceptor`: `admin/src/api/client.ts` can switch demo mode on at runtime (`activateDemoMode()`, e.g. an admin/admin login, see [frontend-admin](frontend-admin.md)) through a lazy `import("./demo/index")`, so that name is in **every** bundle. The reliable marker is the base path in `dist/index.html`: production references `/admin/assets/…`, demo builds `/full/` or `/cloud/`. A demo build in the production folder shows up as a white login screen; recovery — build again without `VITE_DEMO_MODE` (or copy back `/var/www/admin-ai-sekretar24`) and restart.

The old server also had GitHub-push auto-deploy (`ai-secretary-webhook.service`); it was not verified on the new one — deploy by hand.

**Local-only files** (not in git): `.env`, `docker-compose.override.yml`, modified `Dockerfile`

## Deployment Checklist

1. Run lint locally — `ruff check . && cd admin && npm run lint:check`
2. Check for pending DB migrations
3. Kill stale processes — `lsof -i :8002`
4. Clean build artifacts — `rm -rf admin/dist admin/node_modules/.vite`
5. Build — `npm run build` (verify `VITE_DEMO_MODE` is NOT set; `dist/index.html` must reference `/admin/assets/`)
6. Prod only: `rsync -a --delete admin/dist/ /var/www/admin-ai-sekretar24/` (nginx serves from there)
7. Restart — `systemctl restart ai-secretary` on prod; `docker compose restart ai-secretary` in Docker setups
8. Verify — `curl http://localhost:8002/health` + test `/admin/auth/login`

`./test_system.sh` — quick health checks and API smoke tests.

## Demo Sites

Fully offline demo builds at `demo.ai-sekretar24.ru`:
- Full demo (`/full/`): `npm run build -- --mode demo` (admin role, all features)
- Cloud demo (`/cloud/`): `npm run build -- --mode demo-web` (web role, customer-facing)
- Deploy: `bash /root/deploy-demo.sh` — lived on the old server; the new prod has no demo deploy script yet

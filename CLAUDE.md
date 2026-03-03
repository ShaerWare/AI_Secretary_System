# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Secretary System — virtual secretary with voice cloning (XTTS v2, OpenVoice), pre-trained voices (Piper), local LLM (vLLM + Qwen/Llama/DeepSeek), cloud LLM fallback (Gemini, Kimi, OpenAI, Claude, DeepSeek, OpenRouter), and Claude Code CLI bridge. Features GSM telephony (SIM7600E-H), amoCRM integration, Vue 3 PWA admin panel, i18n (ru/en/kk), multi-instance Telegram bots with sales/payments, multi-instance WhatsApp bots (Cloud API), website chat widgets, and LoRA fine-tuning.

## Commands

### Build & Run

```bash
# Docker (recommended)
cp .env.docker.example .env && docker compose up -d          # GPU mode
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d  # CPU mode
docker compose -f docker-compose.yml -f docker-compose.full.yml up -d # Full containerized (includes vLLM)

# Local
./start_gpu.sh              # GPU: XTTS + Qwen2.5-7B + LoRA
./start_cpu.sh              # CPU: Piper + Gemini API
curl http://localhost:8002/health
```

### Admin Panel

```bash
cd admin && npm install     # First-time setup
cd admin && npm run build   # Production build (vue-tsc type-check + vite build)
cd admin && npm run dev     # Dev server (:5173), proxies /admin + /v1 + /health to :8002
DEV_MODE=1 ./start_gpu.sh   # Backend proxies to Vite dev server
```

Default login: admin / admin. Guest demo: demo / demo (read-only).

**No frontend tests** — `npm test` is not configured. Type checking happens during `npm run build` via `vue-tsc -b`.

**Deploy gotcha**: Vite deletes and recreates `admin/dist/` (new inode), breaking Docker bind mounts. Always `docker compose restart` after `npm run build`.

### User Management

```bash
python scripts/manage_users.py list                          # List all users
python scripts/manage_users.py create <user> <pass> --role user  # Roles: admin|user|web|guest
python scripts/manage_users.py set-password <user> <pass>    # Reset password
python scripts/manage_users.py set-role <user> <role>        # Change role
python scripts/manage_users.py disable <user>                # Deactivate
```

### Database Migrations

Three migration systems:
- **Alembic** (preferred) — for schema changes (`ALTER TABLE`, new tables)
- **`scripts/migrate_*.py`** — for data migrations. New scripts **must** use `scripts/_migration_template.py` (transaction-safe)
- **`Base.metadata.create_all`** — auto-creates missing tables on startup (does **not** alter existing)

```bash
alembic upgrade head                        # Apply all pending migrations
alembic revision --autogenerate -m "desc"   # Generate migration from model changes
cp scripts/_migration_template.py scripts/migrate_<name>.py  # New data migration
```

### Lint & Format

```bash
# Python
ruff check .                # Lint (see pyproject.toml for rules)
ruff check . --fix          # Auto-fix
ruff format .               # Format
ruff format --check .       # Check formatting

# Frontend
cd admin && npm run lint         # Lint + auto-fix
cd admin && npm run lint:check   # Lint only (CI-style)
cd admin && npm run format       # Prettier format
cd admin && npm run format:check # Check formatting

# All at once
pre-commit run --all-files
```

### Testing

```bash
pytest tests/                          # All tests
pytest tests/unit/test_retry_on_busy.py -v  # Single file
pytest -k "test_chat" -v               # By name pattern
pytest -m "not slow" -v                # Exclude slow tests
pytest -m "not integration" -v         # Exclude integration (needs external services)
```

`asyncio_mode = "auto"` — async tests run without `@pytest.mark.asyncio`. Custom markers: `slow`, `integration`, `gpu`. Docker: `docker exec ai-secretary python -m pytest tests/ -v -o asyncio_mode=auto`.

### CI

GitHub Actions (`.github/workflows/ci.yml`) on push to `main`/`develop` and PRs:
- `lint-backend` — ruff check + format check + mypy on `orchestrator.py` only (mypy soft, `|| true`)
- `lint-frontend` — npm ci + eslint + build (type check)
- `security` — Trivy vulnerability scanner

Always run lint locally before pushing. Protected branches require PR workflow — never push directly to `main`.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  Orchestrator (port 8002)                     │
│  orchestrator.py + app/routers/ (28 routers, ~400 endpoints) │
│  ┌────────────────────────────────────────────────────────┐  │
│  │        Vue 3 Admin Panel (23 views, PWA)                │  │
│  │                admin/dist/                              │  │
│  └────────────────────────────────────────────────────────┘  │
└────────────┬──────────────┬──────────────┬───────────────────┘
             │              │              │
     ┌───────┴──┐    ┌──────┴───┐   ┌─────┴─────┐
     │ LLM      │    │ TTS      │   │ STT       │
     │ vLLM /   │    │ XTTS v2 /│   │ Vosk /    │
     │ Cloud    │    │ Piper    │   │ Whisper   │
     └──────────┘    └──────────┘   └───────────┘
```

**Request flow:** User message → FAQ check (instant match) OR LLM → TTS → Audio response

**Deployment modes** (`DEPLOYMENT_MODE` env var): `full` (default, everything), `cloud` (no GPU/TTS/STT/GSM), `local` (same as full). Cloud mode skips hardware router registration, hides hardware admin tabs, filters out `speech`/`gsm` permissions.

### Modular Infrastructure (`modules/core/`)

Foundation layer for the ongoing modular decomposition (see issue #489). Purely additive — no existing code modified yet.

- **`EventBus`** (`modules/core/events.py`): In-process async pub/sub. Handlers run concurrently via `asyncio.gather`; exceptions are logged, never propagated to publisher. `BaseEvent` dataclass with auto-timestamp.
- **`TaskRegistry`** (`modules/core/tasks.py`): Named background tasks — periodic (interval-based) or one-shot. `start_all()` / `cancel_all(timeout)` lifecycle. `TaskInfo` dataclass tracks status, run count, last error.
- **`HealthRegistry`** (`modules/core/health.py`): Modular health checks with per-check timeout (`asyncio.wait_for`). Status aggregation: all ok → ok, any degraded → degraded, any error → error.

Import from `modules.core`: `EventBus`, `BaseEvent`, `TaskRegistry`, `TaskInfo`, `HealthRegistry`, `HealthStatus`.

### Key Components

**`orchestrator.py`** (~4100 lines): FastAPI entry point. Initializes all services as module-level globals, populates `ServiceContainer`, includes all routers. Legacy OpenAI-compatible `/v1/*` endpoints still live here.

**`ServiceContainer` (`app/dependencies.py`)**: Singleton holding references to all initialized services. Routers get services via FastAPI `Depends`. Populated during app startup.

**Two service layers**: Core AI services at project root (`cloud_llm_service.py`, `vllm_llm_service.py`, `voice_clone_service.py`, `stt_service.py`, etc.). Domain services in `app/services/` (`amocrm_service.py`, `wiki_rag_service.py`, `backup_service.py`, `sales_funnel.py`, etc.).

**Database layer** (`db/`): Async SQLAlchemy + aiosqlite. `db/database.py` creates engine. `db/integration.py` provides backward-compatible manager classes (e.g., `AsyncChatManager`) used as module-level singletons. Repositories in `db/repositories/` inherit from `BaseRepository` with generic CRUD and `_apply_workspace_filter()` for multi-tenant queries.

**Unit of Work**: Repositories only `flush()` — never `commit()`. Callers own transaction boundaries: managers call `session.commit()`, `get_async_session()` auto-commits on success / rollbacks on exception.

**SQLITE_BUSY retry**: `db/retry.py` `@retry_on_busy()` — exponential backoff (3 retries, 0.1s base). Applied to all write methods in `integration.py` managers.

**Telegram bots**: Subprocesses managed by `multi_bot_manager.py`. Config pre-fetched from DB, written to `/tmp/bot_config_{id}.json`. Two frameworks: `python-telegram-bot` (legacy) + `aiogram` (new). `LLMRouter` in `telegram_bot/services/llm_router.py` routes through orchestrator chat API.

**WhatsApp bots**: Same subprocess pattern via `whatsapp_manager.py`. Module: `whatsapp_bot/` (runs as `python -m whatsapp_bot`).

**Cloud LLM**: `cloud_llm_service.py` factory pattern. OpenAI-compatible providers auto-handled via `OpenAICompatibleProvider`. Custom SDKs get their own provider class inheriting `BaseLLMProvider`. Provider types in `PROVIDER_TYPES` dict in `db/models.py`. Supports model fallback via `fallback_models` list.

**Wiki RAG**: `app/services/wiki_rag_service.py` — tiered search: (1) semantic embeddings (Gemini/OpenAI/local), (2) BM25 with Russian/English stemming. Multi-collection support. Per-instance RAG config on bots/widgets.

### Frontend Architecture

**Stack**: Vue 3 + Composition API + TypeScript, Vite, Pinia (persisted), Vue Router (hash history), TanStack Vue Query, vue-i18n (ru/en/kk), TailwindCSS + radix-vue, lucide-vue-next. Path alias `@` → `admin/src/`.

**Routing** (`admin/src/router.ts`): `createWebHashHistory`. Routes use `meta` fields: `public` (bypass auth), `localOnly` (hidden in cloud mode), `module` (RBAC module name), `minLevel` (view/edit/manage).

**Stores** (`admin/src/stores/`): Key store `auth.ts` holds JWT, user, `deploymentMode`, `permissions`. Exposes `isAdmin`, `isCloudMode`, `hasModule()`, `canView()`, `canEdit()`, `canManage()`. **Toast API**: `toast.success/error/warning/info(title)` — do NOT use `toast.show()` (different signature: `show(type, title, message?)`). **Confirm API**: `confirm.confirm({ title, message, confirmText, type })` returns `Promise<boolean>` — no `ask()` method.

**API layer** (`admin/src/api/`): `client.ts` provides `api.get/post/put/delete/upload` + `createSSE()` (auto-injects JWT). Domain files build on it. All re-exported from `api/index.ts`.

**Demo mode**: `VITE_DEMO_MODE=true` monkey-patches `window.fetch` to intercept API calls with mock data from 23 domain files in `admin/src/api/demo/`.

**Vite base path**: Production `/admin/` (served by FastAPI). Demo/standalone: `/` (via `VITE_BASE_PATH` or `.env.production.local`).

## Code Patterns

**Adding a new API endpoint:**
1. Create/edit router in `app/routers/`
2. Use `ServiceContainer` from `app/dependencies.py` for DI
3. Add router to `__all__` in `app/routers/__init__.py`
4. Register in `orchestrator.py` with `app.include_router()`

**Adding a new cloud LLM provider type:**
1. Add entry to `PROVIDER_TYPES` dict in `db/models.py`
2. OpenAI-compatible → works automatically via `OpenAICompatibleProvider`
3. Custom SDK → create provider class inheriting `BaseLLMProvider` in `cloud_llm_service.py`, register in `CloudLLMService.PROVIDER_CLASSES`

**RBAC auth guards** (in `auth_manager.py`):
- `Depends(require_permission(module, level))` — checks module permission
- `user_has_level(user, module, level)` — inline check within endpoint
- `workspace_context(user, module)` → `(owner_id, workspace_id)` — for repository calls; `owner_id=None` means "shared within workspace"
- Data isolation: always pass both `owner_id` and `workspace_id` to repository/manager

**Gate-check pattern for mutations**: UPDATE/DELETE endpoints call workspace-filtered get first (e.g., `get_by_id_ws(id, workspace_id=ws_id)`); if `None` → 404. Prevents cross-workspace access. `ChatRepository` is the reference implementation.

**Adding i18n translations**: Edit `admin/src/plugins/i18n.ts` — add keys to all three message objects: `ru`, `en`, `kk`.

**API URL patterns:**
- `GET/POST /admin/{resource}` — List/create
- `GET/PUT/DELETE /admin/{resource}/{id}` — CRUD
- `POST /admin/{resource}/{id}/action` — Actions (start, stop, test)
- `POST /webhooks/{service}` — External webhooks
- `POST /v1/chat/completions`, `GET /v1/models` — OpenAI-compatible

## Codebase Conventions

- **Python 3.11+**, line length 100, double quotes (ruff format)
- **Cyrillic is normal** — RUF001/002/003 disabled; Russian in UI text, logging, persona prompts
- **FastAPI Depends** — B008 disabled for `Depends()` in default args
- **Optional imports** — Services like vLLM and OpenVoice use try/except at module level with `*_AVAILABLE` flags
- **SQLAlchemy 2.0 style** — `Mapped[T]` with `mapped_column()` (declarative 2.0)
- **Repository pattern** — `BaseRepository(Generic[T])` provides CRUD + `_apply_workspace_filter()`. Repos only `flush()`, never `commit()`
- **mypy strict** only for `db/`, `auth_manager.py`, `service_manager.py`; other modules relaxed. mypy is soft in CI
- **Pre-commit hooks** — ruff, mypy (core only), eslint, hadolint, standard checks (see `.pre-commit-config.yaml`)

## Key Environment Variables

```bash
LLM_BACKEND=vllm                    # "vllm" or "cloud:{provider_id}" (legacy "gemini" auto-migrates)
VLLM_API_URL=http://localhost:11434 # Auto-normalized: trailing /v1 stripped
DEPLOYMENT_MODE=full                # "full", "cloud", or "local"
ORCHESTRATOR_PORT=8002
ADMIN_JWT_SECRET=...                # Auto-generated if empty
REDIS_URL=redis://localhost:6379/0  # Optional, graceful fallback
DEV_MODE=1                          # Backend proxies to Vite dev server (:5173)
```

## Deployment

### Docker Deployment (Production)

```bash
cd /opt/ai-secretary
docker compose ps                            # status
docker compose logs -f ai-secretary          # logs
docker compose up -d --build                 # rebuild + restart
docker compose restart ai-secretary          # restart only

# Admin panel rebuild (ALWAYS build from /opt/ai-secretary/admin, not git clone!)
cd /opt/ai-secretary/admin && npm run build
docker compose restart ai-secretary          # REQUIRED: re-bind new dist/ inode
```

**Local-only files** (not in git): `.env`, `docker-compose.override.yml`, modified `Dockerfile`, `services/bridge/src/models/`

### Deployment Checklist

1. Run lint locally — `ruff check . && cd admin && npm run lint:check`
2. Check for pending DB migrations
3. Kill stale processes — `lsof -i :8002`
4. Clean build artifacts — `rm -rf admin/dist admin/node_modules/.vite`
5. Build — `npm run build` (verify `VITE_DEMO_MODE` is NOT set)
6. Restart — `docker compose restart ai-secretary`
7. Verify — `curl http://localhost:8002/health` + test `/admin/auth/login`

### Demo Sites

Fully offline demo builds at `demo.ai-sekretar24.ru`:
- Full demo (`/full/`): `npm run build -- --mode demo` (admin role, all features)
- Cloud demo (`/cloud/`): `npm run build -- --mode demo-web` (web role, customer-facing)
- Deploy: `bash /root/deploy-demo.sh`

## Debugging Principles

Check in this order — **infrastructure first**, application logic last:
1. **Build artifacts** — correct build deployed? Stale demo interceptors?
2. **Deploy pipeline** — stale Vite cache, wrong `.env`, `VITE_DEMO_MODE` leaking?
3. **DB state** — migrations applied? `sqlite3 data/secretary.db ".tables"` / `.schema`
4. **Process state** — port conflicts (`lsof -i :8002`), zombie processes?
5. **Auth/JWT** — `ADMIN_JWT_SECRET` auto-generated on restart (invalidates tokens). Sessions validated against `user_sessions` table via `SessionCache`
6. **Application logic** — only after ruling out 1–5

## Parallel Development (Two Claude Code Instances)

This project is developed from two machines:
- **local** — dev workstation with GPU (RTX 3060), full stack
- **server** — Beget VPS, Docker, cloud LLM only

Each machine identifies itself via `~/.claude/projects/.../memory/MEMORY.md` (`## Machine Role` section). **Check your machine role before git operations.**

### Git Workflow

1. **Never push directly to `main`** — always feature branch + PR
2. **Branch prefixes**: `local/*` (dev machine), `server/*` (server), or `feat/`/`fix/`/`docs/` with machine suffix
3. **Always `git pull` before starting work**
4. **Do not amend or force-push commits made by the other instance**

### File Ownership

**Local primary**: Hardware services (`voice_clone_service.py`, `stt_service.py`, `vllm_llm_service.py`, `piper_tts_service.py`), GPU/hardware routers, fine-tuning, voice samples, start scripts.

**Server primary**: Cloud services (`cloud_llm_service.py`, `xray_proxy_manager.py`), Docker files, bot operations (runtime), production data.

**Shared** (coordinate via branches): `orchestrator.py`, `app/routers/`, `db/`, `admin/`, `CLAUDE.md`, migrations (create new files only).

## Known Issues

1. **Vosk model required** — Download to `models/vosk/` for STT
2. **XTTS requires CUDA CC >= 7.0** — RTX 3060+; use OpenVoice for older GPUs
3. **GPU memory** — vLLM ~6GB + XTTS ~5GB must fit in 12GB
4. **VLESS proxy vs localhost** — `GeminiProvider` sets global `HTTP_PROXY`; `OpenAICompatibleProvider` sets `NO_PROXY=127.0.0.1,localhost` for `claude_bridge`; `bridge_manager.py` strips proxy env vars
5. **Claude bridge timeouts** — 7-30s warmup. `read=300s` timeout for bridge (vs 60s default). `max_tokens=4096` (vs 512)
6. **`services/bridge/src/models/` gitignored** — `.gitignore` pattern `models/` catches it. Copy manually after clone
7. **Docker CPU: whisper excluded** — `openai-whisper` fails to build (missing `pkg_resources`). Server Dockerfile patched to `grep -v whisper`
8. **Docker + Claude CLI** — CPU image needs Node.js. Server Dockerfile patched to install Node.js 20 + `@anthropic-ai/claude-code`

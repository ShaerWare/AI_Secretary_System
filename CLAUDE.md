# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Secretary System — virtual secretary with voice cloning (XTTS v2, OpenVoice), pre-trained voices (Piper), local LLM (vLLM + Qwen/Llama/DeepSeek), cloud LLM fallback (Gemini, Kimi, OpenAI, Claude, DeepSeek, OpenRouter), and Claude Code CLI bridge. Features GSM telephony (SIM7600E-H), amoCRM integration, Vue 3 PWA admin panel, i18n (ru/en/kk), multi-instance Telegram bots with sales/payments, multi-instance WhatsApp bots (Meta Cloud API or a self-hosted QR-linked provider), website chat widgets, and LoRA fine-tuning.

## Commands

### Build & Run

```bash
# Docker (recommended)
cp .env.docker.example .env && docker compose up -d          # GPU mode
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d  # CPU mode
docker compose -f docker-compose.yml -f docker-compose.full.yml up -d # Full containerized (includes vLLM)
docker compose --profile vector-search up -d                 # + Vector Search microservice (:8003)

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

### Mobile App

```bash
cd mobile && npm install     # First-time setup
cd mobile && npm run build   # Production build (vue-tsc type-check + vite build)
cd mobile && npm run dev     # Dev server
cd mobile && npx cap sync android  # Sync web assets to Android project
cd mobile && npx cap open android  # Open in Android Studio → Build APK
```

### User Management

```bash
python scripts/manage_users.py list                          # List all users
python scripts/manage_users.py create <user> <pass> --role user  # Roles: admin|user|web|guest
python scripts/manage_users.py set-password <user> <pass>    # Reset password
python scripts/manage_users.py set-role <user> <role>        # Change role
python scripts/manage_users.py disable <user>                # Deactivate
```

### Mobile Internet (SIM7600E-H QMI)

```bash
sudo bash scripts/setup_mobile_internet.sh start   # Connect wwan0 via QMI
sudo bash scripts/setup_mobile_internet.sh stop    # Disconnect
sudo bash scripts/setup_mobile_internet.sh status  # Check connection
sudo bash scripts/mobile-internet-monitor.sh       # Daemon: auto-reconnect + VPN route failover
# systemd: scripts/mobile-internet.service          # Install as persistent service
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

> **Interactive architecture map**: [`docs/architecture/architecture-map.html`](docs/architecture/architecture-map.html) (self-contained, open in a browser — search across modules/services/routers) + machine-readable [`docs/architecture/architecture-map.json`](docs/architecture/architecture-map.json). Regenerate from this file when the module/router/service inventory changes.

```
┌──────────────────────────────────────────────────────────────┐
│                  Orchestrator (port 8002)                     │
│  orchestrator.py + modules/*/router*.py (~28 routers)        │
│  ┌────────────────────────────────────────────────────────┐  │
│  │        Vue 3 Admin Panel (24 views, PWA)                │  │
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

## Project map (read the file before touching that area)

`CLAUDE.md` is the map; details live in `docs/arch/`, one topic per file. Open the relevant file before working in that area, and update it in the same PR when the behaviour it describes changes.

| Area | File | Read it when… |
|------|------|----------------|
| `modules/` foundation: EventBus, TaskRegistry (all background tasks), HealthRegistry, InternetMonitor; domain service and router tables | [docs/arch/modules.md](docs/arch/modules.md) | adding a service/router/task/event, looking for where something lives |
| `orchestrator.py`, `ServiceContainer`, DB layer, Unit of Work, SQLITE_BUSY retry, LLM calls off the event loop | [docs/arch/backend-core.md](docs/arch/backend-core.md) | any backend change touching startup, DB writes or LLM calls |
| Telegram and WhatsApp bots (subprocesses, Cloud API vs QR bridge, sales funnel) | [docs/arch/channels.md](docs/arch/channels.md) | bot behaviour, WhatsApp bridge |
| Outbound approval queue, channel monitoring, КП in PIM ar-gs.ru + timers | [docs/arch/outbound-kp.md](docs/arch/outbound-kp.md) | anything sent to a client, КП |
| Client card: what the assistant remembers about a client between dialogues (WhatsApp), `client-cards` task, CRM tab «Клиенты» | [docs/arch/client-memory.md](docs/arch/client-memory.md) | client memory, anything added to a client channel's prompt |
| Cloud LLM providers, `claude_bridge` tools, platform-agent fallback, personas, role prompts, bridge HOME isolation, per-user Claude token tracking | [docs/arch/llm-prompts.md](docs/arch/llm-prompts.md) | prompt precedence, providers, personas, usage |
| Wiki RAG, Vector Search, agentic RAG, Google Drive sources, RSS, dev-architecture collection, scraped legal/SEO collections | [docs/arch/knowledge-rag.md](docs/arch/knowledge-rag.md) | knowledge base, collections, Drive/RSS sync |
| Admin panel: stack, routing, stores (toast/confirm API), API layer, demo mode, lite variant | [docs/arch/frontend-admin.md](docs/arch/frontend-admin.md) | any `admin/` change |
| Mobile app: roles, instances, default-assistant provisioning, private sessions, file upload, session prompts | [docs/arch/mobile.md](docs/arch/mobile.md) | any `mobile/` change, assistants |
| Landing site `site/` + lead form → Telegram | [docs/arch/landing.md](docs/arch/landing.md) | landing changes |
| Procurement: unified product search and ranking, YML stock feed, supplier price parsers, routing, pricing engine, КП builder, amoCRM triage (StalkerElectric) | [docs/arch/procurement.md](docs/arch/procurement.md) | any `modules/procurement/` or StalkerElectric work |
| Production deploy, checklist, demo sites | [docs/arch/deployment.md](docs/arch/deployment.md) | deploying |
| Known issues (full text) | [docs/arch/known-issues.md](docs/arch/known-issues.md) | debugging GPU, proxy, bridge, tiktoken, imports |

Interactive architecture map: [docs/architecture/architecture-map.html](docs/architecture/architecture-map.html).

## Invariants (break these and something fails silently)

- **`orchestrator.py` is pure wiring** — no endpoints, no domain logic, no raw `asyncio.create_task()`; services start in domain `startup.py`, background work goes through `TaskRegistry`. `ServiceContainer` is the single source of truth for service state. → [backend-core](docs/arch/backend-core.md)
- **LLM calls never run on the event loop** — `asyncio.to_thread` / `iterate_in_threadpool`; regression test `tests/unit/test_stream_does_not_block_loop.py`. → [backend-core](docs/arch/backend-core.md)
- **Repositories only `flush()`**, callers commit. Writes in domain services carry `@retry_on_busy()`. → [backend-core](docs/arch/backend-core.md)
- **Domain `__init__.py` files stay empty** — re-exports cause a circular import through `db/models.py`. → [known-issues](docs/arch/known-issues.md) #10
- **tiktoken never loads on the request path.** → [known-issues](docs/arch/known-issues.md) #9
- **httpx to local services passes `trust_env=False`** — `GeminiProvider` sets a process-global `HTTP_PROXY`. → [known-issues](docs/arch/known-issues.md) #4
- **Client channels (widget/telegram/whatsapp) never get `prompts/platform-agent.md`.** → [llm-prompts](docs/arch/llm-prompts.md)
- **Procurement never invents goods, prices or stock** — `OfferService.search()` returns `[]`; «✅ в наличии» only for confirmed stock; supplier names and purchase prices only for managers. Search changes need a service restart. → [procurement](docs/arch/procurement.md)
- **The assistant only drafts КП; a human approves every send.** → [outbound-kp](docs/arch/outbound-kp.md)
- **Prices and stock never come from memory** — the client card drops such lines in code (`clean_card`); prices only from the live catalog search. → [client-memory](docs/arch/client-memory.md)

## Code Patterns

**Adding a new API endpoint:**
1. Create/edit router in `modules/{domain}/router.py` (preferred) or `app/routers/` (legacy)
2. Use domain service singletons (`from modules.chat.service import chat_service`) for DB access
3. If using `app/routers/`, add to `__all__` in `app/routers/__init__.py`
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

**Adding i18n translations**: Edit `admin/src/plugins/i18n.ts` — add keys to all three message objects: `ru`, `en`, `kk`. Characters `@ { } | %` are vue-i18n syntax — write a literal `@` as `{'@'}` (`user{'@'}example.com`, `{'@'}BotFather`); a bare `@` compiles lazily at render time and crashes the whole page with `SyntaxError: 10` (INVALID_LINKED_FORMAT), so `vue-tsc`/the build will NOT catch it.

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
VECTOR_SEARCH_URL=http://localhost:8003  # Optional, Vector Search microservice
VECTOR_SEARCH_TOKEN=                # Bearer token for Vector Search API
GOOGLE_CLIENT_ID=                   # Google OAuth 2.0 (Drive, Docs, Sheets, Gmail)
GOOGLE_CLIENT_SECRET=               # Google OAuth 2.0 client secret
GOOGLE_REDIRECT_URI=                # OAuth callback URL (default: {BASE_URL}/admin/oauth/google/callback)
PLATFORM_AGENT_PROMPT_FILE=         # Override path to platform-agent fallback prompt (default: /opt/ai-secretary/prompts/platform-agent.md)
BRIDGE_ISOLATE_HOME=                # "1" to spawn Claude CLI with isolated HOME so host's CLAUDE.md/memory files don't leak into user chats
BRIDGE_ISOLATED_HOME=               # Override isolated HOME path (default: /var/lib/ai-secretary-bridge)
LEAD_TELEGRAM_BOT_TOKEN=            # Bot token for landing lead notifications (POST /widget/lead → owner's Telegram)
LEAD_TELEGRAM_CHAT_ID=             # Numeric chat_id that receives landing lead notifications
WHATSAPP_BRIDGE_TOKEN=              # Shared secret for the self-hosted WhatsApp provider; also signs its webhooks
WHATSAPP_BRIDGE_URL=                # Bridge location (default http://127.0.0.1:8005); per-instance override in DB
WHATSAPP_BRIDGE_CALLBACK_HOST=      # Host the bridge calls back on to reach the bot (default 127.0.0.1)
TIKTOKEN_CACHE_DIR=                 # Override tiktoken BPE cache dir (default: <repo>/models/tiktoken)
PROCUREMENT_FEED_URL=               # YML-фид наличия StalkerElectric (остатки+сроки поверх каталога); пусто — задача спит
ARGS_PIM_URL=https://ar-gs.ru/api/v1  # PIM, где живут КП (modules/kp)
ARGS_PIM_API_KEY=                   # apk_… из PIM: Настройки → API; пусто — КП-модуль спит
ARGS_PIM_WEBHOOK_SECRET=            # секрет POST /webhooks/pim; пусто — вебхук выключен
KP_TELEGRAM_BOT_TOKEN=              # уведомления по КП; пусто — LEAD_TELEGRAM_BOT_TOKEN/CHAT_ID
KP_TELEGRAM_CHAT_ID=
```

## Deployment

Production: `ssh root@178.208.81.231 "bash /opt/ai-secretary/deploy.sh"`, then apply pending migrations by hand. Nginx serves the admin panel from `/var/www/admin-ai-sekretar24/`, not from `admin/dist/`. Full procedure, checklist and demo sites: [docs/arch/deployment.md](docs/arch/deployment.md).

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
- **server** — Beget VPS (`root@155.212.231.7`), systemd service, cloud LLM only

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

Full text with causes and fixes: [docs/arch/known-issues.md](docs/arch/known-issues.md).

1. Vosk model required
2. XTTS requires CUDA CC >= 7.0
3. GPU memory
4. VLESS proxy vs localhost
5. Claude bridge timeouts
6. `services/bridge/src/models/` now committed
7. Docker CPU: whisper excluded
8. Docker + Claude CLI
9. tiktoken must never load on the request path
10. Circular import in domain `__init__.py`
11. Trimming a response field breaks the API-layer mappers

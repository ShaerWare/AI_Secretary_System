# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Secretary System — virtual secretary with voice cloning (XTTS v2, OpenVoice), pre-trained voices (Piper), local LLM (vLLM + Qwen/Llama/DeepSeek), cloud LLM fallback (Gemini, Kimi, OpenAI, Claude, DeepSeek, OpenRouter), and Claude Code CLI bridge. Features GSM telephony (SIM7600E-H), amoCRM integration (OAuth2, contacts, leads, pipelines, kanban board, deals table, unified inbox), Vue 3 PWA admin panel, i18n (ru/en/kk), multi-instance Telegram bots with sales/payments, multi-instance WhatsApp bots (Cloud API), website chat widgets, and LoRA fine-tuning.

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

Default login: admin / admin
Guest demo: demo / demo (read-only access)

**Note:** No frontend test infrastructure exists (`npm test` is not configured). Type checking happens during `npm run build` via `vue-tsc -b`.

### User Management

```bash
python scripts/manage_users.py list                          # List all users
python scripts/manage_users.py create <user> <pass> --role user  # Create user (admin|user|web|guest)
python scripts/manage_users.py set-password <user> <pass>    # Reset password
python scripts/manage_users.py set-role <user> <role>        # Change role
python scripts/manage_users.py disable <user>                # Deactivate user
python scripts/manage_users.py enable <user>                 # Reactivate user
python scripts/manage_users.py delete <user>                 # Delete user
```

### Database Migrations

Two migration systems: **Alembic** (preferred for new migrations) and legacy manual scripts in `scripts/migrate_*.py`. New tables are auto-created by `Base.metadata.create_all` on startup; **schema changes to existing tables need migration scripts**. Seed scripts: `scripts/seed_*.py`.

```bash
# Alembic (preferred)
alembic upgrade head                        # Apply all pending migrations
alembic revision --autogenerate -m "desc"   # Generate migration from model changes
alembic history                             # List migrations

# Legacy manual scripts
ls scripts/migrate_*.py                     # List all available migrations
python scripts/migrate_json_to_db.py        # Initial JSON → SQLite migration (first-time)
python scripts/migrate_<feature>.py         # Run specific migration after adding new columns/tables
python scripts/seed_tz_generator.py         # Seed TZ generator bot data
```

### Lint & Format

```bash
# Python (requires .venv with ruff installed)
ruff check .                # Lint (see pyproject.toml for full rule config)
ruff check . --fix          # Auto-fix
ruff format .               # Format
ruff format --check .       # Check formatting (CI uses this)

# Frontend
cd admin && npm run lint         # Lint + auto-fix
cd admin && npm run lint:check   # Lint without auto-fix (CI-style)
cd admin && npm run format       # Prettier format
cd admin && npm run format:check # Check formatting only

# All pre-commit hooks
pre-commit run --all-files
```

### Testing

```bash
pytest tests/                          # All tests
pytest tests/unit/test_db.py -v        # Single file
pytest -k "test_chat" -v               # By name pattern
pytest -m "not slow" -v                # Exclude slow tests
pytest -m "not integration" -v         # Exclude integration (needs external services)
pytest -m "not gpu" -v                 # Exclude GPU-required tests
```

**Note:** The `tests/` directory does not exist yet — test infrastructure is configured in `pyproject.toml` but tests have not been written. Pytest uses `asyncio_mode = "auto"` — async test functions run without needing `@pytest.mark.asyncio`. Custom markers: `slow`, `integration`, `gpu`.

### CI

GitHub Actions (`.github/workflows/ci.yml`) runs on push to `main`/`develop` and on PRs:
- `lint-backend` — ruff check + format check + mypy on `orchestrator.py` only (mypy is soft — `|| true`, won't fail build)
- `lint-frontend` — npm ci + eslint + build (includes type check)
- `security` — Trivy vulnerability scanner

**Always run lint locally before pushing to PRs** to avoid repeated fix-and-push cycles:

```bash
# Backend
ruff check . && ruff format --check .

# Frontend
cd admin && npm run lint:check && npm run format:check

# Or all at once via pre-commit
pre-commit run --all-files
```

Protected branches require PR workflow with CI checks — never push directly to `main`.

## Deployment Checklist

Follow this checklist for every production deploy. Do NOT report deployment as complete until all steps pass.

1. **Run lint locally** — `ruff check . && cd admin && npm run lint:check` (avoids CI failures)
2. **Check for pending DB migrations** — if new columns/tables were added, ensure `scripts/migrate_*.py` exists and is run on server
3. **Kill stale processes** — `lsof -i :8002` to check for port conflicts before restart
4. **Clean build artifacts** — `rm -rf admin/dist admin/node_modules/.vite` before building (prevents demo interceptor leaking into production)
5. **Build and deploy** — `npm run build` (verify `VITE_DEMO_MODE` is NOT set in environment)
6. **Restart services** — `systemctl restart ai-secretary`
7. **Verify endpoints** — `curl http://localhost:8002/health` and test `/admin/auth/login`
8. **Check logs** — `journalctl -u ai-secretary --since "2 minutes ago" --no-pager | tail -20`

**After `git reset --hard`** — always check if local-only files (`.env`, `apply_patches.py`, `deploy.sh`, `admin/.env.production.local`) need to be restored before proceeding.

## Debugging Principles

When diagnosing production or demo issues, check in this order — **infrastructure and build pipeline FIRST**, application logic LAST:

1. **Build artifacts** — is the correct build deployed? Check actual JS files for stale demo interceptors (`grep setupDemoInterceptor admin/dist/assets/*.js`), wrong base paths, or missing chunks
2. **Deploy pipeline** — stale Vite cache (`node_modules/.vite`), wrong `.env` files, `VITE_DEMO_MODE` leaking from demo builds
3. **DB state** — were migrations applied? Missing columns cause silent failures (`sqlite3 data/secretary.db ".tables"` / `.schema`)
4. **Process state** — port conflicts from zombie processes (`lsof -i :8002`), multiple bot instances, systemd service status
5. **Auth/JWT** — `ADMIN_JWT_SECRET` is auto-generated on startup; restarting the service invalidates all existing tokens. Session-based revocation: tokens are validated against `user_sessions` table (via in-memory `SessionCache`); check `revoked_at` and `user.is_active` on cache miss
6. **Application logic** — only investigate after ruling out 1–5

**Never blame browser cache or user error** without first checking server-side build artifacts and config.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  Orchestrator (port 8002)                     │
│  orchestrator.py + app/routers/ (23 routers, ~400 endpoints) │
│  ┌────────────────────────────────────────────────────────┐  │
│  │        Vue 3 Admin Panel (21 views, PWA)                │  │
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

**GPU mode (RTX 3060 12GB):** vLLM ~6GB (50% GPU) + XTTS v2 ~5GB

**Request flow:** User message → FAQ check (instant match) OR LLM → TTS → Audio response

**Deployment modes** (`DEPLOYMENT_MODE` env var): Controls what services/routers exist in a given deployment, orthogonal to user roles (which control who can do what). Three modes:
- `full` (default) — everything loaded, current behavior
- `cloud` — cloud LLM only, no GPU/TTS/STT/GSM services, hardware routers not registered, hardware admin tabs hidden
- `local` — same as `full` (explicit opt-in for documentation clarity)

Backend: `orchestrator.py` conditionally registers hardware routers (`services`, `monitor`, `gsm`, `stt`, `tts`) and skips TTS/STT/GPU initialization in cloud mode. Health endpoint includes `deployment_mode` and adjusts health logic (TTS not required in cloud). `GET /admin/deployment-mode` returns current mode. `/auth/me` includes `deployment_mode`.

Frontend: `auth.ts` store fetches deployment mode via `GET /admin/deployment-mode`, exposes `isCloudMode` computed. Nav items and routes with `localOnly: true` are hidden/guarded in cloud mode (Dashboard, Services, TTS, Monitoring, Models, GSM). Cloud users redirect to `/chat`.

### Key Architectural Decisions

**Global state in orchestrator.py** (~3670 lines, ~100 legacy endpoints): This is the FastAPI entry point. It initializes all services as module-level globals, populates the `ServiceContainer`, and includes all routers. Legacy endpoints (OpenAI-compatible `/v1/*`) still live here alongside the modular router system.

**ServiceContainer (`app/dependencies.py`)**: Singleton holding references to all initialized services (TTS, LLM, STT, Wiki RAG). Routers get services via FastAPI `Depends`. Populated during app startup in `orchestrator.py`.

**Database layer** (`db/`): Async SQLAlchemy with aiosqlite. `db/database.py` creates the engine and `AsyncSessionLocal` factory. `db/integration.py` provides backward-compatible manager classes (e.g., `AsyncChatManager`, `AsyncFAQManager`) that wrap repository calls — these are used as module-level singletons imported by `orchestrator.py` and routers. Repositories in `db/repositories/` inherit from `BaseRepository` with generic CRUD.

**Telegram bots**: Run as subprocesses managed by `multi_bot_manager.py`. Each bot instance has independent config (LLM backend, TTS, prompts, system prompt). Bots with `auto_start=true` restart on app startup. Two Telegram frameworks: `python-telegram-bot` (legacy) and `aiogram` (new bots). In multi-instance mode, `BOT_INSTANCE_ID`, `BOT_INTERNAL_TOKEN`, and `ORCHESTRATOR_URL` env vars are passed to the subprocess. Config loading: manager pre-fetches config from DB and writes it to `/tmp/bot_config_{id}.json` (`BOT_CONFIG_FILE` env var); bot tries this file first (`load_config_from_file()`), then falls back to orchestrator API with retry logic (5 attempts, exponential backoff). `LLMRouter` in `telegram_bot/services/llm_router.py` routes LLM requests through the orchestrator chat API, auto-creates orchestrator DB sessions (mapping bot session IDs to real DB sessions via `_ensure_session()`), and uses the bot instance's `llm_backend` setting. `stream_renderer.py` handles both plain string chunks and OpenAI-format dicts.

**WhatsApp bots**: Run as subprocesses managed by `whatsapp_manager.py` (same pattern as Telegram's `multi_bot_manager.py`). Each instance has independent config (phone_number_id, access_token, LLM backend, TTS, system prompt). Bots with `auto_start=true` restart on app startup. Env vars passed to subprocess: `WA_INSTANCE_ID`, `WA_INTERNAL_TOKEN` (internal admin JWT). Bot module: `whatsapp_bot/` (runs as `python -m whatsapp_bot`). Logs: `logs/whatsapp_bot_{instance_id}.log`. DB model: `WhatsAppInstance` in `db/models.py`, repo: `db/repositories/whatsapp_instance.py`, manager: `AsyncWhatsAppInstanceManager` in `db/integration.py`. API: `app/routers/whatsapp.py` (10 endpoints: CRUD + start/stop/restart/status/logs). Migration: `scripts/migrate_whatsapp.py`. Admin UI: `WhatsAppView.vue`.

**Middleware** (`app/`): `cors_middleware.py` (CORS with configurable origins via `CORS_ORIGINS`), `rate_limiter.py` (slowapi, per-endpoint limits via `RATE_LIMIT_*` env vars), `security_headers.py` (X-Frame-Options, CSP, etc. via `SECURITY_HEADERS_ENABLED`). All registered in `orchestrator.py` startup.

**Two service layers**: Core AI services live at project root (`cloud_llm_service.py`, `vllm_llm_service.py`, `voice_clone_service.py`, `openvoice_service.py`, `piper_tts_service.py`, `stt_service.py`, `llm_service.py`). Orchestration services also at root: `service_manager.py`, `multi_bot_manager.py`, `whatsapp_manager.py`, `telegram_bot_service.py`, `system_monitor.py`, `tts_finetune_manager.py`, `model_manager.py`, `bridge_manager.py` (Claude Code CLI bridge), `xray_proxy_manager.py` (VLESS proxy for xray-core), `phone_service.py` (telephony). Domain-specific services live in `app/services/` (`amocrm_service.py`, `gsm_service.py`, `backup_service.py`, `sales_funnel.py`, `yoomoney_service.py`, `audio_pipeline.py`, `wiki_rag_service.py`).

**Cloud LLM routing**: `cloud_llm_service.py` (project root) has `CloudLLMService` with a factory pattern. OpenAI-compatible providers use `OpenAICompatibleProvider` automatically. Custom SDKs (Gemini) get their own provider class inheriting `BaseLLMProvider`. Provider types defined in `PROVIDER_TYPES` dict in `db/models.py`. The standalone `gemini` backend (`llm_service.py`) is deprecated — all cloud LLM is now routed via `CloudLLMService`. Legacy `LLM_BACKEND=gemini` is auto-migrated to `cloud:{provider_id}` on startup (auto-creates a Gemini provider from `GEMINI_API_KEY` env if needed). Migration script: `scripts/migrate_gemini_to_cloud.py`.

**Wiki RAG & Knowledge Base**: `app/services/wiki_rag_service.py` — tiered search over `wiki-pages/*.md`: (1) semantic embeddings via `app/services/embedding_provider.py` (Gemini, OpenAI-compatible, or local `sentence-transformers`) with cosine similarity, (2) BM25 Okapi with Russian/English stemming (`snowballstemmer`) as fallback. Embedding provider is auto-selected on startup: local (DEPLOYMENT_MODE=full + sentence-transformers installed) → cloud (from active LLM provider's API key) → BM25-only. Embeddings cached in `data/wiki_embeddings.json`. BM25 parameters: k1=1.5, b=0.75, MIN_SCORE=0.5. Title boost 4x. Initialized in `orchestrator.py` startup, stored in `ServiceContainer.wiki_rag_service`. `app/routers/wiki_rag.py` exposes admin API: stats, reload, search, reindex-embeddings, Knowledge Base document CRUD, and collection management. Documents tracked in `knowledge_documents` table (`KnowledgeDocument` model), managed via `AsyncKnowledgeDocManager` in `db/integration.py`. Existing `wiki-pages/*.md` auto-synced to DB on first request. Admin UI: Finetune → LLM → Cloud AI toggle (wiki stats, collections panel, knowledge base table, test search). Migrations: `scripts/migrate_knowledge_base.py`, `scripts/migrate_knowledge_collections.py`.

**Knowledge Collections**: Multiple knowledge base containers for grouping documents. `KnowledgeCollection` model (`knowledge_collections` table) with name, slug, description, enabled, `base_dir` (default `"wiki-pages"`) fields. Each `KnowledgeDocument` has an optional `collection_id` FK. A "Default" collection is auto-created and all existing docs are assigned to it. `KnowledgeCollectionRepository` in `db/repositories/knowledge_collection.py` (includes `get_by_slug()`), `AsyncKnowledgeCollectionManager` in `db/integration.py`. `WikiRAGService` maintains per-collection BM25 indexes (`CollectionIndex` dataclass, `_collection_indexes` dict) loaded at startup via `_load_collection_indexes()` in `orchestrator.py` — reads `base_dir` from collection config (not hardcoded). `retrieve()` and `search()` accept optional `collection_id`; `retrieve_multi(query, collection_ids, top_k, max_chars)` queries multiple collections independently, merges scored results, returns top_k. API: 6 collection endpoints (`GET/POST/GET/{id}/PUT/{id}/DELETE/{id}/POST/{id}/reload` under `/admin/wiki-rag/collections`), plus `collection_id` query/form param on existing document and search endpoints. Default collection cannot be deleted. Frontend: pill-shaped collection selector in Finetune → Cloud AI, inline create form, documents table filtered by selected collection.

**Per-Instance RAG Configuration**: `BotInstance`, `WidgetInstance`, `WhatsAppInstance` have `rag_mode` ("all" | "selected" | "none") and `knowledge_collection_ids` (JSON list of collection IDs) columns. Legacy `knowledge_collection_id` (single FK) still supported for backward compatibility. `ChatSession` has the same fields (nullable, for admin chat overrides). `app/routers/chat.py` resolves RAG config via `_resolve_rag_config()` returning `(mode, collection_ids: list[int])` — priority: request override → widget instance → telegram bot instance → whatsapp instance → session → default ("all", all enabled collections). `_inject_rag_context()` calls `retrieve()` for single collection, `retrieve_multi()` for multiple. `LLMOverrideConfig` accepts `rag_mode` + `knowledge_collection_ids` (list) + backward-compat `knowledge_collection_id` (single). Frontend: RAG mode dropdown with multi-select collection checkboxes in Widget/Telegram/WhatsApp edit forms. `ChatView` has RAG mode selector (persisted to localStorage). Migration: `scripts/migrate_rag_settings.py`, `scripts/migrate_multi_collection_rag.py`.

**amoCRM integration**: `app/services/amocrm_service.py` is a pure async HTTP client (no DB) with optional proxy support (`AMOCRM_PROXY` env var for Docker/VPN environments). Two API layers: standard v4 REST API (Bearer auth) for leads/contacts/pipelines/events/users, and Amojo API (HMAC-SHA1 signing) for chat history and messaging. `app/routers/amocrm.py` handles OAuth2 flow, token auto-refresh, and proxies API calls. Config/tokens stored via `AsyncAmoCRMManager` in `db/integration.py`. `AmoCRMConfig` model includes `amojo_base_url`, `amojo_scope_id`, `amojo_channel_secret` for Amojo inbox integration. Webhook at `POST /webhooks/amocrm`. For private amoCRM integrations, auth codes are obtained from the integration settings (not OAuth redirect). If Docker can't reach amoCRM (VPN on host), run `scripts/amocrm_proxy.py` on the host. Migration: `scripts/migrate_amocrm_inbox.py` (adds amojo columns).

**amoCRM Admin UI** (`CrmView.vue`): Tabbed layout (Settings / Kanban / Deals / Inbox). Settings tab: OAuth config + amojo credentials + CRM Dataset sync card (sync/clear buttons, document/section counts, last sync timestamp). Kanban tab (`CrmKanban.vue`): pipeline selector, horizontal columns per status, drag & drop via `vuedraggable@next` (SortableJS), auto-refresh 30s, resizable columns (drag handle, widths persisted to localStorage, reset button), horizontal scroll with drag-to-scroll. Columns can be collapsed/expanded (click ChevronLeft in header to collapse → 48px vertical strip with status dot, count badge, and vertical name; click to expand). Collapsed state persisted to localStorage (`crm-kanban-collapsed`). Resize handles hidden when adjacent column is collapsed. Deals tab (`CrmDeals.vue`): table with search/filters, detail modal with contacts + notes, create deal dialog. Pagination controls are in the toolbar (between search and Create button), not inside the table card. Inbox tab (`CrmInbox.vue`): unified inbox hub with two sub-tabs — "AI Chats" (default) and "amoCRM Inbox" (only visible if amojo configured). AI Chats sub-tab: shows all non-admin chat sessions (Telegram, Widget, WhatsApp) with source filter chips (All/Telegram/Widget/WhatsApp), session list with source icons, message viewing with markdown rendering (`marked` + `DOMPurify` + `.chat-markdown` CSS), and reply via `chatApi.streamMessage()`. Auto-refresh 15s for sessions, 10s for messages. amoCRM sub-tab renders `CrmInboxAmoCRM.vue` (extracted amojo messenger layout — contact list + message thread, resolves chat UUID from contact via `getContactChats()` API). API endpoints: `GET /admin/crm/leads/{id}`, `PATCH /admin/crm/leads/{id}`, `GET /admin/crm/leads/by-pipeline/{pipeline_id}`, `GET /admin/crm/events`, `GET /admin/crm/contacts/{id}/chats`, `GET /admin/crm/chats/{chat_id}/history`, `POST /admin/crm/chats/{chat_id}/messages`.

**CRM Dataset (Knowledge Base Sync)**: Fetches all amoCRM data (pipelines + leads + contacts + users) and syncs as enriched markdown documents into a dedicated RAG collection, making deals searchable by LLM. `app/services/crm_dataset_service.py` — pure functions: `build_pipeline_document()` generates per-pipeline markdown with enriched deal sections (lead ID, name, status, price with raw digits for BM25, contacts with phone/email, custom fields, responsible user name); `build_summary_document()` generates aggregate stats + recent deals with user names; `_extract_contact_info()` extracts phone/email from contact's `custom_fields_values`; `_normalize_phone()` strips formatting for BM25 matching (`"+7 (999) 123-45-67"` → `"79991234567"`); `_extract_lead_custom_fields()` extracts custom field pairs from leads; `format_price()` formats rubles with thousands separator (amoCRM returns rubles, not kopecks); `clean_crm_files()` cleans output dir (`data/crm-dataset/`). `app/services/amocrm_service.py` adds `get_all_leads_paginated()` (250/page until exhausted), `get_contacts_by_ids()` (batch-fetch contacts with phone/email, up to 50 IDs per request), `get_users()` (all account users → `{id: name}` mapping). Sync orchestration in `app/routers/amocrm.py`: after fetching leads, collects unique contact IDs → `get_contacts_by_ids()` → `contacts_map`, `get_users()` → `users_map` (both with graceful fallback), passes maps to document builders. API endpoints: `POST /admin/crm/dataset-sync` (full sync → auto-create "amocrm" collection with `base_dir="data/crm-dataset"` → reindex, response includes `contacts_enriched` and `users_resolved` counts), `GET /admin/crm/dataset-status` (sync state), `DELETE /admin/crm/dataset` (admin-only clear).

**amoCRM Redis Caching**: `app/routers/amocrm.py` caches pipeline and lead API responses in Redis via `db/redis_client.py` (`cache_get`/`cache_set`/`cache_delete_pattern`). Cache keys use `CacheKey` enum. TTL configured per entity type. Cache invalidated on webhook events and manual sync.

**GSM telephony**: `app/services/gsm_service.py` manages SIM7600E-H modem via AT commands over serial port (`/dev/ttyUSB2`). Auto-switches to mock mode when hardware is unavailable. `app/routers/gsm.py` exposes call/SMS management endpoints. Call and SMS logs stored via `GSMCallLogRepository` and `GSMSMSLogRepository` in `db/repositories/gsm.py`. Models: `GSMCallLog`, `GSMSMSLog` in `db/models.py`. Manager: `AsyncGSMManager` in `db/integration.py`. Migration: `scripts/migrate_gsm_tables.py`.

**Multi-user RBAC**: `User` model in `db/models.py` with roles: `guest` (read-only), `user` (own resources), `admin` (full access). `auth_manager.py` provides DB-backed auth with salted password hashing, JWT tokens with `user_id` and `jti` (token ID), and `require_not_guest` dependency for write endpoints. Resources with `owner_id` column (ChatSession, BotInstance, WidgetInstance, WhatsAppInstance, CloudLLMProvider, TTSPreset) are filtered by ownership for non-admin users. `UserRepository` in `db/repositories/user.py`, `AsyncUserManager` in `db/integration.py`. Profile/password endpoints in `app/routers/auth.py`. Migration: `scripts/migrate_users.py`, `scripts/migrate_user_ownership.py`. CLI management: `scripts/manage_users.py`.

**Session management & token revocation**: `UserSession` model in `db/models.py` tracks every login with `token_jti` (unique), `user_id`, `ip_address`, `user_agent`, `created_at`, `expires_at`, `revoked_at`. `UserSessionRepository` in `db/repositories/user_session.py` (create, get_by_jti with JOIN for is_active, revoke, cleanup). `AsyncUserSessionManager` in `db/integration.py`. `SessionCache` in `auth_manager.py` — in-memory `Dict[jti, user_id]` for fast validation; cache miss falls through to DB with `is_active` check. `get_current_user()` and `get_optional_user()` validate sessions on every request (tokens without `jti` are rejected). Revocation hooks: `set_role()`, `set_active(false)`, `update_password()` in `AsyncUserManager` auto-revoke all sessions. Session endpoints: `GET /admin/auth/sessions`, `DELETE /admin/auth/sessions/{jti}`. `POST /change-password` revokes all sessions and returns a new token. Background cleanup: hourly task in `orchestrator.py` deletes sessions expired >7 days. Migration: `alembic/versions/20260222_0001_add_user_sessions.py`.

**Sales & payments**: `app/routers/bot_sales.py` manages Telegram bot sales funnels (quiz, segments, agent prompts, follow-ups, testimonials, subscribers, broadcast). Subscriber list is enriched with user profile data (username, first_name) from `bot_user_profiles`. `POST /broadcast` sends messages to selected subscribers via Telegram Bot API (httpx). `app/services/sales_funnel.py` implements funnel logic with segment paths: `diy`, `basic`, `custom` (original bot), `qualified`, `unqualified`, `needs_analysis` (TZ generator bot). `app/routers/yoomoney_webhook.py` + `app/services/yoomoney_service.py` handle YooMoney payment callbacks. Migration: `scripts/migrate_sales_bot.py`, `scripts/migrate_add_payment_fields.py`. Seed scripts: `scripts/seed_tz_generator.py` (TZ bot), `scripts/seed_tz_widget.py` (TZ widget).

**Telegram Sales Bot** (`telegram_bot/`): Aiogram 3.x bot with sales funnel, FAQ, and AI chat. Key modules:
- `telegram_bot/sales/keyboards.py` — all inline keyboards (welcome, quiz, DIY, basic, custom, TZ quiz, FAQ, contact)
- `telegram_bot/sales/texts.py` — all message templates (Russian), FAQ answers dict, section intro texts
- `telegram_bot/handlers/sales/common.py` — reply keyboard handlers (Wiki, payment, GitHub, support, ask question) + FAQ callback handler with section navigation
- `telegram_bot/handlers/sales/welcome.py` — `/start`, welcome flow, quiz handlers
- `telegram_bot/config.py` — `TelegramSettings(BaseSettings)` with news repos, GitHub token, etc.
- `telegram_bot/services/llm_router.py` — routes LLM requests through orchestrator chat API
- FAQ is split into 3 sections: Product (`what_is`, `offline`, `security`, `vs_cloud`, `cloud_models`), Installation (`hardware`, `install`, `integrations`), Pricing & Support (`price`, `support`, `free_trial`). Callback data uses `faq:cat_*` for categories, `faq:back_*` for navigation, `faq:{key}` for answers. `FAQ_KEY_TO_SECTION` dict in `texts.py` maps answer keys to sections for back-navigation.
- Reply keyboard buttons are loaded from DB (`action_buttons` config) or fallback to `DEFAULT_ACTION_BUTTONS` in `keyboards.py`. Button text matching in handlers must match the `"{icon} {label}"` format from the DB config.

**WhatsApp Sales Bot** (`whatsapp_bot/sales/` + `whatsapp_bot/handlers/`): Full sales funnel ported from Telegram with WhatsApp interactive messages. Key modules:
- `whatsapp_bot/sales/texts.py` — message templates adapted for WhatsApp (`*bold*` not `**bold**`), 11 FAQ answers, section intros, quiz/DIY/basic/custom path texts, quote template
- `whatsapp_bot/sales/keyboards.py` — 35 keyboard builders using `_quick_reply()` (≤3 buttons, titles ≤20 chars) and `_list_message()` (≤10 sections, ≤10 rows) helpers. Naming: `*_buttons()` = quick-reply, `*_list()` = list message
- `whatsapp_bot/sales/database.py` — SQLite persistence (`data/wa_sales_{instance_id}.db`), `user_id TEXT PRIMARY KEY` (phone number), `funnel_state` column for free-text input state machine, tables: `users`, `events`, `custom_discovery`. Singleton via `get_sales_db()`
- `whatsapp_bot/handlers/interactive.py` — callback routing by `prefix:action` format: `sales:*` → `handlers/sales/router.py`, `faq:*` (full FAQ navigation), `tz:*` (placeholder), `nav:*` (generic). Helpers `_send_buttons()` / `_send_list()` extract payloads from keyboard dicts
- `whatsapp_bot/handlers/messages.py` — greeting detection (9 trigger words) sends welcome buttons; state-aware routing checks `funnel_state` for free-text input (`custom_step_1`, `diy_gpu_custom`) before falling through to LLM
- `whatsapp_bot/handlers/sales/` — handler package: `router.py` (central dispatcher for all `sales:*` actions), `welcome.py`, `quiz.py` (tech + infra → segment routing), `diy.py` (GPU audit, GitHub CTA), `basic.py` (value prop, demo, checkout, YooMoney payment link), `custom.py` (5-step discovery, quote calculation via `calculate_quote()`, "too expensive" alternatives)
- Segmentation logic imported directly from `telegram_bot.sales.segments` (`determine_segment()`, `GPU_AUDIT`, `calculate_quote()`, `INTEGRATION_PRICES`) — no duplication
- Custom step 3 (integrations): sequential single-select with "More"/"Done" buttons (WhatsApp lists are single-select, unlike Telegram's toggle keyboards)
- Payment: YooMoney link + contact info in text message (no Telegram Payments API equivalent)
- WhatsApp constraints: no URL buttons (URLs in body text), no message editing (new message per interaction), reply IDs use `prefix:action` convention (same as Telegram `callback_data`)
- FAQ sections identical to Telegram: Product (5 questions), Installation (3), Pricing & Support (3). Same `FAQ_KEY_TO_SECTION` mapping for back-navigation

**Backup/restore**: `app/routers/backup.py` + `app/services/backup_service.py` — export/import system configuration and data.

**Widget test chat**: Widget instances can be tested live from the admin panel. `app/routers/chat.py` accepts an optional `widget_instance_id` parameter on streaming endpoints, which overrides LLM/TTS settings to match the widget's config. Frontend in `WidgetView.vue` test tab. The embeddable widget (`web-widget/ai-chat-widget.js`) performs a runtime enabled check via `GET /widget/status` (public, no auth) — if the instance is disabled, the widget icon won't render on the site. When embedded in the admin panel, the widget auto-attaches JWT from `localStorage('admin_token')` for authenticated chat.

**Widget session persistence** (Replain-style): The widget preserves chat history across page navigations. Session ID is stored in both a cookie (`SameSite=None; Secure`, 30-day TTL) and `localStorage` (cookie-first, localStorage fallback). On page load, `preloadHistory()` fetches the session via `GET /widget/chat/session/{id}` (public, no auth, `source="widget"` only). The open/closed state is tracked in `sessionStorage` — if the chat was open before navigation, it auto-opens and renders history on the next page. `clearSession()` wipes cookie + localStorage + sessionStorage.

**Chat branching** (OpenWebUI-style): Non-destructive message editing and response regeneration. `ChatMessage` has `parent_id` (self-referential FK) and `is_active` (boolean) fields. Editing a message creates a new sibling branch; regenerating creates a new assistant child. Both user and assistant messages are editable — user edits trigger LLM regeneration, assistant edits save in-place without LLM call. Old versions preserved with `is_active=False`. `ChatRepository` methods: `edit_message()` (non-destructive), `branch_regenerate()`, `get_branch_tree()`, `get_sibling_info()`, `switch_branch()`, `get_active_messages()`, `start_new_branch()` (deactivates all active messages → next send creates fresh root). API endpoints: `GET /sessions/{id}/branches` (tree structure), `POST /sessions/{id}/branches/switch` (change active path), `POST /sessions/{id}/branches/new` (start fresh branch — keeps prompt + context files, zero message history). Frontend: `BranchTree.vue` + `BranchTreeNode.vue` — recursive tree panel with file-explorer-like UX (role icons, collapsible nodes via chevron toggles, branch count badges, indented assistant responses, visual depth capped at 8 levels). "New branch" button in chat header, Branch Tree panel, and per-message action toolbar. Messages with siblings show inline version navigation `< 1/3 >`. Chat export: Download button in header with Copy (markdown to clipboard), Export .md, Export .json. Input position toggleable between top/bottom (persisted to localStorage). Ctrl+Enter sends messages and saves edits. Action buttons placed in normal flow below message content (not absolute overlay) to prevent overflow on short messages. Smart auto-scroll: only scrolls during streaming if user is near bottom; always scrolls after completion. Focus returns to input after AI response. Migration: `scripts/migrate_chat_branches.py`.

**Chat markdown rendering**: Assistant and user messages render markdown via `marked` + `DOMPurify`. Custom `.chat-markdown` CSS in `main.css` styles headings, code blocks, lists, tables, blockquotes, links using HSL theme variables. User message code blocks get special overrides (`.bg-primary .chat-markdown`).

**Chat settings panel**: Slide-out panel from right side (not a modal), toggled via Settings2 button in chat header. Two tabs: Session Prompt (custom per-chat prompt) and Default Prompt (persona prompt view/edit/reset). File attachments managed via separate "Context Files" tab. Panel uses `flex-1` textarea to maximize editing space.

**Chat pinning**: Sessions support `pinned` boolean field. Pinned chats show Pin icon in sidebar and sorted to top. Toggle via hover action button in session list. Migration: `alembic/versions/20260216_0001_add_chat_pinned.py`.

**Chat session source filtering**: `GET /admin/chat/sessions` accepts `source` and `exclude_source` query params for filtering sessions by origin. Values: `admin`, `telegram`, `widget`, `whatsapp`. The `telegram` value maps to `telegram_bot` in DB transparently. `ChatView` (`/admin/#/chat`) uses `listSessions('admin')` to show only admin-created chats (grouped sessions UI was removed). CRM Inbox uses `listSessions(source, 'admin')` to show non-admin chats with source filtering. `list_sessions_grouped()` includes `whatsapp` key and normalizes `telegram_bot` → `telegram` for the frontend.

**Anti-tool-call prompt injection**: `_finalize_prompt()` in `app/routers/chat.py` appends `_NO_TOOLS_SUFFIX` to every system prompt before sending to LLM. Prevents Claude bridge from hallucinating fake tool calls (`filesystem read_file`, `function_calls`) as text, which caused chat responses to hang. Applied to all 4 chat endpoints (send, stream, edit, regenerate).

**Kanban/Tasks** (`app/routers/kanban.py`): Project task management board with Gantt roadmap. `KanbanTask` model with status (`todo`/`in_progress`/`review`/`done`), assignee, dates, tags (JSON), `is_private`, `position` for drag-reorder. `KanbanTaskDependency` (blocker → dependent), `KanbanChecklistItem` (per-task checklists). `KanbanTaskStatus` enum. 10 endpoints: CRUD, reorder, dependency management, checklist items. Frontend: `KanbanView.vue` with `KanbanBoard.vue` (drag & drop columns), `KanbanCard.vue`, `KanbanCardDetail.vue` (side panel), `KanbanTaskForm.vue`, `KanbanRoadmap.vue` (Gantt-style timeline), `KanbanStatusBadge.vue`. Migration: `scripts/migrate_kanban.py`.

**Claude Code Web UI** (`app/routers/claude_code.py`): WebSocket-based terminal for Claude Code CLI. WebSocket at `/admin/claude-code/ws?token=<jwt>` streams structured events (text_delta, thinking_delta, tool_use_start, tool_result, turn_complete). REST endpoints for session management (list/get/delete). `ClaudeCodeSession` model tracks sessions in DB. One active WebSocket per user. Admin-only. Frontend: `useClaudeCode` composable.

**Chat session sharing**: `ChatSessionShare` model (`chat_session_shares` table) enables sharing chat sessions between users. `ChatShareDialog.vue` component in frontend.

**Other routers**: `audit.py` (audit log viewer/export/cleanup), `usage.py` (usage statistics/analytics), `legal.py` (legal compliance, migration: `scripts/migrate_legal_compliance.py`), `wiki_rag.py` (Wiki RAG stats/search/reload + Knowledge Base CRUD + collections management), `github_webhook.py` (GitHub CI/CD webhook handler).

## Code Patterns

**Adding a new API endpoint:**
1. Create or edit router in `app/routers/`
2. Use `ServiceContainer` from `app/dependencies.py` for DI
3. Add router to imports and `__all__` in `app/routers/__init__.py`
4. Register router in `orchestrator.py` with `app.include_router()`

**Adding a new cloud LLM provider type:**
1. Add entry to `PROVIDER_TYPES` dict in `db/models.py`
2. If OpenAI-compatible, it works automatically via `OpenAICompatibleProvider`
3. For custom SDK, create provider class inheriting `BaseLLMProvider` in `cloud_llm_service.py`
4. Register in `CloudLLMService.PROVIDER_CLASSES`

**Adding a new secretary persona:**
1. Add entry to `SECRETARY_PERSONAS` dict in `vllm_llm_service.py`

**RBAC auth guards** (3 levels in `auth_manager.py`):
- `Depends(get_current_user)` — any authenticated user (read endpoints)
- `Depends(require_not_guest)` — user/web + admin only (write endpoints)
- `Depends(require_admin)` — admin only (vLLM, GSM, backups, models)
- Data isolation: `owner_id = None if user.role == "admin" else user.id` in routers

**4 roles** (`VALID_ROLES` in `db/repositories/user.py`):
- `admin` — full access, sees all resources
- `user` — read + write own resources, full admin panel
- `web` — same backend access as `user`, but frontend hides: Dashboard, Services, TTS, Monitoring, Audit, Usage (via `excludeRoles`). Models hidden via `minRole: 'admin'`. Landing page: `/chat`
- `guest` — read-only (demo access)
- Frontend role exclusion: routes/nav items support `excludeRoles: ['web']` meta for per-role hiding
- CLI: `python scripts/manage_users.py create <user> <pass> --role web`

**Adding i18n translations:**
1. Edit `admin/src/plugins/i18n.ts` — add keys to all three message objects: `ru`, `en`, and `kk` (Kazakh)

**Database migrations:** Two systems — **Alembic** (preferred for new work, `alembic revision --autogenerate -m "desc"`) and legacy manual scripts in `scripts/migrate_*.py`. New tables auto-created by `Base.metadata.create_all` on startup; schema changes to existing tables need migration scripts.

**API URL patterns:**
- `GET/POST /admin/{resource}` — List/create
- `GET/PUT/DELETE /admin/{resource}/{id}` — CRUD
- `POST /admin/{resource}/{id}/action` — Actions (start, stop, test)
- `GET /admin/{resource}/stream` — SSE endpoints
- `POST /webhooks/{service}` — External webhooks (amocrm, yoomoney, github)
- `POST /v1/chat/completions`, `POST /v1/audio/speech`, `GET /v1/models` — OpenAI-compatible

## Key Environment Variables

```bash
LLM_BACKEND=vllm                    # "vllm" or "cloud:{provider_id}" (legacy "gemini" auto-migrates)
VLLM_API_URL=http://localhost:11434 # Auto-normalized: trailing /v1 is stripped
SECRETARY_PERSONA=anna             # "anna" or "marina"
ORCHESTRATOR_PORT=8002
ADMIN_JWT_SECRET=...                # Auto-generated if empty
ADMIN_USERNAME=admin                # Legacy fallback when users table is empty
ADMIN_PASSWORD_HASH=...             # Legacy fallback (SHA-256 of password)
REDIS_URL=redis://localhost:6379/0  # Optional, graceful fallback if unavailable
DEPLOYMENT_MODE=full                # "full", "cloud", or "local" — controls service loading
DEV_MODE=1                          # Makes backend proxy to Vite dev server (:5173)
AMOCRM_PROXY=http://host:8888      # Optional, for Docker/VPN environments
RATE_LIMIT_ENABLED=true             # Global rate limiting (slowapi)
RATE_LIMIT_DEFAULT=60/minute        # Default rate limit for all endpoints
```

## Codebase Conventions

- **Python 3.11+**, line length 100, double quotes (ruff format)
- **Cyrillic strings are normal** — RUF001/002/003 disabled; Russian is used in UI text, logging, persona prompts
- **FastAPI Depends pattern** — `B008` (function-call-in-default-argument) is disabled for this reason
- **Optional imports** — Services like vLLM and OpenVoice use try/except at module level with `*_AVAILABLE` flags
- **SQLAlchemy mapped_column style** — Models use `Mapped[T]` with `mapped_column()` (declarative 2.0)
- **Repository pattern** — `BaseRepository(Generic[T])` provides get_by_id, get_all, create, update, delete. Domain repos extend with custom queries.
- **Admin panel** — See **Frontend Architecture** section below for full details (routing, stores, API layer, demo mode, components).
- **mypy strict scope** — Only `db/`, `auth_manager.py`, `service_manager.py` require typed defs; other modules are relaxed. mypy is soft in CI (`|| true`).
- **Pre-commit hooks** — ruff lint+format, mypy (core only), eslint, hadolint (Docker), plus standard checks (trailing whitespace, large files ≤1MB, private key detection, merge conflicts). See `.pre-commit-config.yaml`.

## Frontend Architecture

**Tech stack**: Vue 3 + Composition API + TypeScript, Vite, Pinia (persisted state), Vue Router (hash history), TanStack Vue Query, vue-i18n (ru/en), TailwindCSS + radix-vue, lucide-vue-next, chart.js/vue-chartjs, marked + DOMPurify (markdown rendering). Path alias `@` → `admin/src/`.

**Routing** (`admin/src/router.ts`): Single flat router with `createWebHashHistory`. Routes use rich `meta` fields for access control:
- `meta.public` — bypass auth guard (only `/login`)
- `meta.localOnly` — hidden in `DEPLOYMENT_MODE=cloud` (Dashboard, Services, TTS, Monitoring, Models, GSM)
- `meta.excludeRoles` — per-role hiding (e.g. `['web']` hides Dashboard, Services, TTS, Monitoring, Audit, Usage from `web` role)
- `meta.minRole` — minimum role required (`'user'` or `'admin'`)
- Navigation guard redirects unauthorized users to `/chat` or `/login`

**Stores** (`admin/src/stores/`): Pinia stores re-exported from `stores/index.ts`. Key store: `auth.ts` holds JWT token, decoded user (id, username, role), `deploymentMode` (`full|cloud|local`). Exposes `isAdmin`, `isWeb`, `isCloudMode`, `hasPermission()`, `can()`. UI state stores: `toast`, `confirm`, `search`, `theme` — decouple trigger sites from rendering.

**API layer** (`admin/src/api/`): `client.ts` provides `api.get/post/put/delete/upload` + `createSSE()` helper (auto-injects JWT from `localStorage('admin_token')`). Domain-specific files (`chat.ts`, `telegram.ts`, `llm.ts`, etc.) build on it. All re-exported from `api/index.ts`. In demo mode, `client.ts` awaits `demoReady` promise before any API call.

**Demo mode** (`admin/src/api/demo/`): Activated via `VITE_DEMO_MODE=true`. `setupDemoInterceptor()` monkey-patches `window.fetch` globally to intercept all `/admin/`, `/v1/`, `/health` requests. Routes through `matchDemoRoute()` — regex pattern matcher across 22 domain route files (each exports `DemoRoute[]`). Handlers return JSON data, `'__BLOB__'` (minimal WAV audio), or `'__STREAM__'` (SSE chunks). Adds 100–300ms artificial delay. Config: `VITE_DEMO_ROLE`, `VITE_DEMO_DEPLOYMENT_MODE` env vars.

**Components** (`admin/src/components/`): Flat structure, no `ui/` subdirectory. UI state components (`ConfirmDialog`, `SearchPalette`, `ToastContainer`, `ThemeToggle`) driven by dedicated Pinia stores. `BranchTree.vue` / `BranchTreeNode.vue` for chat branching. `CrmInboxAmoCRM.vue` — extracted amojo messenger (used as sub-tab in `CrmInbox.vue`). `charts/` for Chart.js wrappers.

**Composables** (`admin/src/composables/`): `useSSE`, `useResponsive`, `useExportImport`, `useSidebarCollapse`, `useResizablePanel` (mouse+touch drag-resize), `useClaudeCode`, etc.

**i18n** (`admin/src/plugins/i18n.ts`): Single file with `ru`, `en`, and `kk` (Kazakh) message objects. Add keys to all three when adding translations.

**Vite base path**: Production: `/admin/` (served by FastAPI). Demo builds and server deploy: `/` (overridden via `VITE_BASE_PATH` env or `.env.production.local`). Demo mode: `npm run build -- --mode demo` loads `.env.demo`.

## Server Deployment

The production server runs at `admin.ai-sekretar24.ru`. Single repo at `/opt/ai-secretary/` serves as both **development workspace** and **production runtime**.

### Server Architecture

```
/opt/ai-secretary/                  ← single Git repo (dev + production)
    ├── .env                        ← production config (DEPLOYMENT_MODE=cloud, etc.)
    ├── apply_patches.py            ← cloud-mode patches (makes GPU imports optional)
    ├── deploy.sh                   ← auto-deploy script
    ├── webhook_server.py           ← GitHub webhook for demo auto-deploy
    ├── admin/.env.production.local ← VITE_BASE_PATH=/
    └── venv/                       ← Python 3.12 virtualenv

Systemd services:
    ai-secretary.service            ← orchestrator (port 8002)
    demo-webhook.service            ← webhook listener (port 9876)

Static sites:
    /var/www/admin-ai-sekretar24/   ← admin panel (rsync from admin/dist/)
    /var/www/ai-sekretar24/         ← landing page (static)
    /var/www/demo-ai-sekretar24/    ← demo builds (full/ + cloud/ subdirs)
```

**Local-only files** (not in git, backed up by deploy.sh): `.env`, `apply_patches.py`, `deploy.sh`, `webhook_server.py`, `admin/.env.production.local`

### Development Workflow (on server)

```bash
cd /opt/ai-secretary
git pull origin main                         # sync with remote
git checkout -b server/my-feature            # create feature branch
# ... make changes ...
ruff check . && cd admin && npm run lint:check && npm run build  # verify
git add <files> && git commit -m "feat: ..."
git push -u origin server/my-feature
gh pr create --title "..." --body "..."
gh pr checks <N> --watch                     # wait for CI
gh pr merge <N> --merge                      # merge
git checkout main && git pull                # sync
bash deploy.sh                               # deploy to production
```

### deploy.sh Steps

1. Backs up local-only files to `/tmp/`
2. `git reset --hard origin/main` (syncs to latest main)
3. Restores local-only files
4. `python3 apply_patches.py` (cloud-mode: makes TTS/STT/GPU imports optional)
5. `pip install -r services/bridge/requirements.txt`
6. Cleans `admin/dist/` and `node_modules/.vite` (prevents stale demo artifacts)
7. `VITE_DEMO_MODE= npm run build` (explicit production mode)
8. Verifies no `setupDemoInterceptor` in built JS (aborts if found)
9. `rsync admin/dist/ → /var/www/admin-ai-sekretar24/`
10. `systemctl restart ai-secretary`
11. Health check: `curl http://localhost:8002/health`

### Demo Sites

Fully offline demo builds of the admin panel — no backend needed, mock data only.

```bash
bash /root/deploy-demo.sh       # pull → build both demos → deploy to /var/www/demo-ai-sekretar24/
```

Both demos live on `demo.ai-sekretar24.ru` with path-based routing. Single script `deploy-demo.sh` builds and deploys both.

**Full demo** (`/full/`) — admin role, all features:
- **URL**: https://demo.ai-sekretar24.ru/full/ (auto-login as admin)
- **Build**: `npm run build -- --mode demo` (loads `.env.demo`: `VITE_DEMO_ROLE=admin`, `VITE_DEMO_DEPLOYMENT_MODE=full`)
- **All tabs visible**

**Cloud demo** (`/cloud/`) — web role, customer-facing:
- **URL**: https://demo.ai-sekretar24.ru/cloud/ (auto-login as web)
- **Build**: `npm run build -- --mode demo-web` (loads `.env.demo-web`: `VITE_DEMO_ROLE=web`, `VITE_DEMO_DEPLOYMENT_MODE=cloud`)
- **Hidden tabs**: Dashboard, Services, TTS, Monitoring, Models, GSM

**Auto-deploy**: GitHub webhook → `demo-webhook.service` (port 9876) → `/root/deploy-demo.sh` on push to main

**Landing page**: https://ai-sekretar24.ru — static site in `/var/www/ai-sekretar24/` (not a demo)

**Shared architecture:**
- **How it works**: monkey-patches `window.fetch` in `demo/index.ts` to intercept all API calls with mock data
- **SSE**: polling (3s interval) instead of real EventSource
- **Mock data**: 22 files in `admin/src/api/demo/`, in-memory store for session-persistent mutations
- **Role config**: `VITE_DEMO_ROLE` and `VITE_DEMO_DEPLOYMENT_MODE` env vars control role in JWT and deployment mode mock
- **Auto-login**: inline `<script>` in `index.html` injects JWT with correct role before Vue app loads
- **Nginx**: path-based routing (`/full/`, `/cloud/`), root `/` redirects to `/full/`

## Parallel Development (Two Claude Code Instances)

This project is developed simultaneously from two machines running Claude Code:
- **local** — dev workstation with GPU (RTX 3060), hardware access, full stack
- **server** — cloud VPS at `/opt/ai-secretary/`, no GPU, cloud LLM only, production-facing

### Environment Detection

Each machine identifies itself via per-machine memory at `~/.claude/projects/.../memory/MEMORY.md`. The memory file MUST contain a `## Machine Role` section with `local` or `server`. **Check your machine role before any git or file operations.**

### Git Workflow Rules

1. **Never push directly to `main`** — always create a feature branch and PR
2. **Branch prefixes by machine:**
   - `local/*` — branches created on local dev machine
   - `server/*` — branches created on server
   - `docs/*`, `chore/*`, `fix/*`, `feat/*` — shared prefixes are OK, but add machine suffix if both might work on similar tasks (e.g., `feat/whatsapp-local`, `feat/whatsapp-server`)
3. **Always `git pull` before starting work** — stale branches cause merge conflicts
4. **Do not amend or force-push commits made by the other instance**
5. **If you see uncommitted changes you didn't make** — another instance may have been working. Ask the user before discarding

### File Ownership Zones

To minimize merge conflicts, each machine has primary ownership of certain areas:

**Local machine primary:**
- Hardware services: `voice_clone_service.py`, `openvoice_service.py`, `piper_tts_service.py`, `stt_service.py`, `vllm_llm_service.py`
- GPU/hardware: `system_monitor.py`, `app/services/gsm_service.py`, `app/routers/gsm.py`, `app/routers/services.py`, `app/routers/monitor.py`
- Fine-tuning: `tts_finetune_manager.py`, `finetune_manager.py`
- Voice samples: `Анна/`, `Марина/`
- Start scripts: `start_gpu.sh`, `start_cpu.sh`, `start_qwen.sh`

**Server primary:**
- Cloud services: `cloud_llm_service.py`, `xray_proxy_manager.py`
- Deployment: `docker-compose*.yml`, `Dockerfile`, `scripts/docker-entrypoint.sh`
- Bot operations: `whatsapp_manager.py`, `multi_bot_manager.py` (runtime config, not structure)
- Production data: `data/`, `logs/`

**Shared (both can edit, but coordinate via branches):**
- `orchestrator.py`, `app/routers/`, `db/`, `admin/` — use feature branches, never edit on main
- `CLAUDE.md` — either machine can update, but pull first
- Migration scripts — create new files only, never modify existing migrations

### Coordination Protocol

- Before starting a multi-file change, check `git status` and `git log --oneline -5` to see if the other instance has recent work
- If working on overlapping areas, create the branch immediately and push it — this signals to the other instance that the area is being worked on
- Prefer small, focused PRs over large sweeping changes — reduces conflict surface

## Known Issues

1. **Vosk model required** — Download to `models/vosk/` for STT
2. **XTTS requires CC >= 7.0** — RTX 3060+; use OpenVoice for older GPUs
3. **GPU memory** — vLLM 50% (~6GB) + XTTS ~5GB must fit within 12GB
4. **OpenWebUI Docker** — Use `172.17.0.1` not `localhost` for API URL
5. **Docker + vLLM** — First run needs `docker pull vllm/vllm-openai:latest` (~9GB)
6. **xray-core for VLESS** — Included in Docker image; for local dev, download to `./bin/xray`
7. **VLESS proxy vs localhost services** — `GeminiProvider` sets `HTTP_PROXY`/`HTTPS_PROXY` globally for xray; this breaks `httpx.Client` calls to localhost (bridge, etc.). Fix: `OpenAICompatibleProvider` sets `NO_PROXY=127.0.0.1,localhost` for `claude_bridge` type; `bridge_manager.py` strips proxy env vars from subprocess environment
8. **Claude bridge timeouts** — Claude CLI has 7-30s warmup + processing time. Complex questions with RAG context can exceed 60s before first token. `OpenAICompatibleProvider` uses `read=300s` timeout for `claude_bridge` (vs 60s default). Default `max_tokens` raised to 4096 for bridge (vs 512). Bridge itself allows 600s per-chunk (`STREAM_TIMEOUT`), 300s for sync (`CLI_TIMEOUT`)

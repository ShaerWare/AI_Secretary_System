# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Secretary System — virtual secretary with voice cloning (XTTS v2, OpenVoice), pre-trained voices (Piper), local LLM (vLLM + Qwen/Llama/DeepSeek), cloud LLM fallback (Gemini, Kimi, OpenAI, Claude, DeepSeek, OpenRouter), and Claude Code CLI bridge. Features GSM telephony (SIM7600E-H), amoCRM integration (OAuth2, contacts, leads, pipelines, sync), Vue 3 PWA admin panel, i18n (ru/en), multi-instance Telegram bots with sales/payments, multi-instance WhatsApp bots (Cloud API), website chat widgets, and LoRA fine-tuning.

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

```bash
python scripts/migrate_json_to_db.py         # Initial JSON → SQLite migration
python scripts/migrate_to_instances.py       # Multi-instance bot/widget architecture
python scripts/migrate_users.py              # Create users table, seed admin + demo
python scripts/migrate_user_ownership.py     # Add owner_id to resource tables
python scripts/migrate_persona_rename.py     # Persona name migration (Гуля→Анна, Лидия→Марина)
python scripts/migrate_gsm_tables.py         # GSM call/SMS log tables
python scripts/migrate_amocrm.py             # amoCRM config tables
python scripts/migrate_sales_bot.py          # Sales funnel tables
python scripts/migrate_add_payment_fields.py # Payment fields for sales
python scripts/migrate_legal_compliance.py   # Legal compliance tables
python scripts/migrate_gemini_to_cloud.py    # Migrate standalone gemini backend to cloud provider
python scripts/migrate_knowledge_base.py     # Knowledge base documents table (wiki-pages/ tracking)
python scripts/migrate_widget_placeholder_style.py  # Widget placeholder style migration
python scripts/migrate_rate_limit.py             # Per-instance rate limiting for bots/widgets
python scripts/migrate_whatsapp.py               # WhatsApp bot instances table
python scripts/migrate_chat_branches.py          # Chat message branching (parent_id, is_active)
python scripts/seed_tz_generator.py          # Seed TZ generator bot data
python scripts/seed_tz_widget.py             # Seed TZ widget data
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
5. **Auth/JWT** — `ADMIN_JWT_SECRET` is auto-generated on startup; restarting the service invalidates all existing tokens
6. **Application logic** — only investigate after ruling out 1–5

**Never blame browser cache or user error** without first checking server-side build artifacts and config.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  Orchestrator (port 8002)                     │
│  orchestrator.py + app/routers/ (21 routers, ~372 endpoints) │
│  ┌────────────────────────────────────────────────────────┐  │
│  │        Vue 3 Admin Panel (20 views, PWA)                │  │
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

Frontend: `auth.ts` store fetches deployment mode via `GET /admin/deployment-mode`, exposes `isCloudMode` computed. Nav items and routes with `localOnly: true` are hidden/guarded in cloud mode (Dashboard, Services, TTS, Monitoring, Models, Finetune, GSM). Cloud users redirect to `/chat`.

### Key Architectural Decisions

**Global state in orchestrator.py** (~3650 lines, ~109 endpoints): This is the FastAPI entry point. It initializes all services as module-level globals, populates the `ServiceContainer`, and includes all routers. Legacy endpoints (OpenAI-compatible `/v1/*`) still live here alongside the modular router system.

**ServiceContainer (`app/dependencies.py`)**: Singleton holding references to all initialized services (TTS, LLM, STT, GSM, Wiki RAG, streaming TTS manager, voice config). Routers get services via FastAPI `Depends` (`get_llm_service()`, `get_voice_service()`, `get_piper_service()`, `get_stt_service()`, `get_gsm_service()`, `get_streaming_tts_manager()`, `get_voice_config()`). Populated during app startup in `orchestrator.py`.

**Middleware stack** (`app/`): Three custom middlewares applied in `orchestrator.py`:
- `DynamicCORSMiddleware` (`app/cors_middleware.py`) — Combines static `CORS_ORIGINS` env with `allowed_domains` from widget instances in DB. Widget domains cached with 60s TTL, auto-refreshed on requests. Cache invalidated on widget CRUD via `get_cors_middleware().invalidate_cache()`.
- `SecurityHeadersMiddleware` (`app/security_headers.py`) — Adds `X-Content-Type-Options: nosniff`, `X-Frame-Options` (configurable via `X_FRAME_OPTIONS` env, default `DENY`), `X-XSS-Protection`, `Referrer-Policy`, `Permissions-Policy`. Removes `server` header. Controlled by `SECURITY_HEADERS_ENABLED` env (default: true).
- **Rate limiter** (`app/rate_limiter.py`) — Global rate limiting via `slowapi`. IP detection reads `X-Forwarded-For`/`X-Real-IP` for reverse proxy awareness. Per-endpoint limits: `RATE_LIMIT_AUTH` (10/min), `RATE_LIMIT_CHAT` (30/min), `RATE_LIMIT_TTS` (20/min), `RATE_LIMIT_STT` (20/min). Global default: `RATE_LIMIT_DEFAULT` (60/min). Decorator: `@limiter.limit(RATE_LIMIT_CHAT)`. Controlled by `RATE_LIMIT_ENABLED` env (default: true).

**Database layer** (`db/`): Async SQLAlchemy with aiosqlite (`sqlite+aiosqlite:///data/secretary.db`). `db/database.py` creates the engine (`StaticPool` for SQLite) and `AsyncSessionLocal` factory. `db/integration.py` provides 15 backward-compatible manager classes as module-level singletons: `DatabaseManager`, `AsyncChatManager`, `AsyncFAQManager`, `AsyncPresetManager`, `AsyncConfigManager`, `AsyncTelegramSessionManager`, `AsyncBotInstanceManager`, `AsyncWidgetInstanceManager`, `AsyncWhatsAppInstanceManager`, `AsyncCloudProviderManager`, `AsyncPaymentManager`, `AsyncAmoCRMManager`, `AsyncGSMManager`, `AsyncUserManager`, `AsyncKnowledgeDocManager`. Repositories in `db/repositories/` (31 files) inherit from `BaseRepository` with generic CRUD. 36 SQLAlchemy models in `db/models.py` using declarative 2.0 style.

**Telegram bots**: Run as subprocesses managed by `multi_bot_manager.py`. Each bot instance has independent config (LLM backend, TTS, prompts, system prompt). Bots with `auto_start=true` restart on app startup. Two Telegram frameworks: `python-telegram-bot` (legacy) and `aiogram` (new bots). In multi-instance mode, `BOT_INSTANCE_ID`, `BOT_INTERNAL_TOKEN`, and `ORCHESTRATOR_URL` env vars are passed to the subprocess. Config loading: manager pre-fetches config from DB and writes it to `/tmp/bot_config_{id}.json` (`BOT_CONFIG_FILE` env var); bot tries this file first (`load_config_from_file()`), then falls back to orchestrator API with retry logic (5 attempts, exponential backoff). `LLMRouter` in `telegram_bot/services/llm_router.py` routes LLM requests through the orchestrator chat API, auto-creates orchestrator DB sessions (mapping bot session IDs to real DB sessions via `_ensure_session()`), and uses the bot instance's `llm_backend` setting. `stream_renderer.py` handles both plain string chunks and OpenAI-format dicts.

**WhatsApp bots**: Run as subprocesses managed by `whatsapp_manager.py` (same pattern as Telegram's `multi_bot_manager.py`). Each instance has independent config (phone_number_id, access_token, LLM backend, TTS, system prompt). Bots with `auto_start=true` restart on app startup. Env vars passed to subprocess: `WA_INSTANCE_ID`, `WA_INTERNAL_TOKEN` (internal admin JWT). Bot module: `whatsapp_bot/` (runs as `python -m whatsapp_bot`). Logs: `logs/whatsapp_bot_{instance_id}.log`. DB model: `WhatsAppInstance` in `db/models.py`, repo: `db/repositories/whatsapp_instance.py`, manager: `AsyncWhatsAppInstanceManager` in `db/integration.py`. API: `app/routers/whatsapp.py` (10 endpoints: CRUD + start/stop/restart/status/logs). Migration: `scripts/migrate_whatsapp.py`. Admin UI: `WhatsAppView.vue`.

**Two service layers**: Core AI services live at project root (`cloud_llm_service.py`, `vllm_llm_service.py`, `voice_clone_service.py`, `openvoice_service.py`, `piper_tts_service.py`, `stt_service.py`, `llm_service.py`). Orchestration services also at root: `service_manager.py`, `multi_bot_manager.py`, `whatsapp_manager.py`, `telegram_bot_service.py`, `system_monitor.py`, `tts_finetune_manager.py`, `model_manager.py`, `bridge_manager.py` (Claude Code CLI bridge), `xray_proxy_manager.py` (VLESS proxy for xray-core), `phone_service.py` (telephony). Domain-specific services live in `app/services/` (`amocrm_service.py`, `gsm_service.py`, `backup_service.py`, `sales_funnel.py`, `yoomoney_service.py`, `audio_pipeline.py`, `wiki_rag_service.py`, `embedding_provider.py`).

**Bridge service** (`services/bridge/`): OpenAI-compatible proxy for multi-provider LLM access (Claude, Gemini, GPT). Runs as a separate FastAPI app managed by `bridge_manager.py`. Has its own provider abstraction (`providers/base.py` → `claude/`, `gemini/`, `gpt/`), middleware (auth, logging, rate limiting), and utils (caching, retry, token counting, streaming). Endpoints: `/v1/chat/completions` (streaming), `/v1/models`, file upload. `STREAM_TIMEOUT=600s`, `CLI_TIMEOUT=300s`.

**Landing page** (`landing/`): Static marketing site (`index.html`, `favicon.svg`, `sw.js`) with Matrix rain canvas animation, responsive design, JSON-LD schema, ru/en language switcher. No backend API calls. Deployed to `/var/www/ai-sekretar24/`.

**Cloud LLM routing**: `cloud_llm_service.py` (project root) has `CloudLLMService` with a factory pattern. OpenAI-compatible providers use `OpenAICompatibleProvider` automatically. Custom SDKs (Gemini) get their own provider class inheriting `BaseLLMProvider`. Provider types defined in `PROVIDER_TYPES` dict in `db/models.py`. The standalone `gemini` backend (`llm_service.py`) is deprecated — all cloud LLM is now routed via `CloudLLMService`. Legacy `LLM_BACKEND=gemini` is auto-migrated to `cloud:{provider_id}` on startup (auto-creates a Gemini provider from `GEMINI_API_KEY` env if needed). Migration script: `scripts/migrate_gemini_to_cloud.py`.

**Wiki RAG & Knowledge Base**: `app/services/wiki_rag_service.py` — tiered search over `wiki-pages/*.md`: (1) semantic embeddings via `app/services/embedding_provider.py` (Gemini, OpenAI-compatible, or local `sentence-transformers`) with cosine similarity, (2) BM25 Okapi with Russian/English stemming (`snowballstemmer`) as fallback. Embedding provider is auto-selected on startup: local (DEPLOYMENT_MODE=full + sentence-transformers installed) → cloud (from active LLM provider's API key) → BM25-only. Embeddings cached in `data/wiki_embeddings.json`. BM25 parameters: k1=1.5, b=0.75, MIN_SCORE=0.5. Title boost 4x. Initialized in `orchestrator.py` startup, stored in `ServiceContainer.wiki_rag_service`. `app/routers/wiki_rag.py` exposes admin API: stats, reload, search, reindex-embeddings, and Knowledge Base document CRUD (upload/edit/delete `.md`/`.txt` files). Documents tracked in `knowledge_documents` table (`KnowledgeDocument` model), managed via `AsyncKnowledgeDocManager` in `db/integration.py`. Existing `wiki-pages/*.md` auto-synced to DB on first request. Admin UI: Finetune → LLM → Cloud AI toggle (wiki stats, knowledge base table, test search). Migration: `scripts/migrate_knowledge_base.py`.

**amoCRM integration**: `app/services/amocrm_service.py` is a pure async HTTP client (no DB) with optional proxy support (`AMOCRM_PROXY` env var for Docker/VPN environments). `app/routers/amocrm.py` handles OAuth2 flow, token auto-refresh, and proxies API calls. Config/tokens stored via `AsyncAmoCRMManager` in `db/integration.py`. Webhook at `POST /webhooks/amocrm`. For private amoCRM integrations, auth codes are obtained from the integration settings (not OAuth redirect). If Docker can't reach amoCRM (VPN on host), run `scripts/amocrm_proxy.py` on the host.

**GSM telephony**: `app/services/gsm_service.py` manages SIM7600E-H modem via AT commands over serial port (`/dev/ttyUSB2`). Auto-switches to mock mode when hardware is unavailable. `app/routers/gsm.py` exposes call/SMS management endpoints. Call and SMS logs stored via `GSMCallLogRepository` and `GSMSMSLogRepository` in `db/repositories/gsm.py`. Models: `GSMCallLog`, `GSMSMSLog` in `db/models.py`. Manager: `AsyncGSMManager` in `db/integration.py`. Migration: `scripts/migrate_gsm_tables.py`.

**Multi-user RBAC**: `User` model in `db/models.py` with roles: `guest` (read-only), `user` (own resources), `admin` (full access). `auth_manager.py` provides DB-backed auth with salted password hashing, JWT tokens with `user_id`, and `require_not_guest` dependency for write endpoints. Resources with `owner_id` column (ChatSession, BotInstance, WidgetInstance, WhatsAppInstance, CloudLLMProvider, TTSPreset) are filtered by ownership for non-admin users. `UserRepository` in `db/repositories/user.py`, `AsyncUserManager` in `db/integration.py`. Profile/password endpoints in `app/routers/auth.py`. Migration: `scripts/migrate_users.py`, `scripts/migrate_user_ownership.py`. CLI management: `scripts/manage_users.py`.

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

**Widget test chat**: Widget instances can be tested live from the admin panel. `app/routers/chat.py` accepts an optional `widget_instance_id` parameter on streaming endpoints, which overrides LLM/TTS settings to match the widget's config. Frontend in `WidgetView.vue` test tab. The embeddable widget (`web-widget/ai-chat-widget.js`) performs a runtime enabled check via `GET /widget/status` (public, no auth) — if the instance is disabled, the widget icon won't render on the site. When embedded in the admin panel, the widget auto-attaches JWT from `localStorage('admin_token')` for authenticated chat. Dynamic widget script served via `GET /widget.js?instance=widget_id`.

**Public widget endpoints** (no authentication, in `orchestrator.py`): 3 endpoints for embedded widget chat without admin JWT:
- `POST /widget/chat/session` — Create widget session (body: `source_id`)
- `GET /widget/chat/session/{id}` — Retrieve session with message history (source="widget" only)
- `POST /widget/chat/session/{id}/stream` — Send message & get SSE streaming response (supports per-instance rate limiting via `rate_limit_count`/`rate_limit_hours` from widget config, LLM backend override, Wiki RAG context injection)

**Widget session persistence** (Replain-style): The widget preserves chat history across page navigations. Session ID is stored in both a cookie (`SameSite=None; Secure`, 30-day TTL) and `localStorage` (cookie-first, localStorage fallback). On page load, `preloadHistory()` fetches the session via `GET /widget/chat/session/{id}` (public, no auth, `source="widget"` only). The open/closed state is tracked in `sessionStorage` — if the chat was open before navigation, it auto-opens and renders history on the next page. `clearSession()` wipes cookie + localStorage + sessionStorage.

**Chat branching** (OpenWebUI-style): Non-destructive message editing and response regeneration. `ChatMessage` has `parent_id` (self-referential FK) and `is_active` (boolean) fields. Editing a message creates a new sibling branch; regenerating creates a new assistant child. Old versions preserved with `is_active=False`. `ChatRepository` methods: `edit_message()` (non-destructive), `branch_regenerate()`, `get_branch_tree()`, `get_sibling_info()`, `switch_branch()`, `get_active_messages()`. API endpoints: `GET /sessions/{id}/branches` (tree structure), `POST /sessions/{id}/branches/switch` (change active path). Frontend: `BranchTree.vue` + `BranchTreeNode.vue` — recursive tree panel on right side of chat. Messages with siblings show inline version navigation `< 1/3 >`. Migration: `scripts/migrate_chat_branches.py`.

**System prompt priority** (`app/routers/chat.py`): System prompts are resolved in priority order:
1. **Explicit override** — `llm_override.system_prompt` from API call, or `widget.system_prompt` if `widget_instance_id` provided
2. **Channel-specific** — `widget.system_prompt`, `bot.system_prompt`, `whatsapp.system_prompt`, or `session.system_prompt`
3. **Persona** — active LLM preset from DB (`llm_presets` table) → falls back to hardcoded `SECRETARY_PERSONAS` dict in `vllm_llm_service.py`
4. **RAG context** — always appended: Wiki RAG retrieves top-k relevant documents and appends them as `\n\n[Документация по теме:]\n...`
Default RAG prompt (when no other prompt set): `_DEFAULT_RAG_PROMPT` in `chat.py` — "Ты — ИИ-секретарь. Отвечай на вопросы пользователя кратко и по делу, используя предоставленную документацию."

**Other routers**: `audit.py` (audit log viewer/export/cleanup), `usage.py` (usage statistics/analytics), `legal.py` (legal compliance, migration: `scripts/migrate_legal_compliance.py`), `wiki_rag.py` (Wiki RAG stats/search/reload + Knowledge Base CRUD), `github_webhook.py` (GitHub CI/CD webhook handler).

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
- `web` — same backend access as `user`, but frontend hides: Dashboard, Services, vLLM, XTTS v2, Models, Finetune. Landing page: `/chat`
- `guest` — read-only (demo access)
- Frontend role exclusion: routes/nav items support `excludeRoles: ['web']` meta for per-role hiding
- CLI: `python scripts/manage_users.py create <user> <pass> --role web`

**Adding i18n translations:**
1. Edit `admin/src/plugins/i18n.ts` — add keys to both `ru` and `en` message objects

**Database migrations:** Manual scripts in `scripts/migrate_*.py` (no Alembic). New tables auto-created by `Base.metadata.create_all` on startup; schema changes to existing tables need migration scripts.

**API URL patterns:**
- `GET/POST /admin/{resource}` — List/create
- `GET/PUT/DELETE /admin/{resource}/{id}` — CRUD
- `POST /admin/{resource}/{id}/action` — Actions (start, stop, test)
- `GET /admin/{resource}/stream` — SSE endpoints
- `POST /webhooks/{service}` — External webhooks (amocrm, yoomoney, github)
- `POST /v1/chat/completions`, `POST /v1/audio/speech`, `GET /v1/models` — OpenAI-compatible

## Key Environment Variables

```bash
# Core
LLM_BACKEND=vllm                    # "vllm" or "cloud:{provider_id}" (legacy "gemini" auto-migrates)
VLLM_API_URL=http://localhost:11434 # Auto-normalized: trailing /v1 is stripped
SECRETARY_PERSONA=anna             # "anna" or "marina"
ORCHESTRATOR_PORT=8002
DEPLOYMENT_MODE=full                # "full", "cloud", or "local" — controls service loading
DEV_MODE=1                          # Makes backend proxy to Vite dev server (:5173)

# Auth
ADMIN_JWT_SECRET=...                # Auto-generated if empty
ADMIN_USERNAME=admin                # Legacy fallback when users table is empty
ADMIN_PASSWORD_HASH=...             # Legacy fallback (SHA-256 of password)
AUTH_ENABLED=true                   # Enable JWT authentication

# Infrastructure
REDIS_URL=redis://localhost:6379/0  # Optional, graceful fallback if unavailable
AMOCRM_PROXY=http://host:8888      # Optional, for Docker/VPN environments
CORS_ORIGINS=https://example.com   # Static CORS origins (comma-separated); widget domains added dynamically

# Rate limiting (slowapi)
RATE_LIMIT_ENABLED=true             # Global rate limiting toggle
RATE_LIMIT_DEFAULT=60/minute        # Default rate limit for all endpoints
RATE_LIMIT_AUTH=10/minute           # Auth endpoints (login, register)
RATE_LIMIT_CHAT=30/minute           # Chat streaming endpoints
RATE_LIMIT_TTS=20/minute            # TTS synthesis endpoints
RATE_LIMIT_STT=20/minute            # STT transcription endpoints

# Security headers
SECURITY_HEADERS_ENABLED=true       # Add security headers to all responses
X_FRAME_OPTIONS=DENY                # X-Frame-Options header value (DENY or SAMEORIGIN)
```

## Codebase Conventions

- **Python 3.11+**, line length 100, double quotes (ruff format)
- **Cyrillic strings are normal** — RUF001/002/003 disabled; Russian is used in UI text, logging, persona prompts
- **FastAPI Depends pattern** — `B008` (function-call-in-default-argument) is disabled for this reason
- **Optional imports** — Services like vLLM and OpenVoice use try/except at module level with `*_AVAILABLE` flags
- **SQLAlchemy mapped_column style** — Models use `Mapped[T]` with `mapped_column()` (declarative 2.0)
- **Repository pattern** — `BaseRepository(Generic[T])` provides get_by_id, get_all, create, update, delete. Domain repos extend with custom queries.
- **Admin panel**: Vue 3 + Composition API + TypeScript + Pinia (with `pinia-plugin-persistedstate`) + vue-i18n + TailwindCSS + radix-vue (headless UI) + @tanstack/vue-query (server state) + lucide-vue-next (icons) + chart.js/vue-chartjs. Path alias `@` → `admin/src/`. API layer: `admin/src/api/client.ts` provides shared `api.get/post/put/delete/upload` + `createSSE` helper (auto-injects JWT from `localStorage('admin_token')`); 21 domain-specific API files (`chat.ts`, `telegram.ts`, `whatsapp.ts`, `widget.ts`, `llm.ts`, `tts.ts`, `stt.ts`, `faq.ts`, `services.ts`, `monitor.ts`, `models.ts`, `finetune.ts`, `ttsFinetune.ts`, `audit.ts`, `usage.ts`, `amocrm.ts`, `gsm.ts`, `bot-sales.ts`, `wikiRag.ts`, `index.ts`). Composables in `admin/src/composables/` (`useSSE`, `useResponsive`, `useExportImport`, `useGpuStats`, `useRealtimeMetrics`). Pinia stores (11): `auth.ts` (user/role/deployment mode), `llm.ts` (LLM backend/model/persona), `tts.ts` (voice/preset/params), `services.ts` (service status), `settings.ts` (UI prefs, sidebar, refresh interval), `theme.ts` (light/dark/system/night-eyes), `toast.ts` (notifications), `confirm.ts` (modal dialogs), `search.ts` (global search), `audit.ts` (audit log).
- **Vite base path** — Production: `/admin/` (served by FastAPI). Demo builds and server deploy: `/` (overridden via `VITE_BASE_PATH` env or `.env.production.local`). Demo mode: `npm run build -- --mode demo` loads `.env.demo` (`VITE_DEMO_MODE=true`).
- **mypy strict scope** — Only `db/`, `auth_manager.py`, `service_manager.py` require typed defs; other modules are relaxed. mypy is soft in CI (`|| true`).
- **Pre-commit hooks** — ruff lint+format, mypy (core only), eslint, hadolint (Docker), plus standard checks (trailing whitespace, large files ≤1MB, private key detection, merge conflicts). See `.pre-commit-config.yaml`.

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

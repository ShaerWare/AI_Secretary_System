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

### Modular Infrastructure (`modules/`)

Foundation layer for the modular decomposition. All 28 routers live under `modules/*/router*.py`; inline endpoints and global service variables are gone from `orchestrator.py`; background tasks run through `TaskRegistry`; service initialization lives in per-domain `startup.py` modules; Protocol interfaces (`modules/*/protocols.py`) and facades (`modules/{core,knowledge,llm,chat}/{auth_service,facade}.py`) front the underlying services. History of the migration lives in `CHANGELOG.md` and issue #489.

- **`EventBus`** (`modules/core/events.py`): In-process async pub/sub. Handlers run concurrently via `asyncio.gather`; exceptions are logged, never propagated to publisher. `BaseEvent` dataclass with auto-timestamp. Singleton in `ServiceContainer.event_bus`. Domain events: `InternetStatusChanged`, `UserRoleChanged`, `SessionRevoked`, `DatasetSynced` (in `modules/core/events.py`), `KnowledgeUpdated` (in `modules/knowledge/events.py`), `WidgetSessionCreated`, `WidgetMessageSent`, `WidgetContactSubmitted` (in `modules/channels/widget/events.py`). Subscriptions registered via `setup_event_subscriptions()` in `modules/core/startup.py`, which delegates to domain-specific setup functions (`setup_llm_event_subscriptions()` in `modules/llm/startup.py`, `setup_knowledge_event_subscriptions()` in `modules/knowledge/startup.py`, `setup_crm_event_subscriptions()` in `modules/crm/startup.py`). `DatasetSynced` decouples CRM/ecommerce/kanban from knowledge. Widget events decouple widget router from amoCRM: widget publishes events, CRM domain handles lead/contact/note creation reactively.
- **`TaskRegistry`** (`modules/core/tasks.py`): Named background tasks — periodic (interval-based) or one-shot. `start_all()` / `cancel_all(timeout)` lifecycle. `TaskInfo` dataclass tracks status, run count, last error. 8 tasks registered in `startup_event()`: `session-cleanup` (1h), `periodic-vacuum` (7d), `kanban-sync` (15min), `woocommerce-sync` (daily 23:00 UTC), `procurement-site-sync` (daily 23:30 UTC), `rss-sync` (1h), `wiki-embeddings` (one-shot), `wiki-collection-indexes` (one-shot). Task functions in `modules/core/maintenance.py`, `modules/knowledge/tasks.py`, `modules/knowledge/rss_service.py`, `modules/kanban/tasks.py`, `modules/ecommerce/tasks.py`, `modules/procurement/tasks.py`.
- **`HealthRegistry`** (`modules/core/health.py`): Modular health checks with per-check timeout (`asyncio.wait_for`). Status aggregation: all ok → ok, any degraded → degraded, any error → error.

- **`InternetMonitor`** (`modules/core/internet_monitor.py`): Periodic connectivity checker (ping DNS/Cloudflare). Auto-switches LLM backend: online → cloud provider (claude_bridge priority), offline → local vLLM. Publishes `InternetStatusChanged` events via EventBus (`container.event_bus`). Configurable thresholds, 30s default interval. Status endpoint: `GET /admin/gsm/internet-status`. Health check includes `internet` section.

Import from `modules.core`: `EventBus`, `BaseEvent`, `TaskRegistry`, `TaskInfo`, `HealthRegistry`, `HealthStatus`, `UserRoleChanged`, `SessionRevoked`, `DatasetSynced`.

### Domain Services (`modules/*/service.py`)

Service classes extracted from the former monolithic `db/integration.py` into per-domain `service.py` / `facade.py` files (issue #492):

| Module | File | Service Classes |
|--------|------|-----------------|
| `modules/core/` | `service.py` | `DatabaseService`, `UserService`, `UserSessionService`, `RoleService`, `WorkspaceService`, `ConfigService`, `UserIdentityService` |
| `modules/core/` | `auth_service.py` | `AuthService` — facade wrapping `auth_manager.py`, implements `protocols.py` interface |
| `modules/knowledge/` | `facade.py` | `KnowledgeServiceImpl` — wraps `wiki_rag_service` + knowledge services, implements `protocols.py` interface |
| `modules/llm/` | `facade.py` | `LLMServiceImpl` — wraps `CloudLLMService`/`VLLMLLMService` + `CloudProviderService`, implements `protocols.py` interface |
| `modules/chat/` | `facade.py` | `ChatServiceImpl` — wraps `ChatService` CRUD + LLM generation + `ChatShareService`, implements `protocols.py` interface |
| `modules/chat/` | `service.py` | `ChatService`, `ChatShareService` |
| `modules/knowledge/` | `service.py` | `FAQService`, `KnowledgeDocService`, `KnowledgeCollectionService`, `GitHubRepoProjectService` |
| `modules/channels/telegram/` | `service.py` | `BotInstanceService`, `TelegramSessionService` |
| `modules/channels/whatsapp/` | `service.py` | `WhatsAppInstanceService` |
| `modules/channels/widget/` | `service.py` | `WidgetInstanceService` |
| `modules/channels/mobile/` | `service.py` | `MobileAppInstanceService` |
| `modules/kanban/` | `service.py` | `KanbanService`, `KanbanProjectService` |
| `modules/claude_code/` | `service.py` | `ClaudeCodeService`, `ClaudeCodeProjectService` |
| `modules/llm/` | `service.py` | `CloudProviderService` |
| `modules/monitoring/` | `service.py` | `AuditService`, `PaymentService` |
| `modules/admin/` | `service.py` | `ResourceShareService` |
| `modules/speech/` | `service.py`, `streaming.py` | `PresetService`, `StreamingTTSManager` |
| `modules/crm/` | `service.py` | `AmoCRMService` |
| `modules/ecommerce/` | `service.py` | `WooCommerceService` |
| `modules/procurement/` | `service.py` | `OfferService` (unified product-offer search) |
| `modules/telephony/` | `service.py` | `GSMService` |
| `modules/google/` | `service.py`, `models.py` | `GoogleOAuthService` |
| `modules/search/` | `service.py` | `WebSearchService` (DuckDuckGo via `ddgs`/`duckduckgo_search`, optional import) |

**Import pattern**: `from modules.chat.service import chat_service` (direct, preferred) or `from db.integration import async_chat_manager` (backward-compatible alias). Domain `__init__.py` files do NOT re-export services (see Known Issues #9).

### Domain Routers (`modules/*/router.py`)

All 28 routers live in domain modules. Files under `app/routers/` are 1–3 line facade re-exports kept for backward compatibility.

| Domain | Router file | Facade |
|--------|------------|--------|
| `modules/ecommerce/` | `router.py` | `app/routers/woocommerce.py` |
| `modules/procurement/` | `router.py` | `/admin/procurement/*` (direct include) |
| `modules/crm/` | `router.py` | `app/routers/amocrm.py` (exports `router` + `webhook_router`) |
| `modules/telephony/` | `router.py` | `app/routers/gsm.py` |
| `modules/speech/` | `router_tts.py`, `router_stt.py`, `router_services.py` | `app/routers/tts.py`, `stt.py`, `services.py` |
| `modules/knowledge/` | `router_faq.py`, `router_wiki_rag.py`, `router_github_repos.py` | `app/routers/faq.py`, `wiki_rag.py`, `github_repos.py` |
| `modules/kanban/` | `router.py` | `app/routers/kanban.py` |
| `modules/claude_code/` | `router.py` | `app/routers/claude_code.py` |
| `modules/channels/telegram/` | `router.py` | `app/routers/telegram.py` |
| `modules/channels/whatsapp/` | `router.py` | `app/routers/whatsapp.py` |
| `modules/channels/widget/` | `router.py`, `router_public.py` | `app/routers/widget.py` (admin); public endpoints direct |
| `modules/channels/mobile/` | `router.py` | `app/routers/mobile.py` |
| `modules/sales/` | `router_bot_sales.py`, `router_yoomoney.py` | `app/routers/bot_sales.py`, `yoomoney_webhook.py` |
| `modules/core/` | `router_auth.py`, `router_roles.py`, `router_workspace.py` | `app/routers/auth.py`, `roles.py`, `workspace.py` |
| `modules/admin/` | `router_backup.py`, `router_legal.py`, `router_github_webhook.py` | `app/routers/backup.py`, `legal.py`, `github_webhook.py` |
| `modules/monitoring/` | `router_audit.py`, `router_usage.py`, `router_monitor.py` | `app/routers/audit.py`, `usage.py`, `monitor.py` |
| `modules/chat/` | `router.py` | `app/routers/chat.py` |
| `modules/llm/` | `router.py` | `app/routers/llm.py` |
| `modules/google/` | `router.py` (+ `callback_router`) | `app/routers/google.py` |
| `modules/knowledge/` | `router_google_drive.py` | Google Drive RAG sync (`/admin/google-drive/*`) |

**Routers extracted from `orchestrator.py`** (not from `app/routers/`):

| Domain | Router file | Endpoints |
|--------|------------|-----------|
| `modules/compat/` | `router.py` | Legacy telephony (`/tts`, `/stt`, `/chat`, `/process_call`, `/reset_conversation`) + OpenAI-compat (`/v1/*`) |
| `modules/core/` | `router_health.py` | `/`, `/health`, `/admin/deployment-mode` |
| `modules/llm/` | `router_finetune.py` | LLM finetune: dataset, training, LoRA adapters (`/admin/finetune/*`) |
| `modules/speech/` | `router_finetune.py` | TTS finetune: samples, training, models (`/admin/tts-finetune/*`) |
| `modules/speech/` | `router_voices.py` | Voice selection + test (`/admin/voices`, `/admin/voice`, `/admin/voice/test`) |
| `modules/llm/` | `router_models.py` | HuggingFace model management (`/admin/models/*`) |
| `modules/monitoring/` | `router_logs.py` | Log viewing + streaming (`/admin/logs/*`) |

These routers import domain services directly (`from modules.monitoring.service import audit_service`) instead of through the facade. GPU-only routers (`router_voices.py`, `router_models.py`, `router_finetune.py`) are conditionally registered when `DEPLOYMENT_MODE != "cloud"`.

### Key Components

**`orchestrator.py`** (~320 lines): FastAPI entry point — **pure wiring**, zero domain logic. No inline endpoints, no raw `asyncio.create_task()`, no helper functions, no global service variables. Contains only: imports, CORS/middleware, declarative router registration (~28 routers), `startup_event()` (calls domain init functions + registers tasks), `shutdown_event()` (delegates to `graceful_shutdown()`), static file serving, Vite dev proxy. All service initialization in domain `startup.py` modules: `modules/speech/startup.py` (TTS/STT), `modules/llm/startup.py` (LLM + fallback chain + InternetMonitor callback), `modules/knowledge/startup.py` (Wiki RAG + embeddings), `modules/core/startup.py` (seed, monitor, shutdown), `modules/telephony/startup.py` (GSM), `modules/channels/{telegram,whatsapp}/startup.py` (bot auto-start).

**`ServiceContainer` (`app/dependencies.py`)**: Singleton holding references to all initialized services — the **single source of truth** for service state (no global variables). Includes `event_bus: EventBus` singleton for inter-module events. Routers get services via FastAPI `Depends`. Populated during app startup by domain `init_*()` functions. Runtime mutations (LLM backend switch) write directly to container.

**Two service layers**: Core AI services at project root (`cloud_llm_service.py`, `vllm_llm_service.py`, `voice_clone_service.py`, `stt_service.py`, etc.). Domain services in `app/services/` (`amocrm_service.py`, `wiki_rag_service.py`, `backup_service.py`, `sales_funnel.py`, etc.).

**Database layer** (`db/`): Async SQLAlchemy + aiosqlite. `db/database.py` creates engine. `db/integration.py` is a ~100-line facade that imports singletons and class aliases from domain services (`from modules.chat.service import chat_service as async_chat_manager`). Singletons are created in `modules/*/service.py`; the facade only re-exports them under old names. Repositories in `db/repositories/` inherit from `BaseRepository` with generic CRUD and `_apply_workspace_filter()` for multi-tenant queries.

**Unit of Work**: Repositories only `flush()` — never `commit()`. Callers own transaction boundaries: service methods call `session.commit()`, `get_async_session()` auto-commits on success / rollbacks on exception.

**SQLITE_BUSY retry**: `db/retry.py` `@retry_on_busy()` — exponential backoff (3 retries, 0.1s base). Applied to write methods in domain service classes (16 methods across 5 services).

**Telegram bots**: Subprocesses managed by `multi_bot_manager.py`. Config pre-fetched from DB, written to `/tmp/bot_config_{id}.json`. Two frameworks: `python-telegram-bot` (legacy) + `aiogram` (new). `LLMRouter` in `telegram_bot/services/llm_router.py` routes through orchestrator chat API. File uploads: `telegram_bot/services/file_extractor.py` extracts text from documents (text files + PDF via `pdfplumber`), injected into chat as plain text.

**WhatsApp bots**: Same subprocess pattern via `whatsapp_manager.py`. Module: `whatsapp_bot/` (runs as `python -m whatsapp_bot`). Two transports, chosen per instance by `whatsapp_instances.provider` (migration `scripts/migrate_whatsapp_provider.py`):

- **`cloud`** (default) — Meta Cloud API via `WhatsAppClient`; needs a number enrolled in the WhatsApp Business API.
- **`bridge`** — self-hosted provider in `services/whatsapp-bridge/` (Node + [Baileys](https://github.com/WhiskeySockets/Baileys), port 8005): an ordinary phone links by QR like WhatsApp Web, no third-party SaaS. `BridgeClient` (`whatsapp_bot/services/bridge_client.py`) implements the *same* interface as `WhatsAppClient`, so handlers, the sales funnel and the LLM router are untouched — `get_whatsapp_client()` picks the implementation. Incoming messages arrive at `POST /bridge/webhook` on the bot's own webhook port, HMAC-signed with the bridge token. QR linking from the admin panel: `POST/GET /admin/whatsapp/instances/{id}/bridge/{start,status,stop,logout}` (`modules/channels/whatsapp/bridge.py` resolves URL/token: instance row → env). Docker: `docker compose --profile whatsapp-bridge up -d` (credentials volume is mandatory — without it every restart demands a new QR).

  **Bridge caveats**: interactive buttons/lists don't exist on a linked phone, so `BridgeClient` renders them as a numbered text menu and `whatsapp_bot/services/choices.py` maps the reply ("2", "2)", or the option's title) back to the original `reply_id` — the displayed numbering and the registry numbering must stay in step, so both skip id-less rows. Templates degrade to plain text (no 24h window on a linked phone). Group chats are ignored. The protocol is unofficial: a number behaving like a broadcaster can be banned, and opening WhatsApp Web elsewhere with the same account replaces the session (the bridge then stays down instead of fighting for the slot). Media (voice/photo/doc) is downloadable via `GET /sessions/{id}/media/{msgid}` but not yet wired into STT/file extraction — the bot replies asking for text.

**Platform agent fallback** (`prompts/platform-agent.md`): When a chat session has no `system_prompt` set, `modules/chat/facade.py` loads this file as the system prompt (lazy, cached per-process) before falling back to `llm.get_system_prompt()`. Persona helps end-users configure their own assistants; no admin/ops content. Override path via `PLATFORM_AGENT_PROMPT_FILE`.

**Personas — live LLM-preset binding** (`modules/llm/persona.py`): an `LLMPreset` row (system prompt + temperature/max_tokens/top_p/repetition_penalty) can be attached to a chat session (`chat_sessions.llm_persona`, nullable, migration `scripts/migrate_persona_binding.py`) or to a widget / mobile / Telegram instance (`llm_persona` column, `""` = none). The link stores only the preset id — prompt and params are re-read from the DB on **every** message, so editing a preset in the LLM admin section changes all attached chats/widgets/bots immediately, with no snapshot copies. Prompt precedence in `modules/chat/facade.py:_build_prompt`: explicit override → session/instance `system_prompt` → persona prompt → `platform-agent.md` → `llm.get_system_prompt()`. Params: `merge_params()` overlays persona values under any explicit `llm_params`, and `_generate()` passes them per-call (`generate_response_from_messages(..., params=...)` on `VLLMLLMService`, `CloudLLMService`, `OpenAICompatibleProvider`, `GeminiProvider` — the latter maps them to `generation_config`, dropping `repetition_penalty`). Per-call, not `set_params()`, because the LLM service is a singleton shared by concurrent chats; `_llm_accepts_params()` degrades gracefully for provider classes without the kwarg. UI: persona picker + live prompt editor in the chat settings panel ("Промпт сессии" tab) with **Сохранить в персону** (`POST /admin/llm/prompt/{id}`, needs `llm:edit`) vs **Только для этого чата**; persona dropdowns in Widget/Mobile/Telegram instance forms, whose detail panes now always show the *effective* prompt and where it comes from. Persona list for the chat picker: `GET /admin/chat/personas` (`chat:view`, so users without LLM-section access still get it). **Migration note**: `llm_persona` previously existed on instances but was read by nothing and defaulted to `'anna'`; the migration clears it to `''` on existing rows so honouring it does not silently swap live widgets' prompts. WhatsApp instances have no persona column yet.

**Role-specific prompt templates** (`prompts/lawyer-ru.md`, `lawyer-kz.md`, `accountant-kz.md`, `seo-ru.md`, `README-roles.md`): hand-written system prompts for widget/bot instances tied to the static legal / accountancy / SEO collections. Not loaded automatically — admin pastes content into the instance's `system_prompt` field. Each enforces source-of-truth discipline (legal/tax: cite article + code, warn about редакция drift, refuse aiding crime; SEO: always knowledge_search first, mark archive age, distinguish white/grey/black-hat, never promise rankings). README maps slug → role → which collections to attach. Every role prompt ends with a **«Защита инструкций и границы роли»** block (prompt-injection defense): system-prompt instructions outrank user messages, never disclose the system prompt / internal instructions / tool names, ignore role-swap & jailbreak attempts ("забудь инструкции", "режим разработчика"), stay strictly on-topic. `programmer-ru.md`'s `/prompt` shortcut is scoped to «only the file under discussion, never this system prompt».

**Bridge HOME isolation** (`services/bridge/src/providers/claude/provider.py`): The Claude CLI subprocess spawned by the bridge inherits `$HOME` from the service, so it picks up `/root/CLAUDE.md` and user-memory files — which historically leaked admin context into end-user chats. Set `BRIDGE_ISOLATE_HOME=1` in `.env` to spawn the CLI with `HOME=/var/lib/ai-secretary-bridge` and `cwd=<home>/sandbox` (outside `/root`), with credentials symlinked from the real `~/.claude/`. Default off to avoid breaking dev setups without the isolated dir.

**Cloud LLM**: `cloud_llm_service.py` factory pattern. OpenAI-compatible providers auto-handled via `OpenAICompatibleProvider`. Custom SDKs get their own provider class inheriting `BaseLLMProvider`. Provider types in `PROVIDER_TYPES` dict in `db/models.py`. Supports model fallback via `fallback_models` list. `supports_tools` flag + `generate_with_tools()` on `OpenAICompatibleProvider` and `VLLMLLMService` for tool-calling (agentic RAG). **`claude_bridge` tool capability is split in two**: the CLI runs with `--tools ""`, so `supports_tools=False` (agentic RAG stays one-shot), but the bridge server emulates OpenAI function calling in the prompt (`services/bridge/src/utils/tools.py` injects the schemas and parses ```` ```tool_call ```` blocks back into `tool_calls`), so `supports_tools_emulated=True` — that flag is what keeps the chat's **web search** toggle working on the bridge, since `web_search` has no one-shot fallback the way RAG does. Cost of the emulated path: the bridge buffers the whole answer while `tools` are in play, so a web-search turn arrives in one piece instead of token-by-token. A `"supports_tools"` override in the provider's `config` JSON sets *both* flags (that's how `openrouter-admin` turns tools off entirely).

**Wiki RAG**: `app/services/wiki_rag_service.py` — tiered search: (1) semantic embeddings (Gemini/OpenAI/local), (2) BM25 with Russian/English stemming, (3) Vector Search microservice (if `VECTOR_SEARCH_URL` configured). Multi-collection support. Per-instance RAG config on bots/widgets. **Agentic RAG** (`modules/chat/router.py`): server-side loop where LLM calls `knowledge_search` tool to query the knowledge base on demand (max 5 iterations). Providers without `supports_tools` (Gemini SDK, `claude_bridge`) fall back to one-shot RAG injection. Frontend shows inline search indicator via `tool_start`/`tool_end` SSE events. **Vector Search** (`services/vector-search/`): standalone FastAPI microservice using ChromaDB + `paraphrase-multilingual-mpnet-base-v2` (768 dims). Client: `app/services/vector_search_client.py` (async httpx; `upsert_batch` — one `model.encode(list)` call для массовой индексации через `/upsert-batch`). Runs as Docker profile `vector-search` on port 8003 (main.py запечён в образ → правки требуют `docker compose --profile vector-search build vector-search`). Async search methods (`search_async`, `retrieve_async`, `retrieve_multi_async`) run all engines in parallel via `asyncio.gather` and merge/deduplicate results. Background task `vector-search-sync` upserts all sections on startup. `DatasetSynced` event triggers incremental sync. Admin endpoints: `GET /admin/wiki-rag/vector-search/status`, `POST /admin/wiki-rag/vector-search/sync`.

**Dev-architecture RAG collection** (`wiki-pages/dev-architecture/`): отдельная коллекция (slug `dev-architecture`, `base_dir=wiki-pages/dev-architecture`) для дев-чат-сессий ассистента. Содержит `Code-Patterns.md` (концентрат паттернов с примерами «как делать / как НЕ делать» — модульная структура, RBAC через `require_permission`, EventBus, `createSSE()` вместо raw EventSource, и т.п.); `CLAUDE.md` копируется туда же скриптом из корня репо. Привязывается к чат-сессиям, где admin обсуждает архитектуру проекта (вместе с пользовательской wiki-коллекцией id=1). Bootstrap: `scripts/setup_dev_architecture_rag.sh` копирует файлы, создаёт `KnowledgeCollection` + `KnowledgeDocument` строки, не зависит от уже существующих данных. **После изменений в `CLAUDE.md` или `Code-Patterns.md` — обязательно запустить скрипт + `systemctl restart ai-secretary`**, иначе коллекция уйдёт в дрейф относительно реального кода (локально `CLAUDE.md` в `wiki-pages/dev-architecture/` может отсутствовать до первого запуска).

**RSS knowledge layer** (`modules/knowledge/rss_service.py`, models `RSSFeed`/`RSSFeedItem` in `modules/knowledge/models.py`): each `RSSFeed` row maps a URL to a `KnowledgeCollection`. Periodic task `rss-sync` (1h interval) calls `feedparser` with cached ETag/Last-Modified, dedupes new entries by GUID, optionally fetches full article HTML and converts it to markdown via lxml (chrome stripped: nav/footer/scripts/share/cookie banners), writes one md file per item to the collection's `wiki-pages/` dir, creates `KnowledgeDocument` rows, then calls `wiki_rag.reload_collection()` + `sync_collection_to_vector_search()` directly (skips `DatasetSynced` event because its handler deletes-and-recreates docs which would orphan `rss_feed_items.document_id` FKs). Per-feed flags: `fetch_full_text`, `verify_ssl` (needed for adilet.zan.kz with non-standard CA). Caps: `MAX_ITEMS_PER_FEED=50`, `MAX_FULL_TEXT_BYTES=1.5MB`. Admin CRUD: `GET/POST/PATCH/DELETE /admin/rss/feeds`, `POST /admin/rss/feeds/{id}/sync`, `POST /admin/rss/sync-all`. Admin UI lives in fine-tune Collections section. Seed script `scripts/seed_rss_feeds.py` provisions 3 news collections (`ru-bukh-news`, `ru-pravo-news`, `kz-news`) with 13 verified RU/KZ accountancy & legal feeds.

**Per-user Claude token tracking** (shared $100 Anthropic plan): `usage_log` table has nullable `user_id` (migration `0024_usage_log_user_id`) keyed to chat session owner. `OpenAICompatibleProvider.last_usage` populated from response usage in non-stream path, from final-chunk usage or `tiktoken` estimate in stream path; `CloudLLMService.last_usage` proxies to provider. `modules/chat/facade.py:_log_llm_usage` writes one row per Claude/`claude_bridge` response (best-effort, never raises) with `service_type=llm`, `units_consumed=input+output`, `details={input_tokens, output_tokens, model, estimated}`. Period bounds in `modules/monitoring/period.py` — anchor day-of-month (default 30, capped to last day for short months). Endpoints: `GET /admin/usage/me` (any auth, own total), `GET /admin/usage/by-user` (admin, all users sorted desc by tokens). Mobile shows a thin orange→red bar under the context indicator with the user's own period total ([mobile/src/views/ChatView.vue](mobile/src/views/ChatView.vue)); admin Users view has a "Токены" column ([admin/src/views/UsersView.vue](admin/src/views/UsersView.vue)). Only Claude is tracked — Gemini/OpenAI/vLLM are skipped by `_is_claude_provider`. Streaming numbers are `tiktoken`-estimated (the bridge doesn't currently emit `usage` chunks); non-streaming responses use real Anthropic numbers.

**Static legal & accountancy collections** (`scripts/scrape_digitax/`): scraping pipeline for fixed corpora (federal codes, tax authority pages, professional bodies, SEO knowledge bases). Three steps: `scrape.py --site <slug>` (BFS crawler, BFS link-extractors per site), `parse.py --site <slug>` (HTML→Markdown via lxml + per-site `CONTENT_SELECTORS`), `upload.py --site <slug>` (writes DB rows + copies to `wiki-pages/<slug>/`). Site catalog in `config.py:SITES` — 7 Irish accountancy sites (digitax) + 3 RU bookkeeping (USN) + 10 RU federal codes already scraped (consultant.ru) + 38 additional RU consultant.ru sources generated from `RU_FEDERAL_LAWS` list (Constitution, 11 more codes — НК ч.1/2, БК, ГПК, АПК, КАС, ЗК, ЛК, ВК, ГсК; 24 ФЗ across corporate / administrative / social / finance / info domains; 11 ФКЗ; only `ru-fz-273` actually scraped so far) + 7 KZ codes (adilet.zan.kz) + 2 KZ accountancy practical (kgd.gov.kz, mybuh.kz; configured but not scraped) + 1 RU SEO portal (`ru-sbup-seo`, sbup.com, type `forum`, engine `smf`; scraped + live as collection id=59, ~7.5k docs). SMF (Simple Machines Forum 2.x) sites use `filter_smf_forum` + `extract_links_smf` in `scrape.py`: drops action handlers (`?action=login|register|profile|admin|search|...`), profile/admin/themes/avatars/attachments paths, and strips volatile `PHPSESSID` / `sa=` / `msg=` query params so BFS doesn't explode on session-tagged duplicate URLs. Sites with `engine: smf` in their cfg get a dedicated thread parser (`parse_forum_smf`) that merges every post on a page into one md doc with per-post sub-headers, drops nested quotes/signatures and SMF action chrome ("Записан", "« Ответ #N »", "Цитировать"); non-thread URLs (board indexes, MediaWiki `/wiki/` pages, articles) silently fall through to `parse_generic_page`. **SMF parser gotchas** (fixed): select posts by `.post_wrapper` only — a union with the `.windowbg` ancestor matches every post twice; take the message body from `.postarea//.inner` specifically (a bare `contains(@class,"post")` also grabs the `.poster` author sidebar → poster rank/post-count noise instead of the message). sbup.com junk filter: `SKIP_FILENAMES["ru-sbup-seo"]` keeps only `seo-forum__` / `wiki` / `seo-articales__` (the forum + textbook «SEO от А до Я» + SEO-wiki + articles) and drops SEO-tool output (alexa-rank/pagerank/tic rating tables, site-audit dumps of random external domains, whois/port-scanner utilities). consultant.ru codes: each `cons_doc_LAW_<id>` is a BFS root with article-level URLs branching out; sidebar pollution stripped via `div.seo-links` removal in `parse.py:strip_boilerplate`. adilet.zan.kz codes: each Kazakh code is a single monolithic page (~1.5–5 MB), needs `verify_ssl: False` (Kazakh root CA not in certifi); content selector `div.container_gamma.text.text_upd`. **Critical: global `POST /admin/wiki-rag/reload` only re-indexes the legacy WIKI_DIR (root-level files), NOT collections.** After bulk upload, loop `POST /admin/wiki-rag/collections/{id}/reload` per collection. Server-side runs of `upload.py` skip self-copy when source dir is `wiki-pages/` (parsed/ absent on production).

### Frontend Architecture

**Stack**: Vue 3 + Composition API + TypeScript, Vite, Pinia (persisted), Vue Router (hash history), TanStack Vue Query, vue-i18n (ru/en/kk), TailwindCSS + radix-vue, lucide-vue-next. Path alias `@` → `admin/src/`.

**Routing** (`admin/src/router.ts`): `createWebHashHistory`. Routes use `meta` fields: `public` (bypass auth), `localOnly` (hidden in cloud mode), `module` (RBAC module name), `minLevel` (view/edit/manage).

**Stores** (`admin/src/stores/`): Key store `auth.ts` holds JWT, user, `deploymentMode`, `permissions`. Exposes `isAdmin`, `isCloudMode`, `hasModule()`, `canView()`, `canEdit()`, `canManage()`. **Toast API**: `toast.success/error/warning/info(title)` — do NOT use `toast.show()` (different signature: `show(type, title, message?)`). **Confirm API**: `confirm.confirm({ title, message, confirmText, type })` returns `Promise<boolean>` — no `ask()` method.

**API layer** (`admin/src/api/`): `client.ts` provides `api.get/post/put/delete/upload` + `createSSE()` (auto-injects JWT). Domain files build on it. All re-exported from `api/index.ts`.

**Demo mode**: `VITE_DEMO_MODE=true` monkey-patches `window.fetch` to intercept API calls with mock data from 23 domain files in `admin/src/api/demo/`.

**Product variant** (`VITE_PRODUCT_VARIANT` env var, defaults to `full`): Set to `lite` to ship a stripped admin panel. Lite variant whitelists `/chat`, `/llm`, `/wiki`, `/finetune` (collections CRUD), `/widget`, `/telegram`, `/whatsapp`, `/mobile-app`, `/settings`, `/users`, `/about`, `/login`, `/invite/*` — everything else is blocked by the router guard and hidden from nav. Scripts: `npm run dev:lite` and `npm run build:lite`. Central helper: `admin/src/config/productVariant.ts` (`IS_LITE`, `isPathAllowed()`).

**Vite base path**: Production `/admin/` (served by FastAPI). Demo/standalone: `/` (via `VITE_BASE_PATH` or `.env.production.local`).

### Mobile App (`mobile/`)

**Stack**: Vue 3 + TypeScript, Vite, Pinia, Vue Router, Capacitor (Android), TailwindCSS 4. Path alias `@` → `mobile/src/`.

**Purpose**: Standalone Android chat app connecting to `https://ai-sekretar24.ru` (hardcoded). Role-based experience: admins get full chat controls, non-admins see only shared chats.

**Screens**: LoginView (auth only, no server URL), ChatListView (admin: session list + FAB + delete; non-admin: Claude-like welcome + shared chat cards), ChatView (streaming chat + TTS + role-based controls), SettingsView (account + logout).

**Theme**: Night-eyes (warm brown/amber/gold), hardcoded — no theme switching. Background `#1a1308`, text `#d9c9a8`, primary amber-600, cards stone-800.

**Role-based access**:
- **Admin** (`role=admin`): full chat controls — LLM provider selector, RAG collection multi-select, system prompt editing, export (copy/md/json), branching, context files, all message actions (edit, regenerate, summarize, delete branch), session creation/deletion. Admin-only controls live in admin panel only (not mobile).
- **Non-admin**: shared chats (`is_shared_with_me` filter), Claude-like welcome, basic message actions (TTS + copy), branching, context files, web search toggle. No LLM/RAG selectors, no export, no session deletion.

**Mobile Instances**: Admin creates `MobileAppInstance` (LLM backend, persona, system prompt, TTS, RAG) in admin panel (`/mobile-app` view). Users are assigned to instances via `ResourceShare`. On login, mobile app fetches `GET /admin/mobile/my-config` to get assigned instance config. Chat sessions use `source="mobile"` + `mobile_instance_id` for per-instance LLM/prompt routing.

**Default-assistant provisioning** (`modules/channels/mobile/provisioning.py`): every user gets a default set of assistants automatically at registration — no manual share step. `ASSISTANT_CATALOG` defines 6 `MobileAppInstance`s with a `scope`: country-agnostic (`marketer` → SEO collection `ru-sbup-seo`; `programmer` → prompt-only PHP/Laravel `programmer-ru.md`, stack editable per user) shared with everyone, plus country-specific (`lawyer-ru`+`accountant-ru` for `scope="ru"`, `lawyer-kz`+`accountant-kz` for `scope="kz"`). A user's country comes from `User.country` (`"ru"` default / `"kz"`, migration `0026_add_user_country`; `stalker`+`stalkerelectric` seeded to `kz`). `ensure_default_instances(session)` idempotently upserts the 6 instances from `prompts/*.md` (resolving collection slugs→ids, skipping absent ones); `provision_default_assistants(session, user_id, country)` idempotently adds `ResourceShare` (view) rows for `marketer`+`programmer`+the country pair. Hooked into `WorkspaceService.accept_invite` (invite registration) and `scripts/manage_users.py create` (CLI, best-effort — never blocks user creation). Provisioning is **additive** (never revokes — a country change dropping the other country's pair is a separate concern). Backfill for pre-existing users: `scripts/seed_legal_assistants.py` (ensures instances + shares per-user by country; idempotent, `--dry-run`). Prompts: `lawyer-ru.md`/`lawyer-kz.md`/`accountant-ru.md`/`accountant-kz.md` cite article+code and refuse crime/tax-evasion; `lawyer-ru.md`'s advertised catalog is deliberately trimmed to the 11 collections actually attached (do not re-add laws that aren't scraped, or the assistant hallucinates having them).

**Private per-user assistant sessions**: Assigned assistants (Юрист/Бухгалтер/…) give each user their OWN writable `ChatSession` (`owner_id=user`, `source="mobile"`, `source_id=instance_id`) that inherits the instance's prompt + RAG — the config is shared, the dialogue is private. This replaces the old "share one conversation read-only with everyone" model, which surfaced as a **"Только для чтения"** dead-end for non-admins (the frontend gates input on `is_shared_with_me && share_permission==='read'`, regardless of the user's actual `chat` permission). Find-or-create endpoint: `GET /admin/mobile/instances/{id}/my-session` (`chat:view` only, creates server-side so view-tier users still land in a writable session — but sending still needs `chat:edit`, i.e. operator/user/web roles, since `POST /sessions/{id}/stream` requires it). `ChatRepository.find_user_instance_session()` does the lookup. Both admin (`ChatView.vue` assistant switcher) and mobile (`ChatListView.vue`/`ChatView.vue`) open/create the private session instead of a read share. Migration `scripts/migrate_assistant_private_sessions.py` pre-creates the private sessions and drops the old cross-user `ChatSessionShare` rows on `source="mobile"` sessions (idempotent, `--dry-run` supported).

**API layer** (`mobile/src/api/`): `client.ts` (base fetch + `upload` for multipart FormData), `chat.ts` (sessions/streaming/branches/`uploadImage`), `admin.ts` (admin-only APIs, used only by admin panel).

**File upload in chat**: Same backend as admin (`POST /admin/chat/sessions/{id}/upload-image`). `ChatInput.vue` has paperclip button between input and send. Files uploaded → `image_ids` passed to `streamMessage` → backend injects extracted text (OCR/PDF/DOCX/XLSX) into LLM context. Accepts: JPEG, PNG, WebP, GIF, PDF, XLSX, DOCX, TXT, CSV, MD, JSON, XML, HTML, YAML. Max 300MB (`MAX_FILE_SIZE` in [modules/chat/image_service.py](modules/chat/image_service.py); on prod nginx `client_max_body_size` must be ≥300M — set to 350M). Upload processing (PIL thumbnail, pdfplumber/OCR/text extraction, disk I/O) runs in a worker thread via `asyncio.to_thread` (`_process_upload`) so a large/complex document can't freeze the orchestrator's event loop. Serving uploads (`GET /admin/chat/sessions/{id}/images/{file}`) accepts auth via the `Authorization` header OR a `?token=` query param, since `<img src>` / `<a download>` requests can't send a header (`auth_manager.resolve_user_from_token` validates the query-param JWT identically to the header path).

**Per-session named system prompts** (`ChatSessionPrompt` model, table `chat_session_prompts`): each chat session can hold multiple named prompts; exactly one is active. Endpoints `GET/POST /admin/chat/sessions/{id}/prompts`, `PATCH /admin/chat/sessions/{id}/prompts/{pid}`, `POST /admin/chat/sessions/{id}/prompts/{pid}/activate`, `DELETE …/{pid}`. The active prompt's content is mirrored into `ChatSession.system_prompt`, so the existing streaming pipeline picks it up unchanged — switching prompt swaps the assistant's role while preserving conversation history. Creating the first prompt while the session already has a `system_prompt` preserves it as the initial content. Deleting the active prompt promotes the most recent remaining one.

**Key differences from admin panel**:
- Hardcoded server URL (`https://ai-sekretar24.ru`), no user configuration
- JWT stored in native Preferences (not localStorage)
- No demo mode, no full RBAC UI — role-based chat experience
- ~77KB gzipped (vs ~2MB admin)

**Build**: `cd mobile && npm run build && npx cap sync android`. APK via Android Studio: `npx cap open android` → Build → Build APK.

**No lint/format/test** — mobile app has only `dev`, `build`, `preview` scripts. Type checking happens during `npm run build` via `vue-tsc -b`.

### Landing Site (`site/`)

Static marketing site served at `https://ai-sekretar24.ru/` — no build step, no framework. Plain HTML/CSS/JS with i18n: `site/index.html` (ru, canonical), `site/en/index.html`, `site/kk/index.html`. Auto-detects browser language and redirects from root on first visit only (skipped if user already chose a language or arrived from an in-site language page). `site/main.js` handles the language switcher and shared interactions; `site/styles.css` is hand-written, no Tailwind. Deployed independently of admin/mobile — nginx serves `site/` from `/var/www/` directly. Auth CTAs link to `/login` (not `/admin/`).

### Unified product search (`modules/procurement/`)

Code-pipeline «единый поиск позиции» для торгового ассистента (StalkerElectric). Модель `ProductOffer` (table `product_offers`) — единое структурное представление оффера из любого источника: `source` (`site`/`ekf`/`supplier`), `article`, `name`, `price`, `in_stock`, `lead_time_days`, `url` + `UniqueConstraint(source, source_key)` для upsert. `OfferService.replace_source_offers()` делает полный ре-синк одного источника; `OfferService.search()` детерминированно ранжирует (порядок ранга ниже) и **возвращает `[]`, если ничего не найдено — не выдумывает позиций** (жёсткое требование клиента реализовано архитектурно, а не промптом). `OfferService.search()` фильтрует стоп-слова (мета-запросы «запрос/стоимость/счёт», «из наличия/помоги/найти/подобрать», единицы «квт/вт/ква»), делает префикс-стемминг (`_stem` — 70 % длины слова, но не короче 6: контактор→контакт, электродвигатель→электродвига; плоские 6 символов превращали «электродвигатель» в «электр» и тянули в выдачу всю электроустановочную продукцию) + расширяет аббревиатуры (`_SYNONYMS`: ЧРП/ПЧ/частотник→преобразователь частоты; УЗО/УПП/дифавтомат). **Порядок ранга**: article_exact → article_partial → не-аксессуар (`_is_accessory_for_query` — «Катушка управления ДЛЯ КОНТАКТОРА» ниже контакторов, но не когда просят саму катушку) → lead-токен (название начинается с первого значимого слова запроса: сам товар выше того, что его лишь упоминает) → совпадения по целому слову (`strong` — «Контактный зажим» за 293 ₸ не обгоняет «Контактор» за 6 237 ₸) → число совпавших токенов → head-match. **Тай-брейк**: in_stock → **есть ли цена вообще** (треть site-каталога синкается с `price=0`, и при сортировке по возрастанию цены эти строки вытесняли реальные позиции из выдачи) → `SOURCE_PRIORITY` site<ekf<supplier → price. Строка, совпавшая только по случайному числу («100» из «ТТИ-А 100/5» → «упаковка 100 шт.»), кандидатом не считается — но только если в запросе вообще есть слова длиннее 3 символов (иначе ломались бы артикульные запросы вида `NXC 18`). Матчит name+category; возвращает `confident` (артикул или ≥2 значимых токена) — триаж по нему отсекает спам-темы писем. Регресс-тесты ранжирования: `tests/unit/test_offer_search_ranking.py`. ВАЖНО: правки search в live-каналах требуют рестарта (код кэшируется в памяти процесса). Адаптеры населяют общую таблицу: `site_adapter.sync_site_offers()` (WooCommerce→офферы, ~30k) + `suppliers/` (config-driven парсер, 6 поставщиков). **`modules/procurement/suppliers/`**: `registry.py` (per-supplier конфиги по реестру клиента Reestr v3 лист5 — format/header_row/cols/currency/markup_pct/stock_file; форматы: `xlsx`/`xls`(xlrd,1С)/`pdf_lines`/`pdf_table`), `parser.py` (openpyxl+xlrd+pdfplumber; `parse_number`; мерж остатков; трекинг категорий 1С), `adapter.py` (`sync_supplier`/`sync_all_suppliers` → `replace_source_offers(..., scope_key=cfg["key"])` — удаление по префиксу `{key}#%`, устойчиво к переименованию). Поставщики (наценка per-supplier из реестра): sunwell ×1.30, aksima ×1.30/max-РРЦ, aksima_chint_rrc (РРЦ), xtrade ×1.40, elektrokomplekt/ЭКТ ×1.25, megazakaz (USD, ×1.20×1.16). Прайсы из env `SUPPLIER_PRICES_DIR`; файлы прайсов НЕ в git (`docs/файлысталкера/` в .gitignore — дилерские цены). **Чат-интеграция** (`modules/chat/facade.py`): `_inject_offer_context` для procurement-сессий (коллекция в env `PROCUREMENT_CATALOG_COLLECTIONS`, default {6}) инъектит ТОЧНЫЙ keyword-поиск офферов (цены/артикулы/КП — принцип клиента: КП только точное) + SUPPLEMENTARY семантику каталога через `wiki_rag.retrieve_async(collection_id=6)` (богатые описания/смысл для вагих запросов типа «чем питать насос»→ПЧ; голые офферы НЕ индексируем в вектор — замер 2.8ч+шум); ГЕЙТ видимости — `session.source=='admin'` видит supplier-дилерские цены, клиентские каналы (widget/telegram/mobile) только site-розницу. Провайдер `claude_bridge` без tools → поиск = код-шаг. Роутер `/admin/procurement/{status,search,sync,sync-suppliers,price,kp,route}` (RBAC `sales`). **Маршрутизация** (`routing.py`, Reestr лист3): `SUPPLIER_META` (7 поставщиков вкл. promsitech/eltech без файлов, типы A/B/C), `CATEGORIES` (14 категорий keyword→упорядоченные поставщики), `classify`/`route(query,city)` (Атырау→ЭКТ первым, ELTECH competitor). Эндпоинт `GET /admin/procurement/route`; чат «не найдено» (менеджер) подсказывает у кого запросить. **amoCRM-триаж** (`modules/crm/triage.py` + `GET /admin/crm/triage`): неразобранные лиды (`get_unsorted_leads`, добавляет `_body`=`metadata.content_summary` для mail) → матчинг/КП по ТЕМЕ (точно, confident по значимым токенам ≥4 — спам не проходит), маршрутизация по тема+тело (recall), `body_preview` для менеджера → {routing, matches[client_price], suggestion}; ловит мёртвый токен → `{ok:false, reason:reauth_needed}` (`GET /admin/crm/auth-url`). Дальше: тело чатов (get_chat_history) + LLM-извлечение позиций из длинного письма. Задача `procurement-site-sync` (daily 23:30 UTC). **Генерация КП** (`kp.py`): `build_kp`/`build_kp_for_queries` — спецификация из priced-офферов → markdown (позиции, Итого без НДС/НДС 16%/с НДС, курс+дата если USD, строка доставки по факту веса, срок действия; поставщиков клиенту НЕ раскрывает, Мегазаказ как бренд Stalker, zero-margin/нерасчитанные → flags не в итог; черновик на директора). Эндпоинт `POST /admin/procurement/kp` (body items/client_name/quote_date); менеджерский чат-инъект даёт КП-подсказку. **Ценовой движок**: `rate_service.py` (курс USD/KZT с mig.kz buy-курс, кэш на день, фолбэк env `PROCUREMENT_USD_KZT`/last-known+флаг stale→спросить директора) + `pricing.py` (`compute_pricing`/`price_offer` — per-supplier закупка+цена клиенту по Reestr лист2: KZT-дилер raw×(1+markup), Chint РРЦ, Аксима max(РРЦ,raw×1.30), USD Мегазаказ $×курс×1.20×1.16, НДС не удваивать при vat_included, флаг zero_margin≥→директору). Менеджерский чат-инъект показывает «закуп→клиенту»+курс/дата; клиентам только розница. Ещё не сделано: ПРОМСИТЕХ (файла нет) + EKF API + генерация КП-документа + авто-загрузка прайсов из почты (Reestr правило 4) + цена у ~11 тыс. site-офферов приходит нулевой (вариативные товары WooCommerce). План работ по MASTER WORKFLOW v1.2 — `docs/stalker-workflow-plan.md`.

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
```

**Landing lead form** (`site/` → Telegram): the static landing's lead form (`#leadForm`, handled in `site/main.js`) POSTs JSON to `POST /widget/lead` (in `modules/channels/widget/router_public.py`). Mounted under the already nginx-proxied `/widget/` prefix so no new nginx location is needed. The endpoint reads `LEAD_TELEGRAM_BOT_TOKEN` + `LEAD_TELEGRAM_CHAT_ID` from env (no secrets in the static site) and sends an HTML message to the owner's Telegram via `api.telegram.org/bot<token>/sendMessage`. Anti-spam: a hidden `company` honeypot field (CSS `.lead-form__hp`). If the backend is unreachable, the frontend falls back to opening `t.me/ai_sekretar24bot` with a pre-filled message. Locale + page URL are included in the notification.

## Deployment

### Server Deployment (Production)

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

### Deployment Checklist

1. Run lint locally — `ruff check . && cd admin && npm run lint:check`
2. Check for pending DB migrations
3. Kill stale processes — `lsof -i :8002`
4. Clean build artifacts — `rm -rf admin/dist admin/node_modules/.vite`
5. Build — `npm run build` (verify `VITE_DEMO_MODE` is NOT set)
6. Restart — `docker compose restart ai-secretary`
7. Verify — `curl http://localhost:8002/health` + test `/admin/auth/login`

### Automated Deployment

```bash
./deploy.sh                # git pull, re-apply patches, build admin, restart orchestrator
./test_system.sh           # Quick health checks and API smoke tests
```

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

1. **Vosk model required** — Download to `models/vosk/` for STT
2. **XTTS requires CUDA CC >= 7.0** — RTX 3060+; use OpenVoice for older GPUs
3. **GPU memory** — vLLM ~6GB + XTTS ~5GB must fit in 12GB. `start_gpu.sh` launches vLLM with `--enable-auto-tool-choice` + `--tool-call-parser` (`hermes` for Qwen, `llama3_json` for Llama) — without them the server 400s on `tool_choice: auto` and `VLLMLLMService` permanently flips its `supports_tools` flag off, silently dropping agentic RAG to one-shot injection. Short context windows (`--max-model-len 4096`) also need `trim_messages`' output reserve capped at a quarter of the window, otherwise the fixed 4096-token reserve leaves no input budget at all
4. **VLESS proxy vs localhost** — `GeminiProvider` sets global `HTTP_PROXY`; `OpenAICompatibleProvider` sets `NO_PROXY=127.0.0.1,localhost` for `claude_bridge`; `bridge_manager.py` strips proxy env vars. Because that env var is process-global, anything talking to a *local* service must pass `trust_env=False` to httpx — `VLLMLLMService.client`, the vLLM health check in `modules/llm/router.py`, and `BridgeClient` (WhatsApp) all do. `GeminiProvider` also only exports the proxy vars if `proxy_manager.start()` actually succeeded; a dead xray left `HTTP_PROXY` pointing at a closed port and broke every unrelated HTTP call in the process
5. **Claude bridge timeouts** — 7-30s warmup. `read=300s` timeout for bridge (vs 60s default). `max_tokens=4096` (vs 512)
6. **`services/bridge/src/models/` now committed** — previously the blanket `.gitignore` pattern `models/` swallowed this OpenAI-compat schema package, so fresh clones/deploys crashed the bridge with `ModuleNotFoundError: No module named 'src.models'`. Fixed by a `.gitignore` negation (`!services/bridge/src/models/`); the package (reconstructed) is now tracked. No manual copy needed.
7. **Docker CPU: whisper excluded** — `openai-whisper` fails to build (missing `pkg_resources`). Server Dockerfile patched to `grep -v whisper`
8. **Docker + Claude CLI** — CPU image needs Node.js. Server Dockerfile patched to install Node.js 20 + `@anthropic-ai/claude-code`
9. **tiktoken must never load on the request path** (`app/utils/tokens.py`) — the first `get_encoding()` downloads a ~1.7 MB BPE file, synchronously, and token counting runs inside FastAPI handlers (`GET /admin/chat/sessions/{id}` builds `token_usage` for every fetch), so a cold cache froze the whole event loop for ~30s; behind a dead `HTTP_PROXY` (which `GeminiProvider` sets globally) it hung with no timeout, on every request, because the failure wasn't remembered. Now: persistent cache in `models/tiktoken` (`TIKTOKEN_CACHE_DIR` to override), loads in a background thread (char-based approximation until ready), failures cached for 10 min, prewarmed at startup via `prewarm_token_encodings()` in `startup_event()`. **Never call `count_message_tokens`/`count_tokens` expecting exact numbers immediately after boot**, and never add a blocking encoding load to a handler.
10. **Circular import in domain `__init__.py`** — Domain `__init__.py` files MUST stay empty (no service re-exports). Chain: `db/models.py` imports `from modules.X.models import ...` → Python executes `modules/X/__init__.py` → if it imports `service.py` → `service.py` imports `db.repositories` → `db.repositories` imports `db.models` → circular. **Workaround**: import services directly (`from modules.chat.service import ChatService`). **Future fix** (Phase 3+): eliminate eager imports in `db/models.py` by making it a lazy facade or removing it entirely once consumers import models from domain modules.
11. **Trimming a response field breaks the API-layer mappers** — `admin/src/api/chat.ts` post-processes some responses (`tokenizeSessionImages(r.session)` rewrites image URLs with a `?token=`). When `POST /admin/chat/sessions/{id}/branches/switch` was slimmed down to `{"status": "ok"}` (the frontend refetches session + branches anyway), the mapper kept dereferencing the now-missing `session` and threw `Cannot read properties of undefined (reading 'messages')` — the branch had *already* switched server-side, so the UI showed an error toast and stale messages until a page reload. When an endpoint stops returning a field, grep the API layer for its `.then(...)` mapper; `tokenizeSessionImages` now no-ops on a missing session.

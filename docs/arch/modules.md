# Modular infrastructure, domain services and routers

> Part of the project map in [CLAUDE.md](../../CLAUDE.md). Split out of CLAUDE.md verbatim on 2026-10-31; update it in the same PR as the code it describes.

## Modular Infrastructure (`modules/`)

Foundation layer for the modular decomposition. All 28 routers live under `modules/*/router*.py`; inline endpoints and global service variables are gone from `orchestrator.py`; background tasks run through `TaskRegistry`; service initialization lives in per-domain `startup.py` modules; Protocol interfaces (`modules/*/protocols.py`) and facades (`modules/{core,knowledge,llm,chat}/{auth_service,facade}.py`) front the underlying services. History of the migration lives in `CHANGELOG.md` and issue #489.

- **`EventBus`** (`modules/core/events.py`): In-process async pub/sub. Handlers run concurrently via `asyncio.gather`; exceptions are logged, never propagated to publisher. `BaseEvent` dataclass with auto-timestamp. Singleton in `ServiceContainer.event_bus`. Domain events: `InternetStatusChanged`, `UserRoleChanged`, `SessionRevoked`, `DatasetSynced` (in `modules/core/events.py`), `KnowledgeUpdated` (in `modules/knowledge/events.py`), `WidgetSessionCreated`, `WidgetMessageSent`, `WidgetContactSubmitted` (in `modules/channels/widget/events.py`). Subscriptions registered via `setup_event_subscriptions()` in `modules/core/startup.py`, which delegates to domain-specific setup functions (`setup_llm_event_subscriptions()` in `modules/llm/startup.py`, `setup_knowledge_event_subscriptions()` in `modules/knowledge/startup.py`, `setup_crm_event_subscriptions()` in `modules/crm/startup.py`). `DatasetSynced` decouples CRM/ecommerce/kanban from knowledge. Widget events decouple widget router from amoCRM: widget publishes events, CRM domain handles lead/contact/note creation reactively.
- **`TaskRegistry`** (`modules/core/tasks.py`): Named background tasks — periodic (interval-based) or one-shot. `start_all()` / `cancel_all(timeout)` lifecycle. `TaskInfo` dataclass tracks status, run count, last error. 10 tasks registered in `startup_event()`: `session-cleanup` (1h), `periodic-vacuum` (7d), `kanban-sync` (15min), `woocommerce-sync` (daily 23:00 UTC), `procurement-site-sync` (daily 23:30 UTC), `procurement-supplier-sync` (daily 23:50 UTC), `rss-sync` (1h), `google-drive-sync` (daily 23:15 UTC, RAG-only Drive sources), `wiki-embeddings` (one-shot), `wiki-collection-indexes` (one-shot). Task functions in `modules/core/maintenance.py`, `modules/knowledge/tasks.py`, `modules/knowledge/rss_service.py`, `modules/kanban/tasks.py`, `modules/ecommerce/tasks.py`, `modules/procurement/tasks.py`.
- **`HealthRegistry`** (`modules/core/health.py`): Modular health checks with per-check timeout (`asyncio.wait_for`). Status aggregation: all ok → ok, any degraded → degraded, any error → error.

- **`InternetMonitor`** (`modules/core/internet_monitor.py`): Periodic connectivity checker (ping DNS/Cloudflare). Auto-switches LLM backend: online → cloud provider (claude_bridge priority), offline → local vLLM. Publishes `InternetStatusChanged` events via EventBus (`container.event_bus`). Configurable thresholds, 30s default interval. Status endpoint: `GET /admin/gsm/internet-status`. Health check includes `internet` section.

Import from `modules.core`: `EventBus`, `BaseEvent`, `TaskRegistry`, `TaskInfo`, `HealthRegistry`, `HealthStatus`, `UserRoleChanged`, `SessionRevoked`, `DatasetSynced`.

## Domain Services (`modules/*/service.py`)

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

## Domain Routers (`modules/*/router.py`)

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

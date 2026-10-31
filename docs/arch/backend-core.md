# Backend core: orchestrator, container, DB, event loop

> Part of the project map in [CLAUDE.md](../../CLAUDE.md). Split out of CLAUDE.md verbatim on 2026-10-31; update it in the same PR as the code it describes.

## Key Components

**`orchestrator.py`** (~320 lines): FastAPI entry point — **pure wiring**, zero domain logic. No inline endpoints, no raw `asyncio.create_task()`, no helper functions, no global service variables. Contains only: imports, CORS/middleware, declarative router registration (~28 routers), `startup_event()` (calls domain init functions + registers tasks), `shutdown_event()` (delegates to `graceful_shutdown()`), static file serving, Vite dev proxy. All service initialization in domain `startup.py` modules: `modules/speech/startup.py` (TTS/STT), `modules/llm/startup.py` (LLM + fallback chain + InternetMonitor callback), `modules/knowledge/startup.py` (Wiki RAG + embeddings), `modules/core/startup.py` (seed, monitor, shutdown), `modules/telephony/startup.py` (GSM), `modules/channels/{telegram,whatsapp}/startup.py` (bot auto-start).

**`ServiceContainer` (`app/dependencies.py`)**: Singleton holding references to all initialized services — the **single source of truth** for service state (no global variables). Includes `event_bus: EventBus` singleton for inter-module events. Routers get services via FastAPI `Depends`. Populated during app startup by domain `init_*()` functions. Runtime mutations (LLM backend switch) write directly to container.

**Two service layers**: Core AI services at project root (`cloud_llm_service.py`, `vllm_llm_service.py`, `voice_clone_service.py`, `stt_service.py`, etc.). Domain services in `app/services/` (`amocrm_service.py`, `wiki_rag_service.py`, `backup_service.py`, `sales_funnel.py`, etc.).

**Database layer** (`db/`): Async SQLAlchemy + aiosqlite. `db/database.py` creates engine. `db/integration.py` is a ~100-line facade that imports singletons and class aliases from domain services (`from modules.chat.service import chat_service as async_chat_manager`). Singletons are created in `modules/*/service.py`; the facade only re-exports them under old names. Repositories in `db/repositories/` inherit from `BaseRepository` with generic CRUD and `_apply_workspace_filter()` for multi-tenant queries.

**LLM calls never run on the event loop**: providers stream through a *sync* httpx client, so iterating them inside an async handler parked the loop on every socket read — one slow bridge answer froze health, login and every widget. `modules/chat/facade.py` runs non-stream calls and tool calls via `asyncio.to_thread` (`_join_response`) and drives streams with `_iterate_in_thread`; `modules/compat/router.py` uses `iterate_in_threadpool`. Regression test: `tests/unit/test_stream_does_not_block_loop.py`.

**Unit of Work**: Repositories only `flush()` — never `commit()`. Callers own transaction boundaries: service methods call `session.commit()`, `get_async_session()` auto-commits on success / rollbacks on exception.

**SQLITE_BUSY retry**: `db/retry.py` `@retry_on_busy()` — exponential backoff (3 retries, 0.1s base). Applied to write methods in domain service classes (16 methods across 5 services).

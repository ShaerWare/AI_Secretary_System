# AI Secretary — Code Patterns (для дев-сессий)

Этот файл — короткий концентрат паттернов проекта. Не вики, не пользовательская документация — это **референс для написания нового кода**. Перед декомпозицией задач для агентов или предложением архитектуры обязательно свериться отсюда.

## 1. Куда класть код (ОБЯЗАТЕЛЬНО)

Архитектура: **модульная**. Никакого нового кода в `orchestrator.py` — он чистый wiring (~320 строк, импорты + регистрация роутеров + startup/shutdown).

```
orchestrator.py           # pure wiring, zero domain logic
modules/
  {domain}/
    router.py             # FastAPI router (или router_*.py если несколько)
    service.py            # domain service classes + singleton
    facade.py             # optional: implements Protocol from protocols.py
    startup.py            # init_*() called from orchestrator.startup_event
    events.py             # domain events for EventBus
    tasks.py              # background tasks (periodic/one-shot)
    models.py             # SQLAlchemy 2.0 Mapped[T] models
    protocols.py          # optional: Protocol interfaces
app/routers/{name}.py     # 1-3 line facade re-exports — НЕ КЛАСТЬ ТУДА НОВУЮ ЛОГИКУ
db/
  models.py               # central re-exports
  repositories/{name}.py  # BaseRepository[T] subclasses, only flush(), never commit()
  retry.py                # @retry_on_busy decorator for SQLITE_BUSY
```

Существующие домены: `core`, `chat`, `llm`, `knowledge`, `speech`, `telephony`, `crm`, `ecommerce`, `kanban`, **`claude_code`**, `channels/{telegram,whatsapp,widget,mobile}`, `sales`, `monitoring`, `admin`, `google`, `compat`.

**Прежде чем создавать новый модуль — проверь, есть ли он.** Для Claude Code → `modules/claude_code/` уже есть (`service.py`, `router.py`, `models.py`). Расширяй, не создавай параллельный.

## 2. Роутер (правильный шаблон)

```python
# modules/{domain}/router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth_manager import require_permission, user_has_level, workspace_context
from db.database import get_async_session
from modules.{domain}.service import {domain}_service

router = APIRouter(prefix="/admin/{domain}", tags=["{domain}"])

@router.get("/items")
async def list_items(
    user: dict = Depends(require_permission("{module}", "view")),
    db: AsyncSession = Depends(get_async_session),
):
    owner_id, ws_id = await workspace_context(user, "{module}")
    return await {domain}_service.list(db, owner_id=owner_id, workspace_id=ws_id)
```

**Регистрация в orchestrator.py — одна строка:**
```python
from modules.{domain}.router import router as {domain}_router
app.include_router({domain}_router)
```

## 3. Auth — RBAC, не "role"

**НЕЛЬЗЯ** `Depends(require_role("admin"))` — такой функции нет.

**НАДО:**
```python
# Зависимость
from auth_manager import require_permission
user: dict = Depends(require_permission("chat", "view"))  # module + level
# Levels: "view" | "edit" | "manage"
# Modules: "chat", "llm", "knowledge", "claude_code", "users", ...

# Инлайн-проверка
from auth_manager import user_has_level
if not user_has_level(user, "claude_code", "manage"):
    raise HTTPException(403)

# Multi-tenant scoping
from auth_manager import workspace_context
owner_id, workspace_id = await workspace_context(user, "chat")
# owner_id=None => "shared within workspace"
```

## 4. DB-сессия

```python
from db.database import get_async_session                  # FastAPI dependency
db: AsyncSession = Depends(get_async_session)

# В асинхронных задачах (НЕ роутерах):
from db.database import AsyncSessionLocal
async with AsyncSessionLocal() as db:
    ...
    await db.commit()  # service-level, не repository-level
```

**Repositories только `flush()`, никогда `commit()`.** Транзакции владеет сервис/эндпоинт.

## 5. Service + Singleton (паттерн)

```python
# modules/{domain}/service.py
from db.repositories.{domain} import {Entity}Repository
from db.retry import retry_on_busy

class {Entity}Service:
    @retry_on_busy()
    async def create(self, db: AsyncSession, *, owner_id, workspace_id, ...) -> {Entity}:
        repo = {Entity}Repository(db)
        item = await repo.create(...)
        await db.commit()
        return item

{domain}_service = {Entity}Service()  # singleton
```

## 6. EventBus (in-process pub/sub)

Для inter-module событий — публикуй в `EventBus`, подписывайся в `setup_*_event_subscriptions()` соответствующего домена.

```python
# modules/{domain}/events.py
from dataclasses import dataclass
from modules.core.events import BaseEvent

@dataclass
class AgentSessionStarted(BaseEvent):
    session_id: str
    user_id: int

# Публикация:
from app.dependencies import get_container
await get_container().event_bus.publish(AgentSessionStarted(session_id=..., user_id=...))

# Подписка (в modules/{domain}/startup.py):
def setup_{domain}_event_subscriptions(bus: EventBus) -> None:
    bus.subscribe(AgentSessionStarted, handle_started)
```

## 7. Background-задачи через TaskRegistry

```python
# modules/{domain}/tasks.py
async def my_periodic_task(): ...

# В modules/{domain}/startup.py:
def register_{domain}_tasks(registry: TaskRegistry) -> None:
    registry.register_periodic("my-task", my_periodic_task, interval_seconds=3600)
```

**Никогда `asyncio.create_task(...)` напрямую в orchestrator.py — только через TaskRegistry.**

## 8. SSE — авторизация (важно для фронта)

Браузерный `EventSource` API **НЕ поддерживает custom headers**. `Authorization: Bearer` через него не передать.

Существующий помощник на фронте — `admin/src/api/client.ts → createSSE()`:
```typescript
import { createSSE } from '@/api/client'
const sse = createSSE('/admin/claude-code/stream', (event) => { ... })
// токен инжектится автоматически через query-параметр или сессионный cookie
```

На бэке принимай токен из query-параметра ИЛИ из cookie, не только из Authorization header.

## 9. Frontend — Pinia store + api/client (не raw fetch)

```typescript
// admin/src/stores/myFeature.ts
import { defineStore } from 'pinia'
import { api } from '@/api/client'

export const useMyFeatureStore = defineStore('myFeature', () => {
  const items = ref<Item[]>([])
  async function load() {
    items.value = await api.get('/admin/my-feature/items')  // токен инжектится автоматически
  }
  return { items, load }
})
```

**Не использовать `fetch('/admin/...', { headers: { Authorization: ... } })` напрямую** — всё это уже завёрнуто в `api.get/post/put/delete/upload` с auto-инъекцией JWT и обработкой 401.

## 10. RAG / Knowledge Collections

Чтобы добавить документы в RAG:
1. INSERT в `knowledge_collections` (поле `slug`, `base_dir='wiki-pages'`)
2. Скопировать MD-файлы в `wiki-pages/{slug}/`
3. INSERT в `knowledge_documents` (filename, title, source_type, collection_id)
4. POST `/admin/wiki-rag/collections/{id}/reload` (или restart orchestrator — `wiki-collection-indexes` task переиндексит)

**Глобальный POST `/admin/wiki-rag/reload` НЕ переиндексирует коллекции** — только legacy WIKI_DIR.

## 11. Agentic RAG (Claude / vLLM с tools)

Если LLM поддерживает tools (`supports_tools=True`), бэк запускает loop с инструментом `knowledge_search`:
- модель сама решает когда искать
- max 5 итераций
- frontend показывает `tool_start`/`tool_end` SSE-события

Для моделей без tools — one-shot RAG inject в первое сообщение.

## 12. Существующая Claude Code интеграция

В `modules/claude_code/` уже есть:
- `service.py`: `ClaudeCodeService` (subprocess management), `ClaudeCodeProjectService`
- `router.py`: WebSocket `/admin/claude-code/ws` + REST для проектов
- `models.py`: модели проектов/сессий

WebSocket поднимает Claude CLI как subprocess с `--output-format stream-json --verbose`, парсит NDJSON, ретранслирует через WS. `_ALLOWED_CWDS` ограничивает рабочие директории CLI.

**Для нового функционала (multi-agent orchestration, DAG, parallel workers и т.д.) — extend этот модуль, не создавай claude_code_manager.py в корне репо.**

## 13. Deploy / прод

- Локалка: Windows + Vite dev (`http://localhost:5173/admin/`) + `./start_gpu.sh`
- Прод: Beget VPS (`root@155.212.231.7`), systemd `ai-secretary`, путь `/opt/ai-secretary/`
- Деплой админки: `cd admin && npm run build && rsync admin/dist/ /var/www/admin-ai-sekretar24/ && systemctl restart ai-secretary`
- **Никогда** в коде не делай предположений про конкретные пути типа `/tmp/...` — кросс-платформенно через `pathlib.Path` + `tempfile.gettempdir()`.
- Pause/resume процессов через `SIGSTOP/SIGCONT` работает только на POSIX. На Windows дев-окружении эти сигналы не существуют — нужен conditional import/skip.

## 14. Token tracking

Каждый ответ Claude (`cloud:claude-bridge*` или `cloud:claude-*`) уже логируется в `usage_log` (поля `user_id`, `input_tokens`, `output_tokens`, `model`). См. `modules/chat/facade.py:_log_llm_usage`. Любой новый воркер (включая мультиагентов) должен **проходить через ту же тропу** или явно расширять схему — иначе $100/мес план Claude API сгорает молча.

---

## Чеклист «не наступать на грабли»

- [ ] Код кладу в `modules/{domain}/`, не в корень репо
- [ ] Эндпоинты в `router.py` модуля, не в `orchestrator.py`
- [ ] Auth через `require_permission(module, level)`, не `require_role`
- [ ] DB-сессия через `get_async_session()` / `AsyncSessionLocal`
- [ ] Repository только `flush()`, commit в сервисе
- [ ] Background-задачи через `TaskRegistry`, не raw `asyncio.create_task`
- [ ] Inter-module коммуникация через `EventBus`
- [ ] Frontend — Pinia + `api/client.ts`, не raw `fetch`
- [ ] SSE на фронте — `createSSE()`, не `new EventSource()` с заголовком
- [ ] Workspace-id во всех новых моделях для multi-tenant
- [ ] POSIX-only фичи (SIGSTOP, /tmp) — conditional на Windows
- [ ] Перед декомпозицией для Claude Code агентов — проверить, нет ли уже модуля

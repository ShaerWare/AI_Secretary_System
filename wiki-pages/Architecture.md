# Architecture (Архитектура)

Техническая архитектура AI Secretary System: текущее состояние, модульная инфраструктура и план миграции.

## Обзор

```
┌──────────────────────────────────────────────────────────────┐
│                  Orchestrator (port 8002)                     │
│  orchestrator.py + app/routers/ (28 роутеров, ~400 endpoints)│
│  ┌────────────────────────────────────────────────────────┐  │
│  │        Vue 3 Admin Panel (23 views, PWA)                │  │
│  │                admin/dist/                              │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │        modules/core/ (Phase 0)                          │  │
│  │  EventBus · TaskRegistry · HealthRegistry               │  │
│  └────────────────────────────────────────────────────────┘  │
└────────────┬──────────────┬──────────────┬───────────────────┘
             │              │              │
     ┌───────┴──┐    ┌──────┴───┐   ┌─────┴─────┐
     │ LLM      │    │ TTS      │   │ STT       │
     │ vLLM /   │    │ XTTS v2 /│   │ Vosk /    │
     │ Cloud    │    │ Piper    │   │ Whisper   │
     └──────────┘    └──────────┘   └───────────┘
```

**Пайплайн обработки:** Сообщение пользователя → FAQ-проверка (мгновенный ответ) ИЛИ LLM → TTS → Аудио-ответ

**Профили развёртывания** (`DEPLOYMENT_MODE`): `full` (всё), `cloud` (без GPU/TTS/STT/GSM), `local` (= full).

## Текущее состояние

### Текущее состояние после Phase 4

| Компонент | Размер | Что содержит |
|-----------|--------|-------------|
| `orchestrator.py` | ~320 строк | Чистый wiring: imports, middleware, регистрация 28 роутеров, вызовы доменных init-функций, static files |
| `db/models.py` | ~200 строк (фасад) | Реэкспорт моделей из `modules/*/models.py` (54 модели) |
| `db/integration.py` | ~100 строк (фасад) | Импорт синглтонов и классов из `modules/*/service.py` под старыми именами |

### Что уже хорошо структурировано

| Компонент | Описание |
|-----------|----------|
| `app/routers/` | 28 фасадов-реэкспортов (1–3 строки), логика в `modules/*/router*.py` |
| `db/repositories/` | 45 файлов, чистая изоляция, `BaseRepository` с generic CRUD |
| `telegram_bot/`, `whatsapp_bot/` | Отдельные процессы, общаются через HTTP API |
| `app/services/` | Доменные сервисы (amoCRM, Wiki RAG, backup и др.) |
| `app/dependencies.py` | `ServiceContainer` — DI через FastAPI `Depends` |

---

## Модульная инфраструктура (`modules/`)

### Phase 0: Core (`modules/core/`)

> **Статус:** реализовано (PR [#497](https://github.com/ShaerWare/AI_Secretary_System/pull/497), issue [#490](https://github.com/ShaerWare/AI_Secretary_System/issues/490))

Фундамент для модульной декомпозиции. Три компонента, которые используются всеми доменными модулями.

```
modules/core/
├── __init__.py      ← реэкспорт EventBus, TaskRegistry, HealthRegistry, UserRoleChanged, SessionRevoked
├── events.py        ← EventBus + BaseEvent + domain events (ConnectivityStatus, InternetStatusChanged, UserRoleChanged, SessionRevoked)
├── tasks.py         ← TaskRegistry + TaskInfo
├── health.py        ← HealthRegistry + HealthStatus
├── startup.py       ← seed, setup_event_subscriptions(), init_internet_monitor, graceful_shutdown
└── internet_monitor.py  ← InternetMonitor (imports events from events.py)
```

### Импорт

```python
from modules.core import EventBus, BaseEvent, TaskRegistry, TaskInfo, HealthRegistry, HealthStatus
```

---

### EventBus

In-process асинхронная шина событий для развязки межмодульного взаимодействия.

**Принципы:**
- Обработчики — async callable, выполняются конкурентно через `asyncio.gather`
- Ошибки обработчиков **логируются**, но **не пробрасываются** к издателю
- `publish()` ожидает завершения всех обработчиков (не fire-and-forget)
- Типизированная маршрутизация — обработчик получает только события своего типа

**API:**

| Метод | Описание |
|-------|----------|
| `subscribe(event_type, handler)` | Подписка async обработчика на тип события |
| `publish(event)` | Публикация события всем подписчикам |
| `clear()` | Удаление всех обработчиков (для тестов) |

**Пример:**

```python
from dataclasses import dataclass
from modules.core import EventBus, BaseEvent

@dataclass
class UserCreated(BaseEvent):
    user_id: int
    username: str

bus = EventBus()

async def on_user_created(event: UserCreated):
    print(f"New user: {event.username} (id={event.user_id})")

bus.subscribe(UserCreated, on_user_created)
await bus.publish(UserCreated(user_id=42, username="alice"))
```

**Инфраструктура (Phase 5.1):**

- **Singleton:** `ServiceContainer.event_bus` (`app/dependencies.py`) — доступен через `get_container().event_bus`
- **Подписки:** регистрируются в `setup_event_subscriptions()` (`modules/core/startup.py`), вызывается при старте до инициализации сервисов
- **Каноническое место для событий:** `modules/core/events.py` (core events) и `modules/{domain}/events.py` (domain events)

**Действующие события:**

| Событие | Файл | Издатель | Подписчик |
|---------|------|----------|-----------|
| `InternetStatusChanged` | `modules/core/events.py` | `InternetMonitor` | — (GSM, future) |
| `UserRoleChanged` | `modules/core/events.py` | `WorkspaceService.update_member_role()` | `on_user_role_changed` → cache invalidation + session revocation |
| `SessionRevoked` | `modules/core/events.py` | `UserService` (password/role/deactivation), `WorkspaceService.remove_member()` | `on_session_revoked` → cache invalidation + session revocation |

---

### TaskRegistry

Реестр именованных фоновых задач с управлением жизненным циклом.

**Два типа задач:**
- **Периодические** (`interval=N`) — выполняются в цикле: run → sleep N секунд → repeat
- **Одноразовые** (`interval=None`) — выполняются один раз и завершаются

**Статусы:** `pending` → `running` → `completed` | `failed` | `cancelled`

**API:**

| Метод | Описание |
|-------|----------|
| `register(name, coro_fn, *, interval=None, initial_delay=0)` | Регистрация задачи |
| `start_all()` | Создание `asyncio.Task` для каждой зарегистрированной задачи |
| `cancel_all(timeout=10.0)` | Отмена всех задач с ожиданием завершения |
| `list_tasks()` → `list[TaskInfo]` | Информация о всех задачах |

**Поведение при ошибках:**
- Периодическая задача: ошибка логируется, задача продолжает работать
- Одноразовая задача: ошибка логируется, статус `failed`
- `CancelledError`: статус `cancelled`, исключение пробрасывается (корректное завершение)

**Пример:**

```python
from modules.core import TaskRegistry

registry = TaskRegistry()

async def cleanup_sessions():
    # удаление просроченных сессий
    ...

async def send_welcome_email():
    # одноразовая задача
    ...

registry.register("session-cleanup", cleanup_sessions, interval=3600)
registry.register("welcome-email", send_welcome_email, initial_delay=5)

await registry.start_all()   # запуск всех задач
# ...
await registry.cancel_all()  # graceful shutdown
```

---

### HealthRegistry

Реестр модульных health check-ов с агрегацией статусов.

**Логика агрегации:**
- Все `ok` → общий статус `ok`
- Хотя бы один `degraded` → общий статус `degraded`
- Хотя бы один `error` → общий статус `error`

**Защита:** каждый check выполняется с индивидуальным timeout (`asyncio.wait_for`). Таймаут или исключение → `error`.

**API:**

| Метод | Описание |
|-------|----------|
| `register(name, check)` | Регистрация async health check |
| `check_all(timeout=5.0)` → `dict` | Параллельный запуск всех проверок |

**Формат результата `check_all()`:**

```json
{
  "status": "ok | degraded | error",
  "checks": {
    "database": {"status": "ok", "details": {"tables": 54}},
    "redis": {"status": "degraded", "details": {"reason": "high latency"}}
  }
}
```

**Пример:**

```python
from modules.core import HealthRegistry, HealthStatus

registry = HealthRegistry()

async def check_database():
    # проверка подключения к БД
    return HealthStatus(status="ok", details={"tables": 54})

async def check_redis():
    # проверка Redis
    return HealthStatus(status="ok", details={"connected": True})

registry.register("database", check_database)
registry.register("redis", check_redis)

result = await registry.check_all(timeout=5.0)
print(result["status"])  # "ok"
```

---

### Phase 1: Доменные модели (`modules/*/models.py`)

> **Статус:** реализовано (PR [#499](https://github.com/ShaerWare/AI_Secretary_System/pull/499), issue [#491](https://github.com/ShaerWare/AI_Secretary_System/issues/491))

54 SQLAlchemy модели разнесены из монолитного `db/models.py` по доменным файлам. `db/models.py` стал фасадом-реэкспортом (~200 строк).

```
modules/
├── core/models.py           ← User, UserSession, Role, Workspace, SystemConfig, ...
├── chat/models.py           ← ChatSession, ChatMessage, ChatShare
├── knowledge/models.py      ← FAQEntry, KnowledgeDocument, KnowledgeCollection
├── channels/telegram/models.py  ← BotInstance, TelegramSession
├── channels/whatsapp/models.py  ← WhatsAppInstance
├── channels/widget/models.py    ← WidgetInstance
├── kanban/models.py         ← KanbanTask, KanbanTaskDependency, KanbanChecklistItem, ...
├── monitoring/models.py     ← AuditLog, PaymentLog
├── llm/models.py            ← CloudLLMProvider, LLMPreset
├── speech/models.py         ← TTSPreset
├── crm/models.py            ← AmoCRMConfig, AmoCRMSyncLog
├── ecommerce/models.py      ← WooCommerceConfig
├── telephony/models.py      ← GSMCallLog, GSMSMSLog
├── admin/models.py          ← ResourceShare
├── claude_code/models.py    ← ClaudeCodeConversation, ClaudeCodeProject
└── sales/models.py          ← BotAgentPrompt, BotSegment, BotUserProfile, ...
```

---

### Phase 2.1: Доменные сервисы (`modules/*/service.py`)

> **Статус:** реализовано (PR [#504](https://github.com/ShaerWare/AI_Secretary_System/pull/504), issue [#501](https://github.com/ShaerWare/AI_Secretary_System/issues/501))

31 менеджер-класс извлечён из `db/integration.py` в 15 доменных файлов. Именование: `AsyncXManager` → `XService`. Additive-only — `db/integration.py` пока не изменён.

| Модуль | Файл | Сервисы |
|--------|------|---------|
| `modules/core/` | `service.py` | `DatabaseService`, `UserService`, `UserSessionService`, `RoleService`, `WorkspaceService`, `ConfigService`, `UserIdentityService` |
| `modules/chat/` | `service.py` | `ChatService`, `ChatShareService` |
| `modules/knowledge/` | `service.py` | `FAQService`, `KnowledgeDocService`, `KnowledgeCollectionService`, `GitHubRepoProjectService` |
| `modules/channels/telegram/` | `service.py` | `BotInstanceService`, `TelegramSessionService` |
| `modules/channels/whatsapp/` | `service.py` | `WhatsAppInstanceService` |
| `modules/channels/widget/` | `service.py` | `WidgetInstanceService` |
| `modules/kanban/` | `service.py` | `KanbanService`, `KanbanProjectService` |
| `modules/claude_code/` | `service.py` | `ClaudeCodeService`, `ClaudeCodeProjectService` |
| `modules/llm/` | `service.py` | `CloudProviderService` |
| `modules/monitoring/` | `service.py` | `AuditService`, `PaymentService` |
| `modules/admin/` | `service.py` | `ResourceShareService` |
| `modules/speech/` | `service.py`, `streaming.py` | `PresetService`, `StreamingTTSManager` |
| `modules/crm/` | `service.py` | `AmoCRMService` |
| `modules/ecommerce/` | `service.py` | `WooCommerceService` |
| `modules/telephony/` | `service.py` | `GSMService` |

**Импорт:** `from modules.chat.service import chat_service` (прямой, предпочтительный) или `from db.integration import async_chat_manager` (backward-compatible алиас). Синглтоны создаются в доменных `service.py` и импортируются фасадом.

**Known issue — circular import:** доменные `__init__.py` **нельзя** использовать для реэкспорта сервисов. Цепочка: `db/models.py` → `modules/X/__init__.py` → `service.py` → `db/repositories` → `db/models.py` (цикл). Сервисы импортируются напрямую: `from modules.chat.service import ChatService`. Будет решено в Phase 3+ (устранение eager imports в `db/models.py`).

---

### Phase 2.2: Фасад `db/integration.py`

> **Статус:** реализовано (PR [#506](https://github.com/ShaerWare/AI_Secretary_System/pull/506), issue [#502](https://github.com/ShaerWare/AI_Secretary_System/issues/502))

Монолитный `db/integration.py` (2688 строк) заменён на ~100-строчный фасад. Файл импортирует классы и синглтоны из доменных модулей и реэкспортирует под старыми именами:

```python
from modules.chat.service import ChatService as AsyncChatManager
from modules.chat.service import chat_service as async_chat_manager
# ... 29 классов, 30 синглтонов, 3 lifecycle-функции
```

Ноль изменений в 28 файлах-потребителях.

---

### Phase 3.1: Синглтоны в доменных сервисах

> **Статус:** реализовано (PR [#516](https://github.com/ShaerWare/AI_Secretary_System/pull/516), issue [#508](https://github.com/ShaerWare/AI_Secretary_System/issues/508))

30 синглтонов перенесены из фасада `db/integration.py` в доменные `modules/*/service.py`. Каждый сервисный файл создаёт экземпляр с чистым именем:

```python
# modules/kanban/service.py
kanban_service = KanbanService()
kanban_project_service = KanbanProjectService()
```

Фасад теперь **импортирует** готовые синглтоны вместо создания:
```python
from modules.kanban.service import kanban_service as async_kanban_manager
```

Оба пути импорта ведут к одному объекту (`async_kanban_manager is kanban_service`).

---

### Phase 3.2: Роутеры — ecommerce, crm, telephony, speech

> **Статус:** реализовано (PR [#518](https://github.com/ShaerWare/AI_Secretary_System/pull/518), issue [#509](https://github.com/ShaerWare/AI_Secretary_System/issues/509))

6 «листовых» роутеров (без межроутерных зависимостей) перенесены из `app/routers/` в доменные модули. Все импорты из `db.integration` заменены на прямые импорты из доменных сервисов. Оригинальные файлы стали тонкими фасадами (1-3 строки).

| Старый файл | Новый файл | Ключевые изменения |
|---|---|---|
| `app/routers/woocommerce.py` | `modules/ecommerce/router.py` | 4 db.integration → domain imports |
| `app/routers/amocrm.py` | `modules/crm/router.py` | 4 db.integration → domain imports, dual router (`router` + `webhook_router`) |
| `app/routers/gsm.py` | `modules/telephony/router.py` | 9 inline db.integration → 2 top-level domain imports |
| `app/routers/tts.py` | `modules/speech/router_tts.py` | 1 db.integration → domain import |
| `app/routers/stt.py` | `modules/speech/router_stt.py` | Без изменений (0 db.integration imports) |
| `app/routers/services.py` | `modules/speech/router_services.py` | Без изменений (0 db.integration imports) |

Замены импортов:
- `async_audit_logger` → `audit_service` из `modules.monitoring.service`
- `async_knowledge_collection_manager` → `knowledge_collection_service` из `modules.knowledge.service`
- `async_knowledge_doc_manager` → `knowledge_doc_service` из `modules.knowledge.service`
- `async_woocommerce_manager` → `woocommerce_service` из `modules.ecommerce.service`
- `async_amocrm_manager` → `amocrm_service` из `modules.crm.service`
- `async_preset_manager` → `preset_service` из `modules.speech.service`
- `async_config_manager` (inline) → `config_service` из `modules.core.service`
- `async_gsm_manager` (inline) → `gsm_service` из `modules.telephony.service`

---

### Phase 3.3: Роутеры — kanban, claude_code, knowledge

> **Статус:** реализовано (PR [#520](https://github.com/ShaerWare/AI_Secretary_System/pull/520), issue [#510](https://github.com/ShaerWare/AI_Secretary_System/issues/510))

5 роутеров со сложными зависимостями перенесены в доменные модули. Все импорты из `db.integration` заменены на прямые импорты из доменных сервисов. Оригинальные файлы стали 1-строчными фасадами.

| Старый файл | Новый файл | Ключевые изменения |
|---|---|---|
| `app/routers/faq.py` | `modules/knowledge/router_faq.py` | 2 db.integration → domain imports |
| `app/routers/wiki_rag.py` | `modules/knowledge/router_wiki_rag.py` | 3 db.integration → domain imports |
| `app/routers/github_repos.py` | `modules/knowledge/router_github_repos.py` | 4 db.integration → domain imports |
| `app/routers/kanban.py` | `modules/kanban/router.py` | 5 top-level + 1 inline → 4 top-level domain imports |
| `app/routers/claude_code.py` | `modules/claude_code/router.py` | 8 inline → 2 top-level (claude_code_service, claude_code_project_service) |

Замены импортов:
- `async_audit_logger` → `audit_service` из `modules.monitoring.service`
- `async_faq_manager` → `faq_service` из `modules.knowledge.service`
- `async_knowledge_collection_manager` → `knowledge_collection_service` из `modules.knowledge.service`
- `async_knowledge_doc_manager` → `knowledge_doc_service` из `modules.knowledge.service`
- `async_github_repo_project_manager` → `github_repo_project_service` из `modules.knowledge.service`
- `async_kanban_manager` → `kanban_service` из `modules.kanban.service`
- `async_kanban_project_manager` → `kanban_project_service` из `modules.kanban.service`
- `async_claude_code_manager` → `claude_code_service` из `modules.claude_code.service`
- `async_claude_code_project_manager` → `claude_code_project_service` из `modules.claude_code.service`

Нюансы:
- **claude_code.py** — все 8 inline `from db.integration import` внутри функций заменены на 2 top-level import из доменного сервиса
- **kanban.py** — кросс-доменные зависимости: kanban → claude_code (cc-sessions), kanban → knowledge (dataset-sync/status/clear)
- **Lazy imports** из `app.services.*` и `app.dependencies` оставлены lazy (не часть Phase 3)

---

### Phase 3.4: Роутеры — channels + sales

> **Статус:** реализовано (PR [#530](https://github.com/ShaerWare/AI_Secretary_System/pull/530), issue [#511](https://github.com/ShaerWare/AI_Secretary_System/issues/511))

5 роутеров каналов и продаж перенесены в доменные модули. Все импорты из `db.integration` заменены на прямые импорты из доменных сервисов. Оригинальные файлы стали 1-строчными фасадами.

| Старый файл | Новый файл | Ключевые изменения |
|---|---|---|
| `app/routers/telegram.py` (1031 строк) | `modules/channels/telegram/router.py` | 6 db.integration → domain imports |
| `app/routers/whatsapp.py` (488 строк) | `modules/channels/whatsapp/router.py` | 3 db.integration → domain imports |
| `app/routers/widget.py` (434 строк) | `modules/channels/widget/router.py` | 4 db.integration → domain imports |
| `app/routers/bot_sales.py` (1003 строк) | `modules/sales/router_bot_sales.py` | 2 db.integration → domain imports |
| `app/routers/yoomoney_webhook.py` (119 строк) | `modules/sales/router_yoomoney.py` | 1 db.integration → domain import |

Замены импортов:
- `async_audit_logger` → `audit_service` из `modules.monitoring.service`
- `async_bot_instance_manager` → `bot_instance_service` из `modules.channels.telegram.service`
- `async_config_manager` → `config_service` из `modules.core.service`
- `async_payment_manager` → `payment_service` из `modules.monitoring.service`
- `async_resource_share_manager` → `resource_share_service` из `modules.admin.service`
- `async_telegram_manager` → `telegram_session_service` из `modules.channels.telegram.service`
- `async_whatsapp_instance_manager` → `whatsapp_instance_service` из `modules.channels.whatsapp.service`
- `async_widget_instance_manager` → `widget_instance_service` из `modules.channels.widget.service`

Нюансы:
- **bot_sales.py** — 13 прямых импортов из `db.repositories.*` оставлены как есть (не `db.integration`, вне скоупа Phase 3)
- **yoomoney_webhook.py** — 1 прямой импорт `BotInstanceRepository` оставлен как есть
- **Lazy imports** (`app.services.yoomoney_service`, `fastapi.responses.HTMLResponse`) оставлены lazy
- **Non-db imports** (`multi_bot_manager`, `whatsapp_manager`, `app.cors_middleware`) оставлены без изменений

---

### Phase 3.5: Роутеры — core + admin

> **Статус:** реализовано (PR [#532](https://github.com/ShaerWare/AI_Secretary_System/pull/532), issue [#512](https://github.com/ShaerWare/AI_Secretary_System/issues/512))

6 роутеров core/admin перенесены в доменные модули. Все импорты из `db.integration` заменены на прямые импорты из доменных сервисов. Оригинальные файлы стали 1-строчными фасадами.

| Старый файл | Новый файл | Ключевые изменения |
|---|---|---|
| `app/routers/auth.py` (182 строки) | `modules/core/router_auth.py` | 3 db.integration → domain imports |
| `app/routers/roles.py` (139 строк) | `modules/core/router_roles.py` | 2 db.integration → domain imports |
| `app/routers/workspace.py` (273 строки) | `modules/core/router_workspace.py` | 4 db.integration → domain imports |
| `app/routers/backup.py` (189 строк) | `modules/admin/router_backup.py` | Чистый перенос (0 db.integration imports) |
| `app/routers/legal.py` (637 строк) | `modules/admin/router_legal.py` | 1 inline db.integration → domain import |
| `app/routers/github_webhook.py` (317 строк) | `modules/admin/router_github_webhook.py` | 1 inline db.integration → domain import |

Замены импортов:
- `async_audit_logger` → `audit_service` из `modules.monitoring.service`
- `async_session_manager` → `user_session_service` из `modules.core.service`
- `async_user_manager` → `user_service` из `modules.core.service`
- `async_role_manager` → `role_service` из `modules.core.service`
- `async_workspace_manager` → `workspace_service` из `modules.core.service`
- `async_kanban_project_manager` → `kanban_project_service` из `modules.kanban.service`

Нюансы:
- **backup.py** — 0 импортов из `db.integration`, использует `app.services.backup_service` — чистый перенос без изменений
- **legal.py** — 1 inline `from db.integration import async_audit_logger` внутри `admin_gdpr_delete_data`, заменён на `from modules.monitoring.service import audit_service`
- **github_webhook.py** — 1 inline `from db.integration import async_kanban_project_manager` внутри `_handle_issue_event`, заменён на `from modules.kanban.service import kanban_project_service`

---

### Phase 3.6: Роутеры — monitoring, chat, llm

> **Статус:** реализовано (PR [#534](https://github.com/ShaerWare/AI_Secretary_System/pull/534), issue [#513](https://github.com/ShaerWare/AI_Secretary_System/issues/513))

Последние 5 роутеров перенесены в доменные модули. Все импорты из `db.integration` заменены на прямые импорты из доменных сервисов. **Все 28 роутеров мигрированы — Phase 3 завершена.**

| Старый файл | Новый файл | Ключевые изменения |
|---|---|---|
| `app/routers/audit.py` (126 строк) | `modules/monitoring/router_audit.py` | Чистый перенос (0 db.integration imports) |
| `app/routers/usage.py` (301 строка) | `modules/monitoring/router_usage.py` | Чистый перенос (0 db.integration imports) |
| `app/routers/monitor.py` (246 строк) | `modules/monitoring/router_monitor.py` | Чистый перенос (0 db.integration imports) |
| `app/routers/chat.py` (1176 строк) | `modules/chat/router.py` | 7 db.integration → domain imports |
| `app/routers/llm.py` (1633 строки) | `modules/llm/router.py` | 2 db.integration → domain imports |

Замены импортов (9):
- `async_chat_manager` → `chat_service` из `modules.chat.service`
- `async_chat_share_manager` → `chat_share_service` из `modules.chat.service`
- `async_bot_instance_manager` → `bot_instance_service` из `modules.channels.telegram.service`
- `async_whatsapp_instance_manager` → `whatsapp_instance_service` из `modules.channels.whatsapp.service`
- `async_widget_instance_manager` → `widget_instance_service` из `modules.channels.widget.service`
- `async_cloud_provider_manager` → `cloud_provider_service` из `modules.llm.service`
- `async_knowledge_collection_manager` → `knowledge_collection_service` из `modules.knowledge.service`
- `async_audit_logger` → `audit_service` из `modules.monitoring.service`

Нюансы:
- **audit.py, usage.py, monitor.py** — 0 импортов из `db.integration`, чистый перенос
- **chat.py** — SSE streaming + RAG логика, 7 кросс-доменных импортов (telegram, whatsapp, widget, knowledge, llm)
- **llm.py** — крупнейший роутер (1633 строки, 37 routes), inline `db.repositories` / `db.database` импорты оставлены как есть
- **monitor.py** — условная регистрация в cloud mode, условие остаётся в `orchestrator.py`

---

## Phase 4: Декомпозиция orchestrator.py

### Phase 4.1: StreamingTTSManager → modules/speech/streaming.py

> **Статус:** реализовано (PR [#564](https://github.com/ShaerWare/AI_Secretary_System/pull/564), issue [#546](https://github.com/ShaerWare/AI_Secretary_System/issues/546))

Класс `StreamingTTSManager` (220 строк) извлечён из `orchestrator.py` в `modules/speech/streaming.py`. Менеджер обеспечивает параллельный синтез TTS во время streaming LLM: накапливает текст, разбивает на предложения, синтезирует в `ThreadPoolExecutor`, кэширует склеенное аудио.

**Ключевые решения:**
- `numpy` — lazy import внутри `_cache_full_audio()` (избегает ошибок импорта в cloud mode без GPU)
- Глобальная переменная `streaming_tts_manager` перенесена в `ServiceContainer` (Phase 4.7b)
- `synthesize_with_current_voice()` перенесена в `modules/compat/router.py` в Phase 4.3 (переписана на `get_container()`)
- 5 неиспользуемых импортов удалены из orchestrator (`hashlib`, `re`, `OrderedDict`, `ThreadPoolExecutor`, `numpy`)

**Результат:** orchestrator.py: 4287 → 4062 строк (−225)

---

### Phase 4.2: Widget public endpoints → modules/channels/widget/router_public.py

> **Статус:** реализовано (PR [#566](https://github.com/ShaerWare/AI_Secretary_System/pull/566), issue [#547](https://github.com/ShaerWare/AI_Secretary_System/issues/547))

6 публичных (без auth) widget endpoints + 4 helper-функции извлечены из `orchestrator.py` в `modules/channels/widget/router_public.py`.

**Endpoints:**
- `GET /widget.js` — динамическая генерация JS-скрипта
- `GET /widget/status` — проверка enabled
- `POST /widget/chat/session` — создание сессии
- `GET /widget/chat/session/{id}` — получение с историей
- `POST /widget/chat/session/{id}/stream` — SSE стриминг ответа
- `POST /widget/chat/session/{id}/contacts` — контакты → amoCRM

**Ключевые решения:**
- Импорты модернизированы: `async_*_manager` → domain singletons (`widget_instance_service`, `chat_service`, `config_service`, `cloud_provider_service`, `user_identity_service`)
- amoCRM helpers оставлены lazy (try/except) для graceful degradation
- Widget path: `Path(__file__).parents[3]` (учитывает глубину модуля)
- 4 неиспользуемых импорта удалены из orchestrator

**Результат:** orchestrator.py: 4062 → 3544 строк (−518)

---

### Phase 4.3: Legacy/compat + core health → modules/compat/ + modules/core/

> **Статус:** реализовано (PR [#568](https://github.com/ShaerWare/AI_Secretary_System/pull/568), issue [#548](https://github.com/ShaerWare/AI_Secretary_System/issues/548))

Извлечены legacy telephony, OpenAI-compatible и core health endpoints из `orchestrator.py`.

**modules/compat/router.py** (~510 строк):
- 5 Pydantic-моделей (`ConversationRequest`, `TTSRequest`, `OpenAISpeechRequest`, `ChatMessage`, `ChatCompletionRequest`)
- `synthesize_with_current_voice()` — хелпер выбора TTS-движка (переписан на `get_container()`)
- 5 legacy telephony endpoints: `POST /tts`, `POST /stt`, `POST /chat`, `POST /process_call`, `POST /reset_conversation`
- 4 OpenAI-compatible endpoints: `GET /v1/models`, `GET /v1/voices`, `POST /v1/audio/speech`, `POST /v1/chat/completions`

**modules/core/router_health.py** (~110 строк):
- `GET /` — root status
- `GET /health` — полная диагностика (services, database, internet monitor, streaming TTS stats)
- `GET /admin/deployment-mode` — текущий профиль

**Ключевые решения:**
- Все обращения к глобальным переменным (`voice_service`, `llm_service`, `stt_service` и т.д.) заменены на `get_container()` → `container.*`
- Удалены 4 мёртвых дубликата (3 auth endpoints + `/admin/status`), которые были перекрыты роутерами, зарегистрированными раньше
- `DEPLOYMENT_MODE` читается из `os.getenv()` в каждом модуле (без зависимости от глобала в orchestrator)

**Результат:** orchestrator.py: 3544 → 2875 строк (−669)

---

### Phase 4.4: Finetune endpoints → modules/llm/ + modules/speech/

> **Статус:** реализовано (PR [#570](https://github.com/ShaerWare/AI_Secretary_System/pull/570), issue [#549](https://github.com/ShaerWare/AI_Secretary_System/issues/549))

Извлечены все LLM и TTS finetune endpoints из `orchestrator.py`.

**modules/llm/router_finetune.py** (~260 строк):
- 4 Pydantic-модели (`DatasetProcessRequest`, `GenerateProjectDatasetRequest`, `FinetuneConfigRequest`, `AdapterRequest`)
- 17 эндпоинтов: dataset (upload, process, config, stats, list, augment, generate-project), training (config, start, stop, status, log), adapters (list, activate, delete)
- Prefix: `/admin/finetune`

**modules/speech/router_finetune.py** (~150 строк):
- 13 эндпоинтов: config, samples (list, upload, delete, transcript), transcribe, prepare, processing-status, train (start, stop, status, log), models
- Prefix: `/admin/tts-finetune`
- `tts_finetune_manager` — optional import (try/except)

**Ключевые решения:**
- Оба роутера регистрируются только при `DEPLOYMENT_MODE != "cloud"` (GPU-only), внутри существующего `if`-блока
- Эндпоинты не зависят от глобальных сервисов (`voice_service`, `llm_service`) — работают через свои менеджеры
- Удалены из orchestrator: `get_finetune_manager`, `get_tts_finetune_manager`, `TTS_FINETUNE_AVAILABLE`, `File`, `UploadFile`

**Результат:** orchestrator.py: 2875 → 2471 строк (−404)

### Phase 4.5: Remaining admin endpoints → modules/speech/ + modules/llm/ + modules/monitoring/

> **Статус:** реализовано (PR [#572](https://github.com/ShaerWare/AI_Secretary_System/pull/572), issue [#550](https://github.com/ShaerWare/AI_Secretary_System/issues/550))

Извлечены ВСЕ оставшиеся inline-эндпоинты из `orchestrator.py`. После этой фазы в файле **ноль** `@app.get/post/put/delete` — остались только `@app.on_event("startup")` и `@app.on_event("shutdown")`.

**modules/speech/router_voices.py** (~205 строк):
- `VoiceRequest` Pydantic-модель
- 4 эндпоинта: `GET /admin/voices`, `GET /admin/voice`, `POST /admin/voice`, `POST /admin/voice/test`
- Все используют `get_container()` вместо глобальных переменных

**modules/llm/router_models.py** (~113 строк):
- 10 эндпоинтов: list, scan (start/cancel/status), download (start/cancel/status), delete, search, details
- Prefix: `/admin/models`
- Использует `get_model_manager()`

**modules/monitoring/router_logs.py** (~53 строки):
- 3 эндпоинта: list, read, stream (SSE)
- Prefix: `/admin/logs`
- SSE streaming использует `require_permission("system", "view")`

**Что удалено из orchestrator.py:**
- 52 inline-эндпоинта (35 мёртвых дубликатов + 17 уникальных)
- 18 Pydantic-моделей (все продублированы в модульных роутерах)
- `get_current_tts_service()` helper
- 16 неиспользуемых импортов

**Ключевые решения:**
- `router_voices.py` и `router_models.py` регистрируются внутри `if DEPLOYMENT_MODE != "cloud"` (GPU-only)
- `router_logs.py` регистрируется безусловно (доступен во всех режимах)
- 35 из 52 эндпоинтов были мёртвыми дубликатами (shadowed модульными роутерами, зарегистрированными ранее)

**Результат:** orchestrator.py: 2471 → 1121 строк (−1350). Содержит: импорты, middleware, регистрацию роутеров, startup/shutdown lifecycle, раздачу статических файлов.

### Phase 4.6: Background tasks → TaskRegistry

> **Статус:** реализовано (PR [#578](https://github.com/ShaerWare/AI_Secretary_System/pull/578), issue [#551](https://github.com/ShaerWare/AI_Secretary_System/issues/551))

Перенос 6 фоновых задач из `asyncio.create_task()` в `TaskRegistry` (инфраструктура Phase 0).

**Новые файлы:**

| Файл | Задачи | Тип |
|------|--------|-----|
| `modules/core/maintenance.py` | `cleanup_expired_sessions` (1ч), `periodic_vacuum` (7д, initial_delay=24ч) | periodic |
| `modules/knowledge/tasks.py` | `build_wiki_embeddings`, `load_collection_indexes` | one-shot |
| `modules/kanban/tasks.py` | `sync_kanban_issues` (15мин, initial_delay=60с) | periodic |
| `modules/ecommerce/tasks.py` | `woocommerce_daily_sync` (ежедневно 23:00 UTC) | one-shot с внутренним cron |

**Ключевые решения:**
- WooCommerce sync зарегистрирован как one-shot (управляет своим расписанием внутри), т.к. TaskRegistry не поддерживает cron
- Wiki RAG задачи используют `functools.partial(fn, wiki_rag)` для передачи сервиса
- Core maintenance в отдельном `maintenance.py` (не `tasks.py`), чтобы не путать с инфраструктурой TaskRegistry
- `task_registry.cancel_all()` добавлен в `shutdown_event()` для graceful shutdown

**Результат:** orchestrator.py: 1121 → 1030 строк (−91). Удалены `asyncio`, `datetime`, `timedelta` из импортов.

### Phase 4.7a: Startup helpers → modules/*/startup.py + graceful shutdown

> **Статус:** реализовано (PR [#583](https://github.com/ShaerWare/AI_Secretary_System/pull/583), issue [#580](https://github.com/ShaerWare/AI_Secretary_System/issues/580))

Извлечение 8 helper-функций из `orchestrator.py` в доменные `startup.py` модули + добавление graceful shutdown.

**Новые файлы:**

| Файл | Функции |
|------|---------|
| `modules/core/startup.py` | `seed_system_roles()`, `seed_default_workspace()` |
| `modules/llm/startup.py` | `get_or_create_default_gemini_provider()`, `auto_start_bridge()` |
| `modules/channels/telegram/startup.py` | `auto_start_bots()` |
| `modules/channels/whatsapp/startup.py` | `auto_start_bots()` |
| `modules/knowledge/startup.py` | `reload_llm_faq(container)` |
| `modules/speech/startup.py` | `reload_voice_presets(container)` |

**Ключевые решения:**
- `reload_llm_faq` и `reload_voice_presets` принимают `container` как аргумент (вместо глобальных переменных), вызываются после заполнения контейнера
- Graceful shutdown в `shutdown_event()`: `multi_bot_manager.stop_all()`, `whatsapp_manager.stop_all()`, `bridge_manager.stop()` — каждый в try/except
- 5 неиспользуемых импортов удалены из `db.integration`

**Результат:** orchestrator.py: 1030 → 805 строк (−225, −22%).

### Phase 4.7b: Модульная инициализация сервисов + удаление глобалов

> **Статус:** реализовано (PR [#585](https://github.com/ShaerWare/AI_Secretary_System/pull/585), issue [#581](https://github.com/ShaerWare/AI_Secretary_System/issues/581))

Вынос всей inline-инициализации сервисов из `startup_event()` в доменные startup-модули. Удаление 8 глобальных переменных — `ServiceContainer` стал единственным источником правды.

**Новые/расширенные файлы:**

| Файл | Функции |
|------|---------|
| `modules/speech/startup.py` | `init_tts_services(deployment_mode)`, `init_stt_service()`, `init_streaming_tts_manager()` |
| `modules/llm/startup.py` | `init_llm_service(llm_backend)` → (service, backend), `create_llm_switch_callback(container)` |
| `modules/knowledge/startup.py` | `init_wiki_rag(container, deployment_mode, task_registry)` |
| `modules/core/startup.py` | `init_internet_monitor(container, deployment_mode)`, `check_legacy_files()`, `graceful_shutdown()` |
| `modules/telephony/startup.py` | `init_gsm_services(container, deployment_mode)` |

**Ключевые решения:**
- `_switch_llm` callback переделан в фабрику замыканий `create_llm_switch_callback(container)` — записывает только в `container.llm_service` и `os.environ["LLM_BACKEND"]`, глобальные переменные не используются
- Optional imports (`VLLM_AVAILABLE`, `PIPER_AVAILABLE`, `XTTS_AVAILABLE`, `OPENVOICE_AVAILABLE`) перенесены в соответствующие domain startup модули
- `init_tts_services()` возвращает dict с ключами, совпадающими с атрибутами `ServiceContainer`
- `init_llm_service()` возвращает кортеж `(service, updated_backend)` для обновления `os.environ`

**Удалённые глобальные переменные:** `voice_service`, `anna_voice_service`, `piper_service`, `openvoice_service`, `stt_service`, `llm_service`, `streaming_tts_manager`, `current_voice_config`.

**Результат:** orchestrator.py: 805 → 321 строку (−60%). Чистый wiring: импорты, middleware, регистрация роутеров, вызовы доменных init-функций, static files.

---

## Phase 5: EventBus-события

### Phase 5.1: Инфраструктура EventBus + UserRoleChanged / SessionRevoked

> **Статус:** реализовано (PR [#623](https://github.com/ShaerWare/AI_Secretary_System/pull/623), issue [#617](https://github.com/ShaerWare/AI_Secretary_System/issues/617))

Первая реализация EventBus-паттерна в продакшене: инфраструктура (singleton в контейнере, setup_event_subscriptions) + два реальных события.

**Инфраструктура:**
- `event_bus: EventBus` добавлен в `ServiceContainer` (`app/dependencies.py`)
- `setup_event_subscriptions(event_bus)` в `modules/core/startup.py` — вызывается в `orchestrator.py` startup, регистрирует обработчики
- `InternetMonitor` теперь получает `container.event_bus` (раньше `None`)
- `ConnectivityStatus` и `InternetStatusChanged` перенесены из `internet_monitor.py` в `modules/core/events.py`

**События:**

| Событие | Издатель | Обработчик |
|---------|----------|------------|
| `UserRoleChanged` | `WorkspaceService.update_member_role()` | `_member_role_cache.invalidate_user()` + `revoke_all_user_sessions()` |
| `SessionRevoked` | `UserService.update_password()`, `set_role()`, `set_active()`, `WorkspaceService.remove_member()` | `_member_role_cache.invalidate_user()` + `revoke_all_user_sessions()` |

**Что убрано:**
- Прямые вызовы `_member_role_cache.invalidate_user()` и `revoke_all_user_sessions()` из `router_workspace.py`
- Прямой вызов `auth_manager.revoke_all_user_sessions()` из `UserService._revoke_user_sessions()`
- Метод `UserService._revoke_user_sessions()` заменён на `_publish_session_revoked()`

**Конвенция для следующих Phase 5.x:**
- События определяются в `modules/{domain}/events.py` (или `modules/core/events.py` для core)
- Подписки регистрируются в `setup_events()` функции в `startup.py` домена
- Издатель получает bus через `get_container().event_bus` (lazy import)

### Phase 5.2: KnowledgeUpdated event — FAQ cache reload

> **Статус:** реализовано (PR [#625](https://github.com/ShaerWare/AI_Secretary_System/pull/625), issue [#618](https://github.com/ShaerWare/AI_Secretary_System/issues/618))

Развязка доменов `knowledge` и `llm`: FAQ-роутер публикует `KnowledgeUpdated` событие, LLM-домен подписывается и перезагружает FAQ-кеш.

**Новый файл:** `modules/knowledge/events.py`

```python
@dataclass
class KnowledgeUpdated(BaseEvent):
    kind: str = ""      # "faq", "wiki", "collection"
    action: str = ""    # "created", "updated", "deleted", "reloaded"
    item_id: int | None = None
```

| Событие | Издатель | Обработчик |
|---------|----------|------------|
| `KnowledgeUpdated(kind="faq")` | FAQ CRUD в `router_faq.py` (add, update, delete, reload) | `setup_llm_event_subscriptions()` → reload FAQ cache в LLM service |

**Ключевые решения:**
- Startup FAQ reload (`modules/knowledge/startup.py:reload_llm_faq`) остаётся прямым вызовом — надёжность при инициализации
- Обработчик живёт в `modules/llm/startup.py` (рядом с LLM логикой), вызывается из `setup_event_subscriptions()`
- `/reload` и `/test` endpoints по-прежнему читают `container.llm_service` напрямую (view-layer, не coupling)
- Event generic — в будущем wiki/collection updates могут переиспользовать `KnowledgeUpdated`

---

## Тесты

33 unit-теста для core-инфраструктуры:

```bash
pytest tests/unit/test_event_bus.py tests/unit/test_event_subscriptions.py tests/unit/test_knowledge_events.py tests/unit/test_task_registry.py tests/unit/test_health_registry.py -v
```

| Файл | Тестов | Что покрывает |
|------|--------|---------------|
| `test_event_bus.py` | 11 | publish/subscribe, error isolation, type filtering, clear, UserRoleChanged, SessionRevoked |
| `test_event_subscriptions.py` | 3 | setup_event_subscriptions wiring — cache invalidation + session revocation via events |
| `test_knowledge_events.py` | 3 | KnowledgeUpdated → FAQ reload, non-faq ignored, event fields |
| `test_task_registry.py` | 8 | periodic/one-shot, cancel, errors, initial_delay, list |
| `test_health_registry.py` | 8 | aggregation (ok/degraded/error), timeout, exceptions |

---

## План модульной декомпозиции

> Полный план: issue [#489](https://github.com/ShaerWare/AI_Secretary_System/issues/489)
> Стратегия: **Strangler Fig** — новый код рядом со старым, постепенная миграция импортов, старые файлы → фасады-реэкспорты.

| Фаза | Описание | Issue | Статус |
|------|----------|-------|--------|
| **0** | Инфраструктура core (EventBus, TaskRegistry, HealthRegistry) | [#490](https://github.com/ShaerWare/AI_Secretary_System/issues/490) | ✅ Завершена |
| **1** | Разделение `db/models.py` → доменные модули | [#491](https://github.com/ShaerWare/AI_Secretary_System/issues/491) | ✅ Завершена |
| **2** | Разделение `db/integration.py` → доменные сервисы + фасад | [#492](https://github.com/ShaerWare/AI_Secretary_System/issues/492) | ✅ Завершена (#501, #502, #503) |
| **3** | Перенос роутеров в доменные модули | [#493](https://github.com/ShaerWare/AI_Secretary_System/issues/493) | ✅ Завершена (#508 ✅, #509 ✅, #510 ✅, #511 ✅, #512 ✅, #513 ✅, #514) |
| **4** | Декомпозиция `orchestrator.py` | [#494](https://github.com/ShaerWare/AI_Secretary_System/issues/494) | ✅ Завершена (4.1–4.7b) |
| **5** | Внедрение EventBus-событий | [#495](https://github.com/ShaerWare/AI_Secretary_System/issues/495) | 🔄 5.1 ✅ 5.2 ✅ |
| **6** | Протокольные интерфейсы | [#496](https://github.com/ShaerWare/AI_Secretary_System/issues/496) | ⏳ |

### Ключевые ограничения

1. **Alembic-миграции** — `db/models.py` остаётся как фасад-реэкспорт, чтобы не ломать `from db.models import ...` в существующих миграциях
2. **SQLAlchemy Base** — единый `Base` из `db/database.py` для всех доменных моделей (create_all, relationships, autogenerate)
3. **Cross-domain FK** — `workspace_id`, `owner_id → User.id` — нормальная зависимость "все зависят от core", FK сохраняются
4. **Параллельная разработка** — каждую фазу делает одна машина, мелкие PR с чёткими границами

---

← [[Database]] | [[Deployment-Profiles]] →

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

### Монолит (исторический)

| Компонент | Размер | Что содержит |
|-----------|--------|-------------|
| `orchestrator.py` | ~4100 строк | FastAPI entry point, инициализация сервисов, legacy endpoints, background tasks, регистрация 28 роутеров |
| `db/models.py` | ~200 строк (фасад) | Реэкспорт моделей из `modules/*/models.py` (54 модели) |
| `db/integration.py` | 93 строки (фасад) | Реэкспорт сервисов из `modules/*/service.py` под старыми именами + 30 синглтонов |

### Что уже хорошо структурировано

| Компонент | Описание |
|-----------|----------|
| `app/routers/` | 28 отдельных файлов роутеров |
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
├── __init__.py      ← реэкспорт EventBus, TaskRegistry, HealthRegistry
├── events.py        ← EventBus + BaseEvent
├── tasks.py         ← TaskRegistry + TaskInfo
└── health.py        ← HealthRegistry + HealthStatus
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
| `modules/speech/` | `service.py` | `PresetService` |
| `modules/crm/` | `service.py` | `AmoCRMService` |
| `modules/ecommerce/` | `service.py` | `WooCommerceService` |
| `modules/telephony/` | `service.py` | `GSMService` |

**Импорт:** `from modules.chat.service import ChatService` (прямой) или `from db.integration import async_chat_manager` (backward-compatible синглтон).

**Known issue — circular import:** доменные `__init__.py` **нельзя** использовать для реэкспорта сервисов. Цепочка: `db/models.py` → `modules/X/__init__.py` → `service.py` → `db/repositories` → `db/models.py` (цикл). Сервисы импортируются напрямую: `from modules.chat.service import ChatService`. Будет решено в Phase 3+ (устранение eager imports в `db/models.py`).

---

### Phase 2.2: Фасад `db/integration.py`

> **Статус:** реализовано (PR [#506](https://github.com/ShaerWare/AI_Secretary_System/pull/506), issue [#502](https://github.com/ShaerWare/AI_Secretary_System/issues/502))

Монолитный `db/integration.py` (2688 строк) заменён на 93-строчный фасад. Файл импортирует сервисы из доменных модулей и реэкспортирует под старыми именами:

```python
from modules.chat.service import ChatService as AsyncChatManager
async_chat_manager = AsyncChatManager()
# ... 30 синглтонов, 3 lifecycle-функции
```

Ноль изменений в 28 файлах-потребителях.

---

## Тесты

24 unit-теста для core-инфраструктуры:

```bash
pytest tests/unit/test_event_bus.py tests/unit/test_task_registry.py tests/unit/test_health_registry.py -v
```

| Файл | Тестов | Что покрывает |
|------|--------|---------------|
| `test_event_bus.py` | 8 | publish/subscribe, error isolation, type filtering, clear |
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
| **3** | Перенос роутеров в доменные модули | [#493](https://github.com/ShaerWare/AI_Secretary_System/issues/493) | ⏳ |
| **4** | Декомпозиция `orchestrator.py` | [#494](https://github.com/ShaerWare/AI_Secretary_System/issues/494) | ⏳ |
| **5** | Внедрение EventBus-событий | [#495](https://github.com/ShaerWare/AI_Secretary_System/issues/495) | ⏳ |
| **6** | Протокольные интерфейсы | [#496](https://github.com/ShaerWare/AI_Secretary_System/issues/496) | ⏳ |

### Ключевые ограничения

1. **Alembic-миграции** — `db/models.py` остаётся как фасад-реэкспорт, чтобы не ломать `from db.models import ...` в существующих миграциях
2. **SQLAlchemy Base** — единый `Base` из `db/database.py` для всех доменных моделей (create_all, relationships, autogenerate)
3. **Cross-domain FK** — `workspace_id`, `owner_id → User.id` — нормальная зависимость "все зависят от core", FK сохраняются
4. **Параллельная разработка** — каждую фазу делает одна машина, мелкие PR с чёткими границами

---

← [[Database]] | [[Deployment-Profiles]] →

# RBAC (Роли и права доступа)

Динамическая система ролей с матрицей прав: 16 модулей × 3 уровня доступа.

**Доступ:** admin (управление ролями) / все (просмотр своих прав)

## Архитектура

### Слои доступа

| Слой | Где живёт | Что контролирует |
|------|-----------|-----------------|
| **Workspaces** | `workspaces` + `workspace_members` таблицы | Привязка пользователя к workspace + роль в нём |
| **RBAC роли** | `roles` + `role_permissions` таблицы | Модуль-уровень (16 модулей × 3 уровня) |
| **JWT** | `workspace_id` в payload токена | Определяет workspace для текущей сессии |

С PR #366 разрешение прав идёт через `workspace_members`: JWT содержит `workspace_id`, `MemberRoleCache` кеширует `(user_id, workspace_id) → role_name`, `PermissionsCache` кеширует `role_name → permissions`. Функция `get_role_for_legacy()` **удалена**.

Legacy роли (`users.role`) сохраняются для обратной совместимости. При первом запуске `_seed_default_workspace()` создаёт workspace id=1 и маппит всех существующих пользователей:

| Legacy роль | RBAC роль в workspace |
|-------------|-----------|
| `admin` | admin |
| `user` | operator |
| `web` | operator |
| `guest` | viewer |

### Уровни доступа

| Уровень | Числовое значение | Описание |
|---------|-------------------|----------|
| `view` | 1 | Только просмотр |
| `edit` | 2 | Просмотр + редактирование |
| `manage` | 3 | Полное управление (включая удаление, настройку) |

Уровни иерархические: `manage` включает `edit` и `view`. Функция `level_gte(user_level, required_level)` в `auth_manager.py` сравнивает уровни.

### 16 модулей

| Модуль | Описание |
|--------|----------|
| `dashboard` | Главная панель |
| `chat` | Чат с ИИ |
| `llm` | Настройки LLM |
| `speech` | TTS/STT (только full mode) |
| `faq` | FAQ система |
| `wiki` | Wiki RAG, база знаний |
| `channels` | Telegram, WhatsApp, виджеты |
| `sales` | Воронка продаж |
| `kanban` | Kanban-доска |
| `gsm` | GSM телефония (только full mode) |
| `system` | Системные настройки, логи, finetune |
| `audit` | Журнал аудита |
| `usage` | Статистика использования |
| `settings` | Настройки пользователя |
| `users` | Управление пользователями |
| `claude_code` | Claude Code терминал |

В облачном режиме (`DEPLOYMENT_MODE=cloud`) модули `speech` и `gsm` автоматически исключаются из permissions (фильтрация в `get_user_permissions()`, PR #428). Модуль `system` **остаётся** доступным — он покрывает логи и finetune, которые работают в cloud mode.

## Системные роли

При первом запуске система создаёт 4 системных роли (идемпотентно):

### Owner (Владелец)

Все 16 модулей → `manage`. Полный контроль над системой.

### Admin (Администратор)

Все 16 модулей → `manage`. Идентичен owner по правам, отличается по назначению (owner — собственник, admin — технический специалист).

### Operator (Оператор)

| Модули | Уровень |
|--------|---------|
| chat, llm, speech, faq, wiki, channels, sales, kanban | `edit` |
| audit, usage, dashboard | `view` |

Для повседневной работы с контентом и каналами. Не имеет доступа к системным настройкам, управлению пользователями, Claude Code.

### Viewer (Наблюдатель)

| Модули | Уровень |
|--------|---------|
| dashboard, chat, llm, faq, wiki, kanban, audit | `view` |

Только чтение ключевых модулей. Для демо-доступа и мониторинга.

## Пользовательские роли

Администраторы могут создавать свои роли с произвольным набором прав через API. Пользовательские роли (в отличие от системных) можно удалять.

## API

### Права текущего пользователя

```bash
GET /admin/auth/permissions
Authorization: Bearer <token>
```

**Ответ:**
```json
{
  "dashboard": "manage",
  "chat": "manage",
  "llm": "manage",
  "faq": "manage",
  "wiki": "manage",
  "channels": "manage",
  "sales": "manage",
  "kanban": "manage",
  "audit": "manage",
  "usage": "manage",
  "settings": "manage",
  "users": "manage",
  "claude_code": "manage"
}
```

В облачном режиме модули `speech`, `gsm`, `system` не включаются в ответ.

### Управление ролями (только admin)

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/admin/roles` | Список всех ролей с правами |
| POST | `/admin/roles` | Создать пользовательскую роль |
| GET | `/admin/roles/{id}` | Получить роль по ID |
| PUT | `/admin/roles/{id}` | Обновить роль (системные: можно менять права, нельзя удалять) |
| DELETE | `/admin/roles/{id}` | Удалить роль (только пользовательские, 400 для системных) |

### Создать роль

```bash
POST /admin/roles
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "support",
  "display_name": "Поддержка",
  "description": "Роль для сотрудников техподдержки",
  "permissions": {
    "chat": "edit",
    "faq": "edit",
    "wiki": "view",
    "channels": "view",
    "audit": "view"
  }
}
```

**Ответ (201):**
```json
{
  "id": 5,
  "name": "support",
  "display_name": "Поддержка",
  "description": "Роль для сотрудников техподдержки",
  "is_system": false,
  "created_at": "2026-02-22T07:00:00",
  "permissions": {
    "chat": "edit",
    "faq": "edit",
    "wiki": "view",
    "channels": "view",
    "audit": "view"
  }
}
```

### Обновить права роли

```bash
PUT /admin/roles/3
Authorization: Bearer <token>
Content-Type: application/json

{
  "permissions": {
    "chat": "manage",
    "faq": "edit",
    "wiki": "edit",
    "channels": "edit",
    "sales": "edit",
    "kanban": "edit",
    "audit": "view",
    "usage": "view",
    "dashboard": "view"
  }
}
```

При обновлении `permissions` старые записи полностью заменяются новыми.

## БД-структура

### Таблица `workspaces`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `id` | INTEGER PK | Автоинкремент (default workspace = 1) |
| `name` | VARCHAR(200) | Название workspace |
| `slug` | VARCHAR(100) UNIQUE | URL-slug |
| `owner_id` | INTEGER FK → users.id | Владелец (nullable) |
| `created_at` | DATETIME | Время создания |

### Таблица `workspace_members`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `id` | INTEGER PK | Автоинкремент |
| `workspace_id` | INTEGER FK → workspaces.id | Ссылка на workspace (CASCADE DELETE) |
| `user_id` | INTEGER FK → users.id | Ссылка на пользователя (CASCADE DELETE) |
| `role_name` | VARCHAR(50) FK → roles.name | RBAC-роль в workspace |
| `joined_at` | DATETIME | Время добавления |

Уникальный constraint: `(workspace_id, user_id)`. Индекс: `(user_id, workspace_id)`.

### Таблица `workspace_invites`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `id` | INTEGER PK | Автоинкремент |
| `workspace_id` | INTEGER FK → workspaces.id | Ссылка на workspace (CASCADE DELETE) |
| `email` | VARCHAR(255) | Email приглашаемого (nullable) |
| `invite_code` | VARCHAR(64) UNIQUE | Код приглашения |
| `role_name` | VARCHAR(50) FK → roles.name | Роль при вступлении (default: viewer) |
| `created_by` | INTEGER FK → users.id | Кто создал приглашение |
| `expires_at` | DATETIME | Срок действия (nullable) |
| `used_at` | DATETIME | Когда использовано |
| `used_by` | INTEGER FK → users.id | Кто использовал |

### Таблица `roles`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `id` | INTEGER PK | Автоинкремент |
| `name` | VARCHAR(50) UNIQUE | Уникальное имя роли |
| `display_name` | VARCHAR(200) | Отображаемое имя |
| `description` | TEXT | Описание |
| `is_system` | BOOLEAN | Системная роль (нельзя удалить) |
| `created_at` | DATETIME | Время создания |

### Таблица `role_permissions`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `id` | INTEGER PK | Автоинкремент |
| `role_id` | INTEGER FK → roles.id | Ссылка на роль (CASCADE DELETE) |
| `module` | VARCHAR(50) | Имя модуля |
| `level` | VARCHAR(10) | Уровень: view / edit / manage |

Уникальный индекс: `(role_id, module)` — один модуль на роль.

### workspace_id на ресурсных таблицах

13 ресурсных таблиц имеют колонку `workspace_id INTEGER NOT NULL DEFAULT 1` с FK на `workspaces.id` (миграция `0010`, PR #368):

| Таблица | Композитный индекс |
|---------|-------------------|
| `chat_sessions` | `(workspace_id, owner_id)` |
| `bot_instances` | `(workspace_id, owner_id)` |
| `widget_instances` | `(workspace_id, owner_id)` |
| `whatsapp_instances` | `(workspace_id, owner_id)` |
| `cloud_llm_providers` | `(workspace_id, owner_id)` |
| `tts_presets` | `(workspace_id, owner_id)` |
| `knowledge_documents` | `(workspace_id, owner_id)` |
| `knowledge_collections` | `(workspace_id, id)` |
| `claude_code_sessions` | `(workspace_id, owner_id)` |
| `faq_entries` | `(workspace_id, id)` |
| `kanban_tasks` | `(workspace_id, id)` |
| `kanban_projects` | `(workspace_id, id)` |
| `amocrm_config` | `(workspace_id, id)` |

Все существующие записи заполнены значением `workspace_id = 1` (default workspace). Фильтрация по `workspace_id` в WHERE-запросах — этап 6c (#365).

**Прогресс 6c:**
- [x] **6c-0**: Инфраструктура — `BaseRepository._apply_workspace_filter()`, `workspace_context()` (#376, PR #383)
- [x] **6c-1**: **Chat** — первый модуль с workspace-фильтрацией, эталон для остальных (#377, PR #385)
- [x] **6c-2**: **Channels** — Telegram, WhatsApp, Widget (#378, PR #387)
- [x] **6c-3**: **AI/LLM** — Cloud LLM Providers + TTS Presets (#379, PR #389)
- [x] **6c-4**: **Knowledge/FAQ** — Knowledge Documents, Collections, FAQ Entries (#380, PR #391)
- [x] **6c-5**: **System/Kanban/amoCRM** — Kanban Tasks & Projects, Claude Code Sessions, amoCRM Config (#381, PR #393). Audit excluded (no workspace_id)
- [x] **6c-6**: Финализация — аудит, gate-check на мутациях, документация (#382, PR #395)

Bot-scoped таблицы (`telegram_sessions`, `bot_agent_prompts`, `bot_quiz_questions` и др.) **не** содержат `workspace_id` — они фильтруются через `bot_instances.workspace_id`.

### Этап 8: Инвайт-система + UI workspace (#330)

**8-1: Управление участниками workspace** (PR #406, Issue #398) — ✅ Done

Backend — новый роутер `app/routers/workspace.py` (prefix `/admin/workspace`):

| Метод | Путь | Доступ | Описание |
|-------|------|--------|----------|
| GET | `/admin/workspace` | users:view | Информация о текущем workspace |
| GET | `/admin/workspace/members` | users:view | Список участников с данными пользователя |
| PUT | `/admin/workspace/members/{user_id}/role` | users:manage | Смена роли участника |
| DELETE | `/admin/workspace/members/{user_id}` | users:manage | Удаление участника |

Бизнес-правила:
- Нельзя менять роль себе и owner
- Нельзя удалить себя и owner
- Валидация `role_name` через `async_role_manager.get_by_name()`
- Инвалидация `MemberRoleCache` после смены роли
- `revoke_all_user_sessions()` после удаления участника
- Audit log на все мутации

Frontend — `UsersView.vue` (`/admin/#/users`):
- Карточка workspace (название, количество участников, дата создания)
- Таблица участников: имя, логин, роль (dropdown для manage), дата входа, статус (active/inactive)
- Crown-бейдж на владельце, dropdown и remove disabled для self и owner
- Demo-мок: `admin/src/api/demo/workspace.ts`
- i18n: ru/en/kk (секция `users`)

**8-2: Инвайт-система** (PR #408, Issue #399) — ✅ Done

Миграция: `0012` — `max_uses` (nullable) и `used_count` на `workspace_invites`.

Модель `WorkspaceInvite`:
- `to_dict()` — сериализация с `is_valid`
- `@property is_valid` — проверка expiry + max_uses

Backend — 5 новых эндпоинтов в `app/routers/workspace.py`:

| Метод | Путь | Доступ | Описание |
|-------|------|--------|----------|
| POST | `/admin/workspace/invites` | users:manage | Создать инвайт (role_name, email?, max_uses?, expires_hours?) |
| GET | `/admin/workspace/invites` | users:manage | Список инвайтов workspace |
| DELETE | `/admin/workspace/invites/{id}` | users:manage | Удалить инвайт |
| GET | `/admin/workspace/invites/{code}/info` | **Public** | Информация для страницы принятия |
| POST | `/admin/workspace/invites/accept` | **Public + rate limit** | Регистрация по инвайту (auto-login) |

Бизнес-правила:
- Нельзя создать инвайт на роль "owner"
- Accept: валидация username (regex `^[a-zA-Z0-9_.\-]+$`), пароль min 6 символов
- Rate limit на accept (RATE_LIMIT_AUTH)
- Accept возвращает JWT — auto-login, redirect на `/chat`
- Invite code: `secrets.token_urlsafe(32)` (256 бит)

Frontend:
- `InviteDialog.vue` — модалка создания инвайта (роль, email, max_uses, expires), копирование URL
- `InviteView.vue` — публичная страница `/invite/:code` (регистрация)
- Секция "Invites" в `UsersView.vue` — таблица инвайтов, создание, удаление, копирование ссылки
- Demo-мок: invite CRUD, info, accept
- i18n: ru/en/kk (секции `invites` + `invite`)

**Этап 8 завершён. Вся RBAC-система (#322) полностью реализована.**

### Security-фиксы аудита (PR #418, Issue #411)

Быстрые исправления по результатам аудита #315:

| # | Проблема | Фикс |
|---|----------|------|
| C2 | `api.upload()` не передавал JWT-токен | Добавлен `headers: getAuthHeaders()` в `client.ts:upload()` |
| C2+ | `stt.ts:transcribe()` — та же проблема | Добавлен `getAuthHeaders()` в fetch |
| C3 | TTS preset UPDATE без проверки workspace | Добавлен `workspace_context()` в `tts.py`, `workspace_id` в `preset.py:update_preset()` |
| L3 | `POST /change-password` без rate-limit | Добавлен `@limiter.limit(RATE_LIMIT_AUTH)` |

### Security-фиксы аудита — средние (PR #420, Issue #412)

| # | Проблема | Фикс |
|---|----------|------|
| C1 | Consent grant-эндпоинты под `/admin/` без auth, но вызываются виджетами/ботами | Перенесены на публичный путь: `/admin/legal/consents/grant*` → `/legal/consents/grant*`. `GET /admin/legal/consents/check/{user_id}` — добавлен `require_permission("settings", "view")` |
| H3 | Legacy fallback `admin/admin` при ошибке БД | `except Exception` в `authenticate_user()` теперь возвращает `None`, не падает в фоллбэк. Legacy вход только при `user_count == 0` (пустая БД, первый запуск) |
| H5 | SSE-эндпоинты без JWT (backend) | Дубликат `GET /admin/monitor/gpu/stream` из `orchestrator.py` удалён (auth-версия в `monitor.py`). Добавлен `require_permission("system", "view")` на `GET /admin/logs/stream/{logfile}` и `GET /admin/finetune/train/log` |
| H5 | SSE-эндпоинты без JWT (frontend) | `createSSE()`, `useSSE`, `useRealtimeMetrics` переписаны с `EventSource` на `fetch + ReadableStream` — отправляют `Authorization: Bearer` заголовок. Polling fallback тоже с JWT. Auto-reconnect через 3 сек |

### Kanban owner_id — RBAC ownership (PR #424, Issue #414)

Kanban-задачи ранее использовали `created_by` (строка username) для проверки владения. Это ненадёжно: переименование пользователя ломает доступ, а строковое сравнение не использует FK-связи.

**Фикс:** добавлена колонка `owner_id` (INT FK → `users.id`) рядом с существующей `created_by`:

| Колонка | Тип | Назначение |
|---------|-----|-----------|
| `owner_id` | INTEGER FK → users.id | RBAC: контроль доступа, фильтрация видимости |
| `created_by` | VARCHAR | Аудит: кто создал (отображение, лог) |

**Изменения в логике:**
- Фильтр видимости: `KanbanTask.owner_id == user.id` (вместо `created_by == username`)
- Проверка владения при редактировании: `existing["owner_id"] != user.id` (вместо строкового сравнения)
- Проверка приватности при создании зависимостей: `target["owner_id"] != user.id`
- Создание задачи: `owner_id=user.id` передаётся вместе с `created_by=user.username`

**GitHub-синхронизированные задачи:** `owner_id=NULL` (нет локального пользователя), `created_by` — GitHub username. Эти задачи видны всем (т.к. `is_private=False`).

**Миграция 0013:** Добавляет колонку + FK + индекс, бэкфиллит `owner_id` из `created_by → users.username`.

### GDPR cascade delete (PR #426, Issue #415)

Эндпоинт `POST /admin/legal/gdpr/delete` ранее удалял только `user_consents`. Теперь выполняет полный каскад удаления/анонимизации данных пользователя.

**Два режима удаления:**

| Режим | Параметры | Кто удаляется |
|-------|-----------|--------------|
| Admin user | `user_id: int` | Администраторы, операторы (users.id) |
| External contact | `provider + provider_uid` | Telegram/WhatsApp/Widget контакты |

**Admin user — действия:**

| Действие | Таблицы |
|----------|---------|
| DELETE | `user_sessions`, `chat_sessions` (messages cascade FK), `claude_code_sessions`, `user_consents` |
| SET NULL owner_id | `bot_instances`, `widget_instances`, `whatsapp_instances`, `cloud_llm_providers`, `tts_presets`, `knowledge_documents`, `kanban_tasks`, `workspace_invites` |
| ANONYMIZE | `audit_log` (user_id→"gdpr-deleted", user_ip→"0.0.0.0"), `usage_log` (source_id→"gdpr-deleted") |

**External contact — действия:**

| Действие | Таблицы |
|----------|---------|
| DELETE | `bot_user_profiles`, `bot_subscribers`, `bot_discovery_responses`, `bot_followup_queue`, `bot_events`, `telegram_sessions`, `user_consents`, `chat_sessions`, `user_sessions`, `user_identities`, `users` (role=contact) |
| ANONYMIZE | `payment_log` (username→"gdpr-deleted"), `audit_log` (user_id→"gdpr-deleted", user_ip→"0.0.0.0") |

**Ключевые решения:**
- `audit_log` и `payment_log` **анонимизируются**, не удаляются — требование бухгалтерского и аудит-учёта
- Ресурсы (боты, виджеты, провайдеры) **сохраняются** с `owner_id=NULL` — рабочая конфигурация не теряется
- Для контактов: `user_consents.user_id` может быть в разных форматах (`"123"`, `"telegram:123"`), удаление пробует все варианты
- Защита от самоудаления: нельзя удалить текущего пользователя
- Событие логируется в `audit_log` **до** удаления данных

**Сервис:** `app/services/gdpr_service.py` — две функции `delete_admin_user_data()` и `delete_contact_data()`, возвращают отчёт `{table: count}`.

### Deployment mode — формализация в модели доступа (PR #428, Issue #416)

`DEPLOYMENT_MODE` (full/cloud/local) ограничивает доступ к hardware-модулям ортогонально RBAC-ролям. Три уровня защиты:

| Слой | Механизм | Где |
|------|----------|-----|
| 1. Роутеры | Hardware-роутеры не регистрируются в cloud mode → FastAPI 404 | `orchestrator.py` |
| 2. Permissions | `speech`/`gsm` исключаются из `get_user_permissions()` → `require_permission()` вернёт 403 | `auth_manager.py` |
| 3. Frontend | `meta.localOnly` + `isCloudMode` guard скрывают UI | `router.ts`, `auth.ts` |

**До PR #428:** фильтрация была только в HTTP-ответе `GET /admin/auth/permissions` (post-hoc `pop()`). `require_permission()` использовал полные permissions из БД — если бы hardware-роутер случайно зарегистрировался, auth его пропустил бы.

**После PR #428:** фильтрация перенесена в `get_user_permissions()` — единый источник для всех потребителей (HTTP endpoint, `require_permission()`, `workspace_context()`).

**Модуль `system` оставлен в cloud mode** — покрывает `/admin/logs/stream/{logfile}` и `/admin/finetune/train/log`, которые работают без hardware.

**Баг-фикс:** `PermissionsCache.get()` возвращал ссылку на кешированный dict. `pop()` мутировал кеш — после первого запроса в cloud mode модули навсегда исчезали из кеша для всех последующих запросов. Теперь возвращается копия.

### `owner_id = NULL` — семантика (Issue #417, design decision)

Колонка `owner_id` (FK → users.id, nullable) присутствует в 8 моделях. Значение `NULL` перегружено — означает одновременно «создано админом», «системный ресурс» и «legacy-данные». Это осознанное проектное решение, а не баг.

**Как работает `workspace_context()`:**

| Уровень прав | `owner_id` | Видимость |
|-------------|-----------|-----------|
| manage (admin) | `None` при создании | Видит все ресурсы workspace |
| edit (user) | `user.id` при создании | Видит свои + shared (NULL) |

**Фильтрация в репозиториях:**
```python
query.where((Model.owner_id == owner_id) | (Model.owner_id.is_(None)))
```

Non-admin видит: свои ресурсы + все ресурсы с `owner_id=NULL` (shared).

**Семантика NULL по контексту:**

| Ситуация | owner_id | Причина |
|----------|----------|---------|
| Админ создал ресурс | NULL | `workspace_context()` → None для manage-level |
| Legacy-данные (до multi-user) | NULL | Колонка не существовала |
| Builtin TTS preset | NULL | Системный пресет |
| GitHub-синхронизированная задача | NULL | Нет локального пользователя |

**Исключения из паттерна:**
- `ClaudeCodeSession` — `owner_id` NOT NULL, всегда заполнен
- `KanbanTask` — всегда `owner_id=user.id` (включая админов), видимость через `is_admin` параметр в `get_visible_tasks()`

**Известное ограничение:** админ не может создать приватный ресурс (виден только ему) — всё, что создаёт manage-level пользователь, автоматически shared в workspace. При текущем деплое (один workspace, 1-2 админа) это не проблема.

**Почему оставлено as-is:**
- Безопасность обеспечена `workspace_id` (изоляция между тенантами)
- Утечек между пользователями нет
- Альтернативы (добавление `is_shared` или `visibility` enum) требуют миграции 7 таблиц и изменения ~15 файлов — несоразмерно выгоде
- При появлении multi-admin сценария с приватными ресурсами — пересмотреть

### Security-фиксы аудита — CSP (PR #422, Issue #413)

JWT хранится в `localStorage` — доступен любому JS на странице. CSP-заголовок блокирует инъекцию скриптов через XSS, даже если DOMPurify обойдут.

**Content-Security-Policy** добавлен в `SecurityHeadersMiddleware` (`app/security_headers.py`):

```
default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
img-src 'self' data: https:; font-src 'self'; connect-src 'self';
frame-ancestors 'none'; object-src 'none'; base-uri 'self'
```

| Директива | Зачем |
|-----------|-------|
| `script-src 'self'` | Блокирует инъекцию скриптов — основная защита JWT |
| `style-src 'unsafe-inline'` | Vue `:style` bindings, виджет, chart.js требуют inline styles |
| `frame-ancestors 'none'` | Усиленная версия X-Frame-Options (CSP Level 2) |
| `object-src 'none'` | Блокирует Flash/Java plugins |
| `connect-src 'self'` | WebSocket, SSE, fetch — только same-origin |

Inline-скрипт Service Worker вынесен из `admin/index.html` в `admin/public/sw-cleanup.js` для совместимости с `script-src 'self'`.

Конфигурация: `CSP_ENABLED=false` env var для отключения отдельно от остальных security headers.

Существующая XSS-защита (без изменений): все 9 мест с `v-html` проходят через `DOMPurify.sanitize(marked.parse(...))`. DOMPurify 3.3.1, marked 17.0.2.

### Внешние контакты — user_identities

Контакты из Telegram, WhatsApp и виджетов автоматически становятся пользователями с привязанными `user_identities` (миграция `0011`, PR #370).

**Как работает:**
- При первом сообщении из канала вызывается `find_or_create(provider, provider_uid)` → создаётся пользователь с `username=NULL, password_hash=NULL, role=contact` и запись в `user_identities`
- При повторных сообщениях — обновляется `last_seen` и `display_name`/`metadata`
- Контактные пользователи **не могут** логиниться (`get_by_username` возвращает `None` для NULL username)

**Точки интеграции:**

| Канал | Где вызывается | provider | provider_uid |
|-------|---------------|----------|-------------|
| Telegram | `AsyncTelegramSessionManager.set_session()` в `db/integration.py` | `telegram` | chat_id |
| WhatsApp | `handle_text_message()` в `whatsapp_bot/handlers/messages.py` | `whatsapp` | phone (E.164) |
| Widget | `widget_create_session()` в `orchestrator.py` | `widget` | session_id |

**Таблица `user_identities`:**

| Колонка | Тип | Описание |
|---------|-----|----------|
| `id` | INTEGER PK | Автоинкремент |
| `user_id` | INTEGER FK → users.id | Ссылка на пользователя (CASCADE DELETE) |
| `provider` | VARCHAR(20) | `telegram` / `whatsapp` / `widget` |
| `provider_uid` | VARCHAR(255) | ID пользователя в канале |
| `display_name` | VARCHAR(200) | Отображаемое имя (nullable) |
| `metadata_json` | TEXT | JSON с доп. данными (nullable) |
| `created` | DATETIME | Время создания |
| `last_seen` | DATETIME | Последняя активность |

Уникальный constraint: `(provider, provider_uid)`. Индексы: `(user_id)`, `(provider, provider_uid)`.

**Изменения в таблице `users`** (миграция `0011`):
- `username` — стал nullable (contact-only users без логина)
- `password_hash` — стал nullable
- `email` — новая колонка (VARCHAR(255), nullable, unique)

**Код:**
- Модель: `UserIdentity` в `db/models.py`, связь `User.identities` (one-to-many)
- Репозиторий: `UserIdentityRepository` в `db/repositories/user_identity.py`
- Менеджер: `AsyncUserIdentityManager` в `db/integration.py` (синглтон `async_user_identity_manager`)
- `VALID_ROLES` в `user.py`: `("guest", "web", "user", "admin", "contact")`

## Статус миграции эндпоинтов

Миграция роутеров с legacy `get_current_user` / `require_admin` на `require_permission()` + `user_has_level()`.

| Роутер | Статус | PR |
|--------|--------|-----|
| `chat.py` (21 эндпоинт) | Мигрирован | #351 |
| `kanban.py` (15 эндпоинтов) | Мигрирован | #357 |
| `wiki_rag.py` (15 эндпоинтов) | Мигрирован | #355 |
| `telegram.py` (23 эндпоинта) | Мигрирован | #353 |
| `whatsapp.py` (10 эндпоинтов) | Мигрирован | #353 |
| `widget.py` (7 эндпоинтов) | Мигрирован | #353 |
| `llm.py` (42 эндпоинта) | Мигрирован | #352 |
| `tts.py` (14 эндпоинтов) | Мигрирован | #356 |
| `faq.py` (8 эндпоинтов) | Мигрирован | #355 |
| `usage.py` (8 эндпоинтов) | Мигрирован | #357 |
| `services.py` (6 эндпоинтов) | Мигрирован | #356 |
| `bot_sales.py` (43 эндпоинта) | Мигрирован | #354 |
| `amocrm.py` (26 эндпоинтов) | Мигрирован | #354 |
| `audit.py` (4 эндпоинта) | Мигрирован | #357 |
| `backup.py` (8 эндпоинтов) | Мигрирован | #356 |
| `monitor.py` (9 эндпоинтов) | Мигрирован | #356 |
| `stt.py` (4 эндпоинта) | Мигрирован | #356 |
| `gsm.py` (14 эндпоинтов) | Мигрирован | #356 |
| `claude_code.py` (4 эндпоинта) | Мигрирован | #357 |
| `legal.py` (4 эндпоинта) | Мигрирован | #357 |
| `auth.py` (9 эндпоинтов) | Утилитарный (self-service + inline fixes) | #357, #358 |
| `roles.py` (5 эндпоинтов) | Мигрирован | #358 |

### Матрица прав chat.py

| Эндпоинт | Уровень | Примечание |
|----------|---------|------------|
| `GET /sessions` | `view` | + `user_has_level(manage)` для видимости всех сессий |
| `POST /sessions` | `edit` | + `user_has_level(manage)` для owner_id |
| `POST /sessions/bulk-delete` | `manage` | |
| `GET /sessions/{id}` | `view` | + `user_has_level(manage)` для чужих |
| `PUT /sessions/{id}` | `edit` | через `_check_write_access` |
| `DELETE /sessions/{id}` | `edit` | через `_check_session_owner_or_admin` |
| `POST /messages` | `edit` | через `_check_write_access` |
| `POST /stream` | `edit` | через `_check_write_access` |
| `PUT /messages/{id}` | `edit` | через `_check_write_access` |
| `DELETE /messages/{id}` | `edit` | через `_check_write_access` |
| `POST /regenerate` | `edit` | через `_check_write_access` |
| `POST /summarize` | `edit` | + `user_has_level(manage)` |
| `GET /branches` | `view` | через `_get_branch_visible_ids` |
| `POST /branches/switch` | `view` | через `_get_branch_visible_ids` |
| `POST /branches/new` | `edit` | через `_check_write_access` |
| `GET /shares` | `edit` | через `_check_session_owner_or_admin` |
| `POST /shares` | `edit` | через `_check_session_owner_or_admin` |
| `PUT /shares/{id}` | `edit` | через `_check_session_owner_or_admin` |
| `DELETE /shares/{id}` | `edit` | через `_check_session_owner_or_admin` |
| `POST /fork` | `edit` | + `user_has_level(manage)` |
| `GET /shareable-users` | `view` | |

### Матрица прав llm.py

| Уровень | Кол-во | Эндпоинты |
|---------|--------|-----------|
| `view` | 14 | GET prompt, model, history, backend, models, providers list/detail, personas, persona, params, prompt/{persona}, bridge/status, proxy/status, presets list/detail/current |
| `edit` | 20 | POST prompt, model, history DELETE, backend POST, providers CRUD + test + set-default, persona POST, params POST, prompt/{persona} POST + reset, presets CRUD + activate, bridge start/stop |
| `manage` | 8 | vLLM model GET/POST, proxy test/validate/test-multiple/reset/switch-next |

Cloud providers используют `user_has_level(user, "llm", "manage")` для owner_id bypass — manage видит все провайдеры, остальные только свои.

### Матрица прав channels (telegram.py + whatsapp.py + widget.py)

| Уровень | Кол-во | Эндпоинты |
|---------|--------|-----------|
| `view` | 16 | GET config, status, sessions, instances list/detail/status/sessions/logs, yoomoney auth-url/status |
| `edit` | 24 | POST/PUT/DELETE config, instances CRUD, start/stop/restart, clear sessions, yoomoney disconnect |

5 внутренних эндпоинтов в telegram.py без авторизации (bot session registration, payment logging, payment queries, YooMoney OAuth callback) — не мигрированы, остаются публичными.

Все три роутера используют `workspace_context(user, "channels")` для owner_id + workspace_id фильтрации — manage видит все инстансы workspace, остальные только свои. Action-эндпоинты (start/stop/restart/logs/sessions) проверяют workspace через gate-check `get_instance(id, workspace_id=user.workspace_id)`.

### Матрица прав sales (bot_sales.py + amocrm.py)

| Уровень | Кол-во | Эндпоинты |
|---------|--------|-----------|
| `view` | 32 | GET prompts, quiz, segments, followups, testimonials, hardware, abtests, subscribers, users, events, funnel, discovery, github-config (bot_sales); GET status, config, contacts, leads, events, chats, pipelines, sync-log, dataset-status (amocrm) |
| `edit` | 32 | POST/PUT/DELETE CRUD для всех сущностей + broadcast + github-config (bot_sales); POST test, contacts, leads, notes, chat messages, sync, dataset-sync (amocrm) |
| `manage` | 5 | POST config, auth-url, disconnect, refresh-token; DELETE dataset (amocrm — OAuth/инфраструктура) |

2 внутренних эндпоинта в amocrm.py без авторизации (OAuth redirect callback, amoCRM webhook) — не мигрированы.

### Матрица прав faq (faq.py)

| Уровень | Кол-во | Эндпоинты |
|---------|--------|-----------|
| `view` | 2 | GET list, POST test |
| `edit` | 5 | POST create, PUT update, DELETE, POST reload, POST save |

### Матрица прав wiki (wiki_rag.py)

| Уровень | Кол-во | Эндпоинты |
|---------|--------|-----------|
| `view` | 6 | GET collections, collection/{id}, stats, documents, document/{id}; POST search |
| `edit` | 6 | POST/PUT/DELETE collections CRUD, POST upload, PUT/DELETE documents |
| `manage` | 3 | POST reload, POST reindex-embeddings, POST collections/{id}/reload |

1 inline-проверка: `user_has_level(user, "wiki", "manage")` для owner_id при загрузке документа.

### Матрица прав speech (tts.py + stt.py)

| Уровень | Кол-во | Эндпоинты |
|---------|--------|-----------|
| `view` | 10 | GET presets, cache, xtts/params, piper/params, presets/custom; POST test, POST stream (tts); GET status, models (stt) |
| `edit` | 8 | POST preset, DELETE cache, POST xtts/params, POST piper/params, POST/PUT/DELETE presets/custom (tts); POST transcribe, POST test (stt) |

1 inline-проверка: `user_has_level(user, "speech", "manage")` для owner_id при создании пользовательского пресета. WebSocket `/ws/stream` без авторизации — не мигрирован.

### Матрица прав system (services.py + monitor.py + backup.py)

| Уровень | Кол-во | Эндпоинты |
|---------|--------|-----------|
| `view` | 12 | GET status (services); GET gpu, gpu/stream, health, metrics, errors, system, rate-limits, security (monitor); GET system-info, list, {filename}, {filename}/download (backup) |
| `edit` | 2 | POST metrics/reset (monitor); POST {filename}/validate (backup) |
| `manage` | 9 | POST {service}/start, {service}/stop, {service}/restart, start-all, stop-all (services); POST create, POST restore, DELETE {filename} (backup) |

### Матрица прав gsm (gsm.py)

| Уровень | Кол-во | Эндпоинты |
|---------|--------|-----------|
| `view` | 7 | GET status, config, calls, calls/active, calls/{id}, sms, ports |
| `edit` | 2 | POST initialize, PUT config |
| `manage` | 5 | POST calls/answer, calls/hangup, calls/dial, sms, at |

### Матрица прав kanban (kanban.py)

| Уровень | Кол-во | Эндпоинты |
|---------|--------|-----------|
| `view` | 2 | GET projects, GET tasks |
| `edit` | 9 | POST tasks, PATCH tasks/{id}, POST reorder, POST/DELETE dependencies, POST tasks/{id}/checklist, PATCH/DELETE checklist/{id} |
| `manage` | 4 | POST/PATCH/DELETE projects, DELETE tasks/{id} |

3 inline-проверки: `user_has_level(user, "kanban", "manage")` для видимости всех задач (включая приватные), редактирования чужих задач, доступа к приватным задачам при создании зависимостей.

### Матрица прав audit (audit.py)

| Уровень | Кол-во | Эндпоинты |
|---------|--------|-----------|
| `view` | 3 | GET logs, GET stats, GET export |
| `manage` | 1 | POST cleanup |

Исправлена проблема безопасности: `POST /cleanup` ранее был доступен любому аутентифицированному пользователю (`get_current_user`), теперь требует `audit:manage`.

### Матрица прав usage (usage.py)

| Уровень | Кол-во | Эндпоинты |
|---------|--------|-----------|
| `view` | 3 | GET logs, GET stats, GET summary |
| `manage` | 5 | POST/PUT/DELETE limits, POST limits/bulk, POST cleanup |

2 внутренних эндпоинта без авторизации: `POST /log` (логирование из бэкенда) и `GET /check/{service_type}` (проверка лимитов).

### Матрица прав claude_code (claude_code.py)

| Уровень | Кол-во | Эндпоинты |
|---------|--------|-----------|
| `manage` | 4 | GET status, POST start, POST stop, POST execute |

WebSocket `/ws/claude-code` использует собственный `_ws_auth` с whitelist — без изменений.

### Матрица прав settings/legal (legal.py)

| Уровень | Кол-во | Эндпоинты |
|---------|--------|-----------|
| `view` | 1 | GET consents/check/{user_id} (PR #420) |
| `manage` | 4 | GET consents/{user_id}, POST revoke, GET stats, POST gdpr/delete |

7 публичных эндпоинтов без авторизации: GET/POST consent grant/grant-bulk/grant-required (виджеты/боты), GET privacy-policy, GET terms, GET consent-types.

### auth.py — инфраструктурный роутер

9 эндпоинтов. С PR #366:
- `POST /login` — передаёт `workspace_id=1` в `create_session()`
- `GET /me` — возвращает `workspace_id` в ответе
- `PUT /profile` — использует `require_permission("settings", "edit")` Depends
- `POST /change-password` — использует `require_permission("settings", "edit")` Depends, передаёт `workspace_id` в новый токен, rate-limit `RATE_LIMIT_AUTH` (PR #418)
- `DELETE /sessions/{jti}` — inline `level_gte(user.permissions.get("users", ""), "manage")`
- Остальные (`GET /sessions`, `GET /permissions`, `GET /status`, `GET /profile`) — `get_current_user` без RBAC-gate

### Матрица прав roles (roles.py)

| Уровень | Кол-во | Эндпоинты |
|---------|--------|-----------|
| `manage` | 5 | GET list, POST create, GET detail, PUT update, DELETE |

Все 5 эндпоинтов используют `users:manage`. Управление ролями — административная функция, доступная owner и admin.

## Frontend

Фронтенд использует данные из `GET /admin/auth/permissions` для всех проверок доступа. Захардкоженные ролевые проверки (`isAdmin`/`isGuest`/`isWeb`) заменены на permission-функции (#361).

### Auth Store (`stores/auth.ts`)

При логине и инициализации (восстановление из localStorage) фронтенд вызывает `fetchPermissions()` → `GET /admin/auth/permissions`. Результат хранится в `permissions: Record<string, string>`.

**Permission-функции:**

| Функция | Логика | Пример |
|---------|--------|--------|
| `hasModule(mod)` | `mod in permissions` | `hasModule('speech')` — есть ли доступ к TTS |
| `canView(mod)` | уровень ≥ 1 (view) | `canView('audit')` |
| `canEdit(mod)` | уровень ≥ 2 (edit) | `canEdit('kanban')` — может редактировать задачи |
| `canManage(mod)` | уровень ≥ 3 (manage) | `canManage('system')` — может управлять сервисами |

`isAdmin` сохранён как `computed(() => canManage('users'))` — для badge роли в App.vue.

### Роутер (`router.ts`)

Route meta использует `module` и `minLevel` вместо `minRole`/`excludeRoles`:

```typescript
{ path: '/services', meta: { module: 'system', minLevel: 'manage', localOnly: true } }
{ path: '/llm', meta: { module: 'llm' } }  // minLevel по умолчанию = 'view'
{ path: '/settings', meta: {} }              // без module-gate (self-service)
```

Navigation guard проверяет:
1. `localOnly` + `isCloudMode` → redirect на `/chat`
2. `module` → `permissions[module]` ≥ `minLevel` (по умолчанию `view`)

### Навигация (`AccordionNav.vue`)

Nav items используют `module`/`minLevel`/`localOnly` — фильтруются через `isVisible()`:

```typescript
function isVisible(item: { module?: string; minLevel?: string; localOnly?: boolean }): boolean {
  if (item.localOnly && authStore.isCloudMode) return false
  if (!item.module) return true
  return (LVL[authStore.permissions[item.module]] ?? 0) >= (LVL[item.minLevel || 'view'] ?? 1)
}
```

### Views — inline-проверки

| Контекст | Permission-функция | Файлы |
|----------|-------------------|-------|
| Управление сервисами | `canManage('system')` | ServicesView |
| Переключение LLM backend, vLLM модели | `canManage('llm')` | LlmView |
| Удаление чужих сессий | `canManage('chat')` | ChatView |
| Очистка датасета CRM | `canManage('sales')` | CrmView |
| Управление проектами | `canManage('kanban')` | KanbanView, KanbanCardDetail |
| Создание задач, sync | `canEdit('kanban')` | KanbanView |
| Drag-n-drop, Gantt | `!canEdit('kanban')` (disabled) | KanbanView |
| XTTS голоса, параметры | `canEdit('speech')` | TtsView |
| TTS-вкладка в Fine-tune | `hasModule('speech')` | FinetuneView |
| Профиль, смена пароля | `canEdit('settings')` | SettingsView |

### Demo Mode

`demo/auth.ts` предоставляет mock `GET /admin/auth/permissions`:

| Demo роль | Маппинг |
|-----------|---------|
| `admin` | Все 16 модулей → `manage` |
| `user`/`web` | 8 модулей `edit` + 3 `view` (без users, roles, billing, gsm, claude_code) |
| `guest` | 7 модулей `view` (dashboard, chat, faq, audit, usage, kanban, sales) |

## Технические детали

### Backend

- **Модели**: `Role`, `RolePermission`, `Workspace`, `WorkspaceMember`, `WorkspaceInvite` в `db/models.py`
- **Репозитории**: `RoleRepository` в `db/repositories/role.py`, `WorkspaceRepository` в `db/repositories/workspace.py`
- **Менеджеры**: `AsyncRoleManager`, `AsyncWorkspaceManager` в `db/integration.py`
- **Auth-хелперы**: `level_gte()`, `get_user_permissions()`, `require_permission()`, `user_has_level()`, `invalidate_permissions_cache()` в `auth_manager.py`
- **Кеши**: `PermissionsCache` (role_name → permissions), `MemberRoleCache` ((user_id, workspace_id) → role_name) в `auth_manager.py`
- **JWT**: `TokenPayload.workspace_id` (default 1), `User.workspace_id` — передаётся в `create_access_token()` и `create_session()`
- **Роутер**: `app/routers/roles.py` (5 CRUD-эндпоинтов, все `require_permission("users", "manage")`)
- **Сидирование**: `_seed_system_roles()` + `_seed_default_workspace()` в `orchestrator.py` (идемпотентно, при старте)
- **Миграции**: `20260222_0003_create_roles_permissions.py` (roles), `20260223_0005_add_workspaces.py` (workspaces, workspace_members, workspace_invites, user_sessions.workspace_id), `20260223_0006_add_workspace_id_to_resources.py` (workspace_id на 13 ресурсных таблицах), `20260223_0007_add_user_identities.py` (user_identities, users.username/password_hash nullable, users.email)

### Проверка прав

**Вариант 1 — dependency (рекомендуемый).** `require_permission(module, min_level)` — фабрика FastAPI-зависимости. Проверяет уровень, заполняет `user.permissions`, возвращает 403 при недостаточных правах:

```python
from auth_manager import require_permission, user_has_level, User

@router.get("/items")
async def list_items(user: User = Depends(require_permission("chat", "view"))):
    # user.permissions уже заполнен
    ...

@router.delete("/items/{id}")
async def delete_item(id: int, user: User = Depends(require_permission("chat", "manage"))):
    ...
```

**Вариант 2 — inline-проверка.** `user_has_level(user, module, min_level)` — синхронный хелпер для дополнительных проверок внутри эндпоинта. Требует, чтобы `user.permissions` уже был заполнен (через `require_permission`):

```python
@router.put("/items/{id}")
async def update_item(id: int, user: User = Depends(require_permission("chat", "edit"))):
    if user_has_level(user, "chat", "manage"):
        # manage-уровень может обновлять чужие записи
        ...
```

**Вариант 3 — ручной запрос.** `get_user_permissions(user)` — async-функция, использует `MemberRoleCache` + `PermissionsCache`. Применяется в self-service роутерах (auth.py), где dependency — `get_current_user`, но нужна inline RBAC-проверка:

```python
from auth_manager import get_current_user, get_user_permissions, level_gte

@router.delete("/sessions/{jti}")
async def delete_session(jti: str, user: User = Depends(get_current_user)):
    user.permissions = await get_user_permissions(user)
    if not level_gte(user.permissions.get("users", ""), "manage"):
        # non-manage users can only revoke their own sessions
        ...
```

### Разрешение прав (flow)

```
JWT (workspace_id) → MemberRoleCache.get(user_id, workspace_id)
  → cache miss → async_workspace_manager.get_member_role_name(user_id, workspace_id)
    → SELECT role_name FROM workspace_members WHERE user_id=? AND workspace_id=?
  → role_name → PermissionsCache.get(role_name)
    → cache miss → async_role_manager.get_by_name(role_name) → permissions dict
```

### Кеши

| Кеш | Ключ → Значение | Инвалидация |
|-----|-----------------|-------------|
| `MemberRoleCache` | `(user_id, workspace_id) → role_name` | `invalidate_user(user_id)`, `invalidate_workspace(workspace_id)` |
| `PermissionsCache` | `role_name → Dict[module, level]` | `invalidate_permissions_cache(role_name)` из `roles.py` |
| `SessionCache` | `jti → user_id` | `remove(jti)`, `remove_all_for_user(user_id)` |

---

← [[Settings]] | [[Home]] | [[API-Reference]] →

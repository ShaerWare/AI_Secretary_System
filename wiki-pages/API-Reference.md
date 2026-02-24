# API Reference (Справочник API)

Полная документация по REST API AI Secretary System с примерами запросов и ответов.

## Аутентификация

### Получение токена

```bash
POST /admin/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "admin"
}
```

**Ответ:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

При логине создаётся серверная сессия с записью IP-адреса и User-Agent. Токен содержит `jti` (уникальный ID сессии), который проверяется при каждом запросе.

Пароли хешируются **bcrypt**. Старые SHA-256 хеши автоматически перехешируются при успешном входе (lazy-rehash).

### Использование токена

Добавьте JWT токен в заголовок `Authorization` для всех защищённых эндпоинтов:

```bash
GET /admin/auth/me
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

## Эндпоинты аутентификации

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| POST | `/admin/auth/login` | Вход (получение JWT + создание сессии) |
| GET | `/admin/auth/me` | Текущий пользователь |
| GET | `/admin/auth/status` | Статус аутентификации |
| GET | `/admin/auth/profile` | Профиль пользователя |
| PUT | `/admin/auth/profile` | Обновление профиля |
| POST | `/admin/auth/change-password` | Смена пароля (отзыв всех сессий + новый токен) |
| GET | `/admin/auth/sessions` | Список активных сессий текущего пользователя |
| DELETE | `/admin/auth/sessions/{jti}` | Отзыв конкретной сессии |
| GET | `/admin/auth/permissions` | Эффективные права текущего пользователя |

### Управление сессиями

Каждый вход создаёт серверную сессию. Сессии можно просматривать и отзывать (revoke). При отзыве сессии токен мгновенно становится недействительным.

#### Список активных сессий

```bash
GET /admin/auth/sessions
Authorization: Bearer <token>
```

**Ответ:**
```json
[
  {
    "token_jti": "550e8400-e29b-41d4-a716-446655440000",
    "ip_address": "192.168.1.100",
    "user_agent": "Mozilla/5.0 ...",
    "created_at": "2026-02-22T03:00:00",
    "expires_at": "2026-02-23T03:00:00",
    "revoked_at": null
  }
]
```

#### Отзыв сессии

```bash
DELETE /admin/auth/sessions/{jti}
Authorization: Bearer <token>
```

- Обычные пользователи могут отзывать только свои сессии
- Пользователи с `users:manage` могут отзывать любые сессии
- После отзыва токен возвращает 401

**Ответ:** `{"message": "Session revoked"}`

#### Смена пароля (обновлённое поведение)

```bash
POST /admin/auth/change-password
Authorization: Bearer <token>
Content-Type: application/json

{
  "old_password": "current",
  "new_password": "new_secure_password"
}
```

**Ответ:** Все существующие сессии отзываются, возвращается новый токен:
```json
{
  "message": "Password updated successfully",
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

#### Автоматический отзыв сессий

Все активные сессии пользователя автоматически отзываются при:
- Смене пароля (`POST /admin/auth/change-password`)
- Смене роли (через `manage_users.py set-role`)
- Деактивации аккаунта (через `manage_users.py disable`)

## OpenAI-совместимые эндпоинты

Для интеграции с OpenWebUI и другими клиентами, поддерживающими OpenAI API.

### Список моделей

```bash
GET /v1/models
Authorization: Bearer <token>
```

**Ответ:**
```json
{
  "data": [
    {
      "id": "anna-secretary-vllm",
      "object": "model",
      "created": 1234567890,
      "owned_by": "system"
    },
    {
      "id": "marina-secretary-gemini",
      "object": "model",
      "created": 1234567890,
      "owned_by": "system"
    }
  ]
}
```

Формат ID: `{persona}-secretary-{backend}` (например, `anna-secretary-vllm`, `marina-secretary-cloud_1`)

### Список голосов

```bash
GET /v1/voices
Authorization: Bearer <token>
```

**Ответ:**
```json
{
  "voices": [
    {"id": "anna_ru", "name": "Анна (Russian)"},
    {"id": "marina_ru", "name": "Марина (Russian)"}
  ]
}
```

### Синтез речи (TTS)

```bash
POST /v1/audio/speech
Authorization: Bearer <token>
Content-Type: application/json

{
  "model": "tts-1",
  "input": "Привет, это Анна",
  "voice": "anna_ru"
}
```

**Ответ:** WAV аудиофайл (audio/wav)

**Особенности:**
- Поддержка streaming cache optimization
- Автоматическое кеширование аудио

### Чат (streaming)

```bash
POST /v1/chat/completions
Authorization: Bearer <token>
Content-Type: application/json

{
  "model": "anna-secretary-vllm",
  "messages": [
    {"role": "user", "content": "Привет"}
  ],
  "stream": true
}
```

**Ответ (SSE):**
```
data: {"choices":[{"delta":{"content":"Привет"}}]}

data: {"choices":[{"delta":{"content":"!"}}]}

data: [DONE]
```

**Особенности:**
- Background TTS synthesis (аудио генерируется параллельно)
- Non-streaming режим (stream: false) возвращает полный JSON

## Базовые эндпоинты

### TTS (синтез речи)

```bash
POST /tts
Content-Type: application/json

{
  "text": "Привет, это Анна",
  "voice_id": "anna_ru"
}
```

**Ответ:** WAV аудиофайл

### STT (распознавание речи)

```bash
POST /stt
Content-Type: multipart/form-data

file: <audio.wav>
```

**Ответ:**
```json
{
  "text": "Привет, это Анна"
}
```

### Чат

```bash
POST /chat
Content-Type: application/json

{
  "message": "Привет",
  "persona": "anna"
}
```

**Ответ:**
```json
{
  "response": "Здравствуйте! Чем могу помочь?"
}
```

### Обработка звонка

```bash
POST /process_call
Content-Type: multipart/form-data

audio: <call.wav>
```

**Ответ:**
```json
{
  "transcription": "Текст звонка",
  "response": "Ответ секретаря",
  "audio_url": "/path/to/response.wav"
}
```

### Сброс контекста

```bash
POST /reset_conversation
```

**Ответ:**
```json
{
  "status": "ok",
  "message": "Контекст сброшен"
}
```

## Health check

```bash
GET /health
```

**Ответ:**
```json
{
  "status": "healthy",
  "services": {
    "tts": "running",
    "stt": "running",
    "llm": "running"
  },
  "database": "connected",
  "llm_backend": "vllm"
}
```

## Kanban (Задачи)

### Эндпоинты проектов (GitHub-привязка)

| Метод | Эндпоинт | Описание | Доступ |
|-------|----------|----------|--------|
| GET | `/admin/kanban/projects` | Список всех проектов | kanban:view |
| POST | `/admin/kanban/projects` | Создать проект (GitHub-привязка) | kanban:manage |
| PATCH | `/admin/kanban/projects/{id}` | Обновить проект | kanban:manage |
| DELETE | `/admin/kanban/projects/{id}` | Удалить проект | kanban:manage |
| POST | `/admin/kanban/projects/{id}/sync` | Полная синхронизация GitHub issues | kanban:edit |

### Эндпоинты задач

| Метод | Эндпоинт | Описание | Доступ |
|-------|----------|----------|--------|
| GET | `/admin/kanban/tasks?project_id=N` | Список задач проекта (null = локальные) | kanban:view |
| POST | `/admin/kanban/tasks` | Создать задачу (всегда draft + private) | kanban:edit |
| PATCH | `/admin/kanban/tasks/{id}` | Обновить задачу (+ push на GitHub) | kanban:edit |
| DELETE | `/admin/kanban/tasks/{id}` | Удалить задачу | kanban:manage |
| POST | `/admin/kanban/reorder` | Изменить статус и позицию (+ push на GitHub) | kanban:edit |

### Эндпоинты зависимостей

| Метод | Эндпоинт | Описание | Доступ |
|-------|----------|----------|--------|
| POST | `/admin/kanban/dependencies` | Добавить зависимость (409 при цикле) | kanban:edit |
| DELETE | `/admin/kanban/dependencies?blocker_id=X&dependent_id=Y` | Удалить зависимость | kanban:edit |

### Эндпоинты чеклиста

| Метод | Эндпоинт | Описание | Доступ |
|-------|----------|----------|--------|
| POST | `/admin/kanban/tasks/{id}/checklist` | Добавить пункт чеклиста | kanban:edit |
| PATCH | `/admin/kanban/checklist/{item_id}/toggle` | Переключить выполнение | kanban:edit |
| DELETE | `/admin/kanban/checklist/{item_id}` | Удалить пункт | kanban:edit |

### Создать проект

```bash
POST /admin/kanban/projects
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "AI Secretary",
  "github_owner": "ShaerWare",
  "github_repo": "AI_Secretary_System",
  "github_token": "ghp_xxx...",
  "webhook_secret": "my-secret",
  "label_mapping": {"todo": "status:todo", "in_progress": "status:in_progress", "review": "status:review"},
  "sync_enabled": true
}
```

**Ответ:** `{"project": {...}}` (токен не возвращается, только `has_token: true/false`)

### Синхронизация GitHub issues

```bash
POST /admin/kanban/projects/1/sync
Authorization: Bearer <token>
```

**Ответ:** `{"created": 15, "updated": 3, "total": 18}`

### Создать задачу

```bash
POST /admin/kanban/tasks
Authorization: Bearer <token>
Content-Type: application/json

{
  "title": "Настроить интеграцию",
  "description": "Подключить API",
  "assignee": "admin",
  "due_date": "2026-03-01",
  "tags": ["интеграция", "api"]
}
```

**Ответ:**
```json
{
  "task": {
    "id": 1,
    "title": "Настроить интеграцию",
    "description": "Подключить API",
    "status": "draft",
    "is_private": true,
    "assignee": "admin",
    "created_by": "admin",
    "start_date": null,
    "due_date": "2026-03-01",
    "position": 0,
    "tags": ["интеграция", "api"],
    "project_id": null,
    "github_issue_number": null,
    "checklist": [],
    "blockers": [],
    "dependents": [],
    "created": "2026-02-21T00:00:00",
    "updated": "2026-02-21T00:00:00"
  }
}
```

### Обновить задачу

```bash
PATCH /admin/kanban/tasks/1
Authorization: Bearer <token>
Content-Type: application/json

{
  "status": "in_progress",
  "assignee": "admin"
}
```

При смене статуса с `draft` на любой другой — задача автоматически становится публичной (`is_private: false`). Для GitHub-привязанных задач статус также обновляется на GitHub (лейблы + open/close).

### Добавить зависимость

```bash
POST /admin/kanban/dependencies
Authorization: Bearer <token>
Content-Type: application/json

{
  "blocker_id": 1,
  "dependent_id": 2
}
```

Возвращает **409** если зависимость создаёт цикл или целевая задача приватная.

## URL паттерны

### CRUD ресурсов

| Паттерн | Описание | Пример |
|---------|----------|--------|
| `GET /admin/{resource}` | Список всех | `/admin/chat/sessions` |
| `POST /admin/{resource}` | Создать новый | `/admin/telegram/bots` |
| `GET /admin/{resource}/{id}` | Получить один | `/admin/telegram/bots/123` |
| `PUT /admin/{resource}/{id}` | Обновить | `/admin/telegram/bots/123` |
| `DELETE /admin/{resource}/{id}` | Удалить | `/admin/telegram/bots/123` |

### Действия над ресурсами

| Паттерн | Описание | Пример |
|---------|----------|--------|
| `POST /admin/{resource}/{id}/action` | Выполнить действие | `/admin/telegram/bots/123/start` |

**Примеры действий:**
- `/admin/telegram/bots/{id}/start` — запустить бота
- `/admin/telegram/bots/{id}/stop` — остановить бота
- `/admin/telegram/bots/{id}/test` — тестовое сообщение

### SSE streaming

| Паттерн | Описание | Пример |
|---------|----------|--------|
| `GET /admin/{resource}/stream` | Server-Sent Events | `/admin/chat/stream` |

**Формат SSE:**
```
data: {"message": "chunk"}\n\n
data: [DONE]\n\n
```

### Webhooks

| Паттерн | Описание | Пример |
|---------|----------|--------|
| `POST /webhooks/{service}` | Внешние вебхуки | `/webhooks/amocrm` |

**Доступные вебхуки:**
- `/webhooks/amocrm` — amoCRM webhook
- `/webhooks/yoomoney` — YooMoney payments
- `/webhooks/github` — GitHub PR events + Issues (kanban sync)

## RBAC (контроль доступа)

Все роутеры мигрированы на RBAC. Legacy guard-функции (`require_admin`, `require_not_guest`, `verify_ownership`) удалены в PR #358.

### RBAC permissions

| Dependency | Описание | Применение |
|------------|----------|------------|
| `require_permission(module, level)` | Проверяет уровень прав по модулю | Эндпоинт-уровень (все роутеры) |
| `user_has_level(user, module, level)` | Inline-проверка внутри эндпоинта | Дополнительная логика (owner/manage) |
| `get_current_user` | Аутентификация без RBAC-проверки | Self-service (auth.py) |

Мигрированные роутеры (20): **chat.py** (21), **llm.py** (42), **telegram.py** (23), **whatsapp.py** (10), **widget.py** (7), **bot_sales.py** (43), **amocrm.py** (26), **faq.py** (8), **wiki_rag.py** (15), **stt.py** (4), **services.py** (6), **monitor.py** (9), **backup.py** (8), **gsm.py** (14), **tts.py** (14), **kanban.py** (15), **audit.py** (4), **usage.py** (8), **claude_code.py** (4), **legal.py** (4), **roles.py** (5). Инфраструктурный: **auth.py** (self-service + inline RBAC checks).

### Legacy роли пользователей

| Роль | RBAC маппинг | Права | Ограничения |
|------|-------------|-------|-------------|
| **admin** | admin (manage all) | Полный доступ | Видит все ресурсы всех пользователей |
| **user** | operator (edit) | Read + Write своих ресурсов | Полный доступ к админ-панели |
| **web** | operator (edit) | Как user, но упрощённый UI | Скрыты: Dashboard, Services, vLLM, Models |
| **guest** | viewer (view) | Read-only (demo) | Только просмотр, без изменений |

### Динамические RBAC роли

Матрица прав: 16 модулей × 3 уровня (view/edit/manage). Legacy роли автоматически маппятся на RBAC через `get_role_for_legacy()`.

Подробнее: [[RBAC]]

### Эндпоинты RBAC

#### Права текущего пользователя

```bash
GET /admin/auth/permissions
Authorization: Bearer <token>
```

**Ответ:** `{"dashboard": "manage", "chat": "manage", ...}`

В облачном режиме модули `speech`, `gsm`, `system` автоматически исключаются.

#### Управление ролями (admin only)

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/admin/roles` | Список всех ролей с правами |
| POST | `/admin/roles` | Создать пользовательскую роль |
| GET | `/admin/roles/{id}` | Получить роль по ID |
| PUT | `/admin/roles/{id}` | Обновить роль |
| DELETE | `/admin/roles/{id}` | Удалить роль (только пользовательские) |

### Изоляция данных

Двухуровневая фильтрация: **owner_id** (кто создал) + **workspace_id** (какому workspace принадлежит):

```python
from auth_manager import workspace_context

owner_id, workspace_id = workspace_context(user, "chat")
# owner_id = None для manage-level (видит все ресурсы workspace)
# workspace_id = всегда из JWT (user.workspace_id)
sessions = await manager.list_sessions(owner_id=owner_id, workspace_id=workspace_id)
```

Ресурсы с `owner_id` + `workspace_id`: ChatSession, BotInstance, WidgetInstance, WhatsAppInstance, CloudLLMProvider, TTSPreset, KnowledgeDocument, ClaudeCodeSession и др. (13 таблиц).

### Workspaces

Workspace — контейнер всех ресурсов. Default workspace (id=1) создаётся автоматически. JWT содержит `workspace_id`. Репозитории фильтруют через `BaseRepository._apply_workspace_filter()`.

> **Статус:** workspace_id колонки добавлены на 13 таблиц, инфраструктура фильтрации готова. Модули с workspace-фильтрацией: **Chat** (PR #385), **Channels** — Telegram, WhatsApp, Widget (PR #387), **AI/LLM** — Cloud LLM Providers, TTS Presets (PR #389), **Knowledge/FAQ** — Knowledge Documents, Collections, FAQ Entries (PR #391), **System/Kanban/amoCRM** — Kanban Tasks & Projects, Claude Code Sessions, amoCRM Config (PR #393). Audit excluded (no workspace_id).

### Совместный доступ к чатам

Чат-сессии (admin source) могут быть расшарены другим пользователям с уровнями доступа `read` или `write`.

При `read`-доступе пользователь может просматривать чат, но не может отправлять/редактировать/удалять сообщения. При `write` — полный доступ, аналогичный владельцу (кроме удаления сессии и управления шарами).

#### Эндпоинты шаринга

| Метод | Эндпоинт | Описание | Доступ |
|-------|----------|----------|--------|
| GET | `/admin/chat/sessions/{id}/shares` | Список шар сессии | `chat:edit` + owner/manage |
| POST | `/admin/chat/sessions/{id}/shares` | Расшарить сессию | `chat:edit` + owner/manage |
| PUT | `/admin/chat/sessions/{id}/shares/{user_id}` | Изменить permission | `chat:edit` + owner/manage |
| DELETE | `/admin/chat/sessions/{id}/shares/{user_id}` | Удалить шар | `chat:edit` + owner/manage |
| POST | `/admin/chat/sessions/{id}/fork` | Форк сессии (глубокое копирование) | `chat:edit` |
| GET | `/admin/chat/shareable-users` | Список пользователей для шаринга | `chat:view` |

#### Расшарить чат

```bash
POST /admin/chat/sessions/{id}/shares
Content-Type: application/json
Authorization: Bearer <token>

{
  "user_id": 2,
  "permission": "read"
}
```

**Ответ:**
```json
{
  "share": {
    "id": 1,
    "session_id": "chat_123",
    "user_id": 2,
    "permission": "read",
    "shared_by": 1,
    "shared_at": "2026-02-19T12:00:00"
  }
}
```

#### Обогащение ответов

При получении сессии добавляются поля шаринга:

```json
{
  "session": {
    "id": "chat_123",
    "owner_id": 1,
    "is_shared_with_me": true,
    "share_permission": "read",
    "share_count": 2
  }
}
```

#### Форк сессии

```bash
POST /admin/chat/sessions/{id}/fork
Content-Type: application/json
Authorization: Bearer <token>

{
  "title": "Мой форк"
}
```

Создаёт глубокую копию всех активных сообщений с новым `owner_id`.

## Формат ошибок

Все ошибки возвращаются в единообразном JSON формате:

```json
{
  "detail": "Описание ошибки"
}
```

### HTTP статус-коды

| Код | Описание |
|-----|----------|
| 200 | Успех |
| 201 | Создано |
| 400 | Некорректный запрос |
| 401 | Требуется аутентификация |
| 403 | Доступ запрещён |
| 404 | Не найдено |
| 422 | Ошибка валидации |
| 500 | Внутренняя ошибка сервера |

## Примеры интеграции

### cURL

```bash
# Получить токен
TOKEN=$(curl -s -X POST http://localhost:8002/admin/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r .access_token)

# Запрос к API
curl -X GET http://localhost:8002/v1/models \
  -H "Authorization: Bearer $TOKEN"
```

### Python

```python
import requests

# Аутентификация
response = requests.post(
    "http://localhost:8002/admin/auth/login",
    json={"username": "admin", "password": "admin"}
)
token = response.json()["access_token"]

# Запрос с токеном
headers = {"Authorization": f"Bearer {token}"}
response = requests.get("http://localhost:8002/v1/models", headers=headers)
print(response.json())
```

---

← [[Personas]] | [[Troubleshooting]] →

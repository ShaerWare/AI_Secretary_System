# Claude Code (Web UI)

WebSocket-терминал для Claude Code CLI, встроенный в админ-панель. Позволяет администраторам взаимодействовать с Claude Code напрямую из браузера: отправлять запросы, видеть потоковый вывод текста, мышление модели, вызовы инструментов и результаты их выполнения.

**Доступ:** только admin | **Путь:** интеграция в Chat View

## Концепция

Claude Code Web UI — это браузерный интерфейс к Claude Code CLI. Вместо работы в терминале администратор взаимодействует с Claude через WebSocket-соединение в админ-панели.

Архитектура:

```
Браузер (Vue 3)  ←→  WebSocket  ←→  Orchestrator  ←→  Claude CLI (subprocess)
                     /admin/claude-code/ws              claude -p --output-format stream-json
```

Процесс:
1. Пользователь вводит промпт в интерфейсе
2. Orchestrator запускает Claude CLI как subprocess с флагами `--output-format stream-json --verbose`
3. CLI выводит NDJSON-поток событий в stdout
4. Orchestrator парсит каждую строку и ретранслирует события через WebSocket
5. Frontend отображает текст, мышление и инструменты в реальном времени

Рабочая директория CLI ограничена списком разрешённых путей (`_ALLOWED_CWDS`). По умолчанию: `/root`.

## Подключение

### WebSocket

**URL:** `ws://{host}/admin/claude-code/ws?token=<jwt>`

Аутентификация через JWT-токен в query-параметре `token`. Токен проверяется функцией `_ws_auth()`:
- Декодирует JWT через `decode_token()`
- Проверяет имя пользователя в списке `_ALLOWED_USERS`
- При ошибке — соединение закрывается с кодом `4003`

При повторном подключении того же пользователя предыдущее соединение закрывается с кодом `4001` (заменено новым).

### Протокол обмена

**Клиент → Сервер** (JSON):

| Действие | Поля | Описание |
|----------|------|----------|
| `start` | `prompt`, `cwd?`, `context_files?` | Новая сессия. Создаёт запись в БД, запускает CLI |
| `message` | `prompt`, `session_id?`, `cli_session_id?` | Продолжение сессии (resume). Требует `session_id` или `cli_session_id` |
| `abort` | — | Принудительное завершение процесса (`kill`) |

**Контекстные файлы** (`context_files`) — массив объектов `{name, content}`. Записываются во временную директорию, путь передаётся в CLI через `--add-dir`. Содержимое файлов добавляется в начало промпта.

## Типы событий

**Сервер → Клиент** (JSON через WebSocket):

### Инициализация

| Тип | Поля | Описание |
|-----|------|----------|
| `session_created` | `session` | DB-сессия создана (содержит `id`) |
| `session_init` | `session_id`, `model`, `tools`, `mcp_servers` | CLI инициализирован, получены метаданные |

### Потоковый вывод

| Тип | Поля | Описание |
|-----|------|----------|
| `text_delta` | `text` | Фрагмент текстового ответа (инкрементальный) |
| `thinking_delta` | `text` | Фрагмент мышления модели (extended thinking) |

### Инструменты

| Тип | Поля | Описание |
|-----|------|----------|
| `tool_use_start` | `tool_use_id`, `name` | Начало вызова инструмента (Read, Write, Bash и др.) |
| `tool_use_input` | `tool_use_id`, `name`, `input` | Полные параметры вызова |
| `tool_use_input_delta` | `partial_json` | Инкрементальный ввод параметров (стриминг JSON) |
| `tool_result` | `tool_use_id`, `content`, `is_error` | Результат выполнения инструмента |

### Завершение

| Тип | Поля | Описание |
|-----|------|----------|
| `done` | `session_id`, `cost_usd`, `duration_ms`, `result` | Успешное завершение |
| `error` | `error` | Ошибка (таймаут, невалидный запрос и др.) |
| `aborted` | — | Процесс прерван пользователем |

### Маппинг CLI событий

Orchestrator транслирует NDJSON-события CLI в WebSocket-события:

| CLI event (`type`) | WebSocket event | Примечание |
|---------------------|-----------------|------------|
| `system` | `session_init` | Извлекает `session_id`, `model`, `tools` |
| `assistant` (text) | `text_delta` | Non-streaming fallback |
| `assistant` (thinking) | `thinking_delta` | Non-streaming fallback |
| `assistant` (tool_use) | `tool_use_input` | Полный блок tool_use |
| `content_block_start` (tool_use) | `tool_use_start` | Начало стримингового вызова |
| `content_block_delta` (text) | `text_delta` | Стриминговый текст |
| `content_block_delta` (thinking) | `thinking_delta` | Стриминговое мышление |
| `content_block_delta` (input_json) | `tool_use_input_delta` | Стриминг параметров |
| `user` (tool_result) | `tool_result` | Результат + счётчик turn |
| `result` | `done` | Итоговый результат + стоимость |

## Управление сессиями

Каждый запуск Claude CLI создаёт запись в таблице `claude_code_sessions` (модель `ClaudeCodeSession`).

### Жизненный цикл сессии

1. **Создание** — при `action: "start"` создаётся DB-запись со статусом по умолчанию
2. **Активность** — при `action: "message"` статус обновляется на `active`
3. **Завершение** — `completed` (exit code 0), `error` (exit code != 0), `aborted` (kill)

Метаданные обновляются по мере работы: `cli_session_id` (для resume), `model`, `total_turns`.

### Возобновление (Resume)

Действие `message` с `cli_session_id` запускает CLI с флагом `--resume {session_id}`, продолжая диалог с того же места.

## Frontend

### Composable `useClaudeCode`

Глобальный синглтон (состояние сохраняется при смене роутов). Экспортирует реактивные переменные и функции:

**Состояние:**

| Переменная | Тип | Описание |
|------------|-----|----------|
| `isActive` | `boolean` | Режим Claude Code активирован |
| `isConnected` | `boolean` | WebSocket соединение установлено |
| `isProcessing` | `boolean` | CLI выполняет запрос |
| `cliSessionId` | `string?` | ID сессии CLI (для resume) |
| `dbSessionId` | `string?` | ID записи в БД |
| `streamingText` | `string` | Текущий текст ответа (накопительно) |
| `thinkingText` | `string` | Текущее мышление (накопительно) |
| `currentToolBlocks` | `CcToolBlock[]` | Текущие блоки инструментов |
| `messages` | `CcMessage[]` | История сообщений |
| `currentModel` | `string?` | Модель Claude (напр. `claude-opus-4-6`) |
| `error` | `string?` | Текст ошибки |
| `workingDir` | `string` | Рабочая директория CLI |
| `pendingContextFiles` | `CcContextFile[]` | Файлы для первого запроса |

**Функции:**

| Функция | Описание |
|---------|----------|
| `toggle()` | Включить/выключить режим Claude Code (connect/disconnect + reset) |
| `newSession()` | Начать новую сессию (abort текущий процесс, сбросить состояние) |
| `connect()` | Открыть WebSocket соединение |
| `disconnect()` | Закрыть WebSocket соединение |
| `sendMessage(prompt)` | Отправить промпт. Первый вызов — `start` (с cwd и файлами), последующие — `message` (resume) |
| `abort()` | Прервать текущий процесс |

### Демо-режим

В демо-режиме (`VITE_DEMO_MODE=true`) WebSocket не используется. Вместо этого `_demoSimulate()` эмулирует поток событий с задержками (200–2600 мс): мышление, текст, вызов инструмента Read, результат, завершение.

## Ограничения

| Ограничение | Описание |
|-------------|----------|
| **Один WebSocket на пользователя** | При повторном подключении старый WebSocket закрывается (код `4001`) |
| **Только admin** | REST-эндпоинты защищены `require_admin`. WebSocket проверяет `_ALLOWED_USERS` |
| **Белый список пользователей** | `_ALLOWED_USERS` — жёстко заданный набор имён для WebSocket-доступа |
| **Ограниченные директории** | CLI работает только в `_ALLOWED_CWDS`: `/root`, `/opt/ai-secretary`, `/tmp` |
| **Таймаут тишины** | 5 минут без вывода от CLI → ошибка таймаута |
| **Максимум turn'ов** | `--max-turns 50` — лимит на количество итераций CLI |
| **Один процесс на пользователя** | Повторный `start`/`message` при активном процессе вернёт ошибку |

## API эндпоинты

### WebSocket

| Endpoint | Описание |
|----------|----------|
| `WS /admin/claude-code/ws?token=<jwt>` | Основной WebSocket для взаимодействия с Claude CLI |

### REST (admin-only)

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/admin/claude-code/sessions` | `GET` | Список сессий текущего пользователя |
| `/admin/claude-code/sessions/{id}` | `GET` | Детали конкретной сессии |
| `/admin/claude-code/sessions/{id}` | `DELETE` | Удалить сессию |
| `/admin/claude-code/directories` | `GET` | Список разрешённых рабочих директорий и директория по умолчанию |

### Формат ответов

**GET /sessions:**
```json
{
  "sessions": [
    {"id": "...", "title": "...", "cli_session_id": "...", "model": "...", "status": "completed", "total_turns": 5}
  ]
}
```

**GET /directories:**
```json
{
  "directories": ["/root", "/opt/ai-secretary", "/tmp"],
  "default": "/root"
}
```

## RBAC

| Операция | Требуемая роль |
|----------|----------------|
| WebSocket подключение | admin + `_ALLOWED_USERS` whitelist |
| Список сессий | admin |
| Детали сессии | admin |
| Удаление сессии | admin |
| Список директорий | admin |

Гости, пользователи с ролями `user`, `web`, `guest` не имеют доступа к Claude Code.

---

← [[Settings]] | [[Home]] →

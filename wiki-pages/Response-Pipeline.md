# Response Pipeline (Цепочка ответов)

Полное описание пайплайна обработки сообщений — от индексации базы знаний (RAG) до финального ответа ассистента в чате, виджете и Telegram.

## Обзор

Три точки входа для сообщений пользователей:

| Канал | Эндпоинт | RAG | FAQ | Auth |
|-------|----------|-----|-----|------|
| **Admin Chat** | `POST /admin/chat/sessions/{id}/stream` | да | да | JWT |
| **Telegram бот** | → проксирует в Admin Chat через HTTP | да | да | internal token |
| **Виджет (публичный)** | `POST /widget/chat/session/{id}/stream` | нет | да | нет |
| **Виджет (в админке)** | → идёт через Admin Chat с `widget_instance_id` | да | да | JWT |

## 1. RAG — индексация базы знаний

При старте оркестратора (`orchestrator.py`) создаётся `WikiRAGService`:

```
WikiRAGService(Path("wiki-pages"))
  │
  ├─ Чтение всех *.md из wiki-pages/ (кроме _*)
  ├─ Разбиение по заголовкам ## и ### → WikiSection (заголовок + тело)
  ├─ Фильтрация секций < 50 символов
  ├─ Токенизация со стеммингом (snowball: русский + английский)
  ├─ Заголовок дублируется 4x для буста релевантности
  └─ Построение BM25 индекса (doc_freqs, avg_dl)
```

### Провайдеры эмбеддингов (тиерная система)

Выбирается автоматически при старте, от лучшего к худшему:

| Приоритет | Провайдер | Условие | Размерность |
|-----------|-----------|---------|-------------|
| 1 | `LocalEmbeddingProvider` | `DEPLOYMENT_MODE=full` + `sentence-transformers` установлен | 384 |
| 2 | `GeminiEmbeddingProvider` | API-ключ Gemini доступен | 768 |
| 2 | `OpenAIEmbeddingProvider` | API-ключ OpenAI-compatible доступен | зависит от модели |
| 3 | нет (только BM25) | ничего из вышеуказанного | — |

Эмбеддинги кешируются в `data/wiki_embeddings.json` с фингерпринтом провайдера/модели.

### Поиск: `WikiRAGService.retrieve()`

```
retrieve(query, top_k=3, max_chars=2500)
  │
  ├─ 1. Embedding search (cosine similarity > 0.3) — если провайдер доступен
  ├─ 2. Фолбэк на BM25 Okapi (k1=1.5, b=0.75, min_score=0.5)
  └─ 3. Форматирование результата:
       "[Документация по теме:]\n\n## Title (source_file)\nbody..."
```

Результат — строка markdown, которая **дописывается к системному промпту** (не как отдельное сообщение).

## 2. FAQ — быстрая проверка

FAQ загружается при старте из БД (`FAQService.get_all()` / синглтон `async_faq_manager`), перезагружается при изменениях через `/admin/faq`.

### Алгоритм матчинга

Одинаков во всех LLM-сервисах (`CloudLLMService`, `VLLMLLMService`, `LLMService`):

```
_check_faq(user_message):
  │
  ├─ Нормализация: lower().strip().rstrip("?!.,")
  ├─ 1. Exact match — точное совпадение с ключом
  ├─ 2. Partial match — подстрока в обе стороны (key in query ИЛИ query in key)
  └─ 3. Шаблоны: {current_time}, {current_date}, {day_of_week} подставляются в ответ
```

### Когда проверяется FAQ

- **`generate_response()` / `generate_response_stream()`** — проверяется всегда
- **`generate_response_from_messages()`** — только при `len(user_messages) == 1` (первое сообщение в сессии)
- Если FAQ сработал — **LLM не вызывается**, ответ возвращается мгновенно

## 3. Admin Chat — полный пайплайн

Эндпоинт: `POST /admin/chat/sessions/{id}/stream` (`app/routers/chat.py`)

```
Сообщение пользователя
  │
  ├─ 1. Определение LLM-сервиса
  │     llm_override (per-request) > widget_instance config > container.llm_service (глобальный)
  │
  ├─ 2. Сохранение user message в БД
  │     ChatService.add_message(session_id, "user", content)
  │
  ├─ 3. Системный промпт
  │     Кастомный (виджет / оверрайд) > llm.get_system_prompt() > _DEFAULT_RAG_PROMPT
  │
  ├─ 4. RAG-инжекция
  │     wiki_rag.retrieve(query, top_k=3) → дописывается к системному промпту
  │
  ├─ 5. Сборка сообщений для LLM
  │     get_messages_for_llm(session_id, system_prompt) →
  │     [{"role":"system","content":"промпт + RAG"}, user1, assistant1, user2, ...]
  │     (только is_active=True сообщения — учитывает ветвление)
  │
  ├─ 6. FAQ-проверка (внутри LLM-сервиса)
  │     Только для первого сообщения → если совпало, LLM не вызывается
  │
  ├─ 7. LLM-вызов
  │     generate_response_from_messages(messages, stream=True)
  │     └─ CloudLLMService → провайдер:
  │           GeminiProvider (SDK) / OpenAICompatibleProvider (httpx → /chat/completions)
  │
  ├─ 8. SSE стрим
  │     user_message → chunk* → assistant_message → [DONE]
  │
  └─ 9. Сохранение ответа в БД
        ChatService.add_message(session_id, "assistant", full_text)
```

### Сборка системного промпта (итог)

Финальный системный промпт, который видит LLM, собирается послойно:

```
┌─────────────────────────────────────────────────┐
│ Базовый промпт                                  │
│   widget.system_prompt                          │
│   ИЛИ llm_override.system_prompt               │
│   ИЛИ provider_config.system_prompt (cloud)     │
│   ИЛИ persona prompt (vLLM: Анна/Марина)       │
│   ИЛИ _DEFAULT_RAG_PROMPT (фолбэк)             │
├─────────────────────────────────────────────────┤
│ + RAG-контекст (если найден)                    │
│   [Документация по теме:]                       │
│   ## Заголовок секции (источник.md)             │
│   Содержимое релевантной секции...              │
│   ## Ещё секция (другой_источник.md)            │
│   ...                                           │
└─────────────────────────────────────────────────┘
```

## 4. Telegram бот — проксирование через оркестратор

Telegram бот работает как **отдельный процесс** (aiogram), обращается к оркестратору по HTTP.

### Полный путь сообщения

```
Сообщение в Telegram
  │
  ├─ 1. aiogram handler: on_text_message()                    [handlers/messages.py]
  │     Per-user lock для сериализации
  │
  ├─ 2. Сессия
  │     session_store.get_or_create(user_id)                  [services/session_store.py]
  │     └─ conversation_id = "tg-{user_id}-{uuid[:8]}"
  │     └─ system_prompt из BotConfig (БД) или TelegramSettings (env)
  │     session.append_message("user", text)
  │
  ├─ 3. LLM Router                                           [services/llm_router.py]
  │     llm_router.chat_stream(messages, session_id)
  │     │
  │     ├─ _ensure_session()
  │     │   POST /admin/chat/sessions → создаёт сессию в оркестраторе если нет
  │     │
  │     └─ POST /admin/chat/sessions/{id}/stream
  │         body: { content, llm_override: { llm_backend, system_prompt } }
  │         │
  │         └─ *** Полный пайплайн Admin Chat: RAG → FAQ → LLM ***
  │
  ├─ 4. Рендеринг стрима                                     [services/stream_renderer.py]
  │     render_stream(bot, chat_id, stream)
  │     ├─ Placeholder: ⏳
  │     ├─ Прогрессивное редактирование сообщения (по интервалу/минимум символов)
  │     ├─ Обработка TelegramRetryAfter (rate limit)
  │     └─ Разбиение на несколько сообщений если > 4096 символов
  │
  └─ 5. session.append_message("assistant", full_text)
```

### TZ-генерация (Claude)

Отдельный flow для расчёта заказа — quiz из 6 шагов через FSM (`handlers/tz.py`):

```
Quiz: тип проекта → описание → бизнес-цель → фичи → сроки → бюджет
  │
  └─ llm_router.generate_tz(TZ_SYSTEM_PROMPT, user_text)
       └─ backend = LLMBackend.CLAUDE → "cloud:claude-bridge-..."
            └─ POST /admin/chat/sessions/{id}/stream (llm_override → Claude)
```

## 5. Виджет — два режима

### Публичный виджет (без авторизации)

Эндпоинт: `POST /widget/chat/session/{id}/stream` (`modules/channels/widget/router_public.py`)

```
Сообщение в виджете
  │
  ├─ Валидация: session.source == "widget"
  ├─ LLM из конфига виджет-инстанса (widget.llm_backend)
  ├─ Rate limit per-instance (rate_limit_count / rate_limit_hours)
  ├─ Системный промпт из конфига виджета
  ├─ ⚠️ БЕЗ RAG — retrieve() не вызывается
  ├─ FAQ → LLM → SSE стрим
  └─ Сохранение в БД
```

### Виджет в админке (с JWT)

Если виджет открыт внутри админ-панели, JS-виджет подхватывает JWT из `localStorage('admin_token')` и отправляет запрос через **Admin Chat** эндпоинт с `widget_instance_id`:

```
POST /admin/chat/sessions/{id}/stream
  body: { content, widget_instance_id: "..." }
  │
  └─ Полный пайплайн: RAG + FAQ + LLM (с настройками виджета)
```

### Персистентность сессий (Replain-style)

Виджет сохраняет историю между переходами по страницам:
- Session ID хранится в cookie (`SameSite=None; Secure`, 30 дней) + `localStorage` (фолбэк)
- При загрузке страницы: `preloadHistory()` → `GET /widget/chat/session/{id}`
- Состояние open/closed — в `sessionStorage` (авто-открытие при навигации)

## 6. LLM-сервисы

Три реализации с единым интерфейсом (`generate_response_from_messages()`):

| Сервис | Файл | Когда используется |
|--------|------|--------------------|
| `CloudLLMService` | `cloud_llm_service.py` | `LLM_BACKEND=cloud:*` (основной в cloud mode) |
| `VLLMLLMService` | `vllm_llm_service.py` | `LLM_BACKEND=vllm` (локальный GPU) |
| `LLMService` | `llm_service.py` | legacy (deprecated, `LLM_BACKEND=gemini`) |

### CloudLLMService — фабрика провайдеров

```
CloudLLMService
  │
  ├─ GeminiProvider          — google-generativeai SDK
  │   └─ Конвертирует: system→system_instruction, assistant→"model" role
  │
  └─ OpenAICompatibleProvider — httpx → /chat/completions
      └─ Покрывает: OpenAI, Claude, DeepSeek, Kimi, OpenRouter, claude_bridge, Custom
      └─ claude_bridge: read timeout 300s, max_tokens 4096 (vs 60s/512 default)
```

### VLLMLLMService — персоны

Локальный vLLM с системой персон (Анна, Марина). Если в сообщениях нет system prompt — подставляет промпт текущей персоны. Добавляет `repetition_penalty` к параметрам генерации.

## 7. Сводная диаграмма

```
                    ┌─────────────┐     ┌──────────────┐     ┌──────────────┐
                    │ Admin Panel │     │ Telegram Bot │     │  Widget JS   │
                    │  (Vue 3)    │     │  (aiogram)   │     │  (iframe)    │
                    └──────┬──────┘     └──────┬───────┘     └──────┬───────┘
                           │                   │                    │
                           │            HTTP POST с              JWT есть?
                           │            llm_override             ├─ да → Admin endpoint
                           │                   │                 └─ нет → Widget endpoint
                           ▼                   ▼                    ▼
              ┌────────────────────────────────────────────────────────────┐
              │                    Оркестратор (FastAPI :8002)             │
              │                                                           │
              │  /admin/chat/sessions/{id}/stream    /widget/.../stream   │
              │         │                                  │              │
              │         ├─ RAG: wiki_rag.retrieve()       нет RAG        │
              │         ├─ FAQ check                       ├─ FAQ check  │
              │         ├─ LLM call                        ├─ LLM call   │
              │         └─ SSE stream                      └─ SSE stream │
              │                         │                                │
              │              ┌──────────┴──────────┐                     │
              │              ▼                     ▼                     │
              │     CloudLLMService         VLLMLLMService              │
              │     (Gemini, OpenAI,        (vLLM + персоны)            │
              │      Claude, etc.)                                      │
              └─────────────────────────────────────────────────────────┘
```

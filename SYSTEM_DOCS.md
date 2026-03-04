# AI Secretary System - Системная документация

## Обзор системы

AI Secretary System - интеллектуальная система виртуального секретаря с клонированием голоса (XTTS v2, OpenVoice v2), предобученными голосами (Piper), локальным LLM (vLLM + Qwen/Llama/DeepSeek), облачными LLM (Gemini, OpenAI, Claude, DeepSeek, Kimi, OpenRouter), CLI-OpenAI bridge, multi-instance ботами (Telegram, WhatsApp), чат-виджетами, воронкой продаж и полнофункциональной Vue 3 админ-панелью.

## Архитектура

```
                               ┌──────────────────────────────────────────────┐
                               │         Orchestrator (port 8002)             │
                               │            orchestrator.py                   │
                               │                                              │
                               │   ┌──────────────────────────────────────┐   │
                               │   │  Vue 3 Admin Panel (20 views, PWA)  │   │
                               │   │          admin/dist/                 │   │
                               │   └──────────────────────────────────────┘   │
                               │                                              │
                               │   ┌──────────────────────────────────────┐   │
                               │   │  21 API Routers (~371 endpoints)    │   │
                               │   │          app/routers/                │   │
                               │   └──────────────────────────────────────┘   │
                               │                                              │
                               │   ┌──────────────────────────────────────┐   │
                               │   │  ServiceContainer (DI)              │   │
                               │   │  app/dependencies.py                │   │
                               │   └──────────────────────────────────────┘   │
                               └───────────────────────┬──────────────────────┘
                                                       │
       ┌──────────┬──────────┬──────────┬──────────────┼────────────┬────────────┬──────────┐
       ↓          ↓          ↓          ↓              ↓            ↓            ↓          ↓
   Service     Multi-Bot    Cloud      vLLM        Voice Clone  Piper TTS    STT       System
   Manager     Manager      LLM       Service       XTTS v2      (CPU)     Vosk/      Monitor
               (Telegram,   Service   + LoRA                               Whisper
               WhatsApp)
```

### Режимы развёртывания (DEPLOYMENT_MODE)

| Режим | Описание | GPU | Сервисы |
|-------|----------|-----|---------|
| `full` | Все компоненты | Да | vLLM, XTTS, Piper, Vosk, GSM |
| `cloud` | Только облачные LLM | Нет | Cloud LLM, без TTS/STT/GPU |
| `local` | Эквивалент full | Да | Все компоненты |

### ServiceContainer (DI)

Singleton-контейнер (`app/dependencies.py`), инициализируется в `orchestrator.py` при старте. Содержит все сервисы:

```python
container = ServiceContainer()
container.db_manager          # DatabaseManager
container.service_manager     # ServiceManager (vLLM process)
container.voice_clone_service # VoiceCloneService (XTTS v2)
container.piper_tts_service   # PiperTTSService
container.stt_service         # UnifiedSTTService
container.vllm_service        # VLLMService
container.cloud_llm_service   # CloudLLMService
container.bridge_manager      # BridgeManager (CLI-OpenAI bridge)
container.multi_bot_manager   # MultiBotManager (Telegram)
container.whatsapp_manager    # WhatsAppManager
container.system_monitor      # SystemMonitor (GPU/CPU/RAM)
container.xray_manager        # XrayProxyManager (VLESS)
container.finetune_manager    # FinetuneManager (LoRA)
container.model_manager       # ModelManager (HuggingFace)
container.wiki_rag_service    # WikiRAGService
container.sales_funnel        # SalesFunnel
container.amocrm_service      # AmoCRMService
container.gsm_service         # GSMService
container.backup_service      # BackupService
```

## База данных

### Архитектура

```
┌─────────────────────────────────────────────────────────┐
│                      Orchestrator                        │
│                                                          │
│  ┌─────────────┐    ┌──────────────────┐    ┌────────┐  │
│  │  API        │───▶│  25 Repositories │───▶│ SQLite │  │
│  │  Routers    │    │  (BaseRepository │    │ (async)│  │
│  │  (21)       │    │   [Model])       │    └────────┘  │
│  └─────────────┘    └──────────────────┘         │      │
│                             │                    │      │
│                             ▼                    ▼      │
│                     ┌───────────────┐    ┌────────────┐ │
│                     │ DatabaseMgr   │    │   Redis    │ │
│                     │ (singleton)   │    │ (optional) │ │
│                     └───────────────┘    └────────────┘ │
└─────────────────────────────────────────────────────────┘
```

- **Engine**: SQLite + async SQLAlchemy (aiosqlite)
- **DB File**: `data/secretary.db`
- **Redis**: Опциональное кэширование (graceful fallback если недоступен)
- **Паттерн**: `BaseRepository[Model]` — generic CRUD для всех моделей
- **Доменные сервисы**: 31 класс в `modules/*/service.py` (например, `ChatService` в `modules/chat/service.py`)
- **Фасад**: `db/integration.py` (~100 строк) — импортирует синглтоны и классы из `modules/*/service.py` под старыми именами (например, `chat_service as async_chat_manager`)

### Таблицы (35 таблиц)

| Группа | Таблицы | Ключевые поля |
|--------|---------|---------------|
| **Users** | `users` | username, password_hash, role (admin/user/web/guest), is_active |
| **Chat** | `chat_sessions` | title, system_prompt, owner_id, source, source_id |
| | `chat_messages` | session_id, role, content, parent_id (branching), is_active |
| **FAQ / TTS** | `faq_entries` | question, answer, keywords (JSON), hit_count |
| | `tts_presets` | name, params (JSON), builtin, owner_id |
| **Config** | `system_config` | key (PK), value (JSON) |
| **Telegram** | `telegram_sessions` | bot_id + user_id (composite PK), chat_session_id |
| **Bot Instances** | `bot_instances` | Telegram bot (token, whitelist, LLM, TTS, payment) |
| | `widget_instances` | Website widget (appearance, domains, LLM, TTS) |
| | `whatsapp_instances` | WhatsApp bot (Cloud API credentials, LLM, TTS) |
| **Cloud LLM** | `cloud_llm_providers` | provider_type, api_key, model_name, is_default |
| **Sales Core** | `bot_agent_prompts` | LLM промпты для агентов воронки |
| | `bot_quiz_questions` | Вопросы quiz-сегментации |
| | `bot_segments` | Сегменты пользователей и правила маршрутизации |
| | `bot_user_profiles` | FSM state, segment, quiz_answers, discovery_data |
| **Sales Follow-up** | `bot_followup_rules` | Правила автоматических follow-up |
| | `bot_followup_queue` | Очередь отправки (scheduled_at, status) |
| | `bot_events` | События воронки для аналитики |
| | `bot_testimonials` | Отзывы для social proof |
| **Sales Config** | `bot_hardware_specs` | GPU рекомендации для hardware audit |
| | `bot_ab_tests` | A/B тесты (variants, metric, results) |
| | `bot_discovery_responses` | Ответы discovery flow |
| | `bot_subscribers` | Подписчики на новости |
| | `bot_github_configs` | GitHub webhook + PR comment конфиг |
| **Payments** | `payment_log` | payment_type (yookassa/stars), amount, status |
| **Usage** | `usage_log` | service_type, units_consumed, cost_usd |
| | `usage_limits` | limit_type (daily/monthly), limit_value |
| | `llm_presets` | LLM generation params (temperature, max_tokens) |
| **amoCRM** | `amocrm_config` | OAuth2 tokens, sync settings (singleton) |
| | `amocrm_sync_log` | Лог синхронизации |
| **GSM** | `gsm_call_logs` | direction, state, transcript, audio_file_path |
| | `gsm_sms_logs` | direction, number, text, status |
| **Legal** | `user_consents` | consent_type, consent_version, granted |
| **Knowledge** | `knowledge_documents` | filename, source_type, section_count |
| **Audit** | `audit_log` | action, resource, user_id, details (JSON) |

### Миграции

Миграции в `scripts/migrate_*.py` (идемпотентные, безопасно перезапускать):

```bash
./venv/bin/python scripts/migrate_json_to_db.py      # Первичная миграция JSON → SQLite
./venv/bin/python scripts/migrate_users.py            # Таблица users
./venv/bin/python scripts/migrate_to_instances.py     # Multi-instance боты
./venv/bin/python scripts/migrate_sales_bot.py        # Sales funnel таблицы
./venv/bin/python scripts/migrate_chat_branches.py    # Chat branching (parent_id, is_active)
./venv/bin/python scripts/migrate_whatsapp.py         # WhatsApp instances
./venv/bin/python scripts/migrate_amocrm.py           # amoCRM таблицы
./venv/bin/python scripts/migrate_gsm_tables.py       # GSM call/SMS logs
./venv/bin/python scripts/migrate_knowledge_base.py   # Knowledge Base documents
./venv/bin/python scripts/migrate_legal_compliance.py # Legal consent tracking
```

## LLM подсистема

### Backends

| Backend | Класс | Описание |
|---------|-------|----------|
| `vllm` | `VLLMService` | Локальный vLLM (GPU, Qwen/Llama/DeepSeek + LoRA) |
| `cloud:{id}` | `CloudLLMService` | Облачные провайдеры (Gemini, Kimi, OpenAI, Claude, DeepSeek, OpenRouter) |
| `cloud:bridge-{id}` | `BridgeManager` | CLI-OpenAI bridge (Claude Code, Gemini CLI) |
| `gemini` | `LLMService` | Gemini legacy (устаревший, заменён cloud providers) |

### Cloud LLM Providers (в БД)

| Тип | API | Модели |
|-----|-----|--------|
| `gemini` | Google AI SDK | gemini-2.0-flash, gemini-2.5-pro |
| `kimi` | OpenAI-compat | kimi-k2, moonshot-v1-8k/32k/128k |
| `openai` | OpenAI | gpt-4o, gpt-4o-mini |
| `claude` | Anthropic | claude-opus-4-6, claude-sonnet-4-5 |
| `deepseek` | OpenAI-compat | deepseek-chat, deepseek-reasoner |
| `openrouter` | OpenAI-compat | nemotron-3-nano:free, trinity-large:free |
| `custom` | OpenAI-compat | Любая модель с base_url |

### VLESS Proxy (для Gemini)

`XrayProxyManager` управляет xray-core для маршрутизации Gemini API через VLESS прокси:
- Multiple VLESS URLs с автоматическим failover
- Поддержка: REALITY, TLS, none security; TCP, WebSocket, gRPC transport
- Статус и управление через `/admin/llm/proxy/*` endpoints

### Персоны

| Персона | Имя | Описание |
|---------|-----|----------|
| `anna` | Анна | Дружелюбный секретарь (default) |
| `marina` | Марина | Альтернативная персона |

Системные промпты хранятся в `vllm_llm_service.py:SECRETARY_PERSONAS` и редактируются через API/админ-панель.

## TTS подсистема

### Движки

| Движок | Класс | GPU | Качество | Скорость |
|--------|-------|-----|----------|----------|
| XTTS v2 | `VoiceCloneService` | CC >= 7.0 | Лучшее клонирование | ~5-10s |
| OpenVoice v2 | `OpenVoiceService` | CC >= 6.1 | Хорошее клонирование | ~2-4s |
| Piper | `PiperTTSService` | CPU | Предобученные голоса | ~0.5s |

### XTTS v2 пресеты интонаций

| Пресет | temperature | rep_penalty | speed | Описание |
|--------|-------------|-------------|-------|----------|
| `natural` | 0.75 | 4.0 | 0.98 | Естественный (по умолчанию) |
| `warm` | 0.85 | 3.0 | 0.95 | Тёплый, дружелюбный |
| `calm` | 0.5 | 6.0 | 0.9 | Спокойный, профессиональный |
| `energetic` | 0.9 | 2.5 | 1.1 | Энергичный, быстрый |
| `neutral` | 0.7 | 5.0 | 1.0 | Нейтральный деловой |

Пользовательские пресеты хранятся в таблице `tts_presets` (JSON params).

### Препроцессинг текста

- **Е→Ё замена**: автоматическая (~50 слов: все→всё, еще→ещё, идет→идёт...)
- **Паузы**: двойной пробел → `"... "`, запятая после вводных слов
- **Вводные слова**: "Здравствуйте", "Конечно", "К сожалению", "Пожалуйста"...

### Streaming TTS

| Endpoint | Протокол | Описание |
|----------|----------|----------|
| `/admin/tts/stream` | HTTP chunked | Streaming TTS (POST) |
| `/admin/tts/ws/stream` | WebSocket | Real-time bidirectional TTS |

Для телефонии: target TTFA <500ms, 8kHz PCM16, G.711 A-law.

### Кэширование speaker latents

```
./cache/
└── speaker_latents_*.pkl   # Хэш от списка файлов образцов
```

Предвычисляются при первом запуске, мгновенная загрузка при последующих. Инвалидируются при изменении образцов.

## STT подсистема

| Движок | Класс | Режим | Скорость | Описание |
|--------|-------|-------|----------|----------|
| Vosk | `UnifiedSTTService` | Realtime streaming | Быстро | Телефония, микрофон |
| Whisper | `UnifiedSTTService` | Batch | Медленнее | Транскрибация файлов |

`UnifiedSTTService` автоматически выбирает оптимальный движок.

## Чат-система

### Branching (ветвление диалогов)

OpenWebUI-style non-destructive message editing:

- `ChatMessage.parent_id` — FK на родительское сообщение (дерево)
- `ChatMessage.is_active` — только активная ветка отображается
- Редактирование создаёт sibling (новую ветку), а не перезаписывает
- Regeneration создаёт новый assistant-ответ от того же parent
- Навигация по веткам: `< 1/3 >`

### Source Tracking

Каждая сессия имеет source (admin/telegram/widget/whatsapp) и source_id для группировки и фильтрации.

### Wiki RAG

Тёрофильтрация:
1. **FAQ** — точное/wildcard/regex совпадение → мгновенный ответ
2. **Wiki RAG** — семантический поиск (embeddings + BM25) по `wiki-pages/` → контекст для LLM
3. **LLM** — без дополнительного контекста

Сервис: `WikiRAGService` (`app/services/wiki_rag_service.py`), embeddings через `EmbeddingProvider`.

## Боты (Multi-Instance)

### Telegram

`MultiBotManager` управляет жизненным циклом нескольких ботов. Каждый `BotInstance` имеет:
- Отдельный Telegram token и whitelist пользователей
- Независимые LLM backend, персона, системный промпт
- Независимые TTS engine, голос, пресет
- Изоляция сессий (пользователи в разных ботах имеют отдельные истории)
- Собственные настройки платежей (YooKassa, Telegram Stars)

### WhatsApp

`WhatsAppManager` через WhatsApp Cloud API:
- Multi-instance с независимыми настройками
- Поддержка FAQ, AI-чат, воронка продаж
- phone_number_id, waba_id, access_token, verify_token

### Widget

Multi-instance чат-виджеты для сайтов:
- Встраиваемый `widget.js` с параметром `?instance=...`
- Настраиваемый внешний вид (цвета, тексты, позиция)
- Whitelist доменов
- SSE streaming ответы

## Воронка продаж (Sales Funnel)

`SalesFunnel` (`app/services/sales_funnel.py`) — FSM-based quiz-сегментация:

1. **Welcome** → приветствие + кнопки
2. **Quiz** → 3-4 вопроса для сегментации
3. **Segment** → маршрутизация по правилам (`bot_segments`)
4. **Agent** → LLM с segment-specific промптом (`bot_agent_prompts`)
5. **TZ Generator** → генерация ТЗ для custom-сегмента
6. **Payment** → оплата (YooMoney, Telegram Stars)
7. **Follow-up** → автоматические напоминания (`bot_followup_rules`)

### A/B тестирование

`bot_ab_tests` — сплит-тесты с JSON variants и автоматическим подсчётом результатов.

### GitHub Integration

`bot_github_configs` — webhook для PR comments (AI-review) и broadcast (новости из коммитов).

## amoCRM интеграция

`AmoCRMService` (`app/services/amocrm_service.py`):
- OAuth2 авторизация (access_token + refresh_token)
- Синхронизация контактов и лидов
- Автоматическое создание лидов из Telegram
- Пайплайны и статусы

## Мониторинг

`SystemMonitor` (`system_monitor.py`) собирает данные через nvidia-smi, psutil и Docker CLI:

| Метрики | Источник |
|---------|----------|
| GPU (utilization, VRAM, temperature, power, fan) | nvidia-smi / torch.cuda |
| CPU (model, cores, frequency, per-core usage, temperature) | psutil |
| RAM / Swap | psutil |
| Диски (device, mount, usage) | psutil |
| Docker контейнеры (name, status, CPU, memory) | docker CLI |
| Сеть (interface, IP, traffic) | psutil |
| Процессы (top-10 по CPU + RAM) | psutil |

Данные доставляются через SSE (`/admin/monitor/gpu/stream`) с fallback на polling.

## Аутентификация и RBAC

`AuthManager` (`auth_manager.py`) — JWT аутентификация:

| Роль | Доступ |
|------|--------|
| `admin` | Полный доступ ко всем вкладкам и API |
| `user` | Ограниченный доступ, видит свои ресурсы |
| `web` | Скрыты инфраструктурные вкладки (Dashboard, Services, TTS, Monitoring, Models, Finetune, GSM) |
| `guest` | Только просмотр, не может менять профиль/пароль |

Resource ownership: bot instances, widget instances, chat sessions, TTS presets привязаны к `owner_id`.

Управление пользователями через CLI:
```bash
python scripts/manage_users.py list
python scripts/manage_users.py create <user> <pass> --role user
python scripts/manage_users.py set-role <user> <role>
```

## Админ-панель

Vue 3 PWA с 20 вкладками:

| Технология | Описание |
|------------|----------|
| Vue 3 + Composition API + TypeScript | Frontend framework |
| Vite | Build tool |
| Tailwind CSS | Стилизация (3 темы: Light, Dark, Night Eyes) |
| Pinia + persistedstate | State management (11 stores) |
| TanStack Query | Data fetching + caching + SSE |
| Chart.js + vue-chartjs | Графики и спарклайны |
| vue-i18n | Интернационализация (ru/en) |
| Lucide Vue | Иконки |

### Demo Mode

Для демонстрации без бэкенда:
- Monkey-patches `window.fetch` в `admin/src/api/demo/index.ts`
- 22 файла mock-данных в `admin/src/api/demo/`
- Роли: `VITE_DEMO_ROLE=admin` (полный) или `VITE_DEMO_ROLE=web` (customer-facing)
- Deployment mode: `VITE_DEMO_DEPLOYMENT_MODE=full` или `cloud`

```bash
npm run build -- --mode demo      # Full demo (role=admin, full mode) → /full/
npm run build -- --mode demo-web  # Cloud demo (role=web, cloud mode) → /cloud/
# Both deployed by: bash /root/deploy-demo.sh
```

## API (21 роутер, ~371 endpoint)

| Роутер | Файл | Endpoints | Описание |
|--------|------|-----------|----------|
| auth | `auth.py` | 6 | JWT login, profile, password, auth status |
| audit | `audit.py` | 4 | Audit log, export, cleanup |
| services | `services.py` | 6 | vLLM start/stop/restart, logs |
| monitor | `monitor.py` | 9 | GPU/CPU/system stats, health, metrics SSE |
| faq | `faq.py` | 7 | FAQ CRUD, reload, test, export |
| stt | `stt.py` | 4 | STT status, transcribe, test |
| llm | `llm.py` | 42 | Backend, persona, params, providers, VLESS proxy, models, bridge |
| tts | `tts.py` | 14 | Presets, params, test, cache, streaming |
| chat | `chat.py` | 13 | Sessions, messages, streaming, branching |
| telegram | `telegram.py` | 28 | Bot instances CRUD, control, sales, payments |
| widget | `widget.py` | 7 | Widget instances CRUD |
| whatsapp | `whatsapp.py` | 10 | WhatsApp bot instances CRUD, control |
| gsm | `gsm.py` | 14 | GSM telephony (SIM7600E-H) |
| backup | `backup.py` | 8 | Backup/restore configuration |
| bot_sales | `bot_sales.py` | 43 | Sales funnel, segments, testimonials, subscribers, broadcast |
| yoomoney | `yoomoney_webhook.py` | 1 | YooMoney payment callback |
| amocrm | `amocrm.py` | 16 | amoCRM OAuth2, contacts, leads, pipelines |
| usage | `usage.py` | 10 | Usage tracking, limits, statistics |
| legal | `legal.py` | 11 | Legal compliance |
| wiki_rag | `wiki_rag.py` | 9 | Wiki RAG stats/search, Knowledge Base CRUD |
| github | `github_webhook.py` | 1 | GitHub CI/CD webhook |

### OpenAI-Compatible API

Для интеграции с OpenWebUI и другими клиентами:

```
GET  /v1/models                    # Список моделей
POST /v1/chat/completions          # Chat completion
POST /v1/audio/speech              # Text-to-Speech
```

## GPU конфигурация (для full mode)

### Рекомендации по VRAM

| VRAM | Рекомендация |
|------|-------------|
| 8 GB | Qwen2.5-7B AWQ + Piper TTS |
| 12 GB | Qwen2.5-7B AWQ + XTTS v2 |
| 16 GB+ | Llama-3.1-8B FP16 + XTTS v2 |
| Без GPU | Cloud LLM + Piper TTS |

### Оптимизации CUDA

- TF32 для матричных операций
- cuDNN benchmark mode
- Автоочистка кэша после синтеза
- vLLM: `--gpu-memory-utilization 0.5` для совместного использования с XTTS

## Развёртывание

### Docker

```bash
docker compose up -d                                           # Orchestrator + Redis
docker compose -f docker-compose.yml -f docker-compose.full.yml up -d  # + vLLM
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d   # CPU mode
```

### Systemd (production)

```bash
# Service: ai-secretary.service
# EnvironmentFile: /opt/ai-secretary/.env
systemctl start ai-secretary
systemctl status ai-secretary
curl http://localhost:8002/health
```

### Сборка админ-панели

```bash
cd admin
npm install
npm run build              # Production → admin/dist/
npm run dev                # Dev server → http://localhost:5173
```

## Конфигурация (.env)

```bash
# LLM
LLM_BACKEND=vllm                        # vllm | cloud:{id} | gemini
DEPLOYMENT_MODE=full                     # full | cloud | local
VLLM_API_URL=http://localhost:11434
VLLM_MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ
SECRETARY_PERSONA=anna

# Security
ADMIN_JWT_SECRET=...                     # Auto-generated if empty
ADMIN_AUTH_ENABLED=true
RATE_LIMIT_ENABLED=true

# Database
REDIS_URL=redis://localhost:6379/0       # Optional

# Server
ORCHESTRATOR_PORT=8002
```

Полный список переменных в `.env.example`.

---
*Обновлено: 2026-03-03*

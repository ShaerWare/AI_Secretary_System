<!-- HEADER BANNER -->
<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=6,11,20&height=200&section=header&text=AI%20Secretary%20System&fontSize=45&fontColor=fff&animation=fadeIn&fontAlignY=35&desc=Self-hosted%20AI%20Assistant%20with%20Voice%20Cloning%20%26%20LLM&descSize=16&descAlignY=55" width="100%"/>

<div align="center">

[![CI](https://github.com/ShaerWare/AI_Secretary_System/actions/workflows/ci.yml/badge.svg)](https://github.com/ShaerWare/AI_Secretary_System/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Vue 3](https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white)](https://vuejs.org)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![Endpoints](https://img.shields.io/badge/API-371+_endpoints-FF6D00?logo=fastapi&logoColor=white)](#modular-api-structure)

**Self-hosted AI-секретарь с клонированием голоса, локальным и облачным LLM, Telegram/WhatsApp ботами и Vue 3 админ-панелью**

[![Сайт проекта](https://img.shields.io/badge/Сайт_проекта-ai--sekretar24.ru-4285F4?style=for-the-badge&logo=google-chrome&logoColor=white)](https://ai-sekretar24.ru/)
[![Демо](https://img.shields.io/badge/Демо-demo.ai--sekretar24.ru-00C853?style=for-the-badge&logo=google-chrome&logoColor=white)](https://demo.ai-sekretar24.ru/full/)
[![Telegram](https://img.shields.io/badge/Telegram_бот-@shaerware__digital__bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/shaerware_digital_bot)

[Сайт проекта](https://ai-sekretar24.ru/) | [Демо (Full)](https://demo.ai-sekretar24.ru/full/) | [Демо (Cloud)](https://demo.ai-sekretar24.ru/cloud/) | [Telegram бот](https://t.me/shaerware_digital_bot) | [Wiki](https://github.com/ShaerWare/AI_Secretary_System/wiki) | [Issues](https://github.com/ShaerWare/AI_Secretary_System/issues)

---

</div>

Интеллектуальная система виртуального секретаря с клонированием голоса (XTTS v2, OpenVoice), предобученными голосами (Piper), локальным LLM (vLLM + Qwen/Llama/DeepSeek), облачным LLM (Gemini, OpenAI, Claude, DeepSeek, Kimi, OpenRouter) и CLI-OpenAI bridge (Claude Code, Gemini CLI). Включает полнофункциональную Vue 3 админ-панель с 20 вкладками, i18n, PWA, multi-user RBAC, amoCRM интеграцией и воронкой продаж.

## Features

- **Multi-Voice TTS**: 5 голосов (2 клонированных XTTS, 1 OpenVoice, 2 Piper)
- **Speech-to-Text**: Vosk (realtime streaming) + Whisper (batch)
- **Multi-Persona LLM**: 2 персоны секретаря (Анна, Марина)
- **Local LLM**: vLLM с Qwen2.5-7B/Llama-3.1-8B/DeepSeek-7B + LoRA fine-tuning
- **Cloud LLM Providers**: Подключение облачных LLM (Gemini, Kimi, OpenAI, Claude, DeepSeek, OpenRouter) с хранением credentials в БД
- **Multi-Instance Bots**: Несколько Telegram ботов с независимыми настройками (LLM, TTS, промпт)
- **WhatsApp Bots**: Multi-instance WhatsApp боты (Cloud API) с воронкой продаж, FAQ, AI-чатом
- **Multi-Instance Widgets**: Несколько чат-виджетов для разных сайтов/отделов
- **FAQ System**: Мгновенные ответы на типичные вопросы
- **Sales Funnel**: Quiz-based segmentation, TZ generator, payment integration (YooMoney, Telegram Stars)
- **Admin Panel**: Vue 3 PWA с 20 вкладками, i18n, темами, аудитом, responsive layout
- **GSM Telephony**: Поддержка SIM7600E-H для голосовых звонков и SMS
- **Website Widget**: Встраиваемый чат-виджет для любого сайта
- **Telegram Bot**: Общение с ассистентом через Telegram
- **Chat with TTS**: Озвучивание ответов ассистента в чате
- **OpenAI-compatible API**: Интеграция с OpenWebUI
- **Fine-tuning Pipeline**: Загрузка датасета → Обучение → Hot-swap адаптеров
- **Offline-first**: Все компоненты работают без интернета
- **Database**: SQLite + Redis для надёжного хранения с транзакциями

## Architecture

```
                              ┌──────────────────────────────────────────┐
                              │        Orchestrator (port 8002)          │
                              │           orchestrator.py                │
                              │                                          │
                              │  ┌────────────────────────────────────┐  │
                              │  │  Vue 3 Admin Panel (20 views, PWA) │  │
                              │  │         admin/dist/                │  │
                              │  └────────────────────────────────────┘  │
                              └──────────────────┬───────────────────────┘
                                                 │
      ┌──────────────┬──────────────┬────────────┼────────────┬─────────────┬──────────────┬──────────────┐
      ↓              ↓              ↓            ↓            ↓             ↓              ↓              ↓
 Service        Finetune        LLM         Voice Clone   OpenVoice    Piper TTS       FAQ           STT
 Manager        Manager       Service         XTTS v2       v2          (CPU)         System     Vosk/Whisper
service_      finetune_      vLLM/Gemini   voice_clone_  openvoice_   piper_tts_   typical_      stt_
manager.py    manager.py                   service.py    service.py   service.py   responses.json service.py
```

### Modular API Structure

API endpoints organized into 21 routers with ~371 endpoints total:

```
app/
├── __init__.py
├── dependencies.py          # ServiceContainer for DI
└── routers/
    ├── __init__.py
    ├── auth.py              # 6 endpoints  - JWT login, profile, password, auth status
    ├── audit.py             # 4 endpoints  - Audit log viewing, export, cleanup
    ├── services.py          # 6 endpoints  - vLLM start/stop/restart, logs
    ├── monitor.py           # 9 endpoints  - GPU/CPU/system stats, health, metrics SSE
    ├── faq.py               # 7 endpoints  - FAQ CRUD, reload, test
    ├── stt.py               # 4 endpoints  - STT status, transcribe, test
    ├── llm.py               # 42 endpoints - Backend, persona, params, providers, VLESS proxy, models, bridge
    ├── tts.py               # 14 endpoints - Presets, params, test, cache, streaming
    ├── chat.py              # 13 endpoints - Sessions, messages, streaming, branching
    ├── telegram.py          # 28 endpoints - Bot instances CRUD, control, sales, payments
    ├── widget.py            # 7 endpoints  - Widget instances CRUD
    ├── gsm.py               # 14 endpoints - GSM telephony (SIM7600E-H)
    ├── backup.py            # 8 endpoints  - Backup/restore configuration
    ├── bot_sales.py         # 43 endpoints - Sales funnel, segments, testimonials, subscribers, broadcast
    ├── yoomoney_webhook.py  # 1 endpoint   - YooMoney payment callback
    ├── amocrm.py            # 16 endpoints - amoCRM OAuth2, contacts, leads, pipelines
    ├── usage.py             # 10 endpoints - Usage tracking, limits, statistics
    ├── legal.py             # 11 endpoints - Legal compliance
    ├── wiki_rag.py          # 9 endpoints  - Wiki RAG stats/search, Knowledge Base CRUD
    ├── whatsapp.py          # 10 endpoints - WhatsApp bot instances CRUD, control
    └── github_webhook.py    # 1 endpoint   - GitHub CI/CD webhook
```

### GPU Configuration (RTX 3060 12GB)

```
vLLM Qwen2.5-7B + LoRA  →  ~6GB (50% GPU, port 11434)
XTTS v2 voice cloning   →  ~5GB (remaining)
────────────────────────────────────────────────────────
Total                   →  ~11GB
```

## Quick Start (Docker)

```bash
# Clone repository
git clone https://github.com/ShaerWare/AI_Secretary_System
cd AI_Secretary_System

# Configure environment
cp .env.docker.example .env
# Edit .env: set GEMINI_API_KEY for cloud fallback

# Option 1: Use LOCAL vLLM (recommended - faster, no 9GB download)
./start_qwen.sh                    # Start local vLLM first
docker compose up -d               # Start orchestrator + redis

# Option 2: FULL containerized (downloads ~9GB vLLM image)
docker compose -f docker-compose.yml -f docker-compose.full.yml up -d

# Option 3: CPU Mode (Piper + Gemini) - no GPU required
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d

# Check status
docker compose ps
curl http://localhost:8002/health

# Admin Panel: http://localhost:8002/admin (login: admin / admin)

# View logs
docker compose logs -f orchestrator

# Stop
docker compose down
```

**Requirements (Docker):**
- Docker & Docker Compose v2
- NVIDIA Container Toolkit (GPU mode only)
- 12GB+ VRAM (GPU) or Gemini API key (CPU)

**vLLM в Docker режиме:**

vLLM автоматически запускается как отдельный контейнер при переключении LLM backend в админ-панели.

```bash
# Первый раз: скачать образ vLLM (~9GB, одноразово)
docker pull vllm/vllm-openai:latest

# После этого переключение на vLLM в Admin Panel → LLM → Backend
# автоматически создаст и запустит vLLM контейнер

# Проверить статус vLLM контейнера
docker ps | grep vllm

# Логи vLLM
docker logs ai-secretary-vllm
```

Загрузка модели при первом запуске занимает 2-3 минуты.

## Quick Start (Local Development)

```bash
# First-time setup
./setup.sh
cp .env.example .env
# Edit .env: GEMINI_API_KEY (optional if using vLLM)

# Database setup (first time only)
pip install aiosqlite "sqlalchemy[asyncio]" alembic redis
python scripts/migrate_json_to_db.py

# GPU Mode (recommended): XTTS + Qwen2.5-7B + LoRA
./start_gpu.sh

# CPU Mode: Piper + Gemini API
./start_cpu.sh

# Health check (includes database status)
curl http://localhost:8002/health

# Admin Panel
open http://localhost:8002/admin
# Login: admin / admin (dev mode)
```

## Admin Panel

Полнофункциональная Vue 3 PWA админ-панель с 20 вкладками:

| Tab | Description |
|-----|-------------|
| **Dashboard** | Статусы сервисов, GPU спарклайны, health индикаторы |
| **Chat** | Чат с ИИ, Voice Mode (auto-TTS), голосовой ввод (STT), branching (ветвление диалогов), управление чатами |
| **Services** | Запуск/остановка vLLM, SSE логи в реальном времени |
| **LLM** | Выбор модели (Qwen/Llama/DeepSeek), персоны, параметры генерации, Cloud providers |
| **TTS** | Выбор голоса, пресеты XTTS, тестирование синтеза |
| **FAQ** | Редактирование типичных ответов (CRUD), тест, импорт/экспорт |
| **Finetune** | LoRA fine-tuning + Cloud AI Training (Wiki RAG, Knowledge Base) |
| **Monitoring** | GPU/CPU/RAM/Disk/Docker/Network мониторинг, Chart.js графики |
| **Models** | Управление скачанными моделями HuggingFace |
| **Widget** | Multi-instance чат-виджеты для сайтов |
| **Telegram** | Multi-instance Telegram боты с независимыми настройками |
| **WhatsApp** | Multi-instance WhatsApp боты (Cloud API) |
| **Audit** | Логирование действий, фильтрация, экспорт |
| **Settings** | Профиль, язык, тема, экспорт/импорт |
| **GSM** | Управление GSM-модемом SIM7600E-H, звонки, SMS |
| **amoCRM** | OAuth2 интеграция, контакты, лиды, пайплайны |
| **Sales** | Воронка продаж, сегменты, отзывы, подписчики, рассылки |
| **Usage** | Трекинг использования TTS/STT/LLM, лимиты |
| **Legal** | Юридическое соответствие, пользовательские соглашения |
| **Backup** | Резервное копирование и восстановление конфигураций |

### Admin Panel Features

| Feature | Description |
|---------|-------------|
| **JWT Authentication** | Безопасный вход с dev-mode fallback |
| **Multi-user Roles** | admin, user, web, guest с разными правами (RBAC) |
| **i18n** | Полная поддержка русского и английского |
| **Themes** | Light, Dark, Night-Eyes (тёплая для глаз) |
| **PWA** | Установка как приложение, offline кэширование |
| **Real-time** | SSE метрики GPU с fallback на polling |
| **Chat TTS** | Озвучивание ответов ассистента (Volume2 button) |
| **Voice Mode** | Auto-play TTS при получении ответа |
| **Voice Input** | Голосовой ввод через микрофон (STT) |
| **Prompt Editor** | Редактирование дефолтного промпта из чата |
| **Chat Management** | Переименование, групповое удаление, группировка по источнику (Admin/Telegram/Widget) |
| **Charts** | Спарклайны и графики на Chart.js |
| **Command Palette** | Быстрый поиск ⌘K / Ctrl+K |
| **Audit Log** | Логирование всех действий пользователей |
| **Export/Import** | Резервное копирование конфигураций |
| **Responsive** | Mobile-first с collapsible sidebar |
| **Confirmation** | Диалоги подтверждения для опасных действий |
| **Toasts** | Уведомления о результатах операций |

### Development Mode

```bash
cd admin
npm install
npm run dev
# Open http://localhost:5173
# Login: admin / admin
```

### Technology Stack

- **Frontend**: Vue 3 + Composition API + TypeScript
- **Build**: Vite
- **Styling**: Tailwind CSS (3 themes: Light, Dark, Night Eyes)
- **State**: Pinia + persistedstate (11 stores)
- **Data**: TanStack Query (caching + SSE)
- **Charts**: Chart.js + vue-chartjs
- **i18n**: vue-i18n (ru/en)
- **Icons**: Lucide Vue

## Voices

| Voice | Engine | GPU Required | Speed | Quality |
|-------|--------|--------------|-------|---------|
| `anna` | XTTS v2 | CC >= 7.0 | ~5-10s | Best cloning |
| `marina` | XTTS v2 | CC >= 7.0 | ~5-10s | Best cloning |
| `marina_openvoice` | OpenVoice v2 | CC >= 6.1 | ~2-4s | Good cloning |
| `dmitri` | Piper | CPU | ~0.5s | Pre-trained male |
| `irina` | Piper | CPU | ~0.5s | Pre-trained female |

**Voice Samples:**
- `./Анна/` - 122 WAV files
- `./Марина/` - WAV files

**Switching Voice:**
```bash
# Via API
curl -X POST http://localhost:8002/admin/voice \
  -H "Content-Type: application/json" \
  -d '{"voice": "anna"}'

# Via Admin Panel
open http://localhost:8002/admin → TTS tab
```

## Speech-to-Text (STT)

Система поддерживает два движка распознавания речи:

| Engine | Mode | Speed | Use Case |
|--------|------|-------|----------|
| **Vosk** | Realtime streaming | Fast | Телефония, микрофон |
| **Whisper** | Batch processing | Slower | Транскрибация файлов |

`UnifiedSTTService` автоматически выбирает оптимальный движок.

**Установка модели Vosk:**
```bash
mkdir -p models/vosk
cd models/vosk
wget https://alphacephei.com/vosk/models/vosk-model-ru-0.42.zip
unzip vosk-model-ru-0.42.zip
```

**Использование API:**
```bash
# Статус STT
curl http://localhost:8002/admin/stt/status

# Транскрибация файла
curl -X POST http://localhost:8002/admin/stt/transcribe \
  -F "audio=@recording.wav"
```

## Database

Система использует SQLite для надёжного хранения данных с опциональным Redis кэшированием.

### Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                      Orchestrator                           │
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │   API       │───▶│ Repositories│───▶│ SQLite + Redis  │  │
│  │  Endpoints  │    │  (db/)      │    │ (data/)         │  │
│  └─────────────┘    └─────────────┘    └─────────────────┘  │
│                            │                                │
│                            ▼                                │
│                    ┌─────────────────┐                      │
│                    │ JSON Sync       │                      │
│                    │ (backward compat)│                      │
│                    └─────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

### Таблицы SQLite (35 таблиц)

| Группа | Таблицы | Описание |
|--------|---------|----------|
| **Users & Auth** | `users` | Пользователи, роли (admin/user/web/guest), JWT аутентификация |
| **Chat** | `chat_sessions`, `chat_messages` | Сессии и сообщения с branching (parent_id, is_active), source tracking |
| **FAQ & TTS** | `faq_entries`, `tts_presets` | FAQ записи с hit_count; пресеты TTS с JSON параметрами |
| **Config** | `system_config` | Key-value хранилище конфигурации |
| **Telegram** | `telegram_sessions` | Маппинг Telegram user → chat session (composite PK: bot_id + user_id) |
| **Bot Instances** | `bot_instances`, `widget_instances`, `whatsapp_instances` | Multi-instance боты с независимыми настройками (LLM, TTS, промпт) |
| **Cloud LLM** | `cloud_llm_providers` | Провайдеры облачных LLM (Gemini, Kimi, OpenAI, Claude, DeepSeek, OpenRouter) |
| **Sales Funnel** | `bot_agent_prompts`, `bot_quiz_questions`, `bot_segments`, `bot_user_profiles` | Промпты агентов, quiz-сегментация, профили пользователей |
| **Follow-up** | `bot_followup_rules`, `bot_followup_queue`, `bot_events`, `bot_testimonials` | Правила follow-up, очередь отправки, события воронки, отзывы |
| **Sales Config** | `bot_hardware_specs`, `bot_ab_tests`, `bot_discovery_responses`, `bot_subscribers`, `bot_github_configs` | A/B тесты, подписчики, GitHub webhook конфиг |
| **Payments** | `payment_log` | Логи платежей (YooKassa, Telegram Stars) |
| **Usage** | `usage_log`, `usage_limits`, `llm_presets` | Трекинг использования TTS/STT/LLM, лимиты, пресеты генерации |
| **amoCRM** | `amocrm_config`, `amocrm_sync_log` | OAuth2 конфигурация (singleton), лог синхронизации |
| **GSM** | `gsm_call_logs`, `gsm_sms_logs` | Логи звонков и SMS |
| **Legal** | `user_consents` | Согласия пользователей (GDPR) |
| **Knowledge** | `knowledge_documents` | Документы Knowledge Base (wiki-pages/) |
| **Audit** | `audit_log` | Аудит всех действий пользователей |

### Redis кэширование (опционально)

| Ключ | Назначение | TTL |
|------|------------|-----|
| `chat:session:{id}` | Кэш сессий чата | 5 мин |
| `faq:cache` | FAQ словарь | 10 мин |
| `config:{key}` | Системные конфиги | 5 мин |

### Миграция данных

```bash
# Первый запуск — миграция JSON в SQLite
python scripts/migrate_json_to_db.py

# Или через setup скрипт
./scripts/setup_db.sh

# Тестирование базы данных
python scripts/test_db.py
```

### Расположение файлов

```
data/
└── secretary.db              # SQLite база данных

db/
├── database.py               # Async SQLAlchemy + aiosqlite
├── models.py                 # 35 ORM моделей
├── redis_client.py           # Redis клиент (опционально)
├── integration.py            # DatabaseManager singleton + backward-compat
└── repositories/             # 25 репозиториев (BaseRepository[Model] паттерн)
    ├── base.py               # Базовый generic репозиторий
    ├── chat.py               # ChatRepository (sessions + messages + branching)
    ├── faq.py, preset.py     # FAQ, TTS presets
    ├── config.py, audit.py   # System config, audit log
    ├── user.py, telegram.py  # Users, Telegram sessions
    ├── bot_instance.py       # Telegram bot instances
    ├── widget_instance.py    # Widget instances
    ├── whatsapp_instance.py  # WhatsApp instances
    ├── cloud_provider.py     # Cloud LLM providers
    ├── bot_*.py (12 файлов)  # Sales funnel (prompts, quiz, segments, profiles, followup, events...)
    ├── payment.py, usage.py  # Payments, usage tracking + limits
    ├── amocrm.py, gsm.py    # amoCRM, GSM call/SMS logs
    ├── consent.py            # Legal consents
    ├── knowledge_document.py # Knowledge Base documents
    └── llm_preset.py         # LLM generation presets
```

## External Access (ngrok)

Для работы виджета на внешних сайтах и Telegram бота требуется внешний доступ к серверу:

### Установка ngrok

**Linux:**
```bash
# Через snap
sudo snap install ngrok

# Или скачать бинарник
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
tar xvzf ngrok-v3-stable-linux-amd64.tgz
sudo mv ngrok /usr/local/bin/

# Авторизация (получить токен на https://dashboard.ngrok.com)
ngrok config add-authtoken YOUR_AUTH_TOKEN
```

**macOS:**
```bash
brew install ngrok
ngrok config add-authtoken YOUR_AUTH_TOKEN
```

**Windows:**
```powershell
choco install ngrok
ngrok config add-authtoken YOUR_AUTH_TOKEN
```

### Запуск туннеля

```bash
# Запуск ngrok
ngrok http 8002

# Вы получите URL вида: https://abc123.ngrok.io
# Используйте его в настройках Widget и Telegram
```

**Альтернатива: Cloudflare Tunnel**
```bash
# Установка
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
sudo mv cloudflared-linux-amd64 /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared

# Запуск
cloudflared tunnel --url http://localhost:8002
```

## Website Widget

Встраиваемый чат-виджет для любого сайта с поддержкой нескольких инстансов.

**Настройка:**
1. Откройте Admin → Widget
2. Создайте новый виджет или используйте default
3. Укажите API URL (ngrok URL для внешних сайтов)
4. Настройте цвета, тексты, LLM и TTS
5. Скопируйте код виджета

**Multi-Instance Widgets:**
Каждый инстанс виджета имеет независимые настройки:
- Внешний вид (цвета, тексты, позиция)
- LLM backend, персона, системный промпт
- TTS голос и пресет
- Whitelist доменов

**Интеграция:**
```html
<!-- Default виджет -->
<script src="https://admin.ai-sekretar24.ru/widget.js"></script>

<!-- Конкретный инстанс -->
<script src="https://admin.ai-sekretar24.ru/widget.js?instance=sales"></script>
<script src="https://admin.ai-sekretar24.ru/widget.js?instance=support"></script>
```

**Функции:**
- Плавающая кнопка чата
- Streaming ответы (SSE)
- Сохранение сессии в localStorage
- Настраиваемые цвета и тексты
- Whitelist разрешённых доменов

## Telegram Bot

Общение с ассистентом через Telegram с поддержкой нескольких независимых ботов.

**Настройка (single bot):**
1. Создайте бота через [@BotFather](https://t.me/BotFather)
2. Скопируйте токен бота
3. Откройте Admin → Telegram
4. Выберите бота или создайте нового
5. Вставьте токен, настройте whitelist
6. Нажмите "Start Bot"

**Multi-Instance Bots:**
Каждый инстанс бота имеет независимые настройки:
- Telegram токен и whitelist пользователей
- LLM backend, персона, системный промпт
- TTS голос и пресет
- Изоляция сессий (пользователи в разных ботах имеют отдельные истории)

```bash
# Создать новый инстанс бота
curl -X POST http://localhost:8002/admin/telegram/instances \
  -H "Content-Type: application/json" \
  -d '{"name": "Sales Bot", "bot_token": "...", "api_url": "https://..."}'

# Запустить конкретный бот
curl -X POST http://localhost:8002/admin/telegram/instances/{id}/start
```

**Команды бота:**
| Команда | Описание |
|---------|----------|
| `/start` | Начать разговор |
| `/new` | Новая сессия |
| `/help` | Показать помощь |
| `/status` | Статус системы (только админы) |

**Запуск через командную строку:**
```bash
./start_telegram_bot.sh
```

## Personas

| Persona | Name | Description |
|---------|------|-------------|
| `anna` | Анна | Дружелюбный цифровой секретарь (default) |
| `marina` | Марина | Альтернативная персона |

**Switching Persona:**
```bash
# Environment variable
export SECRETARY_PERSONA=marina

# Via API
curl -X POST http://localhost:8002/admin/llm/persona \
  -H "Content-Type: application/json" \
  -d '{"persona": "marina"}'

# Via Admin Panel
open http://localhost:8002/admin → LLM tab
```

## LLM Backends

| Backend | Model | Speed | Requirements |
|---------|-------|-------|--------------|
| `vllm` | Qwen2.5-7B + LoRA | Fast | GPU 12GB+ |
| `vllm` | Llama-3.1-8B GPTQ | Fast | GPU 12GB+ |
| `gemini` (Cloud AI) | Any cloud provider | Variable | API key |

**Switching Backend:**
```bash
# Environment variable
export LLM_BACKEND=vllm  # or "gemini"

# Via API
curl -X POST http://localhost:8002/admin/llm/backend \
  -H "Content-Type: application/json" \
  -d '{"backend": "vllm"}'
```

## Cloud LLM Providers

Система поддерживает подключение множества облачных LLM провайдеров с хранением credentials в базе данных.

### Поддерживаемые провайдеры

| Provider | Type | Default Models | Base URL |
|----------|------|----------------|----------|
| **Google Gemini** | `gemini` | gemini-2.0-flash, gemini-2.5-pro | SDK |
| **Moonshot Kimi** | `kimi` | kimi-k2, moonshot-v1-8k/32k/128k | api.moonshot.ai |
| **OpenAI** | `openai` | gpt-4o, gpt-4o-mini | api.openai.com |
| **Anthropic Claude** | `claude` | claude-opus-4-6, claude-sonnet-4-5 | api.anthropic.com |
| **DeepSeek** | `deepseek` | deepseek-chat, deepseek-reasoner | api.deepseek.com |
| **OpenRouter** | `openrouter` | nemotron-3-nano:free, trinity-large:free, solar-pro-3:free | openrouter.ai |
| **Custom** | `custom` | (user-defined) | (user-defined) |

### Управление провайдерами

**Через Admin Panel:**
1. Откройте Admin → LLM
2. В секции "Cloud LLM Providers" нажмите "Add Provider"
3. Выберите тип, введите API key и название модели
4. Нажмите "Test Connection" для проверки
5. Нажмите "Use" для переключения на этого провайдера

**Через API:**
```bash
# Список провайдеров
curl http://localhost:8002/admin/llm/providers

# Создать провайдер
curl -X POST http://localhost:8002/admin/llm/providers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Kimi",
    "provider_type": "kimi",
    "api_key": "sk-xxx",
    "base_url": "https://api.moonshot.ai/v1",
    "model_name": "kimi-k2"
  }'

# Тест соединения
curl -X POST http://localhost:8002/admin/llm/providers/{id}/test

# Переключить на облачного провайдера
curl -X POST http://localhost:8002/admin/llm/backend \
  -H "Content-Type: application/json" \
  -d '{"backend": "cloud:my-kimi-id"}'
```

## VLESS Proxy for Gemini

Для регионов с ограниченным доступом к Google API, Gemini провайдеры поддерживают маршрутизацию через VLESS прокси с **автоматическим failover**.

**Настройка:**
1. xray-core уже включён в Docker образ (или скачайте в `./bin/xray`)
2. Создайте/отредактируйте Gemini провайдер в Admin Panel → LLM → Cloud Providers
3. В модальном окне введите VLESS URL(s) в секции "VLESS Proxy" (по одному на строку)
4. Нажмите "Test All Proxies" для проверки
5. Сохраните — все запросы к Gemini API пойдут через прокси

**Multiple Proxies с Fallback:**
- Добавьте несколько VLESS URL (по одному на строку)
- При сбое текущего прокси система переключается на следующий
- В карточке провайдера отображается количество прокси (напр. "3 Proxy")

**Формат VLESS URL:**
```
vless://uuid@host:port?security=reality&pbk=PUBLIC_KEY&sid=SHORT_ID&type=tcp&flow=xtls-rprx-vision#Name
```

**Поддерживаемые протоколы:**
- Security: `none`, `tls`, `reality`
- Transport: `tcp`, `ws` (WebSocket), `grpc`

**API endpoints:**
```bash
# Статус прокси
GET /admin/llm/proxy/status

# Тест одного URL
POST /admin/llm/proxy/test

# Тест нескольких URL
POST /admin/llm/proxy/test-multiple

# Сброс всех прокси
POST /admin/llm/proxy/reset

# Переключиться на следующий прокси
POST /admin/llm/proxy/switch-next
```

## API Reference

### OpenAI-Compatible (for OpenWebUI)

```bash
# Chat completion
curl -X POST http://localhost:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "anna-secretary-qwen", "messages": [{"role": "user", "content": "Привет!"}]}'

# Text-to-Speech
curl -X POST http://localhost:8002/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Привет!", "voice": "anna"}' \
  -o output.wav

# List models
curl http://localhost:8002/v1/models
```

### Admin API (~371 endpoints via 21 routers)

```bash
# Authentication
POST /admin/auth/login              # Login, get JWT token

# Services
GET  /admin/services/status          # All services status
POST /admin/services/{name}/start    # Start service
POST /admin/services/{name}/stop     # Stop service
POST /admin/services/{name}/restart  # Restart service
GET  /admin/logs/{logfile}           # Read log file
GET  /admin/logs/stream/{logfile}    # SSE log stream

# LLM
GET  /admin/llm/backend              # Current backend
POST /admin/llm/backend              # Set backend (vllm, gemini, cloud:{id})
GET  /admin/llm/persona              # Current persona
POST /admin/llm/persona              # Set persona
GET  /admin/llm/params               # Generation params
POST /admin/llm/params               # Update params
GET  /admin/llm/prompt/{persona}     # System prompt
POST /admin/llm/prompt/{persona}     # Update prompt

# Cloud LLM Providers
GET    /admin/llm/providers              # List providers + types
POST   /admin/llm/providers              # Create provider
GET    /admin/llm/providers/{id}         # Get provider
PUT    /admin/llm/providers/{id}         # Update provider
DELETE /admin/llm/providers/{id}         # Delete provider
POST   /admin/llm/providers/{id}/test    # Test connection
POST   /admin/llm/providers/{id}/set-default  # Set as default

# VLESS Proxy (for Gemini)
GET  /admin/llm/proxy/status           # Proxy status, proxy list
POST /admin/llm/proxy/test             # Test single VLESS URL
POST /admin/llm/proxy/test-multiple    # Test multiple VLESS URLs
POST /admin/llm/proxy/reset            # Reset all proxies to enabled
POST /admin/llm/proxy/switch-next      # Switch to next proxy
GET  /admin/llm/proxy/validate         # Validate VLESS URL format

# TTS
GET  /admin/voices                   # List voices
POST /admin/voice                    # Set voice
POST /admin/voice/test               # Test synthesis
GET  /admin/tts/xtts/params          # XTTS params
POST /admin/tts/xtts/params          # Update XTTS params
GET  /admin/tts/presets/custom       # Custom presets
POST /admin/tts/presets/custom       # Create preset

# FAQ
GET    /admin/faq                    # List all FAQ
POST   /admin/faq                    # Add FAQ entry
PUT    /admin/faq/{trigger}          # Update entry
DELETE /admin/faq/{trigger}          # Delete entry
POST   /admin/faq/reload             # Hot reload
POST   /admin/faq/test               # Test matching

# STT (Speech-to-Text)
GET  /admin/stt/status               # STT service status
GET  /admin/stt/models               # Available STT models
POST /admin/stt/transcribe           # Transcribe audio file
POST /admin/stt/test                 # Test with microphone

# Fine-tuning
POST /admin/finetune/dataset/upload  # Upload Telegram export
POST /admin/finetune/dataset/process # Run prepare_telegram.py
GET  /admin/finetune/dataset/stats   # Dataset statistics
GET  /admin/finetune/config          # Training config
POST /admin/finetune/config          # Update config
POST /admin/finetune/train/start     # Start training
POST /admin/finetune/train/stop      # Stop training
GET  /admin/finetune/train/status    # Training progress
GET  /admin/finetune/adapters        # List LoRA adapters
POST /admin/finetune/adapters/activate # Hot-swap adapter

# Monitoring
GET  /admin/monitor/gpu              # GPU stats
GET  /admin/monitor/gpu/stream       # SSE GPU stream
GET  /admin/monitor/health           # Health check
GET  /admin/monitor/metrics          # Request metrics

# Widget
GET  /admin/widget/config            # Widget settings
POST /admin/widget/config            # Update settings
GET  /widget.js                      # Dynamic widget script (public)

# Telegram
GET  /admin/telegram/config          # Bot settings (legacy)
POST /admin/telegram/config          # Update settings (legacy)
GET  /admin/telegram/instances       # List bot instances
POST /admin/telegram/instances       # Create instance
GET  /admin/telegram/instances/{id}  # Get instance
PUT  /admin/telegram/instances/{id}  # Update instance
DELETE /admin/telegram/instances/{id} # Delete instance
POST /admin/telegram/instances/{id}/start # Start bot
POST /admin/telegram/instances/{id}/stop  # Stop bot
POST /admin/telegram/instances/{id}/restart # Restart bot
GET  /admin/telegram/instances/{id}/status  # Bot status
GET  /admin/telegram/instances/{id}/sessions # Bot sessions
GET  /admin/telegram/instances/{id}/logs    # Bot logs

# Chat
GET  /admin/chat/sessions            # List chat sessions
GET  /admin/chat/sessions?group_by=source # List grouped by source (admin/telegram/widget)
POST /admin/chat/sessions            # Create session (with source tracking)
POST /admin/chat/sessions/bulk-delete # Bulk delete sessions
GET  /admin/chat/sessions/{id}       # Get session
PUT  /admin/chat/sessions/{id}       # Update session (rename)
DELETE /admin/chat/sessions/{id}     # Delete session
POST /admin/chat/sessions/{id}/messages # Send message
POST /admin/chat/sessions/{id}/stream   # SSE streaming chat
PUT  /admin/chat/sessions/{id}/messages/{msg_id} # Edit message
DELETE /admin/chat/sessions/{id}/messages/{msg_id} # Delete message
POST /admin/chat/sessions/{id}/messages/{msg_id}/regenerate # Regenerate

# Audit
GET  /admin/audit                    # Audit log with filters
GET  /admin/audit/stats              # Audit statistics
GET  /admin/audit/export             # Export to CSV
DELETE /admin/audit/clear            # Clear old entries
```

## Fine-tuning Pipeline

Полный цикл обучения LoRA адаптера:

```bash
# 1. Export Telegram chat (JSON)
# 2. Upload via Admin Panel → Finetune → Upload Dataset

# Or via API:
curl -X POST http://localhost:8002/admin/finetune/dataset/upload \
  -F "file=@result.json"

# 3. Process dataset
curl -X POST http://localhost:8002/admin/finetune/dataset/process

# 4. View statistics
curl http://localhost:8002/admin/finetune/dataset/stats

# 5. Configure training
curl -X POST http://localhost:8002/admin/finetune/config \
  -H "Content-Type: application/json" \
  -d '{
    "lora_rank": 8,
    "batch_size": 1,
    "gradient_accumulation": 64,
    "learning_rate": 2e-4,
    "epochs": 1
  }'

# 6. Start training
curl -X POST http://localhost:8002/admin/finetune/train/start

# 7. Monitor progress
curl http://localhost:8002/admin/finetune/train/status

# 8. Activate new adapter (hot-swap)
curl -X POST http://localhost:8002/admin/finetune/adapters/activate \
  -H "Content-Type: application/json" \
  -d '{"adapter": "qwen2.5-7b-lydia-lora-new"}'
```

## OpenWebUI Integration

```yaml
# Settings → Connections → OpenAI API
API Base URL: http://172.17.0.1:8002/v1
API Key: sk-dummy

# Settings → Audio → TTS
TTS Engine: OpenAI
API Base URL: http://172.17.0.1:8002/v1
TTS Voice: anna
```

**Available Models:**
- `anna-secretary-qwen` - Анна + Qwen2.5-7B + LoRA
- `marina-secretary-qwen` - Марина + Qwen2.5-7B + LoRA
- `anna-secretary-llama` - Анна + Llama-3.1-8B
- `anna-secretary-gemini` - Анна + Gemini API

## Environment Variables

```bash
# LLM Backend
LLM_BACKEND=vllm                    # "vllm", "cloud:{provider_id}", or legacy "gemini"
DEPLOYMENT_MODE=full                # "full" (all features), "cloud" (no GPU/hardware), "local"

# vLLM configuration
VLLM_API_URL=http://localhost:11434
VLLM_MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ
VLLM_MODEL_NAME=lydia               # LoRA adapter name
VLLM_GPU_ID=1                       # GPU device ID
VLLM_CONTAINER_NAME=ai-secretary-vllm  # Docker container name for vLLM

# Cloud LLM (managed in DB, but Gemini key can be set via env)
GEMINI_API_KEY=...                  # Gemini API key
GEMINI_MODEL=gemini-2.0-flash      # Gemini model
HF_TOKEN=...                       # HuggingFace token (for gated models)

# Server
ORCHESTRATOR_PORT=8002
SECRETARY_PERSONA=anna             # "anna" or "marina"

# Security
ADMIN_JWT_SECRET=...                # JWT secret (auto-generated if empty)
ADMIN_JWT_EXPIRATION_HOURS=24       # Token lifetime
ADMIN_AUTH_ENABLED=true             # Enable authentication
RATE_LIMIT_ENABLED=true             # Enable rate limiting
SECURITY_HEADERS_ENABLED=true       # Enable security headers
CORS_ORIGINS=*                      # Allowed origins

# Database
REDIS_URL=redis://localhost:6379/0  # Optional caching (graceful fallback)

# Voice
VOICE_SAMPLES_DIR=./Марина          # Voice samples directory
COQUI_TOS_AGREED=1                  # XTTS license agreement

# Docker
DOCKER_CONTAINER=0                  # Set to "1" inside Docker
```

## File Structure

```
AI_Secretary_System/
├── orchestrator.py          # FastAPI server (port 8002), mounts app/routers/
├── auth_manager.py          # JWT authentication + RBAC (admin/user/web/guest)
├── service_manager.py       # Service process control (vLLM, Docker)
├── finetune_manager.py      # LoRA fine-tuning pipeline
├── voice_clone_service.py   # XTTS v2 + custom presets
├── openvoice_service.py     # OpenVoice v2
├── piper_tts_service.py     # Piper TTS (CPU)
├── stt_service.py           # Vosk (realtime) + Whisper (batch) STT
├── vllm_llm_service.py      # vLLM + runtime params
├── cloud_llm_service.py     # Cloud LLM providers (Gemini, Kimi, OpenAI, Claude, DeepSeek, OpenRouter)
├── llm_service.py           # Gemini fallback (legacy)
├── bridge_manager.py        # CLI-OpenAI bridge (Claude Code, Gemini CLI)
├── telegram_bot_service.py  # Telegram bot service
├── multi_bot_manager.py     # Multi-instance bot lifecycle manager
├── whatsapp_manager.py      # WhatsApp Cloud API manager
├── model_manager.py         # HuggingFace model download manager
├── system_monitor.py        # GPU/CPU/RAM/Docker monitoring (nvidia-smi, psutil)
├── xray_proxy_manager.py    # VLESS proxy for Gemini (xray-core)
├── phone_service.py         # GSM telephony (SIM7600E-H)
│
├── app/                     # Modular API layer
│   ├── dependencies.py      # ServiceContainer for DI
│   ├── cors_middleware.py    # CORS middleware
│   ├── rate_limiter.py      # Rate limiting
│   ├── security_headers.py  # Security headers
│   ├── routers/             # 21 API routers (~371 endpoints)
│   │   ├── auth.py, audit.py, services.py, monitor.py
│   │   ├── llm.py, tts.py, stt.py, faq.py, chat.py
│   │   ├── telegram.py, widget.py, whatsapp.py, gsm.py
│   │   ├── bot_sales.py, amocrm.py, backup.py
│   │   ├── usage.py, legal.py, wiki_rag.py
│   │   └── yoomoney_webhook.py, github_webhook.py
│   └── services/            # Business logic services
│       ├── sales_funnel.py  # Sales funnel FSM
│       ├── wiki_rag_service.py  # Wiki RAG (embeddings + BM25)
│       ├── amocrm_service.py, gsm_service.py
│       ├── backup_service.py, yoomoney_service.py
│       ├── audio_pipeline.py    # GSM audio (8kHz, PCM16)
│       └── embedding_provider.py # Embeddings for RAG
│
├── db/                      # Database layer (async SQLAlchemy + aiosqlite)
│   ├── models.py            # 35 ORM models
│   ├── database.py          # Async engine + session
│   ├── integration.py       # DatabaseManager singleton
│   ├── redis_client.py      # Redis caching (optional)
│   └── repositories/        # 25 repository files (BaseRepository[Model])
│
├── data/                    # Persistent data
│   └── secretary.db         # SQLite database
│
├── scripts/                 # Utility & migration scripts
│   ├── manage_users.py      # CLI user management
│   ├── migrate_*.py         # 15+ migration scripts
│   ├── seed_tz_*.py         # TZ generator seeds
│   ├── setup_db.sh          # Database setup
│   └── test_db.py           # Database tests
│
├── wiki-pages/              # Wiki documentation (37 .md files, used by Wiki RAG)
│
├── web-widget/              # Embeddable chat widget
│   └── ai-chat-widget.js   # Dynamic widget script
│
├── admin/                   # Vue 3 admin panel (PWA)
│   ├── src/
│   │   ├── views/           # 20 views + LoginView
│   │   ├── api/             # API clients + SSE + demo mocks (22 files)
│   │   ├── stores/          # 11 Pinia stores (auth, theme, toast, audit, ...)
│   │   ├── components/      # UI + charts
│   │   ├── composables/     # useSSE, useRealtimeMetrics, ...
│   │   └── plugins/         # i18n (ru/en)
│   ├── public/              # PWA manifest + service worker
│   └── dist/                # Production build
│
├── Анна/                    # Voice samples (122 WAV)
├── Марина/                   # Voice samples
├── models/                  # AI models
│   ├── piper/               # Piper ONNX models (CPU TTS)
│   └── vosk/                # Vosk models (STT)
├── logs/                    # Service logs
│
├── pyproject.toml           # Python config (ruff, mypy, pytest)
├── .pre-commit-config.yaml  # Pre-commit hooks
├── docker-compose.yml       # Docker deployment (orchestrator + redis)
├── docker-compose.full.yml  # Full Docker (+ vLLM container)
├── docker-compose.cpu.yml   # CPU-only Docker mode
├── Dockerfile               # Production container
│
├── start_gpu.sh             # Launch GPU mode
├── start_cpu.sh             # Launch CPU mode
└── setup.sh                 # First-time setup
```

## Commands

```bash
# GPU Mode: XTTS + Qwen + LoRA (default)
./start_gpu.sh

# GPU Mode: XTTS + Llama
./start_gpu.sh --llama

# CPU Mode: Piper + Gemini
./start_cpu.sh

# OpenVoice Mode (older GPUs)
./start_openvoice.sh

# Start only vLLM
./start_qwen.sh   # Qwen + LoRA
./start_vllm.sh   # Llama

# Admin Panel (dev mode)
cd admin && npm run dev

# Build Admin Panel
cd admin && npm run build

# View logs
tail -f logs/orchestrator.log
tail -f logs/vllm.log
```

## Requirements

### Hardware
- **GPU**: NVIDIA RTX 3060+ (12GB VRAM) for full mode
- **GPU (OpenVoice)**: NVIDIA CC 6.1+ (P104-100, GTX 1080)
- **CPU**: 8+ cores for Piper-only mode
- **RAM**: 16GB+ (32GB recommended)
- **Disk**: 20GB for models

### Software
- Ubuntu 20.04+ / Debian 11+
- Python 3.11+
- Node.js 18+ (for admin panel dev)
- CUDA 12.x
- ffmpeg

## Troubleshooting

### CUDA out of memory
```bash
# Reduce vLLM GPU allocation in start_qwen.sh:
--gpu-memory-utilization 0.6  # Instead of 0.7
```

### Voice quality issues
- Add more WAV samples to voice folder
- Use clean recordings without background noise
- Ensure 16kHz or 44.1kHz sample rate

### Admin panel not loading
```bash
# Check if backend is running
curl http://localhost:8002/health

# Dev mode login
# Username: admin
# Password: admin

# Rebuild admin panel
cd admin && npm run build
```

### vLLM connection refused
```bash
# Check vLLM is running
curl http://localhost:11434/health

# View vLLM logs
tail -f logs/vllm.log
```

### PWA not installing
- Ensure HTTPS or localhost
- Check manifest.json is served correctly
- Clear browser cache

## Development

### Code Quality

Проект использует инструменты для обеспечения качества кода:

| Tool | Purpose | Config |
|------|---------|--------|
| **ruff** | Python linter + formatter | `pyproject.toml` |
| **mypy** | Static type checking | `pyproject.toml` |
| **eslint** | Vue/TypeScript linting | `admin/.eslintrc.cjs` |
| **prettier** | Code formatting | `admin/.prettierrc` |
| **pre-commit** | Git hooks | `.pre-commit-config.yaml` |

```bash
# Активировать venv для lint tools
source .venv/bin/activate

# Python linting
ruff check .              # Проверка
ruff check . --fix        # Автоисправление
ruff format .             # Форматирование

# Vue linting
cd admin && npm run lint

# Pre-commit (все проверки)
pre-commit run --all-files

# Установить pre-commit hooks
pre-commit install
```

### Running Tests
```bash
# Backend
source .venv/bin/activate
pytest tests/

# Frontend
cd admin && npm test
```

### Building Admin Panel
```bash
cd admin
npm install
npm run build
# Output in admin/dist/, served by FastAPI
```

### Adding New Voice
1. Create folder with WAV samples: `./NewVoice/`
2. Add service instance in `orchestrator.py`
3. Add voice ID to admin endpoints
4. Voice appears in admin panel

### Adding New Persona
1. Edit `SECRETARY_PERSONAS` in `vllm_llm_service.py`
2. Restart orchestrator
3. Available via API and admin panel

### Adding New Theme
1. Add CSS variables in `admin/src/assets/main.css`
2. Update `Theme` type in `admin/src/stores/theme.ts`
3. Add translations in `admin/src/plugins/i18n.ts`

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `⌘K` / `Ctrl+K` | Open command palette |
| `Escape` | Close dialogs |

## Roadmap

См. [BACKLOG.md](./BACKLOG.md) для полного плана разработки.

**Текущий фокус:** Офлайн-first + телефония через SIM7600G-H

**Выполнено:**
- [x] Базовая архитектура (orchestrator, TTS, LLM)
- [x] Vue 3 админ-панель (20 вкладок, PWA, i18n, 3 темы)
- [x] XTTS v2 + OpenVoice v2 + Piper TTS
- [x] vLLM + Cloud LLM providers + hot-switching
- [x] Vosk STT (realtime streaming) + Whisper (batch)
- [x] Chat с TTS playback, branching (ветвление диалогов), voice input
- [x] Website Widget (multi-instance чат-виджеты для сайтов)
- [x] Telegram Bot (multi-instance с независимыми настройками)
- [x] WhatsApp Bot (multi-instance через Cloud API)
- [x] **Database** — SQLite + Redis (async SQLAlchemy, 35 таблиц, 25 репозиториев)
- [x] **Cloud LLM Providers** — Gemini, Kimi, OpenAI, Claude, DeepSeek, OpenRouter + CLI-OpenAI bridge
- [x] **RBAC** — 4 роли (admin, user, web, guest) с resource ownership
- [x] **Docker Compose** — one-command deployment (GPU + CPU режимы)
- [x] **Code Quality** — ruff, mypy, eslint, pre-commit hooks, CI/CD
- [x] **Chat Management** — переименование, групповое удаление, группировка по источнику, branching
- [x] **VLESS Proxy** — маршрутизация Gemini через VLESS прокси с автоматическим failover
- [x] **Sales Funnel** — quiz-сегментация, TZ генератор, оплата (YooMoney, Telegram Stars), follow-up, A/B тесты
- [x] **amoCRM Integration** — OAuth2, контакты, лиды, пайплайны, синхронизация
- [x] **Wiki RAG** — семантический поиск (embeddings + BM25) по wiki-pages/ для контекста LLM
- [x] **Knowledge Base** — загрузка документов, управление через админ-панель
- [x] **Usage Tracking** — трекинг TTS/STT/LLM с лимитами и статистикой
- [x] **Legal Compliance** — пользовательские соглашения, GDPR consent tracking
- [x] **Backup & Restore** — экспорт/импорт конфигурации системы
- [x] **Responsive Admin** — mobile-first адаптивная верстка, command palette (⌘K)

**В планах:**
- [ ] Телефония SIM7600G-H (AT-команды, GSM модем)
- [ ] Automated Testing (unit, integration, e2e)

## License

This project is licensed under the [MIT License](LICENSE).

Copyright (c) 2026 ShaerWare

## Support

- **Сайт проекта:** https://ai-sekretar24.ru/
- **Демо (полный):** https://demo.ai-sekretar24.ru/full/
- **Демо (облачный):** https://demo.ai-sekretar24.ru/cloud/
- **Telegram бот:** https://t.me/shaerware_digital_bot
- **Issues:** https://github.com/ShaerWare/AI_Secretary_System/issues
- **Wiki:** https://github.com/ShaerWare/AI_Secretary_System/wiki

---

<div align="center">

**Made with** :brain: **by [ShaerWare](https://github.com/ShaerWare)**

[![Telegram](https://img.shields.io/badge/Telegram-@ShaerWare-26A5E4?logo=telegram&logoColor=white)](https://t.me/ShaerWare)

</div>

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=6,11,20&height=100&section=footer" width="100%"/>

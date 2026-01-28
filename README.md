# AI Secretary System

[![CI](https://github.com/ShaerWare/AI_Secretary_System/actions/workflows/ci.yml/badge.svg)](https://github.com/ShaerWare/AI_Secretary_System/actions/workflows/ci.yml)

Интеллектуальная система виртуального секретаря с клонированием голоса (XTTS v2, OpenVoice), предобученными голосами (Piper), локальным LLM (vLLM + Qwen/Llama) и облачным fallback (Gemini). Включает полнофункциональную Vue 3 админ-панель с PWA поддержкой.

## Features

- **Multi-Voice TTS**: 5 голосов (2 клонированных XTTS, 1 OpenVoice, 2 Piper)
- **Speech-to-Text**: Vosk (realtime streaming) + Whisper (batch)
- **Multi-Persona LLM**: 2 персоны секретаря (Гуля, Лидия)
- **Local LLM**: vLLM с Qwen2.5-7B/Llama-3.1-8B/DeepSeek-7B + LoRA fine-tuning
- **Cloud LLM Providers**: Подключение облачных LLM (Gemini, Kimi, OpenAI, Claude, DeepSeek, OpenRouter) с хранением credentials в БД
- **Multi-Instance Bots**: Несколько Telegram ботов с независимыми настройками (LLM, TTS, промпт)
- **Multi-Instance Widgets**: Несколько чат-виджетов для разных сайтов/отделов
- **FAQ System**: Мгновенные ответы на типичные вопросы
- **Admin Panel**: Vue 3 PWA с 13 вкладками, i18n, темами, аудитом
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
                              │  │  Vue 3 Admin Panel (13 tabs, PWA)  │  │
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
cp .env.docker .env
# Edit .env: set GEMINI_API_KEY for cloud fallback

# GPU Mode (XTTS + vLLM) - requires NVIDIA GPU 12GB+
docker compose up -d

# CPU Mode (Piper + Gemini) - no GPU required
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

Полнофункциональная Vue 3 PWA админ-панель с 13 вкладками:

| Tab | Description |
|-----|-------------|
| **Dashboard** | Статусы сервисов, GPU спарклайны, health индикаторы |
| **Chat** | Чат с ИИ, Voice Mode (auto-TTS), голосовой ввод (STT), редактирование промптов |
| **Services** | Запуск/остановка vLLM, SSE логи в реальном времени |
| **LLM** | Выбор модели (Qwen/Llama/DeepSeek), персоны, параметры генерации |
| **TTS** | Выбор голоса, пресеты XTTS, тестирование синтеза |
| **FAQ** | Редактирование типичных ответов (CRUD) |
| **Finetune** | Загрузка датасета, обучение, управление адаптерами |
| **Monitoring** | GPU/CPU графики Chart.js, логи ошибок |
| **Models** | Управление скачанными моделями HuggingFace |
| **Widget** | Настройка чат-виджета для сайтов |
| **Telegram** | Настройка Telegram бота |
| **Audit** | Логирование действий, фильтрация, экспорт |
| **Settings** | Язык, тема, экспорт/импорт конфигураций |

### Admin Panel Features

| Feature | Description |
|---------|-------------|
| **JWT Authentication** | Безопасный вход с dev-mode fallback |
| **Multi-user Roles** | admin, operator, viewer с разными правами |
| **i18n** | Полная поддержка русского и английского |
| **Themes** | Light, Dark, Night-Eyes (тёплая для глаз) |
| **PWA** | Установка как приложение, offline кэширование |
| **Real-time** | SSE метрики GPU с fallback на polling |
| **Chat TTS** | Озвучивание ответов ассистента (Volume2 button) |
| **Voice Mode** | Auto-play TTS при получении ответа |
| **Voice Input** | Голосовой ввод через микрофон (STT) |
| **Prompt Editor** | Редактирование дефолтного промпта из чата |
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
- **Styling**: Tailwind CSS (4 themes)
- **State**: Pinia + persistedstate
- **Data**: TanStack Query (caching + SSE)
- **Charts**: Chart.js + vue-chartjs
- **i18n**: vue-i18n (ru/en)
- **Icons**: Lucide Vue

## Voices

| Voice | Engine | GPU Required | Speed | Quality |
|-------|--------|--------------|-------|---------|
| `gulya` | XTTS v2 | CC >= 7.0 | ~5-10s | Best cloning |
| `lidia` | XTTS v2 | CC >= 7.0 | ~5-10s | Best cloning |
| `lidia_openvoice` | OpenVoice v2 | CC >= 6.1 | ~2-4s | Good cloning |
| `dmitri` | Piper | CPU | ~0.5s | Pre-trained male |
| `irina` | Piper | CPU | ~0.5s | Pre-trained female |

**Voice Samples:**
- `./Гуля/` - 122 WAV files
- `./Лидия/` - WAV files

**Switching Voice:**
```bash
# Via API
curl -X POST http://localhost:8002/admin/voice \
  -H "Content-Type: application/json" \
  -d '{"voice": "gulya"}'

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

### Таблицы SQLite

| Таблица | Назначение |
|---------|------------|
| `chat_sessions` | Сессии чата (id, title, system_prompt) |
| `chat_messages` | Сообщения (role, content, timestamp) |
| `faq_entries` | FAQ вопрос-ответ |
| `tts_presets` | Пользовательские пресеты TTS |
| `system_config` | Конфиги (telegram, widget, etc.) |
| `telegram_sessions` | Telegram user → chat session |
| `audit_log` | Аудит действий пользователей |

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
└── secretary.db          # SQLite база данных (~72KB)

db/
├── __init__.py
├── database.py           # Подключение SQLite
├── models.py             # SQLAlchemy ORM модели
├── redis_client.py       # Redis клиент
├── integration.py        # Backward-compatible managers
└── repositories/
    ├── base.py           # Базовый репозиторий
    ├── chat.py           # ChatRepository
    ├── faq.py            # FAQRepository
    ├── preset.py         # PresetRepository
    ├── config.py         # ConfigRepository
    ├── telegram.py       # TelegramRepository
    └── audit.py          # AuditRepository
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
<script src="https://your-server.com/widget.js"></script>

<!-- Конкретный инстанс -->
<script src="https://your-server.com/widget.js?instance=sales"></script>
<script src="https://your-server.com/widget.js?instance=support"></script>
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
| `gulya` | Гуля (Гульнара) | Дружелюбный цифровой секретарь (default) |
| `lidia` | Лидия | Альтернативная персона |

**Switching Persona:**
```bash
# Environment variable
export SECRETARY_PERSONA=lidia

# Via API
curl -X POST http://localhost:8002/admin/llm/persona \
  -H "Content-Type: application/json" \
  -d '{"persona": "lidia"}'

# Via Admin Panel
open http://localhost:8002/admin → LLM tab
```

## LLM Backends

| Backend | Model | Speed | Requirements |
|---------|-------|-------|--------------|
| `vllm` | Qwen2.5-7B + LoRA | Fast | GPU 12GB+ |
| `vllm` | Llama-3.1-8B GPTQ | Fast | GPU 12GB+ |
| `gemini` | Gemini 2.5 Pro | Variable | API key |

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
| **Anthropic Claude** | `claude` | claude-opus-4, claude-sonnet-4 | api.anthropic.com |
| **DeepSeek** | `deepseek` | deepseek-chat, deepseek-reasoner | api.deepseek.com |
| **OpenRouter** | `openrouter` | gemma-2-9b:free, llama-3.2-3b:free, qwen-2-7b:free | openrouter.ai |
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

## API Reference

### OpenAI-Compatible (for OpenWebUI)

```bash
# Chat completion
curl -X POST http://localhost:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gulya-secretary-qwen", "messages": [{"role": "user", "content": "Привет!"}]}'

# Text-to-Speech
curl -X POST http://localhost:8002/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Привет!", "voice": "gulya"}' \
  -o output.wav

# List models
curl http://localhost:8002/v1/models
```

### Admin API (~60 endpoints)

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
GET  /admin/telegram/config          # Bot settings
POST /admin/telegram/config          # Update settings
GET  /admin/telegram/status          # Bot status
POST /admin/telegram/start           # Start bot
POST /admin/telegram/stop            # Stop bot
POST /admin/telegram/restart         # Restart bot
GET  /admin/telegram/sessions        # List chat sessions
DELETE /admin/telegram/sessions/{id} # Delete session
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
TTS Voice: gulya
```

**Available Models:**
- `gulya-secretary-qwen` - Гуля + Qwen2.5-7B + LoRA
- `lidia-secretary-qwen` - Лидия + Qwen2.5-7B + LoRA
- `gulya-secretary-llama` - Гуля + Llama-3.1-8B
- `gulya-secretary-gemini` - Гуля + Gemini API

## Environment Variables

```bash
# Required
LLM_BACKEND=vllm                    # "vllm" or "gemini"

# vLLM configuration
VLLM_API_URL=http://localhost:11434
VLLM_MODEL_NAME=lydia               # LoRA adapter name

# Optional
SECRETARY_PERSONA=gulya             # "gulya" or "lidia"
GEMINI_API_KEY=...                  # Only for gemini backend
ORCHESTRATOR_PORT=8002
CUDA_VISIBLE_DEVICES=1              # GPU index
ADMIN_JWT_SECRET=...                # JWT secret (auto-generated if empty)
REDIS_URL=redis://localhost:6379/0  # Optional caching (graceful fallback if unavailable)
```

## File Structure

```
AI_Secretary_System/
├── orchestrator.py          # FastAPI server + ~60 admin endpoints
├── auth_manager.py          # JWT authentication
├── service_manager.py       # Service process control
├── finetune_manager.py      # Fine-tuning pipeline
├── voice_clone_service.py   # XTTS v2 + custom presets
├── openvoice_service.py     # OpenVoice v2
├── piper_tts_service.py     # Piper TTS (CPU)
├── stt_service.py           # Vosk (realtime) + Whisper (batch) STT
├── vllm_llm_service.py      # vLLM + runtime params
├── llm_service.py           # Gemini fallback
├── telegram_bot_service.py  # Telegram bot service
│
├── db/                      # Database layer (SQLite + Redis)
│   ├── __init__.py
│   ├── database.py          # SQLite connection
│   ├── models.py            # SQLAlchemy ORM models
│   ├── redis_client.py      # Redis caching
│   ├── integration.py       # Backward-compatible managers
│   └── repositories/        # Data access layer
│       ├── chat.py          # Chat sessions & messages
│       ├── faq.py           # FAQ entries
│       ├── preset.py        # TTS presets
│       ├── config.py        # System configs
│       ├── telegram.py      # Telegram sessions
│       └── audit.py         # Audit log
│
├── data/                    # Persistent data
│   └── secretary.db         # SQLite database
│
├── scripts/                 # Utility scripts
│   ├── migrate_json_to_db.py  # JSON → SQLite migration
│   ├── test_db.py           # Database tests
│   └── setup_db.sh          # Database setup
│
├── web-widget/              # Embeddable chat widget
│   ├── ai-chat-widget.js    # Widget source code
│   └── README.md            # Widget documentation
│
├── admin/                   # Vue 3 admin panel (PWA)
│   ├── src/
│   │   ├── views/           # 12 main views + LoginView
│   │   ├── api/             # API clients + SSE
│   │   ├── stores/          # Pinia (auth, theme, toast, audit, ...)
│   │   ├── components/      # UI + charts
│   │   ├── composables/     # useSSE, useRealtimeMetrics
│   │   └── plugins/         # i18n
│   ├── public/              # PWA manifest + service worker
│   ├── docs/                # Implementation docs
│   └── dist/                # Production build
│
├── Гуля/                    # Voice samples (122 WAV)
├── Лидия/                   # Voice samples
├── models/                  # AI models
│   ├── piper/               # Piper ONNX models (CPU TTS)
│   └── vosk/                # Vosk models (STT)
├── logs/                    # Service logs
│
├── # Configuration files
├── pyproject.toml           # Python project config (ruff, mypy, pytest)
├── .pre-commit-config.yaml  # Pre-commit hooks
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
- [x] Vue 3 админ-панель (13 табов, PWA)
- [x] XTTS v2 + Piper TTS
- [x] vLLM + Gemini fallback + hot-switching
- [x] Vosk STT (realtime streaming)
- [x] Chat TTS playback
- [x] Website Widget (чат для сайтов)
- [x] Telegram Bot интеграция
- [x] **Database Integration** — SQLite + Redis (транзакции, кэширование)
- [x] **Cloud LLM Providers** — Gemini, Kimi, OpenAI, Claude, DeepSeek, OpenRouter
- [x] **Multi-Instance Bots/Widgets** — несколько ботов и виджетов с независимыми настройками
- [x] **Docker Compose** — one-command deployment (GPU + CPU режимы)
- [x] **Code Quality** — ruff, mypy, eslint, pre-commit hooks

**В планах:**
- [ ] Телефония SIM7600G-H (AT-команды)
- [ ] Backup & Restore
- [ ] Automated Testing (unit, integration, e2e)

## License

MIT

## Support

Issues: https://github.com/ShaerWare/AI_Secretary_System/issues

🇷🇺 Russian Voice AI

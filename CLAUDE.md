# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Secretary System - virtual secretary with voice cloning (XTTS v2, OpenVoice), pre-trained voices (Piper), local LLM (vLLM + Qwen/Llama/DeepSeek), cloud LLM fallback (Gemini with VLESS proxy support, Kimi, OpenAI, Claude, DeepSeek, OpenRouter), and Claude Code CLI bridge. Features GSM telephony support (SIM7600E-H), a Vue 3 PWA admin panel with 19 views, i18n (ru/en), themes, ~236 API endpoints across 18 routers, website chat widgets (multi-instance), Telegram bot integration (multi-instance) with sales bot features and YooMoney/YooKassa/Stars payments, and fine-tuning with project dataset generation.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     Orchestrator (port 8002)                              │
│  orchestrator.py + app/routers/ (18 modular routers, ~236 endpoints)     │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │              Vue 3 Admin Panel (19 views, PWA)                     │   │
│  │                      admin/dist/                                   │   │
│  └───────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
    ┌────────────┬───────────────┼───────────────┬───────────────┐
    ↓            ↓               ↓               ↓               ↓
┌────────┐  ┌────────┐     ┌──────────┐    ┌──────────┐    ┌──────────┐
│ vLLM   │  │ Cloud  │     │ XTTS v2  │    │ Piper    │    │ Vosk/    │
│ Local  │  │ LLM    │     │ OpenVoice│    │ (CPU)    │    │ Whisper  │
│ LLM    │  │ Factory│     │ TTS      │    │ TTS      │    │ STT      │
└────────┘  └────┬───┘     └──────────┘    └──────────┘    └──────────┘
                 │
          ┌──────▼──────┐
          │ xray-core   │  (optional, for Gemini VLESS proxy)
          │ VLESS Proxy │
          └─────────────┘
```

**GPU Mode (RTX 3060 12GB):** vLLM ~6GB (50% GPU) + XTTS v2 ~5GB

**Request flow:** User message → FAQ check (instant) OR LLM → TTS → Audio returned

## Commands

### Quick Start (Docker - Recommended)

```bash
cp .env.docker.example .env && docker compose up -d     # GPU mode
# OR
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d  # CPU mode

docker compose logs -f orchestrator             # View logs
docker compose build --no-cache orchestrator && docker compose up -d  # Rebuild
```

### Local Development

```bash
# Start system
./start_gpu.sh              # GPU: XTTS + Qwen2.5-7B + LoRA
./start_cpu.sh              # CPU: Piper + Gemini API

# Health check
curl http://localhost:8002/health
```

### Admin Panel Development

**Entry point:** http://localhost:8002/admin/ (login: admin / admin)

```bash
cd admin && npm install                # First-time setup
cd admin && npm run build              # Production build
cd admin && npm run dev                # Dev mode (:5173)
DEV_MODE=1 ./start_gpu.sh              # Backend proxies to Vite
```

### Code Quality

```bash
# First-time venv setup (if needed)
python3.11 -m venv .venv
source .venv/bin/activate
pip install ruff mypy pre-commit

# Python
ruff check .                           # Lint
ruff check . --fix                     # Auto-fix
ruff format .                          # Format
mypy orchestrator.py                   # Type check (optional)

# Vue/TypeScript
cd admin && npm run lint

# All checks
pre-commit run --all-files
```

### Testing

```bash
# Backend tests
source .venv/bin/activate
pytest tests/                          # All tests
pytest tests/unit/test_db.py -v        # Single file
pytest -k "test_chat" -v               # By name pattern
pytest -m "not slow" -v                # Exclude slow tests
pytest -m "not integration" -v         # Exclude integration tests
pytest -m "not gpu" -v                 # Exclude GPU-required tests
pytest --cov --cov-report=html         # With coverage report

# Frontend tests
cd admin && npm test

# Integration test (requires running system)
./test_system.sh

# Database tests
python scripts/test_db.py
```

**Test markers** (defined in `pyproject.toml`):
- `slow` — long-running tests
- `integration` — requires external services
- `gpu` — requires CUDA GPU

### CI/CD

GitHub Actions runs on push to `main`/`develop` and on PRs:
- `lint-backend` — ruff check + format check + mypy
- `lint-frontend` — npm ci + eslint + build (includes type check)
- `security` — Trivy vulnerability scanner

All checks must pass before merging (branch protection enabled).

### External Access (for Widget/Telegram)

```bash
ngrok http 8002                        # Dev tunnel
cloudflared tunnel --url http://localhost:8002  # Production tunnel
```

### Fine-tuning (separate venv)

```bash
cd finetune
python -m venv train_venv && source train_venv/bin/activate
pip install -r requirements.txt
python prepare_dataset.py && python train.py
```

## Key Components

### Backend Structure

```
orchestrator.py              # FastAPI entry point, global state, legacy endpoints
app/
├── dependencies.py          # ServiceContainer for DI
├── routers/                 # 18 modular routers (~236 endpoints)
│   ├── auth.py              # 3 endpoints  - JWT login/logout/refresh
│   ├── audit.py             # 4 endpoints  - Audit log viewing/export
│   ├── services.py          # 6 endpoints  - vLLM start/stop/restart
│   ├── monitor.py           # 9 endpoints  - GPU stats, health, SSE metrics
│   ├── faq.py               # 8 endpoints  - FAQ CRUD, reload, test
│   ├── stt.py               # 6 endpoints  - STT status, transcribe
│   ├── llm.py               # 43 endpoints - Backend, persona, cloud providers, VLESS proxy, bridge
│   ├── tts.py               # 16 endpoints - Presets, params, test, cache, streaming
│   ├── chat.py              # 11 endpoints - Sessions (CRUD, bulk delete, grouping), messages, streaming
│   ├── usage.py             # 10 endpoints - Usage tracking, limits, stats, cleanup
│   ├── telegram.py          # 28 endpoints - Bot instances CRUD, control, payments, YooMoney
│   ├── widget.py            # 7 endpoints  - Widget instances CRUD
│   ├── gsm.py               # 15 endpoints - GSM telephony, SIM7600E-H module
│   ├── bot_sales.py         # 44 endpoints - Sales bot (quiz, segments, funnels, A/B tests, discovery, events)
│   ├── legal.py             # 11 endpoints - GDPR compliance, consents, privacy policy
│   ├── backup.py            # 8 endpoints  - Backup/restore system
│   ├── github_webhook.py    # 6 endpoints  - GitHub webhook (stars, releases)
│   └── yoomoney_webhook.py  # 1 endpoint   - YooMoney payment webhook
└── services/
    ├── audio_pipeline.py    # Telephony audio processing (GSM frames, G.711)
    ├── sales_funnel.py      # Sales funnel logic (segmentation, pricing, follow-ups)
    ├── yoomoney_service.py  # YooMoney OAuth & payment processing
    └── backup_service.py    # Backup/restore system (ZIP archives, checksums)
```

**Core Services:**
| File | Purpose |
|------|---------|
| `cloud_llm_service.py` | Cloud LLM factory (Gemini, Kimi, OpenAI, Claude, DeepSeek, OpenRouter, Claude Bridge) |
| `bridge_manager.py` | CLI-OpenAI Bridge process manager (auto-start/stop subprocess) |
| `xray_proxy_manager.py` | VLESS proxy manager for Gemini (xray-core process, URL parsing) |
| `vllm_llm_service.py` | vLLM API + `SECRETARY_PERSONAS` dict |
| `voice_clone_service.py` | XTTS v2 with custom presets + streaming synthesis |
| `piper_tts_service.py` | Piper TTS (CPU) with Dmitri/Irina voices, auto-discovers models dir |
| `stt_service.py` | Vosk (realtime) + Whisper (batch) STT |
| `multi_bot_manager.py` | Subprocess manager for multiple Telegram bots (auto-start on app launch) |
| `telegram_bot/` | Standalone bot module (see structure below) |
| `finetune_manager.py` | LoRA fine-tuning manager (dataset processing, training, adapters, project dataset generation) |
| `app/rate_limiter.py` | Rate limiting with slowapi (configurable per endpoint type) |
| `app/security_headers.py` | Security headers middleware (X-Frame-Options, CSP, etc.) |
| `app/services/audio_pipeline.py` | GSM telephony audio processing (8kHz, PCM16, G.711) |
| `app/services/sales_funnel.py` | Sales funnel logic (segmentation, pricing calculator, follow-ups) |

### Admin Panel (Vue 3)

```
admin/src/
├── views/                   # 19 views (grouped into 5 accordion sections)
├── components/AccordionNav.vue  # Collapsible navigation with 5 groups
├── api/                     # API clients + SSE helpers
├── stores/                  # Pinia (auth, theme, toast, audit, services, llm, settings, tts, confirm, search)
├── composables/             # useSSE, useRealtimeMetrics, useExportImport, useGpuStats
└── plugins/i18n.ts          # vue-i18n translations (ru/en)
```

**Navigation Groups (Accordion):**
- **Мониторинг**: Dashboard, Monitoring, Services, Audit
- **AI-движки**: LLM, TTS, Models, Fine-tune
- **Каналы**: Chat, Telegram, Widget, Telephony (GSM)
- **Бизнес**: FAQ, Sales, CRM (amoCRM placeholder)
- **Система**: Settings, About

### Telegram Bot Module

```
telegram_bot/
├── bot.py               # Main bot class (TelegramBot)
├── config.py            # Bot configuration, multi-instance support
├── handlers/            # Message/command handlers
│   ├── messages.py      # General message routing
│   ├── commands.py      # /start, /help, /settings
│   ├── callbacks.py     # Inline button callbacks
│   ├── tz.py            # TZ (technical spec) handler
│   ├── news.py          # News digest handler
│   ├── files.py         # File upload handler
│   └── sales/           # Sales-specific handlers
│       ├── welcome.py   # Onboarding flow
│       ├── quiz.py      # Quiz funnel
│       ├── payment.py   # Payment processing
│       ├── basic.py, diy.py, common.py, custom.py
├── middleware/           # Access control middleware
├── prompts/             # LLM prompt templates
├── sales/               # Sales logic (keyboards, flows)
├── services/            # Shared services (LLM routing, etc.)
└── utils/               # Helper utilities
```

**LLM routing:** Claude for TZ (technical specs), configurable backend for chat.

### Database (SQLite + Redis)

**Location:** `data/secretary.db`

**Key tables:** `chat_sessions` (with `source`, `source_id` for tracking origin), `chat_messages`, `faq_entries`, `tts_presets`, `llm_presets`, `system_config`, `telegram_sessions`, `audit_log`, `cloud_llm_providers`, `bot_instances` (with `auto_start`, payment fields), `widget_instances`, `payment_log`, `usage_log`, `usage_limits`, `user_consents`

**Redis (optional):** Used for caching with graceful fallback if unavailable.

```bash
python scripts/migrate_json_to_db.py      # First-time migration
python scripts/migrate_to_instances.py    # Multi-instance migration
python scripts/migrate_add_payment_fields.py  # Payment fields migration
python scripts/migrate_sales_bot.py       # Sales bot tables migration
python scripts/migrate_legal_compliance.py # GDPR consent tables migration
```

**Repository pattern:**
```
db/
├── database.py           # SQLite async connection
├── models.py             # SQLAlchemy ORM models + PROVIDER_TYPES dict
├── redis_client.py       # Redis caching with fallback
├── integration.py        # Backward-compatible managers
└── repositories/         # Data access layer (27 repositories)
    ├── base.py           # BaseRepository with CRUD
    ├── chat.py           # ChatRepository
    ├── faq.py            # FAQRepository
    ├── preset.py         # PresetRepository
    ├── llm_preset.py     # LLM preset management
    ├── config.py         # ConfigRepository
    ├── telegram.py       # TelegramRepository
    ├── bot_instance.py   # BotInstanceRepository (Telegram bots)
    ├── payment.py        # PaymentRepository (payment logging)
    ├── widget_instance.py # WidgetInstanceRepository
    ├── cloud_provider.py # CloudProviderRepository
    ├── consent.py        # ConsentRepository (GDPR consent management)
    ├── usage.py          # UsageRepository, UsageLimitsRepository
    ├── audit.py          # AuditRepository
    └── bot_*.py          # Sales bot repositories (A/B tests, discovery, events,
                          #   follow-ups, GitHub, hardware, quiz, segments,
                          #   subscribers, testimonials, user profiles, agent prompts)
```

## Environment Variables

```bash
LLM_BACKEND=vllm                    # "vllm", "gemini", or "cloud:{provider_id}"
VLLM_API_URL=http://localhost:11434 # Base URL without /v1 suffix (auto-normalized)
VLLM_MODEL_NAME=lydia               # LoRA adapter name
VLLM_GPU_ID=1                       # GPU ID for vLLM Docker container (default: 1)
SECRETARY_PERSONA=gulya             # "gulya" or "lidia"
GEMINI_API_KEY=...                  # Only for gemini backend
ORCHESTRATOR_PORT=8002
CUDA_VISIBLE_DEVICES=1
ADMIN_JWT_SECRET=...                # Auto-generated if empty
REDIS_URL=redis://localhost:6379/0  # Optional, for caching

# Security (production)
CORS_ORIGINS=*                      # Comma-separated origins, "*" for dev
RATE_LIMIT_ENABLED=true             # Enable rate limiting
RATE_LIMIT_DEFAULT=60/minute        # Default rate limit
RATE_LIMIT_AUTH=10/minute           # Auth endpoints rate limit
RATE_LIMIT_CHAT=30/minute           # Chat endpoints rate limit
RATE_LIMIT_TTS=20/minute            # TTS endpoints rate limit
SECURITY_HEADERS_ENABLED=true       # Enable security headers
X_FRAME_OPTIONS=DENY                # DENY or SAMEORIGIN
```

## Code Patterns

**Adding a new API endpoint:**
1. Create or edit router in `app/routers/`
2. Use `ServiceContainer` from `app/dependencies.py` for DI
3. Add router to imports and `__all__` in `app/routers/__init__.py`
4. Register router in `orchestrator.py` with `app.include_router()`

**Adding a new cloud LLM provider type:**
1. Add entry to `PROVIDER_TYPES` dict in `db/models.py` (includes name, base_url, default_model)
2. If OpenAI-compatible, `OpenAICompatibleProvider` in `cloud_llm_service.py` handles it automatically
3. For custom SDK (like Gemini), create new provider class inheriting `BaseLLMProvider`
4. Register in `CloudLLMService.PROVIDER_CLASSES`
5. UI dropdown auto-populates from `GET /admin/llm/providers` endpoint

**Adding a new XTTS voice:**
1. Create folder with WAV samples: `./NewVoice/`
2. Add service instance in `orchestrator.py`
3. Add voice ID to admin endpoints

**Adding a new secretary persona:**
1. Add entry to `SECRETARY_PERSONAS` dict in `vllm_llm_service.py`

**Adding i18n translations:**
1. Edit `admin/src/plugins/i18n.ts`
2. Add keys to both `ru` and `en` message objects

**Adding a new theme:**
1. Add CSS variables in `admin/src/assets/main.css`
2. Update `Theme` type in `admin/src/stores/theme.ts`
3. Add translations in `admin/src/plugins/i18n.ts`

## API Quick Reference

**OpenAI-compatible (for OpenWebUI):**
- `POST /v1/chat/completions` — Chat with streaming
- `POST /v1/audio/speech` — TTS with current voice
- `GET /v1/models` — Available models

**Streaming TTS (for telephony):**
- `POST /admin/tts/stream` — HTTP chunked streaming (target <500ms TTFA)
- `WS /admin/tts/ws/stream` — WebSocket real-time TTS for GSM telephony

```bash
# HTTP streaming example
curl -X POST http://localhost:8002/admin/tts/stream \
  -H "Content-Type: application/json" \
  -d '{"text":"Привет!", "voice":"gulya", "target_sample_rate":8000}' \
  --output audio.pcm

# Benchmark streaming latency
python scripts/benchmark_streaming_tts.py --iterations 5
```

**Admin API (JWT required):** See `app/routers/` for complete endpoint definitions.

Key patterns:
- `GET/POST /admin/{resource}` — List/create
- `GET/PUT/DELETE /admin/{resource}/{id}` — CRUD
- `POST /admin/{resource}/{id}/action` — Actions (start, stop, test)
- `GET /admin/{resource}/stream` — SSE endpoints

## Known Issues

1. **Vosk model required** — Download to `models/vosk/` for STT:
   ```bash
   mkdir -p models/vosk && cd models/vosk
   wget https://alphacephei.com/vosk/models/vosk-model-ru-0.42.zip && unzip vosk-model-ru-0.42.zip
   ```
2. **XTTS requires CC >= 7.0** — RTX 3060+; use OpenVoice for older GPUs (CC >= 6.1)
3. **GPU memory sharing** — vLLM 50% (~6GB) + XTTS ~5GB on 12GB GPU
4. **OpenWebUI Docker** — Use `172.17.0.1` not `localhost` for API URL
5. **Ruff ignores Cyrillic** — RUF001/002/003 disabled to allow Russian strings in code
6. **Docker + vLLM** — vLLM автоматически запускается как контейнер при переключении в админке. Первый раз нужно скачать образ: `docker pull vllm/vllm-openai:latest` (~9GB). **Note:** `VLLM_API_URL` is auto-normalized — trailing `/v1` is stripped (code adds it internally)
7. **xray-core for VLESS** — Included in Docker image. For local dev, download to `./bin/xray`:
   ```bash
   mkdir -p bin && cd bin
   wget https://github.com/XTLS/Xray-core/releases/download/v1.8.7/Xray-linux-64.zip
   unzip Xray-linux-64.zip && chmod +x xray
   ```

## Configuration Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | ruff, mypy, pytest, coverage config + test markers |
| `.pre-commit-config.yaml` | Pre-commit hooks |
| `admin/.eslintrc.cjs` | ESLint config |
| `admin/.prettierrc` | Prettier config |
| `.env.docker.example` | Docker environment template |
| `.env.example` | Local development environment template |

## Roadmap

See [BACKLOG.md](./BACKLOG.md) for detailed task tracking and [docs/IMPROVEMENT_PLAN.md](./docs/IMPROVEMENT_PLAN.md) for production readiness plan.

**Current focus:** Foundation (security, testing) → Monetization → GSM Telephony

## Cloud LLM Providers

Supported providers (configured via Admin Panel → LLM → Cloud Providers):

| Provider | Free Models | Paid Models |
|----------|-------------|-------------|
| **OpenRouter** | `nemotron-3-nano:free`, `trinity-large:free`, `solar-pro-3:free` | `gemini-2.0-flash`, `gpt-4o-mini` |
| **Google Gemini** | — | `gemini-2.0-flash`, `gemini-2.5-pro` |
| **OpenAI** | — | `gpt-4o`, `gpt-4o-mini` |
| **Anthropic** | — | `claude-opus-4.5`, `claude-sonnet-4` |
| **DeepSeek** | — | `deepseek-chat`, `deepseek-coder` |
| **Kimi** | — | `kimi-k2`, `moonshot-v1-128k` |
| **Claude Bridge** | (uses local `claude` CLI) | `sonnet`, `opus`, `haiku` |

**Usage in Telegram bots:**
- Set `llm_backend` in bot config: `"vllm"` or `"cloud:{provider_id}"` (dynamic dropdown in UI)
- Action buttons can override LLM per-mode (e.g., creative mode uses different model)
- LLM dropdown dynamically loads all enabled cloud providers from database

**Per-session LLM override in Chat:**
- Chat view has an LLM selector dropdown in the header
- Select a provider to override the default LLM for that session
- "Default" uses the system-wide LLM backend setting
- Useful for testing different providers without changing global settings

## VLESS Proxy for Gemini

Optional VLESS proxy for Gemini in restricted regions, with automatic failover across multiple proxies.

**Key files:** `xray_proxy_manager.py` (manages xray-core subprocess), `cloud_llm_service.py` (GeminiProvider uses it)

**Flow:** `GeminiProvider → XrayProxyManagerWithFallback → xray-core (SOCKS5) → VLESS Server → Google API`

**Storage:** VLESS URLs stored in provider's `config` JSON field as `vless_urls` array. Proxy endpoints are in `app/routers/llm.py` under `/admin/llm/proxy/` prefix.

**VLESS URL format:** `vless://uuid@host:port?security=reality&pbk=KEY&sid=ID&type=tcp&flow=xtls-rprx-vision#Name`

## CLI-OpenAI Bridge (Claude Code)

Wraps local `claude` CLI into an OpenAI-compatible API via a bridge subprocess (`services/bridge/` FastAPI on port 8787). No API key needed.

**Key files:** `bridge_manager.py` (process manager), `services/bridge/` (bridge server source)

**Flow:** `OpenAICompatibleProvider → services/bridge/ → claude CLI subprocess`

**Config:** Stored in provider's `config` JSON: `{"bridge_port": 8787, "permission_level": "chat"}`. Permission levels: `chat` (safe default), `readonly`, `edit`, `full`.

**Auto-management:** Bridge auto-starts/stops when switching LLM providers. Endpoints under `/admin/llm/bridge/`.

## GSM Telephony (SIM7600E-H)

GSM telephony via SIM7600E-H 4G LTE module (USB). Audio: 8kHz, 16-bit PCM, mono.

**Key files:** `app/routers/gsm.py` (15 endpoints under `/admin/gsm/`), `app/services/audio_pipeline.py` (TelephonyAudioPipeline for G.711/PCM processing)

**USB ports:** `/dev/ttyUSB2` (AT commands), `/dev/ttyUSB4` (audio/voice stream)

## Telegram Bot Auto-Start

Bots with `auto_start=true` in `bot_instances` table automatically restart on app startup. Managed by `multi_bot_manager.py`.

## Telegram Bot Payments

Three payment methods: YooKassa (RUB, via BotFather token), YooMoney (OAuth), Telegram Stars (XTR, no token needed).

**Key files:** `telegram_bot/handlers/sales/payment.py` (bot-side), `app/routers/telegram.py` (admin endpoints under `/admin/telegram/instances/{id}/payments`), `app/services/yoomoney_service.py` (OAuth), `app/routers/yoomoney_webhook.py`

**Flow:** `/pay` → `send_invoice()` → `PreCheckoutQuery` (auto-approved) → `SuccessfulPayment` → log to `payment_log` table

## Sales Bot Features

Advanced sales automation with 44 endpoints in `app/routers/bot_sales.py`.

**Features:** Quiz funnels, segment targeting, A/B testing, pricing calculator, testimonials, follow-up sequences, discovery prompts, event tracking, agent prompts.

**Key files:** `app/routers/bot_sales.py`, `app/services/sales_funnel.py`, `telegram_bot/handlers/sales/`, `db/repositories/bot_*.py` (14 domain-specific repositories)

## Fine-tuning & Project Dataset Generation

LoRA fine-tuning for Qwen2.5-7B with dataset generation from project sources (FAQ, code, docs, sales scenarios) and external GitHub repos.

**Key files:** `finetune_manager.py` (dataset processing, training control, adapter management), `finetune/train.py` (4-bit QLoRA training), `finetune/prepare_dataset.py` (Telegram export → JSONL)

**Output:** `finetune/datasets/project_dataset.jsonl`

**Pipeline:** Generate dataset → configure LoRA params → train on GPU → activate adapter → restart vLLM

**External repo support:** Shallow clone public GitHub/GitLab repos, parse `*.py` and `*.md` files. API: `POST /admin/finetune/dataset/generate-project`

## Local Model Discovery

The system automatically discovers downloaded HuggingFace models in `~/.cache/huggingface/hub/`.

**Supported model types:**
- Qwen, Llama, DeepSeek, Mistral, Phi, Gemma, Yi

**Detected quantization formats:**
- AWQ, GPTQ, GGUF, BNB-4bit, EXL2, FP16

**API response:**
```json
{
  "available_models": {
    "qwen2_5_7b_instruct_awq": {
      "full_name": "Qwen/Qwen2.5-7B-Instruct-AWQ",
      "downloaded": true,
      "quant_type": "AWQ",
      "lora_support": true
    }
  }
}
```

**Models tab** in admin panel shows all local models with download status and quantization type

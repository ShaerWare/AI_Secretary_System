# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Secretary System - virtual secretary with voice cloning (XTTS v2, OpenVoice), pre-trained voices (Piper), local LLM (vLLM + Qwen/Llama/DeepSeek), cloud LLM fallback (Gemini with VLESS proxy support, Kimi, OpenAI, Claude, DeepSeek, OpenRouter), and Claude Code CLI bridge. Features GSM telephony support (SIM7600E-H), a Vue 3 PWA admin panel with 15 tabs, i18n (ru/en), themes, ~160 API endpoints across 15 routers, website chat widgets (multi-instance), Telegram bot integration (multi-instance) with sales bot features and YooMoney/YooKassa/Stars payments, and fine-tuning with project dataset generation.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     Orchestrator (port 8002)                              │
│  orchestrator.py + app/routers/ (15 modular routers, ~160 endpoints)     │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │              Vue 3 Admin Panel (15 tabs, PWA)                      │   │
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
├── routers/                 # 15 modular routers (~160 endpoints)
│   ├── auth.py              # 3 endpoints  - JWT login/logout/refresh
│   ├── audit.py             # 4 endpoints  - Audit log viewing/export
│   ├── services.py          # 6 endpoints  - vLLM start/stop/restart
│   ├── monitor.py           # 7 endpoints  - GPU stats, health, SSE metrics
│   ├── faq.py               # 7 endpoints  - FAQ CRUD, reload, test
│   ├── stt.py               # 4 endpoints  - STT status, transcribe
│   ├── llm.py               # 30 endpoints - Backend, persona, cloud providers, VLESS proxy, bridge
│   ├── tts.py               # 15 endpoints - Presets, params, test, cache, streaming
│   ├── chat.py              # 12 endpoints - Sessions (CRUD, bulk delete, grouping), messages, streaming
│   ├── telegram.py          # 29 endpoints - Bot instances CRUD, control, payments, YooMoney
│   ├── widget.py            # 7 endpoints  - Widget instances CRUD
│   ├── gsm.py               # 12 endpoints - GSM telephony, SIM7600E-H module
│   ├── bot_sales.py         # 20 endpoints - Sales bot (quiz, segments, funnels, testimonials)
│   ├── github_webhook.py    # 4 endpoints  - GitHub webhook (stars, releases)
│   └── yoomoney_webhook.py  # 2 endpoints  - YooMoney payment webhook
└── services/
    ├── audio_pipeline.py    # Telephony audio processing (GSM frames, G.711)
    ├── sales_funnel.py      # Sales funnel logic (segmentation, pricing, follow-ups)
    └── yoomoney_service.py  # YooMoney OAuth & payment processing
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
| `finetune_manager.py` | LoRA fine-tuning manager (dataset processing, training, adapters, project dataset generation) |
| `app/rate_limiter.py` | Rate limiting with slowapi (configurable per endpoint type) |
| `app/security_headers.py` | Security headers middleware (X-Frame-Options, CSP, etc.) |
| `app/services/audio_pipeline.py` | GSM telephony audio processing (8kHz, PCM16, G.711) |
| `app/services/sales_funnel.py` | Sales funnel logic (segmentation, pricing calculator, follow-ups) |

### Admin Panel (Vue 3)

```
admin/src/
├── views/                   # 18 views (grouped into 5 accordion sections)
├── components/AccordionNav.vue  # Collapsible navigation with 5 groups
├── api/                     # API clients + SSE helpers
├── stores/                  # Pinia (auth, theme, toast, audit, services, llm)
├── composables/             # useSSE, useRealtimeMetrics, useExportImport
└── plugins/i18n.ts          # vue-i18n translations (ru/en)
```

**Navigation Groups (Accordion):**
- **Мониторинг**: Dashboard, Monitoring, Services, Audit
- **AI-движки**: LLM, TTS, Models, Fine-tune
- **Каналы**: Chat, Telegram, Widget, Telephony (GSM)
- **Бизнес**: FAQ, Sales, CRM (amoCRM placeholder)
- **Система**: Settings, About

### Database (SQLite + Redis)

**Location:** `data/secretary.db`

**Key tables:** `chat_sessions` (with `source`, `source_id` for tracking origin), `chat_messages`, `faq_entries`, `tts_presets`, `llm_presets`, `system_config`, `telegram_sessions`, `audit_log`, `cloud_llm_providers`, `bot_instances` (with `auto_start`, payment fields), `widget_instances`, `payment_log`

**Redis (optional):** Used for caching with graceful fallback if unavailable.

```bash
python scripts/migrate_json_to_db.py      # First-time migration
python scripts/migrate_to_instances.py    # Multi-instance migration
python scripts/migrate_add_payment_fields.py  # Payment fields migration
python scripts/migrate_sales_bot.py       # Sales bot tables migration
```

**Repository pattern:**
```
db/
├── database.py           # SQLite async connection
├── models.py             # SQLAlchemy ORM models + PROVIDER_TYPES dict
├── redis_client.py       # Redis caching with fallback
├── integration.py        # Backward-compatible managers
└── repositories/         # Data access layer
    ├── base.py           # BaseRepository with CRUD
    ├── chat.py           # ChatRepository
    ├── faq.py            # FAQRepository
    ├── preset.py         # PresetRepository
    ├── config.py         # ConfigRepository
    ├── telegram.py       # TelegramRepository
    ├── bot_instance.py   # BotInstanceRepository (Telegram bots)
    ├── payment.py        # PaymentRepository (payment logging)
    ├── widget_instance.py # WidgetInstanceRepository
    ├── cloud_provider.py # CloudProviderRepository
    └── audit.py          # AuditRepository
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
3. Router is auto-registered via `app/routers/__init__.py`

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

For regions where Google API is restricted, Gemini providers support optional VLESS proxy routing via xray-core with **automatic failover** support.

**Setup:**
1. Install xray-core (included in Docker image, or download to `./bin/xray`)
2. Create/edit Gemini provider in Admin Panel → LLM → Cloud Providers
3. In the modal, enter VLESS URLs in the "VLESS Proxy" section (one per line for failover)
4. Click "Test All Proxies" to verify connections
5. Save — all Gemini API requests will route through the proxy

**Multiple Proxies with Fallback:**
- Add multiple VLESS URLs (one per line) for automatic failover
- When current proxy fails, system switches to next available
- UI shows proxy count badge (e.g., "3 Proxy") on provider cards
- "Test All Proxies" tests each URL and shows per-proxy results

**VLESS URL format:**
```
vless://uuid@host:port?security=reality&pbk=PUBLIC_KEY&sid=SHORT_ID&type=tcp&flow=xtls-rprx-vision#Name
```

**Supported protocols:**
- Security: `none`, `tls`, `reality`
- Transport: `tcp`, `ws` (WebSocket), `grpc`
- Flow: `xtls-rprx-vision` (for XTLS)

**API endpoints:**
- `GET /admin/llm/proxy/status` — xray availability, proxy list and current proxy
- `POST /admin/llm/proxy/test` — Test single VLESS URL
- `POST /admin/llm/proxy/test-multiple` — Test multiple VLESS URLs
- `POST /admin/llm/proxy/reset` — Reset all proxies to enabled state
- `POST /admin/llm/proxy/switch-next` — Manually switch to next proxy
- `GET /admin/llm/proxy/validate` — Validate VLESS URL format

**How it works:**
```
GeminiProvider → XrayProxyManagerWithFallback → xray-core (SOCKS5/HTTP) → VLESS Server → Google API
                         ↓ (on failure)
                 Auto-switch to next proxy
```

**Storage:** VLESS URLs stored in provider's `config` JSON field:
```json
{
  "temperature": 0.7,
  "vless_urls": [
    "vless://uuid@host1:port?...#proxy1",
    "vless://uuid@host2:port?...#proxy2"
  ]
}
```

**Error handling:**
- xray not found → Warning logged, falls back to direct connection
- Invalid VLESS URL → Error shown in UI at save time
- Proxy fails → Auto-switch to next proxy (if multiple configured)
- All proxies fail → Fallback to direct connection
- VLESS server unreachable → SDK timeout, error returned to user

## CLI-OpenAI Bridge (Claude Code)

The Claude Bridge provider wraps the local `claude` CLI (Claude Code) into an OpenAI-compatible API via a bridge subprocess. This allows using Claude Code as an LLM backend without an API key.

**How it works:**
```
Admin Panel → Select "Claude Bridge" provider → Click "Use"
                                                      ↓
                                              BridgeProcessManager.start()
                                                      ↓
                                          services/bridge/ (FastAPI on port 8787)
                                                      ↓
                                              claude CLI (subprocess)
                                                      ↓
                                          OpenAICompatibleProvider → /v1/chat/completions
```

**Setup:**
1. Ensure `claude` CLI is installed and authenticated
2. In Admin → LLM → Cloud Providers → Add Provider
3. Select type "Claude Bridge (Local CLI)"
4. Configure permission level (chat/readonly/edit/full) and port
5. Click "Use" — bridge auto-starts

**Permission levels:**
- `chat` — Chat only, no file access (safe, default)
- `readonly` — Can read files
- `edit` — Can edit files
- `full` — Full access (dangerous)

**API endpoints:**
- `GET /admin/llm/bridge/status` — Bridge process status (running, pid, port, uptime)
- `POST /admin/llm/bridge/start` — Manually start bridge
- `POST /admin/llm/bridge/stop` — Manually stop bridge

**Auto-management:**
- Bridge auto-starts when switching to a `claude_bridge` provider
- Bridge auto-stops when switching to another provider or backend
- Bridge config stored in provider's `config` JSON: `{"bridge_port": 8787, "permission_level": "chat"}`

**Key files:**
- `bridge_manager.py` — Process manager (start/stop/status)
- `services/bridge/` — Full bridge source (FastAPI server)
- `services/bridge/.env` — Bridge configuration

## GSM Telephony (SIM7600E-H)

Support for GSM telephony via SIM7600E-H 4G LTE module for voice calls and SMS.

**Hardware:**
- Module: SIM7600E-H (4G LTE, voice, SMS)
- Connection: USB to server
- Antennas: MAIN (required), AUX (optional for better signal)

**USB Ports (Linux):**
```
/dev/ttyUSB0 - Diag (diagnostics)
/dev/ttyUSB1 - NMEA (GPS data)
/dev/ttyUSB2 - AT commands ← main control port
/dev/ttyUSB3 - Modem (PPP)
/dev/ttyUSB4 - Audio (USB PCM) ← voice stream
```

**Audio format:** 8kHz, 16-bit PCM, mono (compatible with TelephonyAudioPipeline)

**Key AT commands:**
```bash
AT           # Check connection
AT+CPIN?     # SIM status
AT+CSQ       # Signal strength (0-31, 99=unknown)
AT+CREG?     # Network registration
AT+CLIP=1    # Enable Caller ID
ATA          # Answer incoming call
ATH          # Hang up
AT+CMGF=1    # SMS text mode
AT+CMGS="+7..." # Send SMS
```

**API endpoints (`/admin/gsm/`):**
- `GET /status` — Module status (signal, SIM, network)
- `GET/PUT /config` — Configuration (auto-answer, timeouts, messages)
- `GET /calls` — Call history
- `POST /calls/answer|hangup|dial` — Call control
- `GET/POST /sms` — SMS history and send
- `POST /at` — Execute AT command (debug)
- `GET /ports` — List serial ports

**Admin UI:** Tab "Телефония" with status, calls, SMS, settings, and AT console.

## Telegram Bot Auto-Start

Telegram bots persist their running state and automatically restart after app/container restart.

**How it works:**
1. When bot is started via UI → `auto_start=true` saved in DB
2. When bot is stopped via UI → `auto_start=false` saved in DB
3. On app startup → all bots with `auto_start=true` automatically start

**Startup logs:**
```
📱 Auto-started Telegram bot: MyBot
📱 Auto-started 2/2 Telegram bots
```

**Migration for existing databases:**
```sql
ALTER TABLE bot_instances ADD COLUMN auto_start BOOLEAN DEFAULT 0;
```

## Telegram Bot Payments

Telegram bots support accepting payments via YooKassa (RUB), YooMoney (OAuth), and Telegram Stars (XTR).

**Supported payment methods:**
- **YooKassa** — Russian payment provider, requires provider token from BotFather
- **YooMoney** — Direct wallet payments via OAuth (no BotFather token needed)
- **Telegram Stars (XTR)** — Telegram's native digital currency, no provider token needed

**How it works:**
1. Configure payment in Admin Panel → Telegram → Edit bot → Payments section
2. Enable payments, add products (title, description, price in RUB/Stars)
3. Bot shows "Оплата" button in keyboard and responds to `/pay` command
4. User selects product → Telegram sends invoice → payment processed
5. Payment logged to `payment_log` table, visible in admin panel

**Payment flow:**
```
/pay or "Оплата" button → send_invoice() → PreCheckoutQuery (auto-approved) → SuccessfulPayment → log to DB
```

**YooMoney OAuth flow:**
1. Configure YooMoney client_id/secret in bot settings
2. Click "Authorize YooMoney" → OAuth popup
3. User grants access → callback stores access token
4. Bot can now accept YooMoney payments

**API endpoints:**
- `POST /admin/telegram/instances/{id}/payments` — Log payment (internal, from bot)
- `GET /admin/telegram/instances/{id}/payments` — Payment history (admin UI)
- `GET /admin/telegram/instances/{id}/payments/stats` — Payment statistics
- `GET /admin/telegram/instances/{id}/yoomoney/auth-url` — Get YooMoney OAuth URL
- `GET /admin/telegram/instances/{id}/yoomoney/callback` — OAuth callback handler
- `POST /admin/telegram/instances/{id}/yoomoney/disconnect` — Disconnect YooMoney
- `POST /yoomoney/webhook` — YooMoney payment notification webhook

**Migration for existing databases:**
```bash
python scripts/migrate_add_payment_fields.py
```

## Sales Bot Features

Telegram bots support advanced sales automation via `app/routers/bot_sales.py` (20 endpoints).

**Features:**
- **Quiz funnels** — lead qualification via interactive questions
- **Segment targeting** — different messages for different user segments
- **Pricing calculator** — dynamic pricing based on user responses
- **Testimonials** — social proof integration
- **Follow-up sequences** — automated drip campaigns

**Key files:**
- `app/routers/bot_sales.py` — API endpoints
- `app/services/sales_funnel.py` — Funnel logic, segmentation, pricing

**Migration:**
```bash
python scripts/migrate_sales_bot.py
```

## Fine-tuning & Project Dataset Generation

The system supports LoRA fine-tuning for Qwen2.5-7B with built-in dataset generation from project sources.

**Admin panel:** Tab "Обучение" (Fine-tune) → "Датасет из проекта"

**Project dataset sources:**
- **Sales scenarios (ТЗ)** — pricing, objection handling, case studies, multi-turn sales flows
- **FAQ from DB** — all FAQ entries automatically converted to training pairs
- **Technical docs** — installation, configuration, API, models, integrations
- **Escalation templates** — examples of handoff to senior support

**API endpoint:**
```bash
# Generate project dataset
curl -X POST http://localhost:8002/admin/finetune/dataset/generate-project \
  -H "Content-Type: application/json" \
  -d '{"include_tz": true, "include_faq": true, "include_docs": true, "include_escalation": true}'
```

**Output:** `finetune/datasets/project_dataset.jsonl` (same format as Telegram export dataset)

**Training pipeline:**
1. Generate project dataset OR upload Telegram export → process
2. Configure LoRA params (rank, alpha, epochs, learning rate)
3. Start training (runs on GPU in background)
4. Activate trained adapter → restart vLLM

**Key files:**
| File | Purpose |
|------|---------|
| `finetune_manager.py` | Dataset processing, training control, adapter management |
| `finetune/train.py` | LoRA training script (4-bit QLoRA on RTX 3060) |
| `finetune/prepare_dataset.py` | Telegram export → JSONL conversion |

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

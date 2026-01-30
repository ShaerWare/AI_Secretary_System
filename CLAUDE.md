# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Secretary System - virtual secretary with voice cloning (XTTS v2, OpenVoice), pre-trained voices (Piper), local LLM (vLLM + Qwen/Llama/DeepSeek), and cloud LLM fallback (Gemini, Kimi, OpenAI, Claude, DeepSeek, OpenRouter). Features a Vue 3 PWA admin panel with 13 tabs, i18n (ru/en), themes, ~112 API endpoints across 11 routers, website chat widgets (multi-instance), and Telegram bot integration (multi-instance).

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     Orchestrator (port 8002)                              │
│  orchestrator.py + app/routers/ (11 modular routers, ~112 endpoints)     │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │              Vue 3 Admin Panel (13 tabs, PWA)                      │   │
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
└────────┘  └────────┘     └──────────┘    └──────────┘    └──────────┘
```

**GPU Mode (RTX 3060 12GB):** vLLM ~6GB (50% GPU) + XTTS v2 ~5GB

**Request flow:** User message → FAQ check (instant) OR LLM → TTS → Audio returned

## Commands

### Quick Start (Docker - Recommended)

```bash
cp .env.docker .env && docker compose up -d     # GPU mode
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
source .venv/bin/activate              # Activate venv

# Python
ruff check .                           # Lint
ruff check . --fix                     # Auto-fix
ruff format .                          # Format

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
├── routers/                 # 11 modular routers (~115 endpoints)
│   ├── auth.py              # 3 endpoints  - JWT login/logout/refresh
│   ├── audit.py             # 4 endpoints  - Audit log viewing/export
│   ├── services.py          # 6 endpoints  - vLLM start/stop/restart
│   ├── monitor.py           # 7 endpoints  - GPU stats, health, SSE metrics
│   ├── faq.py               # 7 endpoints  - FAQ CRUD, reload, test
│   ├── stt.py               # 4 endpoints  - STT status, transcribe
│   ├── llm.py               # 24 endpoints - Backend, persona, cloud providers
│   ├── tts.py               # 15 endpoints - Presets, params, test, cache, streaming
│   ├── chat.py              # 12 endpoints - Sessions (CRUD, bulk delete, grouping), messages, streaming
│   ├── telegram.py          # 22 endpoints - Bot instances CRUD, control
│   └── widget.py            # 7 endpoints  - Widget instances CRUD
└── services/
    └── audio_pipeline.py    # Telephony audio processing (GSM frames, G.711)
```

**Core Services:**
| File | Purpose |
|------|---------|
| `cloud_llm_service.py` | Cloud LLM factory (Gemini, Kimi, OpenAI, Claude, DeepSeek, OpenRouter) |
| `vllm_llm_service.py` | vLLM API + `SECRETARY_PERSONAS` dict |
| `voice_clone_service.py` | XTTS v2 with custom presets + streaming synthesis |
| `stt_service.py` | Vosk (realtime) + Whisper (batch) STT |
| `multi_bot_manager.py` | Subprocess manager for multiple Telegram bots |
| `app/services/audio_pipeline.py` | GSM telephony audio processing (8kHz, PCM16, G.711) |

### Admin Panel (Vue 3)

```
admin/src/
├── views/                   # 13 tabs + LoginView
├── api/                     # API clients + SSE helpers
├── stores/                  # Pinia (auth, theme, toast, audit, services, llm)
├── composables/             # useSSE, useRealtimeMetrics, useExportImport
└── plugins/i18n.ts          # vue-i18n translations (ru/en)
```

### Database (SQLite + Redis)

**Location:** `data/secretary.db`

**Key tables:** `chat_sessions` (with `source`, `source_id` for tracking origin), `chat_messages`, `faq_entries`, `tts_presets`, `system_config`, `telegram_sessions`, `audit_log`, `cloud_llm_providers`, `bot_instances`, `widget_instances`

**Redis (optional):** Used for caching with graceful fallback if unavailable.

```bash
python scripts/migrate_json_to_db.py      # First-time migration
python scripts/migrate_to_instances.py    # Multi-instance migration
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
    └── audit.py          # AuditRepository
```

## Environment Variables

```bash
LLM_BACKEND=vllm                    # "vllm", "gemini", or "cloud:{provider_id}"
VLLM_API_URL=http://localhost:11434
VLLM_MODEL_NAME=lydia               # LoRA adapter name
SECRETARY_PERSONA=gulya             # "gulya" or "lidia"
GEMINI_API_KEY=...                  # Only for gemini backend
ORCHESTRATOR_PORT=8002
CUDA_VISIBLE_DEVICES=1
ADMIN_JWT_SECRET=...                # Auto-generated if empty
REDIS_URL=redis://localhost:6379/0  # Optional, for caching
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
6. **Docker + vLLM** — vLLM runs on host, not in container. Start `./start_qwen.sh` before switching to vLLM in admin panel

## Configuration Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | ruff, mypy, pytest, coverage config + test markers |
| `.pre-commit-config.yaml` | Pre-commit hooks |
| `admin/.eslintrc.cjs` | ESLint config |
| `admin/.prettierrc` | Prettier config |
| `.env.docker` | Docker environment template |
| `.env.example` | Local development environment template |

## Roadmap

See [BACKLOG.md](./BACKLOG.md) for task tracking and [docs/IMPROVEMENT_PLAN.md](./docs/IMPROVEMENT_PLAN.md) for production readiness plan.

**Current focus:** Foundation (security, testing) → Monetization → GSM Telephony

**Recently completed:**
- ✅ **Chat Management** — Inline rename, bulk delete, grouping by source (Admin/Telegram/Widget)
- ✅ **Source Tracking** — Chat sessions track origin (admin panel, telegram bot, widget)
- ✅ **Cloud AI Label** — Renamed "Gemini" to "Cloud AI" for generic cloud provider support
- ✅ Cloud LLM provider selection with dropdown UI (OpenRouter, Gemini, OpenAI, etc.)
- ✅ Updated OpenRouter models list (January 2026 free models)
- ✅ Improved error messages for cloud API errors (401, 404, 429)
- ✅ Streaming TTS with <500ms TTFA target (`synthesize_streaming()`)
- ✅ HTTP/WebSocket streaming endpoints for telephony
- ✅ GSM audio pipeline (8kHz, PCM16, G.711 A-law)
- ✅ Benchmark script for latency testing

## Cloud LLM Providers

Supported providers (configured via Admin Panel → LLM → Cloud Providers):

| Provider | Free Models | Paid Models |
|----------|-------------|-------------|
| **OpenRouter** | `nvidia/nemotron-3-nano-30b-a3b:free`, `arcee-ai/trinity-large-preview:free`, `upstage/solar-pro-3:free` | `google/gemini-2.0-flash-001`, `openai/gpt-4o-mini` |
| **Google Gemini** | — | `gemini-2.0-flash`, `gemini-2.5-pro` |
| **OpenAI** | — | `gpt-4o`, `gpt-4o-mini` |
| **Anthropic** | — | `claude-opus-4-5-20251101`, `claude-sonnet-4-20250514` |
| **DeepSeek** | — | `deepseek-chat`, `deepseek-coder` |
| **Kimi** | — | `kimi-k2`, `moonshot-v1-128k` |

**Usage in Telegram bots:**
- Set `llm_backend` in bot config: `"vllm"`, `"gemini"`, or `"cloud:{provider_id}"`
- Action buttons can override LLM per-mode (e.g., creative mode uses different model)

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Secretary "Лидия" - virtual secretary with voice cloning (XTTS v2) and pre-trained voices (Piper). Handles phone calls via Twilio with STT → LLM → TTS pipeline. Integrated with OpenWebUI for text chat with voice responses.

## Architecture

```
                         ┌─────────────────────────────────────┐
                         │     Orchestrator (port 8002)        │
                         │         orchestrator.py             │
                         └──────────────┬──────────────────────┘
                                        │
        ┌───────────────┬───────────────┼───────────────┬───────────────┬──────────────────┐
        ↓               ↓               ↓               ↓               ↓                  ↓
   STT Service     LLM Service    Voice Clone    OpenVoice v2     Piper TTS        Admin Panel
  (disabled)       vLLM/Gemini   (XTTS v2)      openvoice_       piper_tts_       admin_web.html
                        │         voice_clone_   service.py       service.py
                        │         service.py     (GPU CC 6.1+)    (CPU)
                        │         (GPU CC 7.0+)
                        ↓
                  FAQ System
              typical_responses.json
```

**GPU Mode (Single GPU - RTX 3060):**
```
RTX 3060 (12GB, CC 8.6):
  - vLLM Qwen2.5-7B + Lydia LoRA (default, 70% GPU = ~8.4GB, port 11434)
  - XTTS v2 voice cloning (remaining ~3.6GB)
```

**Request flow:**
1. User message → FAQ check (instant) OR vLLM/Gemini LLM
2. Response text → TTS (XTTS/Piper based on `current_voice_config`)
3. Audio returned to user

## Commands

```bash
# GPU Mode: XTTS + Qwen2.5-7B + Lydia LoRA (recommended)
./start_gpu.sh

# GPU Mode with Llama (fallback)
./start_gpu.sh --llama

# Start Qwen vLLM separately (for debugging)
./start_qwen.sh

# Start Llama vLLM separately (for debugging)
./start_vllm.sh

# CPU-only mode (Piper TTS + Gemini API)
./start_cpu.sh

# Health check
curl http://localhost:8002/health

# Test individual services
./venv/bin/python voice_clone_service.py    # Test XTTS (requires GPU CC >= 7.0)
./venv/bin/python piper_tts_service.py      # Test Piper
./venv/bin/python llm_service.py            # Test Gemini LLM + FAQ
./venv/bin/python vllm_llm_service.py       # Test vLLM (requires running vLLM server)

# First-time setup
./setup.sh && cp .env.example .env          # Edit .env: add GEMINI_API_KEY (optional with vLLM)

# Start OpenVoice mode (GPU CC 6.1+, e.g. P104-100)
./setup_openvoice.sh                        # First-time OpenVoice setup
./start_openvoice.sh

# Check logs (after start_gpu.sh)
tail -f logs/orchestrator.log               # Main service logs
tail -f logs/vllm.log                       # vLLM logs
```

## Key Components

### Multi-Voice TTS System
Five voices available, switchable via admin panel or API:

| Voice | Engine | GPU | Speed | Quality | Default |
|-------|--------|-----|-------|---------|---------|
| gulya | XTTS v2 | CC >= 7.0 | ~5-10s | Best cloning quality | ✅ |
| lidia | XTTS v2 | CC >= 7.0 | ~5-10s | Best cloning quality | |
| lidia_openvoice | OpenVoice v2 | CC >= 6.1 | ~2-4s | Good cloning, works on P104-100 | |
| dmitri | Piper | CPU | ~0.5s | Pre-trained male | |
| irina | Piper | CPU | ~0.5s | Pre-trained female | |

**Voice samples:**
- Гуля: `./Гуля/` (122 WAV files, converted from OGG)
- Лидия: `./Лидия/` (WAV files)

**Voice switching:**
- Admin: http://localhost:8002/admin → TTS tab
- API: `POST /admin/voice {"voice": "gulya"}` or `{"voice": "lidia"}`
- Code: `current_voice_config` dict in `orchestrator.py:306`

### Secretary Personas
Two personas available, controlled by `SECRETARY_PERSONA` env var (default: `gulya`):

| Persona | Name | Description |
|---------|------|-------------|
| gulya | Гуля (Гульнара) | Default persona, friendly digital secretary |
| lidia | Лидия | Alternative persona |

**Persona switching:**
- Env: `SECRETARY_PERSONA=gulya` or `SECRETARY_PERSONA=lidia`
- Code: `SECRETARY_PERSONAS` dict in `vllm_llm_service.py:20`
- Runtime: `llm_service.set_persona("lidia")`

### LLM Backend Selection
Controlled by `LLM_BACKEND` env var (`orchestrator.py:50`):
- `vllm` — Local LLM via vLLM (default for GPU mode)
  - **Qwen2.5-7B + LoRA** (default): `./start_gpu.sh`
  - Llama-3.1-8B GPTQ (fallback): `./start_gpu.sh --llama`
- `gemini` — Google Gemini API (requires GEMINI_API_KEY)

Both backends share the same interface and FAQ system.

**LoRA adapter path:** `/home/shaerware/qwen-finetune/qwen2.5-7b-lydia-lora/final`

### FAQ System (`typical_responses.json`)
Bypasses LLM for common questions. Checked in `llm_service.py:79` and `vllm_llm_service.py:188`.

```json
{
  "привет": "Здравствуйте! Чем могу помочь?",
  "сколько времени": "Сейчас {current_time}."
}
```

Templates: `{current_time}`, `{current_date}`, `{day_of_week}`

Hot reload: `llm_service.reload_faq()`

### Streaming TTS Manager
Pre-synthesizes audio during LLM streaming for faster response. Caches audio by text hash.
- Location: `orchestrator.py:57` (`StreamingTTSManager` class)
- Active during `/v1/chat/completions` streaming
- Cache checked in `/v1/audio/speech` before synthesis

## API Quick Reference

**OpenAI-compatible (for OpenWebUI):**
- `POST /v1/chat/completions` — Chat with streaming
- `POST /v1/audio/speech` — TTS with current voice
- `GET /v1/models` — Available models

**Admin voice control:**
- `GET /admin/voices` — List all voices
- `POST /admin/voice` — Set voice `{"voice": "irina"}`
- `POST /admin/voice/test` — Test synthesis

**Admin TTS/LLM:**
- `GET/POST /admin/tts/preset` — XTTS preset
- `GET/POST /admin/llm/model` — Gemini model
- `DELETE /admin/llm/history` — Clear conversation

## OpenWebUI Integration

```
URL: http://172.17.0.1:8002/v1  (Docker bridge IP)
API Key: sk-dummy (any value)
TTS Voice: gulya (or lidia)
Model: gulya-secretary-qwen (or lidia-secretary-qwen, gulya-secretary-llama, gulya-secretary-gemini)
```

**Model naming format:** `{persona}-secretary-{backend}`
- Personas: `gulya`, `lidia`
- Backends: `qwen` (Qwen2.5-7B + LoRA), `llama` (Llama-3.1-8B), `gemini`

## Environment Variables

```bash
# LLM Backend selection
LLM_BACKEND=vllm             # "vllm" (local Qwen/Llama) or "gemini" (cloud API)
VLLM_API_URL=http://localhost:11434  # vLLM server URL
VLLM_MODEL_NAME=lydia        # LoRA adapter name (auto-detect if empty)

# Secretary persona
SECRETARY_PERSONA=gulya      # "gulya" (default) or "lidia"

# Gemini (only needed if LLM_BACKEND=gemini)
GEMINI_API_KEY=...           # Google AI Studio API key

# Optional
ORCHESTRATOR_PORT=8002       # Default port
CUDA_VISIBLE_DEVICES=1       # GPU index for RTX 3060
```

## Key Files

| File | Purpose |
|------|---------|
| `orchestrator.py` | FastAPI server, routes, voice switching, StreamingTTSManager |
| `voice_clone_service.py` | XTTS v2, GPU synthesis (CC >= 7.0), presets, Е→Ё replacement |
| `openvoice_service.py` | OpenVoice v2, GPU synthesis (CC >= 6.1), fallback for older GPUs |
| `piper_tts_service.py` | Piper ONNX wrapper (CPU) |
| `llm_service.py` | Gemini API + FAQ system |
| `vllm_llm_service.py` | vLLM API (Qwen/Llama) + FAQ system |
| `typical_responses.json` | FAQ data (hot-reloadable) |
| `admin_web.html` | Admin panel UI |
| `Гуля/` | WAV samples for Гуля voice cloning (122 files, default) |
| `Лидия/` | WAV samples for Лидия voice cloning |
| `models/*.onnx` | Piper voice models (dmitri, irina) |
| `start_gpu.sh` | Launch XTTS + Qwen/Llama on RTX 3060 (default: Qwen + LoRA) |
| `start_qwen.sh` | Launch Qwen2.5-7B + Lydia LoRA only (vLLM) |
| `start_vllm.sh` | Launch Llama-3.1-8B GPTQ only (vLLM) |
| `start_cpu.sh` | Launch Piper + Gemini (CPU mode) |
| `start_openvoice.sh` | Launch OpenVoice + vLLM (for older GPUs CC 6.1+) |
| `setup_openvoice.sh` | First-time OpenVoice environment setup |

### Dataset Preparation (for fine-tuning)

| File | Purpose |
|------|---------|
| `prepare_telegram.py` | Convert Telegram export (result.json) to ShareGPT JSONL for QLoRA training |
| `analyze_dataset.py` | Statistics and analysis of prepared dataset |
| `augment_dataset.py` | Data augmentation for training |

## Known Issues

1. **STT disabled** — faster-whisper hangs on load; use text chat only
2. **XTTS requires CC >= 7.0** — Use RTX 3060 or newer GPU
3. **GPU memory sharing** — vLLM uses 70% (~8.4GB), XTTS needs ~3.6GB, works on 12GB GPU
4. **OpenWebUI Docker** — Use `172.17.0.1` not `localhost`

## Code Patterns

**Adding a new XTTS voice (like Гуля):**
1. Create folder with WAV samples (e.g., `./NewVoice/`)
2. Add new service instance in `orchestrator.py` (see `gulya_voice_service`)
3. Add voice ID to admin endpoints (`admin_get_voices`, `admin_set_voice`, `admin_test_voice`)
4. Add synthesis case in `synthesize_with_current_voice()`

**Adding a new secretary persona:**
1. Add entry to `SECRETARY_PERSONAS` dict in `vllm_llm_service.py:20`
2. Include: name, full_name, company, boss, prompt
3. Persona available via `SECRETARY_PERSONA` env var or `llm_service.set_persona()`

**Adding a new Piper voice:**
1. Add ONNX model to `./models/`
2. Add entry to `PiperTTSService.VOICES` dict in `piper_tts_service.py`
3. Voice auto-appears in admin panel

**Adding FAQ response:**
1. Edit `typical_responses.json`
2. Call `llm_service.reload_faq()` or restart orchestrator

**Changing default TTS for all endpoints:**
1. Modify `current_voice_config` dict in `orchestrator.py:306`
2. Or use API: `POST /admin/voice {"voice": "gulya"}`

**Modifying system prompt:**
- vLLM: Edit persona in `SECRETARY_PERSONAS` dict (`vllm_llm_service.py:20`)
- Gemini: `llm_service.py:128` (`_default_system_prompt` method)
- vLLM: `vllm_llm_service.py:228` (`_default_system_prompt` method)

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
        ┌───────────────┬───────────────┼───────────────┬──────────────────┐
        ↓               ↓               ↓               ↓                  ↓
   STT Service     LLM Service    Voice Clone      Piper TTS        Admin Panel
  (disabled)      llm_service.py  (XTTS v2)     piper_tts_service   admin_web.html
                        │         voice_clone_      (CPU)
                        │         service.py
                        │         (GPU)
                        ↓
                  FAQ System
              typical_responses.json
```

**Request flow:**
1. User message → FAQ check (instant) OR Gemini LLM
2. Response text → TTS (XTTS/Piper based on `current_voice_config`)
3. Audio returned to user

## Commands

```bash
# Start orchestrator (main command)
COQUI_TOS_AGREED=1 ./venv/bin/python orchestrator.py

# Health check
curl http://localhost:8002/health

# Test individual services
./venv/bin/python voice_clone_service.py    # Test XTTS
./venv/bin/python piper_tts_service.py      # Test Piper
./venv/bin/python llm_service.py            # Test LLM + FAQ

# First-time setup
./setup.sh && cp .env.example .env          # Add GEMINI_API_KEY
```

## Key Components

### Multi-Voice TTS System
Three voices available, switchable via admin panel or API:

| Voice | Engine | Speed | Quality |
|-------|--------|-------|---------|
| lidia | XTTS v2 (GPU) | ~5-10s | Cloned voice |
| dmitri | Piper (CPU) | ~0.5s | Pre-trained male |
| irina | Piper (CPU) | ~0.5s | Pre-trained female |

**Voice switching:**
- Admin: http://localhost:8002/admin → TTS tab
- API: `POST /admin/voice {"voice": "dmitri"}`
- Code: `current_voice_config` dict in orchestrator.py

### FAQ System (`typical_responses.json`)
Bypasses LLM for common questions. Checked before every Gemini API call.

```json
{
  "привет": "Здравствуйте! Чем могу помочь?",
  "сколько времени": "Сейчас {current_time}."
}
```

Templates: `{current_time}`, `{current_date}`, `{day_of_week}`

Hot reload: `llm_service.reload_faq()`

### XTTS Voice Presets
```python
service.synthesize(text, preset="warm")      # Тёплый
service.synthesize(text, preset="calm")      # Спокойный
service.synthesize(text, preset="energetic") # Энергичный
service.synthesize(text, preset="natural")   # Default
service.synthesize(text, preset="neutral")   # Деловой
```

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
TTS Voice: lidia
Model: lidia-gemini
```

## Environment Variables

```bash
GEMINI_API_KEY=...           # Required
ORCHESTRATOR_PORT=8002       # Default
VOICE_SAMPLES_DIR=./Лидия    # XTTS samples
```

## Key Files

| File | Purpose |
|------|---------|
| `orchestrator.py` | FastAPI server, routes, voice switching |
| `voice_clone_service.py` | XTTS v2, GPU synthesis, presets |
| `piper_tts_service.py` | Piper ONNX wrapper |
| `llm_service.py` | Gemini API + FAQ system |
| `typical_responses.json` | FAQ data |
| `admin_web.html` | Admin panel UI |
| `Лидия/` | 53 WAV samples for voice cloning |
| `models/*.onnx` | Piper voice models |

## Known Issues

1. **STT disabled** — faster-whisper hangs on load; use text chat only
2. **P104-100 GPU** — Compute capability 6.1 < 7.0 required, use RTX 3060
3. **Gemini 429** — Quota exceeded; use `gemini-2.5-flash` not `pro`
4. **OpenWebUI Docker** — Use `172.17.0.1` not `localhost`

## Code Patterns

**Adding a new voice (Piper):**
1. Add ONNX model to `./models/`
2. Add entry to `PiperTTSService.VOICES` dict
3. Voice auto-appears in admin panel

**Adding FAQ response:**
1. Edit `typical_responses.json`
2. Call `llm_service.reload_faq()` or restart

**Changing TTS for all endpoints:**
- Modify `synthesize_with_current_voice()` in orchestrator.py
- All TTS endpoints (`/tts`, `/v1/audio/speech`) use this function

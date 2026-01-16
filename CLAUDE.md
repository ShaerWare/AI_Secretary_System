# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Secretary "Лидия" - a virtual secretary system with voice cloning using XTTS v2. Handles phone calls via Twilio with STT → LLM → TTS pipeline. Integrated with OpenWebUI for text chat with voice responses.

## Current Status (2026-01-16)

| Component | Status | Performance |
|-----------|--------|-------------|
| Voice Clone Service (XTTS) | **Working** | RTF 0.95x on GPU |
| Piper TTS Service | **Working** | Dmitri, Irina voices |
| LLM Service | **Working** | Gemini 2.5 Flash |
| FAQ System | **Working** | Instant responses |
| OpenWebUI Integration | **Working** | Chat + TTS |
| Streaming TTS | **Working** | Parallel synthesis during LLM streaming |
| Admin CLI | **Working** | `./lidia-admin` |
| Admin Web UI | **Working** | http://localhost:8002/admin |
| Multi-Voice Selection | **Working** | Switch via admin panel |
| GPU (RTX 3060) | **Active** | 10 GB / 12 GB used |
| GPU (P104-100) | Not supported | CC 6.1 < 7.0 required |
| Speaker Latents Cache | **Enabled** | `./cache/` |
| Intonation Presets | **5 presets** | warm, calm, energetic, natural, neutral |
| Text Preprocessing | **Enabled** | Е→Ё, pauses, punctuation |
| STT Service | **Disabled** | faster-whisper model loading issues |

## Architecture

```
Phone Call (Twilio) → Phone Service (8001) → Orchestrator (8002)
                                                    ↓
                                    ┌───────────────┼───────────────┐
                                    ↓               ↓               ↓
                                STT Service    LLM Service    TTS Service
                                (Whisper)      (Gemini)       (XTTS v2)
                                                               ↓
                                                         RTX 3060 GPU
```

**Data flow**: Audio → STT → LLM → TTS (with Лидия's cloned voice) → Audio response

## Commands

### Run Voice Synthesis (standalone test)
```bash
source venv/bin/activate
COQUI_TOS_AGREED=1 python3 voice_clone_service.py
# Output: test_warm.wav, test_calm.wav, test_energetic.wav
```

### Run Orchestrator (for OpenWebUI)
```bash
# Start orchestrator (TTS + LLM, no STT)
COQUI_TOS_AGREED=1 ./venv/bin/python orchestrator.py

# Or in background:
COQUI_TOS_AGREED=1 ./venv/bin/python orchestrator.py &

# Check status:
curl http://localhost:8002/health
```

### Run Full System (with phone service)
```bash
./run.sh                      # Start orchestrator + phone service

# Or individually:
COQUI_TOS_AGREED=1 ./venv/bin/python orchestrator.py     # Port 8002
./venv/bin/python phone_service.py                        # Port 8001
```

### Setup (first time)
```bash
./setup.sh
cp .env.example .env          # Add GEMINI_API_KEY
```

## Voice Clone Service (`voice_clone_service.py`)

### GPU Configuration
- **RTX 3060 (12GB)**: Automatically detected and used (cuda:0)
- **P104-100 (8GB)**: NOT supported (compute capability 6.1 < 7.0 minimum)
- Falls back to CPU if no compatible GPU found
- Use `force_cpu=True` in constructor to disable GPU

### Performance (RTX 3060)
```
Средний RTF: 0.95x (почти реальное время)
Пик GPU памяти: 10.12 GB
Время синтеза: ~5-10 сек на фразу
```

### Intonation Presets
```python
service.synthesize(text, preset="warm")       # Тёплый, дружелюбный
service.synthesize(text, preset="calm")       # Спокойный, профессиональный
service.synthesize(text, preset="energetic")  # Энергичный, быстрый
service.synthesize(text, preset="natural")    # Естественный (default)
service.synthesize(text, preset="neutral")    # Нейтральный деловой
```

### Fine-tuning Parameters
| Parameter | Range | Effect |
|-----------|-------|--------|
| `temperature` | 0.1-1.0 | Higher = more expressive |
| `repetition_penalty` | 1.0-10.0 | Higher = fewer "ммм" sounds |
| `top_k` | 1-100 | Lower = more predictable |
| `top_p` | 0.1-1.0 | Lower = more stable |
| `speed` | 0.5-2.0 | Speech rate multiplier |
| `gpt_cond_len` | 6-30 | Conditioning length (sec) |

### Text Preprocessing (automatic)
- **Е→Ё replacement**: `все` → `всё`, `идет` → `идёт`, etc.
- **Pauses**: double space `"  "` → `"... "`
- **Introductory words**: auto-comma after "Здравствуйте", "Да", "К сожалению"

### Caching
- Speaker latents precomputed at startup from all 53 samples
- Cached to `./cache/speaker_latents_*.pkl`
- Cache invalidated if voice samples change

### API Usage
```python
from voice_clone_service import VoiceCloneService

service = VoiceCloneService()  # Auto-detects GPU

# Simple synthesis
service.synthesize_to_file("Привет!", "output.wav", preset="warm")

# With fine-tuning
wav, sr = service.synthesize(
    text="Текст",
    preset="natural",
    temperature=0.8,
    speed=0.95
)
```

## Other Services

### STT Service (`stt_service.py`)
- Whisper / Faster-Whisper
- Default: `base` model, `faster_whisper=True`
- VAD enabled

### LLM Service (`llm_service.py`)
- Gemini API (`gemini-2.5-flash`) - changed from pro due to quota limits
- Requires `GEMINI_API_KEY` in `.env`
- System prompt defines Лидия's persona
- Supports streaming responses
- **FAQ System**: Instant responses for typical questions (no LLM call)

### FAQ System (`typical_responses.json`)
Predefined responses for common questions. Checked BEFORE calling LLM API.

**File format:**
```json
{
  "привет": "Здравствуйте! Чем могу помочь?",
  "сколько времени": "Сейчас {current_time}.",
  "какой сегодня день": "Сегодня {current_date}.",
  "спасибо": "Пожалуйста! Рада помочь."
}
```

**Supported template variables:**
- `{current_time}` - HH:MM format
- `{current_date}` - DD.MM.YYYY format
- `{day_of_week}` - понедельник, вторник, etc.

**How it works:**
1. User message normalized (lowercase, trim punctuation)
2. Exact match checked against FAQ keys
3. Partial match checked (key in message or message in key)
4. If match found → instant response (no Gemini API call)
5. If no match → normal LLM generation

**Hot reload:** `llm_service.reload_faq()` reloads without restart

### Piper TTS Service (`piper_tts_service.py`)
Fast TTS using pre-trained ONNX models. Alternative to XTTS for quick responses.

**Available voices:**
| Voice ID | Name | Description |
|----------|------|-------------|
| dmitri | Дмитрий | Male, medium quality |
| irina | Ирина | Female, medium quality |

**Models location:** `./models/ru_RU-dmitri-medium.onnx`, `./models/ru_RU-irina-medium.onnx`

**Piper binary:** `/home/shaerware/voice-tts/venv/bin/piper`

**Usage:**
```python
from piper_tts_service import PiperTTSService

service = PiperTTSService()
service.synthesize_to_file("Привет!", "output.wav", voice="irina")
```

### Orchestrator (`orchestrator.py`)
- FastAPI on port 8002
- OpenAI-compatible API for OpenWebUI integration
- Logs to `calls_log/`

## Multi-Voice System

The system supports multiple TTS engines and voices, switchable via admin panel.

### Available Voices
| Voice ID | Name | Engine | Description |
|----------|------|--------|-------------|
| lidia | Лидия | XTTS v2 | Cloned voice (GPU, ~5-10s) |
| dmitri | Дмитрий | Piper | Pre-trained male (CPU, ~0.5s) |
| irina | Ирина | Piper | Pre-trained female (CPU, ~0.5s) |

### Voice Selection
- **Admin Panel**: http://localhost:8002/admin → TTS tab → Voice selector
- **API**: `POST /admin/voice` with `{"voice": "dmitri"}`
- **Current voice stored in**: `current_voice_config` global variable

### Architecture
```
User Request → /v1/audio/speech or /tts
                      ↓
            current_voice_config
                      ↓
        ┌─────────────┴─────────────┐
        ↓                           ↓
   engine=xtts                 engine=piper
        ↓                           ↓
  VoiceCloneService          PiperTTSService
   (voice_service)            (piper_service)
        ↓                           ↓
    GPU XTTS v2              CPU ONNX Piper
```

## API Endpoints (Port 8002)

### Core Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/tts` | POST | TTS with current voice (JSON: text, language) |
| `/stt` | POST | STT (multipart: audio) - currently disabled |
| `/chat` | POST | LLM with FAQ check (JSON: text) |
| `/process_call` | POST | Full pipeline: STT→LLM→TTS |

### OpenAI-Compatible Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/models` | GET | Models list |
| `/v1/chat/completions` | POST | Chat (streaming supported) |
| `/v1/audio/speech` | POST | TTS with current voice |
| `/v1/voices` | GET | Available voices list |

### Admin Endpoints - Voice Management
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/voices` | GET | List all voices with availability |
| `/admin/voice` | GET | Get current voice config |
| `/admin/voice` | POST | Set active voice `{"voice": "dmitri"}` |
| `/admin/voice/test` | POST | Test synthesis `{"voice": "irina"}` |

### Admin Endpoints - TTS
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/tts/presets` | GET | List XTTS presets |
| `/admin/tts/preset` | POST | Set default preset |
| `/admin/tts/test` | POST | Test XTTS synthesis |
| `/admin/tts/cache` | GET | Streaming cache stats |
| `/admin/tts/cache` | DELETE | Clear streaming cache |

### Admin Endpoints - LLM
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/llm/prompt` | GET/POST | System prompt |
| `/admin/llm/model` | GET/POST | Gemini model |
| `/admin/llm/history` | GET/DELETE | Conversation history |

## OpenWebUI Integration

### Setup (OpenWebUI in Docker on Linux)

1. **Admin Panel → Settings → Connections → OpenAI API**
   - URL: `http://172.17.0.1:8002/v1`
   - API Key: `sk-dummy` (any value, not validated)
   - Click "Verify" to test connection

2. **Settings → Audio → Text-to-Speech**
   - TTS Engine: `OpenAI`
   - OpenAI API Base URL: `http://172.17.0.1:8002/v1`
   - TTS Voice: `lidia`
   - Auto-play response: Enable for automatic voice playback

3. **Select model `lidia-gemini` in chat**

### Available Models
- `lidia-gemini` - Chat model (Gemini 2.5 Flash backend)
- `lidia-voice` - TTS model (XTTS v2 with cloned voice)

## Environment Variables (.env)

```bash
GEMINI_API_KEY=...            # Required for LLM
ORCHESTRATOR_PORT=8002
VOICE_SAMPLES_DIR=./Лидия

# Optional (telephony)
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=...
```

## Directory Structure

```
AI_Secretary_System/
├── orchestrator.py          # Main coordinator (FastAPI)
├── voice_clone_service.py   # XTTS v2 TTS with GPU
├── piper_tts_service.py     # Piper TTS with ONNX models
├── llm_service.py           # Gemini LLM + FAQ system
├── stt_service.py           # Speech-to-text (disabled)
├── phone_service.py         # Twilio integration
├── admin_web.html           # Admin panel UI
├── typical_responses.json   # FAQ responses
├── Лидия/                   # 53 voice samples (WAV) for XTTS
├── models/                  # Piper ONNX models
│   ├── ru_RU-dmitri-medium.onnx
│   └── ru_RU-irina-medium.onnx
├── cache/                   # Speaker latents cache
├── calls_log/               # Call recordings
├── temp/                    # Temporary audio files
└── venv/                    # Python environment
```

## Known Issues & Solutions

1. **P104-100 not working**: Expected, compute capability 6.1 not supported by PyTorch 2.9+
2. **First synthesis slow**: Normal, model loading + latent computation cached after first run
3. **GPU OOM**: Reduce `gpt_cond_len` or use fewer voice samples (`max_samples=20`)
4. **Unnatural pronunciation**: Check Ё replacement, add pauses with `...` or double spaces
5. **STT (faster-whisper) hangs on startup**: Model download/loading issue. Currently disabled in orchestrator. For text chat via OpenWebUI, STT is not needed.
6. **Gemini quota exceeded (429)**: Switch from `gemini-2.5-pro` to `gemini-2.5-flash` in `llm_service.py`
7. **OpenWebUI can't connect**: Use `http://172.17.0.1:8002/v1` instead of `localhost` when OpenWebUI runs in Docker

## TODO / Next Steps

1. **Fix STT Service**: Debug faster-whisper model loading, or switch to openai-whisper
2. **Twilio Integration**: Connect phone_service.py for actual phone calls
3. **Voice Input in OpenWebUI**: Enable STT for voice-to-voice conversations
4. **Expand FAQ**: Add more typical responses to `typical_responses.json`
5. **Voice per session**: Allow different voices for different conversations/users

## Session Log (2026-01-16)

### Changes Made

**1. FAQ System for LLM (`llm_service.py`)**
- Added `_check_faq()` method for instant responses
- Added `_apply_faq_templates()` for dynamic values (time, date)
- Added `reload_faq()` for hot reload without restart
- Integrated into `generate_response()`, `generate_response_stream()`, `generate_response_from_messages()`
- Fixed duplicated model initialization code

**2. Multi-Voice TTS System**
- Created `piper_tts_service.py` - Piper TTS wrapper for ONNX models
- Added `current_voice_config` global for voice selection
- Created `synthesize_with_current_voice()` helper function
- Updated `/tts` and `/v1/audio/speech` to use selected voice
- Added voice selection API endpoints

**3. Admin Panel Updates (`admin_web.html`)**
- Added voice selector card in TTS tab
- Added Piper TTS status indicator
- Added `fetchVoices()`, `setVoice()`, `testVoice()` functions

**4. New API Endpoints**
- `GET /admin/voices` - list all voices
- `GET /admin/voice` - current voice config
- `POST /admin/voice` - change voice
- `POST /admin/voice/test` - test voice synthesis

### Files Modified
- `llm_service.py` - FAQ system
- `orchestrator.py` - multi-voice support
- `admin_web.html` - voice selector UI

### Files Created
- `piper_tts_service.py` - Piper TTS service
- `typical_responses.json` - FAQ data

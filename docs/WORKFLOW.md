# AI Secretary System - Workflow & Architecture

## Overview

AI Secretary System - виртуальный секретарь с клонированием голоса, локальным LLM и многоканальной коммуникацией.

```
                           ┌─────────────────────────────────┐
                           │        ПОЛЬЗОВАТЕЛЬ             │
                           └───────────┬─────────────────────┘
                                       │
          ┌────────────────────────────┼────────────────────────────┐
          │                            │                            │
          ▼                            ▼                            ▼
    ┌──────────┐               ┌──────────────┐             ┌───────────┐
    │ Telegram │               │ Website      │             │ GSM       │
    │ Bot      │               │ Widget       │             │ Телефония │
    │ (aiogram)│               │ (WebSocket)  │             │ SIM7600   │
    └────┬─────┘               └──────┬───────┘             └─────┬─────┘
         │                            │                           │
         └────────────────────────────┼───────────────────────────┘
                                      │
                                      ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │                    ORCHESTRATOR (FastAPI :8002)                     │
    │                                                                     │
    │  ┌─────────────────────────────────────────────────────────────┐   │
    │  │ 19 роутеров (~346 endpoints)                                │   │
    │  │ auth │ audit │ services │ monitor │ faq │ stt │ llm │ tts  │   │
    │  │ chat │ telegram │ widget │ gsm │ bot_sales │ usage │ legal │   │
    │  │ backup │ github_webhook │ yoomoney_webhook │ amocrm         │   │
    │  └─────────────────────────────────────────────────────────────┘   │
    │                                                                     │
    │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐   │
    │  │ LLM       │  │ TTS        │  │ STT        │  │ Database   │   │
    │  │ Service   │  │ Service    │  │ Service    │  │ + Redis    │   │
    │  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └────────────┘   │
    └────────┼───────────────┼───────────────┼─────────────────────────┘
             │               │               │
    ┌────────┴───────┐ ┌────┴────────┐ ┌───┴──────────┐
    │                │ │             │ │              │
    ▼                ▼ ▼             ▼ ▼              ▼
┌────────┐    ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐
│ vLLM   │    │ Cloud  │ │ XTTS   │ │ Piper  │ │ Vosk/    │
│ Local  │    │ LLM    │ │ v2 GPU │ │ CPU    │ │ Whisper  │
│ Qwen2.5│    │ Gemini │ │        │ │        │ │          │
│ 7B     │    │ Claude │ │        │ │        │ │          │
│        │    │ OpenAI │ │        │ │        │ │          │
└────────┘    └────────┘ └────────┘ └────────┘ └──────────┘
```

---

## Request Flow (Полный цикл)

### Сценарий: Пользователь отправляет сообщение в Telegram

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. ПОЛУЧЕНИЕ СООБЩЕНИЯ                                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  User: "Расскажи о функциях синтеза речи"                              │
│                           │                                             │
│                           ▼                                             │
│  telegram_bot/handlers/messages.py                                      │
│  • Parse update                                                         │
│  • Check access middleware (allowed_users)                              │
│  • Route to handler                                                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. FAQ CHECK (Мгновенный ответ)                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  async_faq_manager.search("синтез речи")                               │
│                           │                                             │
│           ┌───────────────┴───────────────┐                             │
│           │                               │                             │
│     [НАЙДЕНО]                      [НЕ НАЙДЕНО]                         │
│           │                               │                             │
│           ▼                               ▼                             │
│    Вернуть FAQ ответ               Продолжить к LLM                    │
│    (без LLM)                                                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. LLM ROUTING                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  LLM_BACKEND = "vllm" | "gemini" | "cloud:{provider_id}"               │
│                           │                                             │
│       ┌───────────────────┼───────────────────┐                         │
│       │                   │                   │                         │
│       ▼                   ▼                   ▼                         │
│  ┌─────────┐       ┌───────────┐       ┌────────────┐                   │
│  │  vLLM   │       │  Gemini   │       │ Cloud LLM  │                   │
│  │  Local  │       │  + VLESS  │       │ Factory    │                   │
│  │         │       │  proxy    │       │            │                   │
│  │ Qwen2.5 │       │           │       │ OpenAI     │                   │
│  │ 7B-AWQ  │       │           │       │ Claude     │                   │
│  │ + LoRA  │       │           │       │ DeepSeek   │                   │
│  └─────────┘       └───────────┘       │ OpenRouter │                   │
│       │                   │            │ Kimi       │                   │
│       │                   │            │ Bridge     │                   │
│       └───────────────────┴────────────┴────────────┘                   │
│                           │                                             │
│                           ▼                                             │
│  SECRETARY_PERSONAS: "anna" | "marina"                                 │
│  System prompt + температура + max_tokens                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. STREAMING RESPONSE + PARALLEL TTS                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  async for chunk in llm.stream():                                       │
│      text_buffer += chunk                                               │
│                                                                         │
│      if text_buffer.ends_with('.', '!', '?'):  # Sentence complete     │
│          ┌─────────────────────────────────────────┐                    │
│          │ StreamingTTSManager                     │                    │
│          │ • Запуск TTS параллельно с LLM         │                    │
│          │ • TTFA < 500ms (Time To First Audio)   │                    │
│          └─────────────────────────────────────────┘                    │
│                           │                                             │
│           ┌───────────────┴───────────────┐                             │
│           │                               │                             │
│           ▼                               ▼                             │
│     ┌──────────┐                   ┌──────────┐                         │
│     │ XTTS v2  │                   │  Piper   │                         │
│     │ GPU      │                   │  CPU     │                         │
│     │ (Anna/  │                   │ (Dmitri/ │                         │
│     │  Marina)  │                   │  Irina)  │                         │
│     └──────────┘                   └──────────┘                         │
│           │                               │                             │
│           └───────────────┬───────────────┘                             │
│                           │                                             │
│                           ▼                                             │
│  audio_chunks: List[bytes]  # PCM 24kHz 16-bit                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 5. RESPONSE DELIVERY                                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  По каналу:                                                             │
│                                                                         │
│  TELEGRAM:                                                              │
│    bot.send_voice(chat_id, audio_bytes, caption=text)                  │
│                                                                         │
│  WIDGET:                                                                │
│    WebSocket binary message / HTTP StreamingResponse                   │
│                                                                         │
│  GSM:                                                                   │
│    TelephonyAudioPipeline → 8kHz G.711 → /dev/ttyUSB4                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 6. PERSISTENCE                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  chat_sessions:                                                         │
│    source = "telegram" | "widget" | "gsm"                              │
│    source_id = "bot_id:user_id"                                        │
│    owner_id → users.id (RBAC data isolation)                           │
│                                                                         │
│  chat_messages:                                                         │
│    role = "user" | "assistant"                                         │
│    content = текст сообщения                                           │
│                                                                         │
│  usage_log:                                                             │
│    tokens_in, tokens_out, cost                                         │
│                                                                         │
│  audit_log:                                                             │
│    action = "message"                                                  │
│    user_id = telegram_user_id                                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Service Architecture

### Service Container (Dependency Injection)

```
app/dependencies.py → ServiceContainer (Singleton, single source of truth)
│
├─ .voice_service          → VoiceCloneService (XTTS Marina)
├─ .anna_voice_service     → VoiceCloneService (XTTS Anna)
├─ .piper_service          → PiperTTSService (CPU)
├─ .openvoice_service      → OpenVoiceService (GPU CC 6.1+)
├─ .llm_service            → CloudLLMService or VLLMLLMService
├─ .stt_service            → VoskSTTService
├─ .streaming_tts_manager  → StreamingTTSManager
├─ .wiki_rag_service       → WikiRAGService
├─ .gsm_service            → GSMService
├─ .internet_monitor       → InternetMonitor
└─ .current_voice_config   → dict (engine + voice)

Populated by domain init functions in modules/*/startup.py
No global service variables — container is the only state holder
```

### Cloud LLM Factory

```
cloud_llm_service.py → CloudLLMService
│
├─ PROVIDER_TYPES (db/models.py):
│  ├─ gemini       → Google Generative AI
│  ├─ kimi         → Moonshot Kimi (OpenAI-compatible)
│  ├─ openai       → OpenAI API
│  ├─ claude       → Anthropic API
│  ├─ deepseek     → DeepSeek API
│  ├─ openrouter   → OpenRouter aggregator
│  ├─ custom       → Custom endpoint
│  └─ claude_bridge → Local Claude CLI wrapper
│
├─ Provider Classes:
│  ├─ BaseLLMProvider (abstract)
│  ├─ OpenAICompatibleProvider
│  ├─ GeminiProvider (+ VLESS proxy)
│  └─ ClaudeBridgeProvider
│
└─ Usage:
   provider = service.get_provider(provider_id)
   response = await provider.chat_completion(messages, stream=True)
```

### TTS Pipeline

```
voice_clone_service.py (XTTS v2)
│
├─ GPU Selection:
│  • Auto-select GPU with CC >= 7.0
│  • RTX 3060: ~5GB VRAM
│
├─ INTONATION_PRESETS:
│  ├─ warm       → natural, friendly
│  ├─ calm       → slow, soothing
│  ├─ energetic  → fast, expressive
│  ├─ natural    → default
│  └─ neutral    → monotone
│
├─ Pipeline:
│  text → normalize → split sentences → synthesize → cache → stream
│
└─ Parameters:
   ├─ temperature (0.5-1.0)
   ├─ repetition_penalty (1.0-2.0)
   ├─ speed (0.5-2.0)
   └─ gpt_cond_len / gpt_cond_chunk_len
```

---

## Database Schema

```
data/secretary.db (SQLite)
│
├─ USERS & RBAC
│  └─ users (id, username, password_hash, salt, role, display_name,
│           is_active, created, updated, last_login)
│     Roles: admin (full) │ user (own resources) │ guest (read-only)
│
├─ CHAT SYSTEM
│  ├─ chat_sessions (id, title, system_prompt, source, source_id, owner_id)
│  └─ chat_messages (id, session_id, role, content, created)
│
├─ LLM & TTS CONFIG
│  ├─ llm_presets (id, name, system_prompt, temp, max_tokens)
│  ├─ tts_presets (name, params, intonation, speed, owner_id)
│  ├─ cloud_llm_providers (provider_type, api_key, config, enabled, owner_id)
│  └─ system_config (key-value pairs)
│
├─ TELEGRAM BOTS (Multi-instance)
│  ├─ bot_instances (instance_id, bot_token, llm_backend, tts_engine, owner_id...)
│  └─ telegram_sessions (bot_id, user_id, state, context)
│
├─ WEBSITE WIDGETS (Multi-instance)
│  └─ widget_instances (instance_id, name, allowed_domains, config, owner_id)
│
├─ SALES BOT (14 tables, 13 repositories)
│  ├─ bot_agent_prompts
│  ├─ bot_quiz_questions
│  ├─ bot_segments
│  ├─ bot_user_profiles
│  ├─ bot_followup_rules
│  ├─ bot_followup_queue
│  ├─ bot_events
│  ├─ bot_testimonials
│  ├─ bot_hardware_specs
│  ├─ bot_ab_tests
│  ├─ bot_discovery_responses
│  ├─ bot_subscribers
│  └─ bot_github_configs
│
├─ PAYMENTS & USAGE
│  ├─ payment_log (bot_id, user_id, amount, provider, status)
│  ├─ usage_log (session_id, tokens_in, tokens_out, cost)
│  └─ usage_limits (user_id, limit_type, tokens_per_day)
│
├─ COMPLIANCE
│  ├─ audit_log (timestamp, user_id, action, resource, details)
│  ├─ user_consents (GDPR)
│  └─ amocrm_config, amocrm_sync_log (CRM integration)
│
├─ GSM TELEPHONY
│  ├─ gsm_call_logs (id, phone, direction, duration, status)
│  └─ gsm_sms_logs (id, phone, direction, message, status)
│
└─ FAQ
   └─ faq_entries (id, trigger, response, fuzzy_match_score)
```

### Redis (Optional Cache)

```
redis://localhost:6379/0
│
├─ chat:{session_id}:messages   → cached messages
├─ faq:matches:{query_hash}     → fuzzy match cache
├─ voice:{text_hash}:audio      → TTS cache (TTL 300s)
├─ llm:response:{hash}          → LLM completion cache
├─ rate_limit:{user}:{endpoint} → sliding window
└─ config:*:cached              → config snapshots

Fallback: если Redis недоступен → только SQLite
```

---

## Admin Panel (Vue 3 PWA)

### 19 Views (Accordion Navigation)

```
┌─────────────────────────────────────────────────────────────┐
│ МОНИТОРИНГ                                                  │
├─────────────────────────────────────────────────────────────┤
│ • DashboardView   - Overview: status, sessions, GPU         │
│ • MonitoringView  - Real-time GPU, CPU, Redis (SSE)        │
│ • ServicesView    - vLLM/cloud start/stop/restart          │
│ • AuditView       - Audit logs with export                  │
├─────────────────────────────────────────────────────────────┤
│ AI-ДВИЖКИ                                                   │
├─────────────────────────────────────────────────────────────┤
│ • LlmView         - Backend switch, providers, personas     │
│ • TtsView         - Engine/voice selection, params, test    │
│ • ModelsView      - Local model discovery                   │
│ • FinetuneView    - LoRA training, dataset generation       │
├─────────────────────────────────────────────────────────────┤
│ КАНАЛЫ                                                      │
├─────────────────────────────────────────────────────────────┤
│ • ChatView        - Session CRUD, messages, grouped         │
│ • TelegramView    - Bot instances, payment config           │
│ • WidgetView      - Widget instances CRUD + test chat        │
│ • GSMView         - SIM7600E-H config, call history         │
├─────────────────────────────────────────────────────────────┤
│ БИЗНЕС                                                      │
├─────────────────────────────────────────────────────────────┤
│ • FaqView         - FAQ CRUD, fuzzy search testing          │
│ • SalesView       - Sales bot dashboard                     │
│ • CrmView         - amoCRM integration (placeholder)        │
├─────────────────────────────────────────────────────────────┤
│ СИСТЕМА                                                     │
├─────────────────────────────────────────────────────────────┤
│ • SettingsView    - Profile, config, backups, audit          │
│ • UsageView       - Usage tracking, limits, statistics      │
│ • AboutView       - Version, GitHub, docs                   │
└─────────────────────────────────────────────────────────────┘
```

### State Management (Pinia)

```
admin/src/stores/
├─ auth.ts      - JWT token, user info, RBAC roles & permissions
│                 Roles: admin (*) │ user (chat, cloud, bots) │ guest (demo)
│                 hasPermission(), can(action, resource)
├─ theme.ts     - Current theme (8 variants)
├─ toast.ts     - Notifications
├─ services.ts  - Service status (vLLM, cloud)
├─ llm.ts       - Backend, personas, providers
├─ tts.ts       - Presets, voice params
└─ settings.ts  - System configuration
```

---

## Telegram Bot Architecture

### Multi-Bot Management

```
multi_bot_manager.py
│
├─ Singleton managing N subprocess bots
├─ Each bot: python -m telegram_bot
├─ Env var: BOT_INSTANCE_ID="bot_abc123"
├─ Auto-restart if auto_start=true in DB
│
└─ API: /admin/telegram/instances/{id}/(start|stop|restart|logs)
```

### Bot Module Structure

```
telegram_bot/
├─ __main__.py              - Entry point
├─ bot.py                   - Bot init, routers, middleware
├─ config.py                - BotConfig, load_config_from_api()
│
├─ handlers/
│  ├─ messages.py           - General message routing
│  ├─ commands.py           - /start, /help, /settings
│  ├─ callbacks.py          - Inline button callbacks
│  ├─ files.py              - File upload handling
│  │
│  └─ sales/                - Sales bot handlers
│     ├─ welcome.py         - Onboarding
│     ├─ quiz.py            - Segmentation quiz
│     └─ payment.py         - YooKassa, Stars
│
├─ middleware/
│  └─ access.py             - User/admin access control
│
├─ services/
│  └─ llm_router.py         - Route to vLLM or cloud
│
└─ prompts/                  - System prompt templates
```

---

## GSM Telephony Flow

```
SIM7600E-H 4G LTE Module
│
├─ /dev/ttyUSB2 (AT commands)
│  • AT+CREG?     → Registration status
│  • AT+CSQ       → Signal strength
│  • ATA          → Answer call
│  • ATH          → Hang up
│
├─ /dev/ttyUSB4 (Audio stream)
│  • 8kHz PCM 16-bit mono
│  • G.711 µ-law codec
│
└─ Flow:
   Incoming call
        │
        ▼
   Auto-answer (ATA)
        │
        ▼
   STT (Vosk real-time)
        │
        ▼
   LLM processing
        │
        ▼
   TTS synthesis
        │
        ▼
   TelephonyAudioPipeline
   • Resample 24kHz → 8kHz
   • Encode PCM → G.711
        │
        ▼
   Output to /dev/ttyUSB4
```

---

## API Quick Reference

### OpenAI-compatible (для OpenWebUI и внешних клиентов)

```
POST /v1/chat/completions     - Chat with streaming
POST /v1/audio/speech         - TTS
GET  /v1/models               - Available models
```

### Auth API

```
POST /admin/auth/login                - Login → JWT token
GET  /admin/auth/me                   - Current user info
GET  /admin/auth/profile              - Full profile
PUT  /admin/auth/profile              - Update display name
POST /admin/auth/change-password      - Change password
```

### Admin API (JWT required)

```
GET/POST   /admin/{resource}           - List/create
GET/PUT/DELETE /admin/{resource}/{id}  - CRUD
POST /admin/{resource}/{id}/action     - Actions (start, stop, test)
GET  /admin/{resource}/stream          - SSE endpoints
POST /webhooks/{service}               - External webhooks (amocrm, yoomoney, github)
```

### Streaming TTS

```
POST /admin/tts/stream        - HTTP chunked (TTFA <500ms)
WS   /admin/tts/ws/stream     - WebSocket real-time
```

---

## Performance Characteristics

| Metric | Target | Notes |
|--------|--------|-------|
| TTS TTFA | <500ms | Time To First Audio |
| vLLM GPU | ~6GB | 50% of RTX 3060 |
| XTTS GPU | ~5GB | Voice cloning |
| FAQ lookup | <10ms | Fuzzy match |
| LLM streaming | Real-time | Chunked response |
| Rate limiting | Configurable | Per endpoint type |

---

## Security

- **Multi-user RBAC** - 3 roles: admin (full), user (own resources), guest (read-only)
- **JWT Authentication** - HS256 tokens with user_id + role, DB-backed auth
- **Data Isolation** - `owner_id` on resources; users see only their data, admins see all
- **Auth Guards** - `get_current_user` (read), `require_not_guest` (write), `require_admin` (system)
- **Rate Limiting** - Configurable per endpoint
- **Security Headers** - X-Frame-Options, CSP, etc.
- **CORS** - Whitelist domains
- **Audit Logging** - All admin actions
- **GDPR Compliance** - Consent tracking

---

## Deployment

### Docker (Recommended)

```bash
docker compose up -d              # GPU mode
docker compose logs -f orchestrator
```

### Local Development

```bash
./start_gpu.sh                    # GPU: XTTS + vLLM
./start_cpu.sh                    # CPU: Piper + Gemini
```

### Admin Panel

```bash
cd admin && npm run build         # Production
cd admin && npm run dev           # Dev mode (:5173)
```

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `orchestrator.py` | FastAPI entry point |
| `app/routers/*.py` | 19 modular routers |
| `app/dependencies.py` | Service container (DI) |
| `cloud_llm_service.py` | Cloud LLM factory |
| `voice_clone_service.py` | XTTS v2 synthesis |
| `piper_tts_service.py` | Piper TTS (CPU) |
| `stt_service.py` | Vosk + Whisper STT |
| `multi_bot_manager.py` | Telegram multi-bot |
| `telegram_bot/` | Standalone bot module |
| `auth_manager.py` | RBAC auth + JWT + 3-level guards |
| `db/repositories/` | 33 data access classes |
| `admin/src/views/` | 19 Vue 3 views |

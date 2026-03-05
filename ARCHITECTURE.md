# Архитектура AI Secretary System

## Обзор компонентов (2026-01-29)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       AI SECRETARY SYSTEM                                │
│                  (Виртуальный секретарь с voice cloning)                │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Telegram   │  │    Widget    │  │   Twilio     │  │  SIM7600G-H  │
│     Bot      │  │   (Website)  │  │  (Cloud)     │  │  GSM Modem   │
│  (multi-bot) │  │ (multi-inst) │  │              │  │  (planned)   │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │                 │
       └────────────────┴────────┬────────┴─────────────────┘
                                 │
                                 v
┌─────────────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (port 8002)                              │
│        orchestrator.py + modules/*/router*.py (28 routers)             │
│                        ~400 API endpoints                                │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                   Vue 3 Admin Panel (20 views, PWA)                 │ │
│  │                          admin/dist/                                │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
      ┌───────────┬───────────────┼───────────────┬───────────────┐
      │           │               │               │               │
      v           v               v               v               v
┌──────────┐ ┌──────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐
│   vLLM   │ │  Cloud   │  │  XTTS v2  │  │   Piper   │  │   Vosk/   │
│  Local   │ │   LLM    │  │  Voice    │  │   TTS     │  │  Whisper  │
│   LLM    │ │ Factory  │  │  Clone    │  │  (CPU)    │  │   STT     │
│          │ │          │  │           │  │           │  │           │
│ Qwen2.5  │ │ Gemini   │  │ Streaming │  │ ONNX      │  │ Realtime  │
│ + LoRA   │ │ OpenAI   │  │ Synthesis │  │ Voices    │  │ + Batch   │
│          │ │ Claude   │  │ <500ms    │  │           │  │           │
│ ~6GB GPU │ │ DeepSeek │  │ TTFA      │  │ Fast CPU  │  │ ru-0.42   │
└────┬─────┘ │ OpenRouter│  └─────┬─────┘  └───────────┘  └───────────┘
     │       └──────────┘        │
     │                           │
     v                           v
┌────────────┐           ┌────────────────┐
│  RTX 3060  │           │ Audio Pipeline │
│  12GB VRAM │           │  8kHz PCM16    │
│  CUDA 12.x │           │  G.711 A-law   │
└────────────┘           │  GSM frames    │
                         └────────────────┘
```

## Поток данных

### 1. Входящий звонок

```
Звонок → Twilio
         ↓
    Phone Service (/incoming_call)
         ↓
    Приветствие (TwiML)
         ↓
    Запись речи абонента
         ↓
    /handle_speech endpoint
```

### 2. Обработка звонка

```
Аудио запись
    ↓
Orchestrator (/process_call)
    ↓
┌───┴─────────────────────────────┐
│ 1. STT Service                  │
│    audio.wav → text             │
│    "Здравствуйте, это XYZ?"     │
├─────────────────────────────────┤
│ 2. LLM Service                  │
│    text → response_text         │
│    "Да, компания XYZ. Чем помочь?"│
├─────────────────────────────────┤
│ 3. TTS Service                  │
│    response_text → audio        │
│    "Да, компания..." → audio.wav│
└───┬─────────────────────────────┘
    ↓
Возврат аудио ответа
    ↓
Phone Service
    ↓
Twilio → Абоненту
```

### 3. Логирование

Каждый звонок сохраняется в `calls_log/`:

```
calls_log/
├── call_20240108_153045_input.wav      # Входящее аудио
├── call_20240108_153045_output.wav     # Ответ секретаря
└── call_20240108_153045_transcript.txt # Текстовая расшифровка
```

## Детали сервисов

### Voice Clone Service (voice_clone_service.py)

**Технология**: Coqui TTS XTTS v2

**Функции**:
- Загрузка образцов голоса из `./Анна/` или `./Марина/`
- Few-shot voice cloning (3+ образца)
- **Batch синтез** для предзаписи
- **Streaming синтез** для телефонии (<500ms TTFA)
- Пресеты интонаций (warm, calm, energetic, natural, neutral)
- Кэширование speaker latents

**Требования**:
- GPU: 5-6GB VRAM (RTX 3060 рекомендуется)
- Образцы: 3+ WAV файлов, чистая речь
- CUDA Compute Capability >= 7.0

**Производительность**:
| Режим | Латентность | RTF |
|-------|-------------|-----|
| Batch | 2-4 сек | 0.9x |
| Streaming TTFA | 300-500ms | 0.5-0.9x |

### Audio Pipeline (app/services/audio_pipeline.py)

**Назначение**: Подготовка аудио для GSM телефонии

**Классы**:
- `TelephonyAudioPipeline` - конвертация 24kHz→8kHz, фреймирование
- `StreamingAudioBuffer` - кольцевой буфер для jitter smoothing

**GSM спецификации**:
- Sample rate: 8000 Hz
- Bit depth: 16-bit signed PCM
- Frame size: 20ms (160 samples)
- Кодирование: PCM16 или G.711 A-law

### STT Service (stt_service.py)

**Технологии**: Vosk (realtime) + Whisper (batch)

**Vosk (рекомендуется для телефонии)**:
- Модель: `vosk-model-ru-0.42` (~1.5GB)
- Realtime распознавание
- Низкая латентность

**Whisper (для высокого качества)**:
- Модели: tiny, base, small, medium, large
- Batch обработка
- Высокая точность

### LLM Service

**Локальный (vLLM)**:
- Модель: Qwen2.5-7B + Lydia LoRA
- Потребление: ~6GB VRAM (50% GPU)
- Персоны: anna, marina

**Cloud LLM (fallback)**:
| Провайдер | Модели |
|-----------|--------|
| Gemini | gemini-2.0-flash, gemini-2.5-pro |
| OpenAI | gpt-4o-mini, gpt-4o |
| Claude | claude-sonnet-4-5, claude-opus-4 |
| DeepSeek | deepseek-chat |
| OpenRouter | 20+ моделей |

### Telegram Bot Service

**Технологии**: python-telegram-bot (legacy) + aiogram 3.x (new bots)

**Multi-instance**:
- Независимые настройки LLM/TTS на каждый бот
- Whitelist пользователей
- Изолированные сессии чата
- Action buttons (📦, 💳, 🛠️, 📚, ❓, 📰, 🚀, 📋)

**Sales Funnel (aiogram)**:
- Quiz-сегментация: diy / basic / custom
- TZ генератор: qualified / unqualified / needs_analysis
- FAQ: 3 тематических раздела (Продукт, Установка, Цены и поддержка)
- Оплата: YooMoney, Telegram Stars
- Новости: автоматический парсинг `## NEWS` из GitHub PR/коммитов

### Widget Service

**Технология**: Встраиваемый JS виджет

**Multi-instance**:
- Независимые настройки на каждый виджет
- Кастомизация внешнего вида
- Автогенерация widget.js

**Персистентность сессий** (Replain-style):
- Session ID хранится в cookie (`SameSite=None; Secure`, 30 дней) + `localStorage` (fallback)
- При загрузке страницы — `preloadHistory()` загружает историю через `GET /widget/chat/session/{id}`
- Состояние открыт/закрыт сохраняется в `sessionStorage` — автовосстановление при навигации
- Безопасность: публичный GET эндпоинт отдаёт только сессии с `source="widget"`

## Streaming TTS Pipeline

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│    Text     │───▶│   XTTS      │───▶│   Audio     │───▶│    GSM      │
│   Input     │    │  Streaming  │    │  Pipeline   │    │   Output    │
│             │    │  inference  │    │  8kHz PCM   │    │  20ms frames│
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                         │
                         │ ~50-200ms chunks
                         │ with crossfade
                         v
                   ┌─────────────┐
                   │  Resample   │
                   │ 24kHz→8kHz  │
                   │   scipy     │
                   └─────────────┘
```

**Ключевые метрики**:
- Time-to-first-audio (TTFA): <500ms target
- Chunk interval: ~100ms
- Crossfade overlap: 256 samples

## Масштабирование

### Горизонтальное

```
                    ┌─ Orchestrator 1 (GPU 1)
Load Balancer  ─────┼─ Orchestrator 2 (GPU 2)
                    └─ Orchestrator 3 (CPU-only, Piper TTS)
```

### Вертикальное

- Больше GPU памяти → vLLM + XTTS одновременно
- Больше CPU → Piper TTS fallback
- SSD → быстрая загрузка моделей

### Оптимизации

1. **Streaming TTS** - <500ms до первого звука
2. **Кэширование speaker latents** - мгновенная инициализация
3. **vLLM GPU split** - 50% GPU для LLM, остальное для TTS
4. **Crossfade** - плавные переходы между чанками
5. **Audio buffering** - jitter smoothing для телефонии

## Безопасность

### API Keys
- Хранятся в `.env`
- Не попадают в git
- Доступ через переменные окружения

### Network
- HTTPS для production
- API authentication tokens
- Rate limiting
- Firewall rules

### Data
- Шифрование аудио в transit
- Автоудаление старых логов
- Анонимизация персональных данных

## Мониторинг

### Метрики
- Количество звонков
- Время обработки
- Ошибки по типам
- Использование GPU/CPU
- Использование памяти

### Логи
- Структурированное логирование
- Уровни: DEBUG, INFO, WARNING, ERROR
- Ротация логов
- Централизованный сбор (ELK, Loki)

## Deployment

### Development
```bash
./run.sh
```

### Production
```bash
docker-compose up -d
```

### CI/CD
```yaml
- Build Docker images
- Run tests
- Push to registry
- Deploy to servers
- Health checks
- Rollback if needed
```

## Расширения

### Будущие возможности
- WebRTC для браузерных звонков
- Asterisk/FreeSWITCH интеграция
- Поддержка других языков
- CRM интеграция (Битрикс24, AmoCRM)
- Календарь (Google Calendar, Outlook)
- Email отправка
- SMS уведомления
- Голосовая аналитика
- Sentiment analysis
- Автоматическая классификация звонков

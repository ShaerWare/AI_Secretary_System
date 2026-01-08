# AI Secretary System (Лидия)

Интеллектуальная система виртуального секретаря с клонированием голоса, способная принимать телефонные звонки и общаться с клиентами.

## Архитектура

```
┌─────────────┐
│  Телефонный │  Twilio / SIP
│    звонок   │
└──────┬──────┘
       │
       v
┌─────────────────────────────────────┐
│      Phone Service (port 8001)      │
│   Прием звонков, запись аудио       │
└──────────────┬──────────────────────┘
               │
               v
┌─────────────────────────────────────┐
│    Orchestrator (port 8000)         │
│  Координация всех компонентов       │
└─────────────┬───────────────────────┘
              │
    ┌─────────┼─────────┐
    │         │         │
    v         v         v
┌───────┐ ┌───────┐ ┌───────┐
│  STT  │ │  LLM  │ │  TTS  │
│Whisper│ │Gemini │ │XTTS v2│
└───────┘ └───────┘ └───────┘
```

### Компоненты

1. **Voice Clone Service** (`voice_clone_service.py`)
   - Клонирование голоса на базе XTTS v2
   - Использует образцы из папки `Лидия/`
   - Синтез речи с клонированным голосом

2. **STT Service** (`stt_service.py`)
   - Распознавание речи через Whisper/Faster-Whisper
   - Поддержка русского языка
   - Voice Activity Detection (VAD)

3. **LLM Service** (`llm_service.py`)
   - Интеграция с Gemini API
   - Системный промпт секретаря
   - История диалога

4. **Orchestrator** (`orchestrator.py`)
   - FastAPI сервер
   - Координация STT → LLM → TTS
   - API endpoints для всех операций

5. **Phone Service** (`phone_service.py`)
   - Интеграция с Twilio
   - Обработка входящих звонков
   - TwiML генерация

## Требования

### Железо
- GPU: NVIDIA с 12GB+ VRAM (например, RTX 3060)
- RAM: 16GB+ (64GB рекомендуется)
- Диск: 10GB свободного места

### ПО
- Ubuntu 20.04+ / Debian 11+
- Python 3.11+
- CUDA 11.8+ (для GPU)
- Docker + Docker Compose (опционально)
- ffmpeg

## Установка

### Вариант 1: Локальная установка

```bash
# 1. Клонирование и переход в директорию
cd /path/to/voice-tts

# 2. Запуск установки
./setup.sh

# 3. Настройка .env
cp .env.example .env
nano .env  # Добавьте GEMINI_API_KEY

# 4. Запуск
./run.sh
```

### Вариант 2: Docker

```bash
# 1. Настройка .env
cp .env.example .env
nano .env  # Добавьте API ключи

# 2. Сборка и запуск
docker-compose up -d

# 3. Проверка логов
docker-compose logs -f
```

## Настройка

### 1. Gemini API

Получите API ключ на https://makersuite.google.com/app/apikey

```env
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-pro-latest
```

### 2. Twilio (для телефонии)

1. Зарегистрируйтесь на https://www.twilio.com
2. Получите телефонный номер
3. Настройте Webhook для входящих звонков:
   - URL: `https://your-domain.com/incoming_call`
   - Method: POST

```env
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1234567890
```

### 3. Образцы голоса

Поместите WAV файлы в папку `Лидия/`:
- Формат: WAV, 16kHz или 44.1kHz
- Длительность: 3-30 секунд каждый
- Количество: минимум 3, рекомендуется 10+
- Качество: чистая речь без шума

## Использование

### API Endpoints

#### Health Check
```bash
curl http://localhost:8000/health
```

#### Синтез речи (TTS)
```bash
curl -X POST http://localhost:8000/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Привет, это тест", "language": "ru"}' \
  -o output.wav
```

#### Распознавание речи (STT)
```bash
curl -X POST http://localhost:8000/stt \
  -F "audio=@input.wav"
```

#### Чат с LLM
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "Здравствуйте, какой график работы?"}'
```

#### Полный цикл обработки
```bash
curl -X POST http://localhost:8000/process_call \
  -F "audio=@voice_message.wav" \
  -o response.wav
```

### Тестирование

```bash
# Запуск тестов
./test_system.sh

# Ручной тест TTS
python voice_clone_service.py

# Ручной тест STT
python stt_service.py

# Ручной тест LLM
python llm_service.py
```

## Интеграция с OpenWebUI

Если у вас запущен OpenWebUI с Gemini:

1. Используйте `llm_service.py` напрямую
2. Или настройте проксирование через OpenWebUI:

```python
# В llm_service.py замените на:
OPENWEBUI_URL = "http://localhost:8080/api/chat"
```

## Системный промпт

Промпт секретаря настраивается в `llm_service.py`:

```python
def _default_system_prompt(self) -> str:
    return """Ты - профессиональный виртуальный секретарь по имени Лидия.

    [Ваши инструкции здесь]
    """
```

Вы можете изменить:
- Имя секретаря
- Стиль общения
- Специфические инструкции для вашего бизнеса
- Информацию о компании

## Производительность

### Типичные задержки

- **STT (Whisper base)**: ~0.5-2 секунды на 10 сек аудио
- **LLM (Gemini)**: ~1-3 секунды
- **TTS (XTTS v2)**: ~2-5 секунд на предложение
- **Общий цикл**: ~5-10 секунд

### Оптимизация

1. **GPU**: Используйте CUDA для ускорения
2. **Модели**:
   - STT: `base` для скорости, `medium` для качества
   - LLM: `gemini-flash` для скорости, `gemini-pro` для качества
3. **Batch processing**: Обрабатывайте несколько запросов параллельно

## Логи и отладка

```bash
# Логи вызовов
ls -lh calls_log/

# Структура:
# call_20240101_120000_input.wav - входящее аудио
# call_20240101_120000_output.wav - ответ секретаря
# call_20240101_120000_transcript.txt - текстовая расшифровка

# Логи сервисов
docker-compose logs -f orchestrator
docker-compose logs -f phone-service
```

## Безопасность

1. **API ключи**: Храните в `.env`, не коммитьте
2. **HTTPS**: Используйте SSL для production
3. **Аутентификация**: Добавьте API tokens для endpoints
4. **Firewall**: Ограничьте доступ к портам

## Troubleshooting

### CUDA out of memory
```bash
# Уменьшите размер моделей
# В stt_service.py: model_size = "small"
# В voice_clone_service.py: используйте CPU fallback
```

### Плохое качество голоса
- Добавьте больше образцов в папку `Лидия/`
- Используйте чистые записи без шума
- Проверьте качество исходных WAV файлов

### Медленная работа
- Используйте faster-whisper вместо обычного Whisper
- Переключитесь на gemini-flash
- Увеличьте количество GPU workers

## Roadmap

- [ ] Поддержка нескольких голосов
- [ ] WebRTC для браузерных звонков
- [ ] Asterisk/FreeSWITCH интеграция
- [ ] Real-time streaming TTS
- [ ] Multi-language support
- [ ] Календарная интеграция
- [ ] CRM интеграция

## Лицензия

MIT

## Поддержка

Для вопросов и багов создавайте Issues в репозитории.

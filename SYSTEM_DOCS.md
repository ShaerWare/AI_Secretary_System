# AI Secretary System - Системная документация

## Обзор системы

AI Secretary "Лидия" - система синтеза речи с клонированием голоса, интегрированная с LLM для работы виртуального секретаря.

## Текущий статус (2026-01-14)

| Компонент | Статус | Примечания |
|-----------|--------|------------|
| Voice Clone Service | ✅ Работает | XTTS v2, голос Лидии |
| PyTorch | ✅ Установлен | v2.9.1 (CPU режим) |
| coqui-tts | ✅ Установлен | v0.27.3 |
| torchcodec | ✅ Установлен | v0.9.1 |
| Виртуальное окружение | ✅ Настроено | ./venv |

### Ограничения GPU

NVIDIA P104-100 (compute capability 6.1) **не поддерживается** PyTorch 2.9+.
Синтез работает на **CPU** (~32 сек на фразу).

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                      OpenWebUI (порт 3000)                   │
│                    LLM API (Gemini backend)                  │
└─────────────────────────┬───────────────────────────────────┘
                          │ /api/chat/completions
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR (порт 8002)                   │
│                     orchestrator.py                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │ STT Service │  │ LLM Service │  │ TTS Service │          │
│  │  (Whisper)  │  │  (Gemini)   │  │  (XTTS v2)  │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                 PHONE SERVICE (порт 8001)                    │
│                   phone_service.py                           │
│                  (Twilio webhooks)                           │
└─────────────────────────────────────────────────────────────┘
```

## Быстрый старт: Синтез голоса

### Запуск синтеза с голосом Лидии

```bash
# Активировать окружение
source venv/bin/activate

# Запустить синтез (тестовая фраза)
COQUI_TOS_AGREED=1 python3 voice_clone_service.py
```

Результат: файл `test_lidia_2026.wav`

### Изменение текста для синтеза

Откройте `voice_clone_service.py` и измените строку 97:

```python
if __name__ == "__main__":
    service = VoiceCloneService()
    test_text = "Ваш новый текст здесь"  # ← ИЗМЕНИТЕ ЭТУ СТРОКУ
    output = "output.wav"                  # ← Имя выходного файла
    service.synthesize_to_file(test_text, output)
    print(f"✅ Готово. Файл: {output}")
```

### Программное использование

```python
from voice_clone_service import VoiceCloneService

# Инициализация (загрузка модели ~30 сек)
service = VoiceCloneService()

# Синтез в файл
service.synthesize_to_file(
    text="Привет, это Лидия!",
    output_path="my_audio.wav",
    language="ru"
)

# Синтез в массив (для стриминга)
wav_array, sample_rate = service.synthesize(
    text="Текст для синтеза",
    language="ru"
)
```

## Голосовые образцы

**Папка:** `./Лидия/`
**Файлов:** 54 WAV
**Используются:** первые 3 файла для voice cloning

## Конфигурация (.env)

```bash
# Gemini API
GEMINI_API_KEY=AIzaSy...
GEMINI_MODEL=gemini-2.5-pro-latest

# OpenWebUI интеграция
OPENWEBUI_URL=http://localhost:3000
OPENWEBUI_API_KEY=

# Порты
ORCHESTRATOR_PORT=8002
TTS_SERVER_PORT=5002

# Голосовые образцы
VOICE_SAMPLES_DIR=./Лидия
```

## API Endpoints

### Orchestrator (порт 8002)

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/` | GET | Информация о сервисе |
| `/health` | GET | Проверка здоровья |
| `/tts` | POST | Синтез речи (JSON: text, language) |
| `/stt` | POST | Распознавание речи (multipart: audio) |
| `/chat` | POST | LLM ответ (JSON: text) |
| `/process_call` | POST | Полный цикл: STT → LLM → TTS |

## Файловая структура

```
AI_Secretary_System/
├── voice_clone_service.py   # ← ГЛАВНЫЙ: синтез голоса XTTS v2
├── orchestrator.py          # Координатор сервисов
├── phone_service.py         # Twilio webhooks
├── stt_service.py           # Whisper STT
├── llm_service.py           # Gemini LLM
├── .env                     # Конфигурация
├── requirements.txt         # Зависимости
├── CLAUDE.md                # Контекст для Claude Code
├── Лидия/                   # 54 голосовых образца WAV
├── venv/                    # Python окружение
└── test_lidia_2026.wav      # Последний синтезированный файл
```

## Решённые проблемы

1. **Импорт coqui_tts** → Исправлен на `from TTS.api import TTS`
2. **Лицензия XTTS** → Используется `COQUI_TOS_AGREED=1`
3. **GPU P104-100** → Принудительно CPU режим
4. **torchcodec** → Установлен для загрузки аудио

---
*Обновлено: 2026-01-14*

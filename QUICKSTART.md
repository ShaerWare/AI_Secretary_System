# Быстрый старт AI Secretary

## Docker (рекомендуется)

### 1. Клонирование и настройка

```bash
git clone https://github.com/ShaerWare/AI_Secretary_System
cd AI_Secretary_System

# Настройка переменных окружения
cp .env.docker.example .env
nano .env  # Добавьте GEMINI_API_KEY (опционально для CPU режима)
```

### 2. Запуск

```bash
# GPU режим (XTTS + vLLM) - требуется NVIDIA GPU 12GB+
docker compose up -d

# CPU режим (Piper + Gemini API) - без GPU
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d
```

### 3. Проверка

```bash
# Проверка состояния
docker compose ps
curl http://localhost:8002/health

# Админ-панель
open http://localhost:8002/admin
# Логин: admin / admin
```

## Локальная разработка

### 1. Установка зависимостей

```bash
./setup.sh
cp .env.example .env
nano .env  # Добавьте GEMINI_API_KEY если нужен fallback
```

### 2. База данных (первый запуск)

```bash
pip install aiosqlite "sqlalchemy[asyncio]" alembic redis
python scripts/migrate_json_to_db.py
```

### 3. Запуск

```bash
# GPU режим: XTTS + Qwen + LoRA
./start_gpu.sh

# CPU режим: Piper + Gemini
./start_cpu.sh

# Проверка
curl http://localhost:8002/health
```

### 4. Админ-панель

Откройте http://localhost:8002/admin (логин: admin / admin)

## Быстрые тесты

### Синтез речи

```bash
curl -X POST http://localhost:8002/admin/tts/test \
  -H "Content-Type: application/json" \
  -d '{"text": "Здравствуйте! Это виртуальный секретарь."}' \
  -o test.wav

ffplay test.wav  # или aplay test.wav
```

### Чат с секретарем

```bash
# Создать сессию
SESSION=$(curl -s -X POST http://localhost:8002/admin/chat/sessions \
  -H "Content-Type: application/json" \
  -d '{"title": "Test"}' | jq -r '.id')

# Отправить сообщение (streaming)
curl -N http://localhost:8002/admin/chat/sessions/$SESSION/stream \
  -H "Content-Type: application/json" \
  -d '{"content": "Привет! Как дела?"}'
```

### Распознавание речи (STT)

```bash
# Статус STT
curl http://localhost:8002/admin/stt/status

# Транскрибация файла
curl -X POST http://localhost:8002/admin/stt/transcribe \
  -F "audio=@recording.wav"
```

## Архитектура

```
                    ┌─────────────────────────────────┐
                    │  Orchestrator (port 8002)       │
                    │  ┌───────────────────────────┐  │
                    │  │ Vue 3 Admin Panel (PWA)   │  │
                    │  └───────────────────────────┘  │
                    └───────────────┬─────────────────┘
                                    │
    ┌───────────┬───────────┬───────┼───────┬───────────┬───────────┐
    ↓           ↓           ↓       ↓       ↓           ↓           ↓
  vLLM      Gemini       XTTS    Piper    Vosk      Widget    Telegram
  (GPU)     (Cloud)      (GPU)   (CPU)    (STT)     (Chat)     (Bot)
```

## Что дальше?

1. **Настройте персону** - Admin → LLM → выберите Gulya или Lidia
2. **Добавьте облачный LLM** - Admin → LLM → Cloud Providers
3. **Настройте виджет** - Admin → Widget → включите и скопируйте код
4. **Настройте Telegram бота** - Admin → Telegram → добавьте токен
5. **Прочитайте [README.md](./README.md)** - полная документация

## Troubleshooting

### "CUDA out of memory"
```bash
# Уменьшите использование GPU в start_qwen.sh:
--gpu-memory-utilization 0.5  # вместо 0.7
```

### "vLLM connection refused"
```bash
# Проверьте vLLM
curl http://localhost:11434/health
tail -f logs/vllm.log
```

### "Database error"
```bash
# Пересоздать базу данных
rm data/secretary.db
python scripts/migrate_json_to_db.py
```

### Медленный первый запуск
- Модели загружаются при первом запуске
- Следующие запросы будут быстрее
- Используйте GPU для ускорения TTS и LLM

## Контакты

Вопросы? Создайте Issue: https://github.com/ShaerWare/AI_Secretary_System/issues

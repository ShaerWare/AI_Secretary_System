# AI Secretary - Шпаргалка

## Быстрый старт

```bash
# Docker (рекомендуется)
cp .env.docker.example .env
docker compose up -d

# Локальный запуск с GPU
./start_gpu.sh

# CPU-only (Piper + Gemini)
./start_cpu.sh

# Тестирование
./test_system.sh
curl http://localhost:8002/health
```

## Основные команды

### Управление сервисами

```bash
# Запуск всех сервисов
./run.sh

# Остановка (Ctrl+C в терминале с run.sh)

# Docker запуск
docker-compose up -d

# Docker остановка
docker-compose down

# Логи Docker
docker-compose logs -f orchestrator
docker-compose logs -f phone-service
```

### API вызовы

```bash
# Health check
curl http://localhost:8002/health | jq

# Batch синтез речи
curl -X POST http://localhost:8002/admin/tts/test \
  -H "Content-Type: application/json" \
  -d '{"text": "Привет!", "preset": "natural"}' \
  -o output.wav

# Streaming TTS (для телефонии)
curl -X POST http://localhost:8002/admin/tts/stream \
  -H "Content-Type: application/json" \
  -d '{"text": "Привет!", "target_sample_rate": 8000}' \
  -o output.pcm

# Benchmark streaming TTS
python scripts/benchmark_streaming_tts.py --iterations 5

# OpenAI-совместимый TTS
curl -X POST http://localhost:8002/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Привет!", "voice": "gulya"}' \
  -o output.wav

# Чат (streaming)
curl -X POST http://localhost:8002/admin/chat/sessions/1/stream \
  -H "Content-Type: application/json" \
  -d '{"content": "Здравствуйте"}'
```

### Python примеры

```python
# Batch синтез речи
from voice_clone_service import VoiceCloneService
service = VoiceCloneService(voice_folder="./Гуля")
service.synthesize_to_file("Привет!", "output.wav", preset="warm")

# Streaming синтез (для телефонии)
for chunk, sr in service.synthesize_streaming(
    text="Привет!",
    target_sample_rate=8000,  # GSM
    stream_chunk_size=20,     # Меньше = быстрее первый чанк
):
    # chunk: np.ndarray float32
    # Отправлять чанки в телефонию по мере генерации
    pass

# Распознавание (Vosk realtime)
from stt_service import STTService
service = STTService(use_vosk=True)
result = service.transcribe("audio.wav")
print(result["text"])

# LLM (vLLM локальный)
from vllm_llm_service import VLLMLLMService
service = VLLMLLMService(persona="gulya")
response = await service.generate_response("Здравствуйте")
print(response)
```

## Настройка

### .env файл

```bash
# Обязательно
GEMINI_API_KEY=your_key_here

# Опционально (Twilio)
TWILIO_ACCOUNT_SID=ACxxx...
TWILIO_AUTH_TOKEN=xxx...
TWILIO_PHONE_NUMBER=+1234567890
```

### Системный промпт

Редактируйте `llm_service.py`, метод `_default_system_prompt()`

### Модели

```python
# В stt_service.py
model_size = "base"  # tiny, base, small, medium, large

# В llm_service.py
model_name = "gemini-2.5-pro-latest"  # или gemini-flash
```

## Мониторинг

```bash
# Health check
curl http://localhost:8002/health | jq

# GPU usage
watch -n 1 nvidia-smi

# Streaming TTS benchmark
python scripts/benchmark_streaming_tts.py --iterations 10

# Логи Docker
docker compose logs -f orchestrator

# Процессы
ps aux | grep -E 'python|vllm'

# Порты
ss -tlnp | grep -E '8002|11434'
```

## Отладка

```bash
# Проверка зависимостей
pip list | grep -E "TTS|whisper|fastapi|twilio"

# Проверка GPU
python3 -c "import torch; print(torch.cuda.is_available())"

# Проверка Twilio
curl http://localhost:8001/status | jq

# Тест компонентов
python3 voice_clone_service.py
python3 stt_service.py
python3 llm_service.py
```

## Docker команды

```bash
# Быстрый старт (локальный vLLM)
./start_docker.sh          # Запускает vLLM + Docker
./stop_docker.sh           # Останавливает всё

# Ручное управление
docker compose up -d       # Запуск
docker compose down        # Остановка
docker compose logs -f orchestrator  # Логи

# CPU-only режим
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d

# Полный контейнеризованный (скачивает vLLM образ)
docker compose -f docker-compose.full.yml up -d

# Пересборка после изменений
docker compose build --no-cache orchestrator && docker compose up -d

# Вход в контейнер
docker compose exec orchestrator bash
```

## Twilio интеграция

```bash
# Установка ngrok
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
tar xvzf ngrok-v3-stable-linux-amd64.tgz
sudo mv ngrok /usr/local/bin/

# Запуск туннеля
ngrok http 8001

# Webhook URL
https://xxxx.ngrok.io/incoming_call
```

## Частые проблемы

### CUDA out of memory
```python
# В stt_service.py
model_size = "small"  # или "tiny"

# В voice_clone_service.py
device = "cpu"  # вместо "cuda"
```

### API ключ не найден
```bash
# Проверьте .env
cat .env | grep GEMINI_API_KEY

# Должно быть без пробелов
GEMINI_API_KEY=AIza...
```

### Порт занят
```bash
# Найти процесс
lsof -i :8000
lsof -i :8001

# Убить процесс
kill -9 <PID>
```

### Плохое качество голоса
```bash
# Проверьте образцы
ls -lh Лидия/*.wav

# Должны быть чистые WAV файлы
# Минимум 3 шт, рекомендуется 10+
```

## Полезные алиасы

Добавьте в `~/.bashrc`:

```bash
# AI Secretary shortcuts
alias ai-start='cd /home/shaerware/voice-tts && ./run.sh'
alias ai-test='cd /home/shaerware/voice-tts && ./test_system.sh'
alias ai-logs='cd /home/shaerware/voice-tts && tail -f calls_log/*.txt'
alias ai-health='curl -s http://localhost:8000/health | jq'
```

## Производительность

### Benchmark Streaming TTS
```bash
# Полный бенчмарк с метриками
python scripts/benchmark_streaming_tts.py --iterations 10

# Сравнение streaming vs batch
python scripts/benchmark_streaming_tts.py --compare-batch

# Результаты:
# TTFA (Time-to-first-audio): 300-500ms
# RTF (Real-time factor): 0.5-0.9x
```

### Benchmark Batch TTS
```bash
time curl -X POST http://localhost:8002/admin/tts/test \
  -H "Content-Type: application/json" \
  -d '{"text": "Тест производительности", "preset": "natural"}' \
  -o /dev/null
```

### Benchmark LLM
```bash
time curl -X POST http://localhost:8002/admin/chat/sessions/1/stream \
  -H "Content-Type: application/json" \
  -d '{"content": "Привет"}'
```

## Бэкап

```bash
# Сохранить образцы голоса
tar -czf lidia_voice_backup.tar.gz Лидия/

# Сохранить логи звонков
tar -czf calls_backup_$(date +%Y%m%d).tar.gz calls_log/

# Сохранить конфигурацию
cp .env .env.backup
```

## Обновление

```bash
# Обновить зависимости
pip install -r requirements.txt --upgrade

# Пересобрать Docker
docker-compose build --no-cache

# Перезапуск
docker-compose down
docker-compose up -d
```

## Безопасность

```bash
# Проверить права на .env
chmod 600 .env

# Проверить API ключ
grep -v '^#' .env | grep -v '^$'

# Файрвол (опционально)
sudo ufw allow 8000/tcp  # Orchestrator
sudo ufw allow 8001/tcp  # Phone Service
```

## Ссылки

- Документация: README.md
- Архитектура: ARCHITECTURE.md
- Примеры: examples.md
- Быстрый старт: QUICKSTART.md

## Поддержка

```bash
# Версия Python
python3 --version

# Версия CUDA
nvidia-smi

# Системная информация
uname -a
free -h
df -h
```

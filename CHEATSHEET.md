# AI Secretary - Шпаргалка

## Быстрый старт

```bash
# Установка
./setup.sh

# Настройка API ключа
nano .env  # Добавьте GEMINI_API_KEY

# Запуск
./run.sh

# Тестирование
./test_system.sh
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
curl http://localhost:8000/health | jq

# Синтез речи
curl -X POST http://localhost:8000/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Привет!", "language": "ru"}' \
  -o output.wav

# Распознавание речи
curl -X POST http://localhost:8000/stt \
  -F "audio=@input.wav" | jq

# Чат
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "Здравствуйте"}' | jq

# Полный цикл
curl -X POST http://localhost:8000/process_call \
  -F "audio=@question.wav" \
  -o answer.wav
```

### Python примеры

```python
# Синтез речи
from voice_clone_service import VoiceCloneService
service = VoiceCloneService()
service.synthesize_to_file("Привет!", "output.wav")

# Распознавание
from stt_service import STTService
service = STTService()
result = service.transcribe("audio.wav")
print(result["text"])

# LLM
from llm_service import LLMService
service = LLMService()
response = service.generate_response("Здравствуйте")
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
# Логи звонков
ls -lh calls_log/
tail -f calls_log/call_*_transcript.txt

# GPU
watch -n 1 nvidia-smi

# Процессы
ps aux | grep python

# Порты
netstat -tlnp | grep -E '8000|8001'
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
# Сборка
docker-compose build

# Запуск
docker-compose up -d

# Остановка
docker-compose down

# Логи
docker-compose logs -f

# Перезапуск
docker-compose restart orchestrator

# Вход в контейнер
docker-compose exec orchestrator bash

# Удаление
docker-compose down -v
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

### Benchmark TTS
```bash
time curl -X POST http://localhost:8000/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Тест производительности"}' \
  -o /dev/null
```

### Benchmark STT
```bash
time curl -X POST http://localhost:8000/stt \
  -F "audio=@test_audio.wav" \
  -o /dev/null
```

### Benchmark полного цикла
```bash
time curl -X POST http://localhost:8000/process_call \
  -F "audio=@test_audio.wav" \
  -o /dev/null
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

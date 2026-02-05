# Примеры использования AI Secretary

## 1. Базовый запуск

```bash
# Docker (рекомендуется)
cp .env.docker.example .env
# Отредактируйте .env при необходимости
docker compose up -d

# Локальный запуск с GPU
./start_gpu.sh

# Проверка работы
curl http://localhost:8002/health | jq
```

## 2. Тестирование компонентов

### Тест Batch TTS (клонирование голоса)

```bash
python3 << EOF
from voice_clone_service import VoiceCloneService

service = VoiceCloneService(voice_folder="./Гуля")
service.synthesize_to_file(
    text="Добрый день! Это тест клонированного голоса.",
    output_path="test_voice.wav",
    preset="warm"
)
print("✅ Готово: test_voice.wav")
EOF
```

### Тест Streaming TTS (для телефонии)

```bash
python3 << EOF
import time
from voice_clone_service import VoiceCloneService

service = VoiceCloneService(voice_folder="./Гуля")

start = time.time()
first_chunk_time = None

def on_first():
    global first_chunk_time
    first_chunk_time = (time.time() - start) * 1000

chunks = []
for chunk, sr in service.synthesize_streaming(
    text="Здравствуйте! Чем могу помочь?",
    target_sample_rate=8000,  # GSM телефония
    stream_chunk_size=20,
    on_first_chunk=on_first,
):
    chunks.append(chunk)

print(f"✅ TTFA: {first_chunk_time:.0f}ms")
print(f"✅ Chunks: {len(chunks)}")
print(f"✅ Total: {(time.time() - start)*1000:.0f}ms")
EOF
```

### Benchmark Streaming TTS

```bash
# Полный бенчмарк
python scripts/benchmark_streaming_tts.py --iterations 10

# Сравнение с batch режимом
python scripts/benchmark_streaming_tts.py --compare-batch --iterations 5
```

### Тест распознавания речи

```bash
# Создайте тестовый аудио файл или используйте существующий
python3 << EOF
from stt_service import STTService

service = STTService(model_size="base")
result = service.transcribe("test_audio.wav")
print(f"Распознано: {result['text']}")
EOF
```

### Тест LLM

```bash
# Убедитесь что GEMINI_API_KEY в .env
python3 << EOF
from llm_service import LLMService

service = LLMService()

# Диалог
print("Пользователь: Здравствуйте")
response = service.generate_response("Здравствуйте")
print(f"Секретарь: {response}")

print("\nПользователь: Какой у вас график работы?")
response = service.generate_response("Какой у вас график работы?")
print(f"Секретарь: {response}")
EOF
```

## 3. API примеры (через curl)

### Health check

```bash
curl http://localhost:8002/health | jq
```

### Batch TTS (тест синтеза)

```bash
curl -X POST http://localhost:8002/admin/tts/test \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Здравствуйте! Компания на связи.",
    "preset": "natural"
  }' \
  -o greeting.wav
```

### Streaming TTS (для телефонии)

```bash
# HTTP chunked streaming
curl -X POST http://localhost:8002/admin/tts/stream \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Здравствуйте! Чем могу помочь?",
    "voice": "gulya",
    "target_sample_rate": 8000,
    "output_format": "pcm16"
  }' \
  -o response.pcm

# Конвертация PCM в WAV
ffmpeg -f s16le -ar 8000 -ac 1 -i response.pcm response.wav
```

### OpenAI-совместимый TTS

```bash
curl -X POST http://localhost:8002/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Привет! Это тест.",
    "voice": "gulya",
    "model": "tts-1"
  }' \
  -o output.wav
```

### Chat API (streaming)

```bash
curl -X POST http://localhost:8002/admin/chat/sessions/1/stream \
  -H "Content-Type: application/json" \
  -d '{"content": "Здравствуйте, какой у вас график работы?"}'
```

## 4. Python интеграция

### Batch TTS

```python
import requests

# Отправка текста на синтез
response = requests.post(
    "http://localhost:8002/admin/tts/test",
    json={
        "text": "Спасибо за звонок. Хорошего дня!",
        "preset": "warm"
    }
)

with open("response.wav", "wb") as f:
    f.write(response.content)
```

### Streaming TTS (HTTP)

```python
import requests
import numpy as np

# Streaming синтез для телефонии
response = requests.post(
    "http://localhost:8002/admin/tts/stream",
    json={
        "text": "Здравствуйте! Чем могу помочь?",
        "voice": "gulya",
        "target_sample_rate": 8000,
        "output_format": "pcm16"
    },
    stream=True
)

# Обработка чанков по мере поступления
for chunk in response.iter_content(chunk_size=640):  # 20ms @ 8kHz * 2 bytes
    if chunk:
        # Конвертация в numpy array
        audio = np.frombuffer(chunk, dtype=np.int16)
        # Отправка в телефонию...
        print(f"Received chunk: {len(audio)} samples")
```

### Streaming TTS (WebSocket)

```python
import asyncio
import websockets
import json
import numpy as np

async def streaming_tts_websocket():
    uri = "ws://localhost:8002/admin/tts/ws/stream"

    async with websockets.connect(uri) as ws:
        # Отправляем запрос
        await ws.send(json.dumps({
            "text": "Здравствуйте! Это тест WebSocket streaming.",
            "voice": "gulya",
            "target_sample_rate": 8000
        }))

        # Получаем чанки
        while True:
            message = await ws.recv()
            if isinstance(message, bytes):
                # Бинарный аудио чанк
                audio = np.frombuffer(message, dtype=np.int16)
                print(f"Audio chunk: {len(audio)} samples")
            else:
                # JSON статус
                status = json.loads(message)
                if status.get("done"):
                    print(f"Done! TTFA: {status['first_chunk_ms']}ms")
                    break

asyncio.run(streaming_tts_websocket())
```

### Прямое использование VoiceCloneService

```python
from voice_clone_service import VoiceCloneService
from app.services.audio_pipeline import TelephonyAudioPipeline

# Инициализация
service = VoiceCloneService(voice_folder="./Гуля")
pipeline = TelephonyAudioPipeline(target_sample_rate=8000)

# Streaming синтез с обработкой для GSM
for chunk, sr in service.synthesize_streaming(
    text="Привет! Это тест.",
    target_sample_rate=8000,
    stream_chunk_size=20,
):
    # chunk уже в 8kHz, конвертируем в PCM16
    pcm_data = pipeline.float_to_pcm16(chunk)
    # Отправка в GSM модем...
```

## 5. Настройка системного промпта

```python
# Создайте custom_secretary.py
from llm_service import LLMService

custom_prompt = """
Ты - секретарь компании "Моя Компания".

Информация о компании:
- График работы: Пн-Пт 9:00-18:00
- Телефон: +7 (123) 456-78-90
- Email: info@mycompany.ru
- Услуги: консультации, разработка, поддержка

Твои задачи:
1. Вежливо отвечать на вопросы о компании
2. Записывать клиентов на встречи
3. Принимать сообщения для руководителя
4. Отвечать на типовые вопросы

Стиль: профессиональный, дружелюбный, краткий
"""

llm = LLMService(system_prompt=custom_prompt)
response = llm.generate_response("Какие у вас услуги?")
print(response)
```

## 6. Интеграция с Twilio

### Настройка Webhook

В админке Twilio:
1. Купите номер телефона
2. Настройте Webhook для входящих звонков:
   - **URL**: `https://your-server.com/incoming_call`
   - **Method**: POST
   - **Status Callback**: `https://your-server.com/recording_status`

### Локальное тестирование с ngrok

```bash
# Установка ngrok
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
tar xvzf ngrok-v3-stable-linux-amd64.tgz
sudo mv ngrok /usr/local/bin/

# Запуск туннеля
ngrok http 8001

# Используйте полученный URL в Twilio:
# https://xxxx-xx-xx-xx-xx.ngrok.io/incoming_call
```

### Тестовый звонок

```python
from twilio.rest import Client

account_sid = "YOUR_ACCOUNT_SID"
auth_token = "YOUR_AUTH_TOKEN"
client = Client(account_sid, auth_token)

# Исходящий звонок
call = client.calls.create(
    url="http://your-server.com/incoming_call",
    to="+79991234567",
    from_="+1234567890"
)

print(f"Call SID: {call.sid}")
```

## 7. Мониторинг и логирование

### Просмотр логов звонков

```bash
# Все звонки
ls -lh calls_log/

# Последний звонок
ls -t calls_log/*.txt | head -1 | xargs cat

# Статистика
find calls_log -name "*.txt" | wc -l
```

### Анализ транскрипций

```python
from pathlib import Path

logs_dir = Path("calls_log")

for transcript in logs_dir.glob("*_transcript.txt"):
    print(f"\n{'='*50}")
    print(f"Звонок: {transcript.stem}")
    print(f"{'='*50}")
    print(transcript.read_text())
```

## 8. Docker примеры

### Сборка и запуск

```bash
# Сборка образов
docker-compose build

# Запуск всех сервисов
docker-compose up -d

# Только оркестратор
docker-compose up -d orchestrator

# Логи
docker-compose logs -f orchestrator

# Рестарт
docker-compose restart orchestrator
```

### Вход в контейнер

```bash
# Bash в контейнере оркестратора
docker-compose exec orchestrator bash

# Проверка GPU
docker-compose exec orchestrator nvidia-smi

# Тест из контейнера
docker-compose exec orchestrator python voice_clone_service.py
```

## 9. Производительность

### Benchmark

```python
import time
import requests

def benchmark_tts(text: str, iterations: int = 10):
    times = []
    for i in range(iterations):
        start = time.time()
        response = requests.post(
            "http://localhost:8000/tts",
            json={"text": text}
        )
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"Итерация {i+1}: {elapsed:.2f}s")

    avg_time = sum(times) / len(times)
    print(f"\nСредняя: {avg_time:.2f}s")
    print(f"Мин: {min(times):.2f}s, Макс: {max(times):.2f}s")

# Запуск
benchmark_tts("Здравствуйте, это тест производительности")
```

## 10. Troubleshooting

### Проверка доступности сервисов

```bash
#!/bin/bash
echo "Проверка сервисов..."

# Orchestrator
if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ Orchestrator работает"
else
    echo "❌ Orchestrator недоступен"
fi

# Phone Service
if curl -s http://localhost:8001/status > /dev/null; then
    echo "✅ Phone Service работает"
else
    echo "⚠️  Phone Service недоступен (опционально)"
fi

# GPU
if nvidia-smi > /dev/null 2>&1; then
    echo "✅ GPU доступен"
else
    echo "⚠️  GPU не найден (будет использоваться CPU)"
fi
```

### Очистка временных файлов

```bash
# Удаление старых логов (старше 7 дней)
find calls_log -type f -mtime +7 -delete

# Очистка temp
rm -rf temp/*

# Пересоздание папок
mkdir -p temp calls_log
```

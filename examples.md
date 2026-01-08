# Примеры использования AI Secretary

## 1. Базовый запуск

```bash
# Установка
./setup.sh

# Настройка API ключа
echo "GEMINI_API_KEY=your_key_here" >> .env

# Запуск
./run.sh
```

## 2. Тестирование компонентов

### Тест клонирования голоса

```bash
# Запуск из Python
python3 << EOF
from voice_clone_service import VoiceCloneService

service = VoiceCloneService()
service.synthesize_to_file(
    text="Добрый день! Это тест клонированного голоса Лидии.",
    output_path="test_voice.wav"
)
print("✅ Готово: test_voice.wav")
EOF
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
curl http://localhost:8000/health | jq
```

### Синтез речи

```bash
curl -X POST http://localhost:8000/tts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Здравствуйте! Компания на связи. Чем могу помочь?",
    "language": "ru"
  }' \
  -o secretary_greeting.wav
```

### Распознавание речи

```bash
# Запишите голосовое сообщение в voice_input.wav
curl -X POST http://localhost:8000/stt \
  -F "audio=@voice_input.wav" | jq
```

### Чат

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Добрый день, я хотел бы записаться на консультацию"
  }' | jq
```

### Полный цикл

```bash
# Обработка голосового сообщения с возвратом аудио ответа
curl -X POST http://localhost:8000/process_call \
  -F "audio=@customer_question.wav" \
  -o secretary_answer.wav

# Проверяем headers с метаданными
curl -X POST http://localhost:8000/process_call \
  -F "audio=@customer_question.wav" \
  -o secretary_answer.wav \
  -v 2>&1 | grep "^< X-"
```

## 4. Python интеграция

### Простой пример

```python
import requests

# Отправка текста на синтез
response = requests.post(
    "http://localhost:8000/tts",
    json={
        "text": "Спасибо за звонок. Хорошего дня!",
        "language": "ru"
    }
)

with open("response.wav", "wb") as f:
    f.write(response.content)
```

### Обработка голосового сообщения

```python
import requests

# Отправка аудио на обработку
with open("customer_voice.wav", "rb") as f:
    response = requests.post(
        "http://localhost:8000/process_call",
        files={"audio": f}
    )

# Сохраняем ответ
with open("secretary_response.wav", "wb") as f:
    f.write(response.content)

# Получаем метаданные
recognized_text = response.headers.get("X-Recognized-Text")
response_text = response.headers.get("X-Response-Text")

print(f"Клиент сказал: {recognized_text}")
print(f"Секретарь ответил: {response_text}")
```

### Асинхронная обработка

```python
import asyncio
import aiohttp

async def process_call(audio_path: str):
    async with aiohttp.ClientSession() as session:
        with open(audio_path, "rb") as f:
            form = aiohttp.FormData()
            form.add_field("audio", f, filename="audio.wav")

            async with session.post(
                "http://localhost:8000/process_call",
                data=form
            ) as response:
                audio_data = await response.read()
                return audio_data

# Использование
audio_response = asyncio.run(process_call("input.wav"))
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

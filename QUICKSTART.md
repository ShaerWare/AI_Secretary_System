# Быстрый старт AI Secretary

## За 5 минут

### 1. Установка зависимостей

```bash
./setup.sh
```

### 2. Настройка API ключа

```bash
cp .env.example .env
nano .env
```

Добавьте ваш Gemini API ключ:
```
GEMINI_API_KEY=ваш_ключ_здесь
```

Получить ключ: https://makersuite.google.com/app/apikey

### 3. Запуск

```bash
./run.sh
```

Система запустится на:
- Orchestrator: http://localhost:8000
- Phone Service: http://localhost:8001

### 4. Тест

```bash
# В новом терминале
./test_system.sh
```

## Быстрые тесты

### Синтез речи голосом Лидии

```bash
curl -X POST http://localhost:8000/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Здравствуйте! Это виртуальный секретарь Лидия."}' \
  -o test.wav

# Проиграть
ffplay test.wav
```

### Чат с секретарем

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "Какой у вас график работы?"}' | jq -r '.response'
```

### Обработка голосового сообщения

Запишите голосовое сообщение в файл `question.wav`, затем:

```bash
curl -X POST http://localhost:8000/process_call \
  -F "audio=@question.wav" \
  -o answer.wav

# Проиграть ответ
ffplay answer.wav
```

## Архитектура (упрощенно)

```
Звонок → Twilio → Phone Service → Orchestrator
                                      ↓
                           STT → LLM → TTS
                           ↓     ↓     ↓
                        Whisper Gemini XTTS
                                      ↓
                                  Голос Лидии
```

## Настройка голоса

Образцы голоса находятся в папке `Лидия/`:
- Уже есть ~54 WAV файла
- Система автоматически использует первые 3 для клонирования
- Чем больше качественных образцов, тем лучше результат

## Что дальше?

1. **Настройте системный промпт** - отредактируйте `llm_service.py`
2. **Добавьте Twilio** - для реальных звонков (опционально)
3. **Деплой в Docker** - `docker-compose up -d`
4. **Прочитайте README.md** - полная документация

## Troubleshooting

### "CUDA out of memory"
- Система пытается использовать GPU
- Если памяти не хватает, измените в `stt_service.py`: `model_size = "small"`
- Или отключите GPU: `device = "cpu"`

### "GEMINI_API_KEY not found"
- Проверьте что `.env` файл создан
- Проверьте что ключ добавлен без пробелов
- Перезапустите систему

### Плохое качество голоса
- Система использует первые 3 WAV из папки `Лидия/`
- Проверьте качество этих файлов
- Убедитесь что это чистые записи без шумов

### Медленная работа
- Первый запуск медленный - модели загружаются
- Следующие запросы будут быстрее
- Используйте GPU для ускорения

## Контакты

Вопросы? Проблемы? Создайте Issue в репозитории.

#!/bin/bash
# Скрипт тестирования AI Secretary

echo "🧪 Тестирование AI Secretary System"
echo "===================================="

BASE_URL="http://localhost:8000"

# Проверка доступности
echo "1️⃣  Проверка доступности сервиса..."
curl -s "$BASE_URL/health" | python3 -m json.tool
echo ""

# Тест TTS
echo "2️⃣  Тест синтеза речи (TTS)..."
curl -X POST "$BASE_URL/tts" \
    -H "Content-Type: application/json" \
    -d '{"text": "Здравствуйте, это тест синтеза речи с голосом Лидии", "language": "ru"}' \
    -o test_tts_output.wav

if [ -f "test_tts_output.wav" ]; then
    echo "✅ TTS тест пройден. Файл: test_tts_output.wav"
    echo "   Воспроизведите файл для проверки качества голоса"
else
    echo "❌ TTS тест не прошел"
fi
echo ""

# Тест Chat
echo "3️⃣  Тест LLM (Gemini)..."
curl -X POST "$BASE_URL/chat" \
    -H "Content-Type: application/json" \
    -d '{"text": "Здравствуйте, это компания XYZ?"}' | python3 -m json.tool
echo ""

# Информация о полном тесте
echo "4️⃣  Тест полного цикла (STT + LLM + TTS)..."
echo "   Для этого теста нужен аудио файл с речью."
echo "   Используйте команду:"
echo "   curl -X POST $BASE_URL/process_call -F \"audio=@your_audio.wav\" -o response.wav"
echo ""

echo "✅ Базовые тесты завершены"
echo ""
echo "📊 Проверьте:"
echo "   - test_tts_output.wav - качество синтезированного голоса"
echo "   - calls_log/ - логи обработанных звонков"
echo ""

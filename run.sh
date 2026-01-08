#!/bin/bash
# Скрипт запуска AI Secretary System

set -e

echo "🚀 Запуск AI Secretary System"
echo "=============================="

# Активация venv
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "✅ Virtual environment активирован"
else
    echo "❌ Virtual environment не найден. Запустите ./setup.sh"
    exit 1
fi

# Проверка .env
if [ ! -f ".env" ]; then
    echo "❌ Файл .env не найден. Создайте его на основе .env.example"
    exit 1
fi

# Загрузка переменных окружения
source .env

# Проверка API ключа
if [ -z "$GEMINI_API_KEY" ]; then
    echo "⚠️  GEMINI_API_KEY не установлен в .env"
    echo "    Система не сможет генерировать ответы!"
fi

# Создание папок
mkdir -p temp calls_log

echo ""
echo "🎯 Запуск сервисов..."
echo ""

# Запуск оркестратора в фоне
echo "🤖 Запуск Orchestrator на порту 8000..."
python orchestrator.py &
ORCHESTRATOR_PID=$!

# Ждем запуска
sleep 5

# Запуск телефонного сервиса
if [ ! -z "$TWILIO_ACCOUNT_SID" ]; then
    echo "📞 Запуск Phone Service на порту 8001..."
    python phone_service.py &
    PHONE_PID=$!
else
    echo "⚠️  Twilio не настроен. Phone Service не запущен."
    PHONE_PID=""
fi

echo ""
echo "✅ Система запущена!"
echo ""
echo "📡 Доступные endpoints:"
echo "   Orchestrator: http://localhost:8000"
echo "   Health: http://localhost:8000/health"
echo "   Docs: http://localhost:8000/docs"
if [ ! -z "$PHONE_PID" ]; then
    echo "   Phone Service: http://localhost:8001"
fi
echo ""
echo "🛑 Для остановки нажмите Ctrl+C"
echo ""

# Обработка завершения
cleanup() {
    echo ""
    echo "🛑 Остановка сервисов..."
    if [ ! -z "$ORCHESTRATOR_PID" ]; then
        kill $ORCHESTRATOR_PID 2>/dev/null || true
    fi
    if [ ! -z "$PHONE_PID" ]; then
        kill $PHONE_PID 2>/dev/null || true
    fi
    echo "✅ Сервисы остановлены"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Ждем
wait

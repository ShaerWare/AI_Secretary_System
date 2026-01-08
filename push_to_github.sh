#!/bin/bash
# Скрипт для загрузки проекта в GitHub

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║        Загрузка AI Secretary в GitHub                    ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Проверка что мы в git репозитории
if [ ! -d ".git" ]; then
    echo "❌ Ошибка: это не git репозиторий"
    exit 1
fi

# Проверка что есть коммит
if ! git log -1 &>/dev/null; then
    echo "❌ Ошибка: нет коммитов"
    exit 1
fi

echo "📊 Статус репозитория:"
echo "   Коммитов: $(git rev-list --count HEAD)"
echo "   Файлов: $(git ls-files | wc -l)"
echo "   Remote: $(git remote get-url origin)"
echo ""

echo "Выберите метод аутентификации:"
echo ""
echo "1) SSH - рекомендуется (нужен настроенный SSH ключ)"
echo "2) HTTPS + Personal Access Token"
echo "3) GitHub CLI (gh)"
echo "4) Force Push (ОСТОРОЖНО! Перезапишет репозиторий)"
echo ""
read -p "Ваш выбор (1-4): " choice

case $choice in
  1)
    echo ""
    echo "🔑 Используем SSH..."

    # Проверка SSH ключа
    if [ ! -f ~/.ssh/id_ed25519.pub ] && [ ! -f ~/.ssh/id_rsa.pub ]; then
        echo "⚠️  SSH ключ не найден. Создать новый? (y/n)"
        read -p "> " create_key
        if [ "$create_key" = "y" ]; then
            read -p "Введите ваш email: " email
            ssh-keygen -t ed25519 -C "$email"
            echo ""
            echo "✅ SSH ключ создан. Теперь добавьте его в GitHub:"
            echo ""
            echo "1. Скопируйте ключ:"
            cat ~/.ssh/id_ed25519.pub
            echo ""
            echo "2. Откройте: https://github.com/settings/keys"
            echo "3. Нажмите 'New SSH key'"
            echo "4. Вставьте ключ и сохраните"
            echo ""
            read -p "Нажмите Enter когда добавите ключ в GitHub..."
        else
            echo "❌ Отменено"
            exit 1
        fi
    fi

    # Тест SSH подключения
    echo "Проверка SSH подключения..."
    if ssh -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
        echo "✅ SSH подключение работает"
    else
        echo "❌ SSH не настроен. Добавьте ключ в GitHub:"
        echo "   https://github.com/settings/keys"
        exit 1
    fi

    git remote set-url origin git@github.com:ShaerWare/AI_Secretary_System.git
    echo "Пушим в GitHub..."
    git push -u origin main
    ;;

  2)
    echo ""
    echo "🔐 Используем HTTPS + Token..."
    echo ""
    echo "Получите Personal Access Token здесь:"
    echo "https://github.com/settings/tokens"
    echo "(выберите repo scope)"
    echo ""

    git remote set-url origin https://github.com/ShaerWare/AI_Secretary_System.git

    echo "При запросе пароля введите ваш Personal Access Token"
    echo ""
    git push -u origin main
    ;;

  3)
    echo ""
    echo "🚀 Используем GitHub CLI..."

    # Проверка gh
    if ! command -v gh &> /dev/null; then
        echo "❌ gh не установлен. Устанавливаем..."
        sudo apt update && sudo apt install -y gh
    fi

    # Проверка авторизации
    if ! gh auth status &>/dev/null; then
        echo "Авторизуйтесь в GitHub:"
        gh auth login
    fi

    echo "Пушим в GitHub..."
    git push -u origin main
    ;;

  4)
    echo ""
    echo "⚠️  ВНИМАНИЕ! Force push перезапишет весь репозиторий!"
    echo "   Все существующие файлы в GitHub будут удалены."
    echo ""
    read -p "Вы уверены? Введите 'YES' для продолжения: " confirm

    if [ "$confirm" != "YES" ]; then
        echo "❌ Отменено"
        exit 1
    fi

    echo "Force push..."
    git push -u origin main --force
    ;;

  *)
    echo "❌ Неверный выбор"
    exit 1
    ;;
esac

# Проверка результата
if [ $? -eq 0 ]; then
    echo ""
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║              ✅ УСПЕШНО ЗАГРУЖЕНО!                        ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo ""
    echo "📦 Репозиторий обновлен:"
    echo "   https://github.com/ShaerWare/AI_Secretary_System"
    echo ""
    echo "📊 Загружено файлов: $(git ls-files | wc -l)"
    echo "📝 Последний коммит: $(git log -1 --oneline)"
    echo ""
else
    echo ""
    echo "❌ Ошибка при загрузке"
    echo ""
    echo "Попробуйте:"
    echo "1. Проверить аутентификацию"
    echo "2. Прочитать GITHUB_PUSH_INSTRUCTIONS.md"
    echo "3. Запустить скрипт снова"
    exit 1
fi

# Инструкция по загрузке в GitHub

Проект готов к загрузке! Git репозиторий настроен, коммит создан.

## Что уже сделано ✅

- ✅ Git инициализирован
- ✅ Remote добавлен: `git@github.com:ShaerWare/AI_Secretary_System.git`
- ✅ Все файлы добавлены (21 файл, 3410 строк)
- ✅ Коммит создан
- ✅ .gitignore настроен (модели и образцы голоса исключены)

## Что нужно сделать

Выберите один из способов:

### Вариант 1: SSH ключ (Рекомендуется)

```bash
# 1. Создайте SSH ключ (если нет)
ssh-keygen -t ed25519 -C "your_email@example.com"
# Нажмите Enter 3 раза (файл по умолчанию, без пароля)

# 2. Скопируйте публичный ключ
cat ~/.ssh/id_ed25519.pub

# 3. Добавьте в GitHub:
# - Откройте: https://github.com/settings/keys
# - Нажмите "New SSH key"
# - Вставьте скопированный ключ
# - Сохраните

# 4. Проверьте подключение
ssh -T git@github.com

# 5. Запушьте
git push -u origin main
```

### Вариант 2: Personal Access Token (PAT)

```bash
# 1. Создайте PAT:
# - Откройте: https://github.com/settings/tokens
# - "Generate new token (classic)"
# - Выберите: repo (все галочки)
# - Сохраните токен!

# 2. Измените remote на HTTPS
git remote set-url origin https://github.com/ShaerWare/AI_Secretary_System.git

# 3. Запушьте (введите username и токен как пароль)
git push -u origin main
# Username: ShaerWare
# Password: ваш_токен_здесь
```

### Вариант 3: GitHub CLI (Самый простой)

```bash
# 1. Установите gh
sudo apt install gh

# 2. Авторизуйтесь
gh auth login
# Выберите: GitHub.com → HTTPS → Login with a web browser

# 3. Запушьте
git push -u origin main
```

## После успешного пуша

Проверьте репозиторий:
```bash
# Откройте в браузере
https://github.com/ShaerWare/AI_Secretary_System
```

## Что будет в репозитории

Загружены только нужные файлы:

📚 **Документация:**
- 00_START_HERE.txt
- README.md
- QUICKSTART.md
- ARCHITECTURE.md
- examples.md
- CHEATSHEET.md
- PROJECT_SUMMARY.md

🔧 **Код:**
- orchestrator.py
- phone_service.py
- voice_clone_service.py
- stt_service.py
- llm_service.py

⚙️ **Конфигурация:**
- .env.example (БЕЗ ключей!)
- requirements.txt
- docker-compose.yml
- Dockerfiles

🚀 **Скрипты:**
- setup.sh
- run.sh
- test_system.sh

## Что НЕ загружено (и правильно!)

❌ `.env` - файл с API ключами
❌ `Лидия/` - образцы голоса (личные данные)
❌ `models/` - большие модели AI
❌ `venv/` - виртуальное окружение
❌ `calls_log/` - логи звонков
❌ `*.wav`, `*.mp3` - аудио файлы

## Troubleshooting

### Permission denied (publickey)
→ Используйте Вариант 1 или 2

### fatal: Authentication failed
→ Проверьте токен или SSH ключ

### ! [rejected] main -> main (fetch first)
```bash
# Если в репозитории уже есть файлы:
git fetch origin
git merge origin/main --allow-unrelated-histories
git push -u origin main
```

### Или force push (ОСТОРОЖНО! Удалит старые файлы)
```bash
git push -u origin main --force
```

## Быстрый скрипт

Сохраните как `push_to_github.sh`:

```bash
#!/bin/bash
echo "Выберите метод аутентификации:"
echo "1) SSH (нужен настроенный ключ)"
echo "2) HTTPS + Token"
echo "3) GitHub CLI"
read -p "Ваш выбор (1-3): " choice

case $choice in
  1)
    git remote set-url origin git@github.com:ShaerWare/AI_Secretary_System.git
    git push -u origin main
    ;;
  2)
    git remote set-url origin https://github.com/ShaerWare/AI_Secretary_System.git
    echo "Введите username: ShaerWare"
    echo "Введите Personal Access Token как пароль"
    git push -u origin main
    ;;
  3)
    gh auth status || gh auth login
    git push -u origin main
    ;;
  *)
    echo "Неверный выбор"
    exit 1
    ;;
esac

echo "✅ Готово! Проверьте: https://github.com/ShaerWare/AI_Secretary_System"
```

Запустите:
```bash
chmod +x push_to_github.sh
./push_to_github.sh
```

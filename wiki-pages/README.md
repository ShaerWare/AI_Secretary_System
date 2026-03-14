# Wiki Pages - Инструкция по загрузке

Эта папка содержит подготовленные страницы для GitHub Wiki.

## Структура файлов (37 страниц)

```
wiki-pages/
├── Home.md                  # Главная страница
├── _Sidebar.md              # Боковое меню
│
│ # Вкладки админ-панели (20)
├── Dashboard.md             # Главная панель
├── Chat.md                  # Ассистенты
├── Services.md              # Управление сервисами
├── LLM.md                   # Настройки LLM
├── TTS.md                   # Синтез речи
├── FAQ.md                   # Быстрые ответы
├── Finetune.md              # Дообучение
├── Monitoring.md            # Мониторинг системы
├── Models.md                # Управление моделями
├── Widget.md                # Веб-виджеты
├── Telegram.md              # Telegram боты
├── WhatsApp.md              # WhatsApp боты
├── GSM.md                   # GSM телефония
├── Sales.md                 # Воронка продаж
├── CRM.md                   # amoCRM интеграция
├── Usage.md                 # Статистика использования
├── Audit.md                 # Аудит действий
├── Settings.md              # Настройки
│
│ # Интеграции и справка
├── Cloud-LLM-Providers.md   # Облачные LLM провайдеры
├── VLESS-Proxy.md           # VLESS прокси для Gemini
├── Payments.md              # Платежи (Stars, YooKassa)
├── Personas.md              # Персоны секретаря
├── Prompts.md               # Системные промпты
├── Wiki-RAG.md              # База знаний и RAG
├── Backup.md                # Резервное копирование
├── Deployment-Profiles.md   # Профили развёртывания
├── Cloud-AI-Training.md     # Wiki RAG обучение
├── API-Reference.md         # Справочник API
├── Installation.md          # Установка
├── Troubleshooting.md       # Решение проблем
│
├── images/                  # Скриншоты
└── README.md                # Эта инструкция
```

## Как загрузить в GitHub Wiki

### Способ 1: Через веб-интерфейс

1. Перейдите на https://github.com/ShaerWare/AI_Secretary_System/wiki
2. Нажмите "Create the first page"
3. Вставьте содержимое `Home.md`
4. Сохраните
5. Для каждой следующей страницы:
   - Нажмите "New Page"
   - Введите название (без .md)
   - Вставьте содержимое
   - Сохраните

### Способ 2: Через Git (рекомендуется)

После создания первой страницы через веб:

```bash
# Клонировать wiki репозиторий
git clone https://github.com/ShaerWare/AI_Secretary_System.wiki.git
cd AI_Secretary_System.wiki

# Скопировать все файлы
cp ../AI_Secretary_System/wiki-pages/*.md .

# Создать папку для изображений
mkdir -p images

# Закоммитить и запушить
git add .
git commit -m "Add wiki documentation"
git push
```

## Добавление скриншотов

1. Сделайте скриншоты каждой вкладки админки
2. Сохраните их в папку `images/` с именами:
   - `dashboard.png`, `chat.png`, `services.png`
   - `llm.png`, `tts.png`, `faq.png`, `finetune.png`
   - `monitoring.png`, `models.png`
   - `widget.png`, `telegram.png`, `whatsapp.png`
   - `gsm.png`, `sales.png`, `crm.png`
   - `usage.png`, `audit.png`, `settings.png`

3. Загрузите в wiki репозиторий:
```bash
cd AI_Secretary_System.wiki
git add images/
git commit -m "Add screenshots"
git push
```

## Placeholder'ы для скриншотов

В каждом файле есть строка вида:
```markdown
<!-- Вставьте скриншот страницы Dashboard -->
![Dashboard](images/dashboard.png)
```

После загрузки скриншотов они автоматически отобразятся.

## Рекомендации по скриншотам

- Разрешение: 1280x800 или выше
- Формат: PNG
- Показывайте всю страницу, включая sidebar
- Используйте тему Light для лучшей читаемости
- Скройте личные данные (API ключи, токены)

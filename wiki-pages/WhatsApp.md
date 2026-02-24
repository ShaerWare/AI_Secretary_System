# WhatsApp (Боты)

Управление мультиинстансными WhatsApp ботами через WhatsApp Cloud API с независимыми настройками AI, TTS и воронкой продаж.

## Скриншот

<!-- Вставьте скриншот страницы WhatsApp -->
![WhatsApp](images/whatsapp.png)

## Концепция

Система поддерживает **несколько WhatsApp ботов одновременно**. Каждый бот:
- Запускается как **отдельный субпроцесс** Python (аналогично Telegram ботам)
- Использует **WhatsApp Cloud API** (Meta Business Platform)
- Имеет независимый LLM бэкенд, персону и системный промпт
- Может иметь свою воронку продаж (квиз, сегменты, агентские промпты)
- Поддерживает интерактивные сообщения (quick reply, list messages)
- Управляется (start/stop/restart) из админ-панели

## Предварительная настройка

### Шаг 1: Создание приложения в Meta

1. Зарегистрируйтесь на [Meta for Developers](https://developers.facebook.com/)
2. Создайте Business App → добавьте продукт **WhatsApp**
3. Получите **Phone Number ID** и **WhatsApp Business Account ID (WABA ID)**
4. Сгенерируйте **Permanent Access Token** (System User → Generate Token)
5. Задайте **Verify Token** (произвольная строка для верификации webhook)
6. Скопируйте **App Secret** из настроек приложения

### Шаг 2: Настройка Webhook

WhatsApp требует публичный HTTPS URL для вебхука:

1. Используйте ngrok или Cloudflare Tunnel:
   ```bash
   ngrok http 8003  # порт webhook бота
   ```
2. В Meta Developer Portal → WhatsApp → Configuration:
   - Callback URL: `https://your-tunnel.ngrok.io/webhook`
   - Verify Token: тот же, что в настройках бота
   - Подписка на: `messages`

## Список ботов

Левая панель отображает все инстансы:

| Элемент | Описание |
|---------|----------|
| **Индикатор** | Зелёный = запущен, серый = остановлен |
| **Название** | Имя бота |
| **Enabled** | Включён ли бот |
| **Действия** | Start / Stop / Restart / Delete |

## Создание бота

1. Нажмите **"Добавить бота"** в админ-панели
2. Введите название
3. Заполните данные WhatsApp Cloud API (см. выше)
4. Настройте AI параметры
5. Нажмите **"Сохранить"**

Из названия автоматически генерируется slug-ID (например, `"Support Bot"` → `support-bot`).

## Настройки бота

Конфигурация организована по вкладкам:

### Основные (Settings)

| Параметр | Описание |
|----------|----------|
| **Название** | Отображаемое имя инстанса |
| **Phone Number ID** | ID номера телефона из Meta Business |
| **WABA ID** | WhatsApp Business Account ID |
| **Access Token** | Постоянный токен доступа (маскируется) |
| **Verify Token** | Токен верификации вебхука |
| **App Secret** | Секрет приложения для проверки подписи вебхука |
| **Webhook Port** | Порт для приёма вебхуков (по умолчанию: 8003) |
| **Enabled** | Включить/отключить бот |

### AI настройки

| Параметр | Описание |
|----------|----------|
| **LLM Backend** | `vllm`, `gemini` или `cloud:{provider_id}` |
| **System Prompt** | Кастомный системный промпт |
| **LLM Params** | JSON с параметрами: `temperature`, `max_tokens`, `top_p` |

### TTS настройки

| Параметр | Описание |
|----------|----------|
| **TTS Enabled** | Включить голосовые ответы |
| **Engine** | `xtts`, `piper` или `openvoice` |
| **Voice** | ID голоса (`anna`, `marina`) |
| **Preset** | Опциональный пресет TTS |

При включённом TTS бот отправляет аудио-сообщения вместе с текстовыми ответами.

### Контроль доступа (Access)

| Параметр | Описание |
|----------|----------|
| **Allowed Phones** | Список разрешённых номеров телефонов (пустой = все допущены) |
| **Blocked Phones** | Список заблокированных номеров |

### Rate Limiting

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| **Rate Limit Count** | Максимум сообщений за период | 5 |
| **Rate Limit Hours** | Период в часах | 5 |

## Воронка продаж

WhatsApp бот поддерживает полную воронку продаж, аналогичную Telegram:

### Интерактивные сообщения

WhatsApp использует два типа интерактивных элементов:

| Тип | Ограничения | Использование |
|-----|-------------|---------------|
| **Quick Reply** | ≤3 кнопки, заголовок ≤20 символов | Простые ответы да/нет, навигация |
| **List Message** | ≤10 секций, ≤10 строк | Квиз-вопросы, каталоги, FAQ-разделы |

### Квиз и сегментация

- Вопросы квиза отображаются как **list messages**
- Сегментация (DIY/Basic/Custom) импортируется из модуля Telegram (`telegram_bot.sales.segments`)
- Логика `determine_segment()`, `GPU_AUDIT`, `calculate_quote()` — общая, без дублирования

### Пути сегментов

| Сегмент | Описание |
|---------|----------|
| **DIY** | GPU-аудит, ссылка на GitHub |
| **Basic** | Презентация ценности, демо, оформление заказа |
| **Custom** | 5-шаговый discovery, расчёт стоимости, альтернативы |

### Платежи

WhatsApp не поддерживает встроенные платежи (как Telegram Stars), поэтому:
- YooMoney: ссылка на оплату в тексте сообщения
- Контактная информация для связи с менеджером

### FAQ

FAQ-разделы идентичны Telegram:
- **Продукт** (5 вопросов): `what_is`, `offline`, `security`, `vs_cloud`, `cloud_models`
- **Установка** (3 вопроса): `hardware`, `install`, `integrations`
- **Цены и поддержка** (3 вопроса): `price`, `support`, `free_trial`

Навигация: `faq:cat_*` → раздел, `faq:{key}` → ответ, `faq:back_*` → назад к разделу.

### Особенности WhatsApp

| Ограничение | Решение |
|-------------|---------|
| Нет URL-кнопок | Ссылки в тексте сообщения |
| Нет редактирования сообщений | Новое сообщение на каждое взаимодействие |
| List = single-select | Последовательный выбор с кнопками "Ещё"/"Готово" |
| `*bold*` вместо `**bold**` | Адаптированные шаблоны текстов |

## Управление ботом

### Запуск / Остановка

| Кнопка | Действие | Эффект на auto_start |
|--------|----------|---------------------|
| **Start** | Запустить субпроцесс | `auto_start = true` |
| **Stop** | Остановить (SIGTERM → 5с → SIGKILL) | `auto_start = false` |
| **Restart** | Stop + Start | Без изменений |

### Auto-Start

Боты с `auto_start = true` **автоматически запускаются** при старте оркестратора. Флаг устанавливается при первом запуске и снимается при остановке.

### Логи

- Просмотр последних 100 строк лога бота
- Лог-файл: `logs/whatsapp_bot_{instance_id}.log`

## Архитектура субпроцесса

```
POST /admin/whatsapp/instances/{id}/start
  → WhatsAppManager.start_bot(id)
    → Спавнит: python -m whatsapp_bot
    → ENV: WA_INSTANCE_ID={id}, WA_INTERNAL_TOKEN={jwt}
    → Логи: logs/whatsapp_bot_{id}.log
```

Внутри субпроцесса:
1. Бот загружает конфиг через API оркестратора (используя `WA_INTERNAL_TOKEN`)
2. Запускает webhook-сервер на указанном порту
3. Принимает входящие сообщения от WhatsApp Cloud API
4. Маршрутизирует: приветствия → воронка, FAQ → ответы, остальное → LLM

### Обработка сообщений

```
Incoming webhook → Signature verification (X-Hub-Signature-256)
  → Text message:
    1. Проверка приветствия (9 триггерных слов) → Welcome buttons
    2. Проверка funnel_state (свободный ввод: custom_step_1, diy_gpu_custom)
    3. Fallback → LLM через orchestrator API
  → Interactive reply:
    → Routing по prefix:action формату:
      sales:* → handlers/sales/router.py
      faq:*   → FAQ навигация
      tz:*    → TZ генератор
      nav:*   → Общая навигация
```

### База данных воронки

Каждый WhatsApp бот хранит данные воронки в отдельной SQLite БД:
- Файл: `data/wa_sales_{instance_id}.db`
- Таблицы: `users`, `events`, `custom_discovery`
- Ключ пользователя: номер телефона (TEXT)
- Колонка `funnel_state` для отслеживания состояния свободного ввода

## API эндпоинты

### Управление инстансами

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/admin/whatsapp/instances` | Список всех инстансов |
| POST | `/admin/whatsapp/instances` | Создать инстанс |
| GET | `/admin/whatsapp/instances/{id}` | Конфиг инстанса |
| PUT | `/admin/whatsapp/instances/{id}` | Обновить инстанс |
| DELETE | `/admin/whatsapp/instances/{id}` | Удалить инстанс |
| POST | `/admin/whatsapp/instances/{id}/start` | Запустить бота |
| POST | `/admin/whatsapp/instances/{id}/stop` | Остановить бота |
| POST | `/admin/whatsapp/instances/{id}/restart` | Перезапустить бота |
| GET | `/admin/whatsapp/instances/{id}/status` | Статус бота |
| GET | `/admin/whatsapp/instances/{id}/logs` | Последние N строк лога |

### Webhook (публичный)

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/webhook` (на порту webhook_port) | Верификация вебхука (challenge) |
| POST | `/webhook` (на порту webhook_port) | Приём входящих сообщений |

## RBAC

- **Admin** — видит и управляет всеми ботами в workspace
- **User/Web** — только свои боты (`owner_id`)
- **Guest** — только чтение

Все CRUD-эндпоинты и action-эндпоинты (start/stop/restart/status/logs) фильтруются по `workspace_id` из JWT. Системные методы (`get_auto_start_instances`, `get_instance_with_token`) не фильтруются — работают без JWT-контекста.

## Миграция

```bash
python scripts/migrate_whatsapp.py
```

Создаёт таблицу `whatsapp_instances` со всеми полями конфигурации.

---

← [[Telegram]] | [[GSM]] →

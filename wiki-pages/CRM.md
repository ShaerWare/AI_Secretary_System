# CRM (amoCRM)

Интеграция с amoCRM v4 API: OAuth2 аутентификация, синхронизация контактов, лидов и задач, автоматическое создание сделок.

## Скриншот

<!-- Вставьте скриншот страницы CRM -->
![CRM](images/crm.png)

## Концепция

Интеграция с **amoCRM v4 API** через OAuth2 с автоматическим обновлением токенов. Система позволяет:

- **Двусторонняя синхронизация**: импорт контактов и лидов из amoCRM → экспорт данных из бота в CRM
- **Автоматическое создание сделок**: при обращении в Telegram бот или виджет
- **Webhook-интеграция**: получение событий от amoCRM (обновление контактов, сделок, задач)
- **Управление воронками**: выбор pipeline и статуса для новых лидов
- **Docker/VPN proxy**: поддержка прокси для работы из контейнера

## Страница CRM

Управление интеграцией через `CrmView.vue` с 4 вкладками: **Settings** (настройки), **Kanban** (доска сделок), **Deals** (таблица сделок), **Inbox** (сообщения).

---

### Вкладка: Kanban (Доска сделок)

Визуальная доска сделок в стиле Trello/Kanban (`CrmKanban.vue`):

| Функция | Описание |
|---------|----------|
| **Выбор воронки** | Выпадающий список всех pipelines из amoCRM |
| **Колонки по статусам** | Горизонтальные колонки — каждая соответствует статусу воронки |
| **Drag & Drop** | Перетаскивание сделок между статусами через `vuedraggable@next` (SortableJS) |
| **Изменяемая ширина колонок** | Перетаскивание разделителя между колонками, ширина сохраняется в localStorage |
| **Сброс ширины** | Кнопка ↺ сбрасывает все колонки до ширины по умолчанию (288px) |
| **Горизонтальная прокрутка** | Drag-to-scroll по горизонтали |
| **Авто-обновление** | Каждые 30 секунд |
| **Карточка сделки** | Название, сумма, ответственный, контакт |

### Вкладка: Deals (Таблица сделок)

Табличный вид всех сделок (`CrmDeals.vue`):

| Функция | Описание |
|---------|----------|
| **Поиск** | Фильтрация сделок по названию |
| **Пагинация** | Навигация по страницам |
| **Детали сделки** | Модальное окно: контакты, примечания, теги |
| **Создание сделки** | Диалог с полями: название, сумма, воронка, статус, контакт |

### Вкладка: Inbox (Сообщения)

Мессенджер-интерфейс для переписки с контактами через Amojo API (`CrmInbox.vue`):

| Функция | Описание |
|---------|----------|
| **Список контактов** | Поиск контактов из amoCRM |
| **Разрешение чата** | Выбор контакта → автоматический запрос `getContactChats()` → получение UUID чата |
| **История сообщений** | Загрузка переписки из Amojo API |
| **Отправка сообщений** | Ввод текста → `POST /admin/crm/chats/{chat_id}/messages` |
| **Авто-обновление** | Каждые 10 секунд |

> **Требования**: для Inbox необходимо настроить Amojo credentials (Amojo Scope ID, Channel Secret) во вкладке Settings.

---

### Вкладка: Settings (Настройки)

#### Connection Status (Статус подключения)

| Индикатор | Описание |
|-----------|----------|
| 🟢 Подключено | OAuth2 токены активны, аккаунт доступен |
| 🔴 Не подключено | Нет токенов или истекли |
| 🟡 Ошибка | Ошибка при последнем запросе |

### Settings Form (Настройки)

| Поле | Описание |
|------|----------|
| **Subdomain** | Поддомен amoCRM (например, `mycompany` для `mycompany.amocrm.ru`) |
| **Client ID** | OAuth2 Client ID из настроек интеграции |
| **Client Secret** | OAuth2 Client Secret |
| **Redirect URI** | URI для OAuth callback (автозаполняется: `https://yourdomain.com/admin/crm/callback`) |
| **Sync Contacts** | Включить синхронизацию контактов |
| **Sync Leads** | Включить синхронизацию лидов |
| **Sync Tasks** | Включить синхронизацию задач |
| **Auto Create Lead** | Автоматически создавать лид при первом обращении |
| **Lead Pipeline ID** | ID воронки для новых лидов |
| **Lead Status ID** | ID статуса для новых лидов |

### OAuth2 Flow

#### Шаг 1: Настройка интеграции в amoCRM

1. Зайдите в **Настройки → Интеграции → Создать интеграцию**
2. Выберите тип **Private app** (для приватного доступа) или **OAuth2** (для публичной интеграции)
3. Скопируйте **Client ID** и **Client Secret**
4. Укажите **Redirect URI**: `https://yourdomain.com/admin/crm/callback`
5. Выберите права доступа (scope): `crm` (контакты, сделки, задачи)

#### Шаг 2: Подключение в админ-панели

1. Вставьте **Subdomain**, **Client ID** и **Client Secret** в форму
2. Нажмите **"Получить URL авторизации"** → появится кнопка **"Подключить amoCRM"**
3. Кликните на кнопку → откроется popup с OAuth-страницей amoCRM
4. Подтвердите доступ в amoCRM
5. После редиректа система получит токены и отобразит статус **"Подключено"**

#### Приватные интеграции (без OAuth redirect)

Для приватных интеграций amoCRM код авторизации (`authorization_code`) получается из настроек интеграции:

1. Создайте приватную интеграцию в amoCRM
2. Скопируйте код авторизации из раздела **"Получить код"**
3. Используйте этот код вместо OAuth2 flow
4. Система автоматически обменяет код на токены

### Account Info (Информация об аккаунте)

После подключения отображается:

| Поле | Описание |
|------|----------|
| **Account Name** | Название аккаунта |
| **Subdomain** | Поддомен |
| **User Name** | Имя пользователя |
| **User Email** | Email пользователя |

### Sync Controls (Управление синхронизацией)

| Кнопка | Действие |
|--------|----------|
| **Синхронизировать** | Запустить синхронизацию контактов/лидов |
| **Отключить** | Отозвать токены OAuth2 |

### Sync Log (Лог синхронизации)

История операций синхронизации:

| Поле | Описание |
|------|----------|
| **Timestamp** | Дата и время |
| **Operation** | Тип операции (`sync_contacts`, `sync_leads`, `create_lead`) |
| **Status** | Статус (`success`, `error`) |
| **Details** | Детали (количество синхронизированных записей, ошибки) |

## Статистика

| Метрика | Описание |
|---------|----------|
| **Contacts Count** | Количество контактов в amoCRM |
| **Leads Count** | Количество сделок |
| **Last Sync Time** | Время последней успешной синхронизации |

## Docker/VPN Proxy

Если Docker-контейнер не может напрямую достучаться до amoCRM (например, VPN настроен на хосте), используйте прокси:

### Шаг 1: Запустить прокси на хосте

```bash
python scripts/amocrm_proxy.py
```

Прокси запустится на порту `8888` и пробросит запросы к amoCRM.

### Шаг 2: Указать прокси в Docker

Добавьте в `.env`:

```bash
AMOCRM_PROXY=http://172.17.0.1:8888
```

Где `172.17.0.1` — IP хост-машины из Docker-сети.

## Webhook

Endpoint для получения событий от amoCRM: **`POST /webhooks/amocrm`**

### Настройка вебхука в amoCRM

1. Перейдите в **Настройки → Интеграции → Вебхуки**
2. Укажите URL: `https://yourdomain.com/webhooks/amocrm`
3. Выберите события: `add`, `update`, `delete` для контактов, сделок, задач
4. Сохраните

### Обрабатываемые события

| Событие | Описание |
|---------|----------|
| `contacts:add` | Создан контакт |
| `contacts:update` | Обновлён контакт |
| `leads:add` | Создана сделка |
| `leads:update` | Обновлена сделка |
| `leads:status` | Изменён статус сделки |
| `tasks:add` | Создана задача |
| `tasks:update` | Обновлена задача |

## Автоматическое создание лидов

Если включено **Auto Create Lead**, при первом обращении пользователя из Telegram бота или виджета:

1. Система проверяет, существует ли контакт с этим Telegram User ID
2. Если нет — создаёт контакт
3. Создаёт сделку (лид) в указанной воронке (`Lead Pipeline ID`) и статусе (`Lead Status ID`)
4. Связывает сделку с контактом

## API эндпоинты

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/admin/crm/config` | Получить конфигурацию CRM |
| PUT | `/admin/crm/config` | Обновить конфигурацию |
| GET | `/admin/crm/auth-url` | Получить URL для OAuth2 авторизации |
| GET | `/admin/crm/callback` | OAuth2 callback (обмен кода на токены) |
| GET | `/admin/crm/status` | Статус подключения (токены активны?) |
| POST | `/admin/crm/disconnect` | Отключить amoCRM (отозвать токены) |
| GET | `/admin/crm/contacts` | Список контактов из amoCRM |
| GET | `/admin/crm/leads` | Список сделок из amoCRM |
| GET | `/admin/crm/pipelines` | Список воронок и статусов |
| POST | `/admin/crm/sync` | Запустить синхронизацию |
| GET | `/admin/crm/sync/log` | Получить лог синхронизации |
| GET | `/admin/crm/account` | Информация об аккаунте |
| GET | `/admin/crm/leads/{id}` | Детали сделки |
| PATCH | `/admin/crm/leads/{id}` | Обновить сделку (статус, pipeline) |
| GET | `/admin/crm/leads/by-pipeline/{pipeline_id}` | Сделки по воронке (для Kanban) |
| GET | `/admin/crm/events` | Лента событий |
| GET | `/admin/crm/contacts/{id}/chats` | Чаты контакта (Amojo) |
| GET | `/admin/crm/chats/{chat_id}/history` | История сообщений чата (Amojo) |
| POST | `/admin/crm/chats/{chat_id}/messages` | Отправить сообщение в чат (Amojo) |

### Пример запроса: Получить контакты

```http
GET /admin/crm/contacts?limit=50&offset=0
Authorization: Bearer <jwt_token>
```

### Пример ответа: Список контактов

```json
{
  "_embedded": {
    "contacts": [
      {
        "id": 12345,
        "name": "Иван Иванов",
        "custom_fields_values": [
          {
            "field_code": "PHONE",
            "values": [{"value": "+79001234567"}]
          },
          {
            "field_code": "EMAIL",
            "values": [{"value": "ivan@example.com"}]
          }
        ]
      }
    ]
  }
}
```

## Error Handling (Обработка ошибок)

### AmoCRMAPIError

Общая ошибка API amoCRM:

```python
raise AmoCRMAPIError(f"API error: {response.status_code}")
```

### AmoCRMTokenExpired

Истёк токен доступа (401):

```python
raise AmoCRMTokenExpired("Access token expired")
```

Система **автоматически** обновляет токен при получении 401 и повторяет запрос.

### Rate Limiting (429)

При превышении лимита запросов (429 Too Many Requests):

- Максимум повторов: **3** (`MAX_429_RETRIES`)
- Задержка между повторами: **1.5 секунды** (`RETRY_DELAY_SECONDS`)
- Система использует экспоненциальный backoff

```python
if response.status_code == 429 and retry_count < MAX_429_RETRIES:
    await asyncio.sleep(RETRY_DELAY_SECONDS * (retry_count + 1))
    return await self._request(...)
```

## Архитектура сервиса

```
app/routers/amocrm.py
  → app/services/amocrm_service.py (AmoCRMService)
    → AsyncAmoCRMManager (db/integration.py)
      → AmoCRMRepository (db/repositories/amocrm.py)
        → AmoCRMConfig, AmoCRMToken (db/models.py)
```

### AmoCRMService

Чистый async HTTP-клиент **без прямого DB-доступа**. Методы:

- `get_contacts(limit, offset)` — список контактов
- `get_leads(limit, offset)` — список сделок
- `create_lead(name, price, pipeline_id, status_id, contact_id)` — создать сделку
- `get_pipelines()` — список воронок и статусов
- `refresh_tokens()` — обновить токены при 401
- `exchange_code(code)` — обмен `authorization_code` на токены

### AsyncAmoCRMManager

Менеджер в `db/integration.py` для работы с конфигурацией и токенами в БД:

- `get_config()` — получить конфигурацию
- `save_config(config)` — сохранить конфигурацию
- `get_tokens()` — получить токены
- `save_tokens(tokens)` — сохранить токены
- `delete_tokens()` — удалить токены (отключение)

### Proxy Support

Если установлена переменная окружения **`AMOCRM_PROXY`**, все запросы проксируются:

```python
proxies = {"http://": os.getenv("AMOCRM_PROXY"), "https://": os.getenv("AMOCRM_PROXY")}
async with httpx.AsyncClient(proxies=proxies) as client:
    response = await client.get(url)
```

## RBAC

- **Admin** — полный доступ к CRM-интеграции
- **User** — только своя конфигурация (по `owner_id`)
- **Guest** — только чтение

---

← [[Sales]] | [[Usage]] →

# Settings (Настройки)

Профиль пользователя, безопасность, тема, язык и управление данными.

**Доступ:** все роли | **Путь:** `/settings`

## Профиль

### Информация

| Поле | Описание | Редактируемо |
|------|----------|-------------|
| **ID** | Числовой идентификатор | Нет |
| **Имя пользователя** | Логин | Нет |
| **Отображаемое имя** | Display name | Да |
| **Роль** | admin / user / web / guest (RBAC) | Нет (только через CLI) |
| **Дата создания** | Когда создан аккаунт | Нет |
| **Последний вход** | Время последнего логина | Нет |

### Обновление профиля

**API:** `PUT /admin/auth/profile` с телом `{"display_name": "Новое имя"}`

Гости (`guest`) не могут менять профиль.

### Смена пароля

1. Введите текущий пароль
2. Введите новый пароль (мин. 4 символа)
3. Подтвердите новый пароль
4. Нажмите "Изменить пароль"

**API:** `POST /admin/auth/change-password` с `{"old_password": "...", "new_password": "..."}`

Гости (`guest`) не могут менять пароль.

## Интерфейс

### Язык

| Язык | Код | Покрытие |
|------|-----|----------|
| Русский | `ru` | 100% |
| English | `en` | 100% |

Переключение мгновенное через vue-i18n, без перезагрузки. Сохраняется в localStorage.

### Тема

| Тема | Описание |
|------|----------|
| **Light** | Светлая тема — белый фон, тёмный текст |
| **Dark** | Тёмная тема — тёмный фон, светлый текст |
| **Night Eyes** | Тёплая тёмная — пониженная яркость, тёплые тона для длительной работы |

Тема сохраняется в Pinia store + localStorage (persistedstate). CSS-переменные определены в `admin/src/assets/main.css`.

## Резервное копирование

Подробная документация: [[Backup]]

### Быстрый экспорт

Кнопки для скачивания конфигурации:

| Тип | Что включено |
|-----|-------------|
| **FAQ** | Только FAQ записи |
| **TTS пресеты** | Только TTS пресеты |
| **Полный** | FAQ, TTS, персоны, боты, виджеты, cloud providers, sales config |

### Быстрый импорт

1. Нажмите "Импорт"
2. Выберите JSON файл (из предыдущего экспорта)
3. Подтвердите

Импорт использует стратегию merge (не перезаписывает всё), чувствительные данные (API ключи) маскируются при экспорте.

## Режимы развёртывания (Deployment Modes)

Система поддерживает три режима, определяемых переменной окружения `DEPLOYMENT_MODE`:

| Режим | Описание |
|-------|----------|
| **full** (по умолчанию) | Все сервисы: локальный LLM (vLLM), TTS (XTTS/Piper), STT, GSM. Требует GPU |
| **cloud** | Только облачные LLM. GPU/TTS/STT/GSM сервисы не загружаются, hardware-роутеры не регистрируются |
| **local** | Идентичен `full`, для явного указания в конфигурации |

### Бэкенд

В режиме `cloud`:
- Роутеры `services`, `monitor`, `gsm`, `stt`, `tts` **не регистрируются**
- TTS/STT/GPU инициализация **пропускается**
- Эндпоинт `/health` включает `deployment_mode` в ответ и не требует TTS для healthy-статуса
- `GET /admin/deployment-mode` возвращает текущий режим
- `/auth/me` включает `deployment_mode` в ответ

### Фронтенд

- Store `auth.ts` запрашивает `GET /admin/deployment-mode` и предоставляет `isCloudMode` computed
- Маршруты и навигация с `meta.localOnly: true` **скрываются** в облачном режиме:
  - Dashboard, Services, TTS, Monitoring, Models, GSM
- Облачные пользователи перенаправляются на `/chat`

### Переменная окружения

```bash
DEPLOYMENT_MODE=full    # full | cloud | local
```

## О программе (About)

Доступна через навигацию:

| Параметр | Описание |
|----------|----------|
| **Версия** | Текущая версия из CHANGELOG |
| **Health** | Результат `/health` (статус, deployment_mode, сервисы) |
| **Deployment Mode** | full / cloud / local |
| **Ссылки** | GitHub репозиторий, Wiki, Issues |

## Управление пользователями (CLI)

Администратор может управлять пользователями через CLI:

```bash
python scripts/manage_users.py list                          # Список
python scripts/manage_users.py create <user> <pass> --role user  # Создать
python scripts/manage_users.py set-password <user> <pass>    # Сменить пароль
python scripts/manage_users.py set-role <user> <role>        # Сменить роль
python scripts/manage_users.py disable <user>                # Деактивировать
python scripts/manage_users.py enable <user>                 # Активировать
python scripts/manage_users.py delete <user>                 # Удалить
```

### Роли и RBAC

Legacy роли при создании пользователя автоматически маппятся на RBAC-роли через `workspace_members`:

| Legacy роль | RBAC роль | Доступ |
|-------------|-----------|--------|
| `admin` | **admin** | Все 16 модулей — `manage` |
| `user` | **operator** | 8 модулей `edit` + 3 `view` |
| `web` | **operator** | Аналогично `user` |
| `guest` | **viewer** | 7 модулей `view` (только чтение) |

Уровни доступа: `view` (чтение) → `edit` (изменение) → `manage` (полный доступ).

Подробнее о RBAC: [[API-Reference]].

## API

| Endpoint | Описание |
|----------|----------|
| `POST /admin/auth/login` | Аутентификация, получение JWT |
| `GET /admin/auth/me` | Текущий пользователь + deployment_mode |
| `GET /admin/auth/profile` | Полный профиль |
| `PUT /admin/auth/profile` | Обновить display_name |
| `POST /admin/auth/change-password` | Сменить пароль |
| `GET /admin/auth/status` | Конфигурация аутентификации |

---

← [[Audit]] | [[Home]] | [[Backup]] →

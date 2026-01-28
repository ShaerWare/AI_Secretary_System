# BACKLOG.md

Roadmap и план работ для AI Secretary System. Этот файл используется для отслеживания прогресса и планирования разработки.

**Последнее обновление:** 2026-01-28 (v8 — Consolidated Improvement Plan)
**Контекст:** Офлайн-first система + телефония через SIM7600G-H Waveshare

> **See also:** [Consolidated Improvement Plan](docs/IMPROVEMENT_PLAN.md) — detailed technical plan for production readiness with timeline, budget, and ROI calculations.

---

## Текущий статус проекта

- [x] Базовая архитектура (orchestrator, TTS, LLM)
- [x] Vue 3 админ-панель (13 табов)
- [x] JWT аутентификация
- [x] FAQ система
- [x] Fine-tuning pipeline
- [x] XTTS v2 + Piper TTS
- [x] vLLM + Gemini fallback + hot-switching
- [x] **Chat TTS playback** — озвучивание ответов ассистента в чате
- [x] **Локальный STT (Vosk)** — VoskSTTService + UnifiedSTTService + API endpoints
- [x] **Website Widget** — встраиваемый чат-виджет для сайтов
- [x] **Telegram Bot** — интеграция с Telegram (python-telegram-bot)
- [x] **Database Integration** — SQLite + Redis (транзакции, кэширование, миграция)
- [x] **Audit Log** — логирование действий с фильтрацией и экспортом (AuditView.vue)
- [x] **Voice Mode** — auto-play TTS при получении ответа ассистента
- [x] **Voice Input** — голосовой ввод через микрофон (STT в чате)
- [x] **Prompt Editor** — редактирование дефолтного промпта из настроек чата
- [x] **DeepSeek LLM** — третья модель для vLLM (--deepseek flag)
- [x] **LLM Models UI** — отображение доступных моделей с характеристиками
- [x] **Cloud LLM Providers** — универсальное подключение облачных LLM (Gemini, Kimi, OpenAI, Claude, DeepSeek, OpenRouter, custom)
- [x] **Telegram Action Buttons** — интерактивные кнопки с переключением LLM
- [ ] **Телефония SIM7600** — в планах
- [ ] **Монетизация** — в планах
- [x] **CI/CD Pipeline** — выполнено

---

## Фаза 0: Foundation (P0 — блокирующие задачи)

> **Детали:** [docs/IMPROVEMENT_PLAN.md](docs/IMPROVEMENT_PLAN.md#phase-0-foundation-before-everything-else)
>
> **Срок:** 2 недели | **Бюджет:** 120,000₽

### 0.1 CI/CD Pipeline [P0]
**Статус:** `done`
**Приоритет:** P0 (критичный)
**Сложность:** 4/10
**Влияние:** ★★★★★

**Описание:**
Автоматизация проверки кода при каждом PR. Без этого каждый PR — риск сломать production.

**Задачи:**
- [x] Создать `.github/workflows/ci.yml` с lint-backend, lint-frontend, security jobs
- [x] Добавить CI badge в README
- [x] Настроить branch protection (require CI pass) — GitHub Rulesets
- [x] Добавить Dependabot для Python и npm

---

### 0.2 Code Restructuring [P0]
**Статус:** `done`
**Приоритет:** P0 (критичный)
**Сложность:** 6/10
**Влияние:** ★★★★★
**Завершено:** 2026-01-28

**Описание:**
Разбить orchestrator.py (~170 endpoints) на модульную структуру `app/routers/`.

**Задачи:**
- [x] Создать `app/` структуру с routers, services, models
- [x] Вынести auth, llm, stt, faq, monitoring, services, audit endpoints (7 роутеров, ~60 endpoints)
- [x] Вынести tts, chat, telegram, widget endpoints (4 роутера, ~52 endpoints)
- [ ] Добавить `app/config.py` с Pydantic Settings (backlog)
- [ ] Обновить Dockerfile (backlog)
- [x] Сохранить backward compatibility (routers + legacy endpoints работают параллельно)

**Результат:**
```
orchestrator.py: 4641 → 3074 строк (-34% reduction)
11 routers, ~112 endpoints извлечено
```

**Созданные файлы:**
```
app/
├── __init__.py
├── dependencies.py       # ServiceContainer для DI
└── routers/
    ├── __init__.py
    ├── auth.py           # 3 endpoints
    ├── audit.py          # 4 endpoints
    ├── services.py       # 6 endpoints
    ├── monitor.py        # 7 endpoints
    ├── faq.py            # 7 endpoints
    ├── stt.py            # 4 endpoints
    ├── llm.py            # 24 endpoints
    ├── tts.py            # 13 endpoints
    ├── chat.py           # 10 endpoints
    ├── telegram.py       # 22 endpoints
    └── widget.py         # 7 endpoints
```

---

### 0.3 Basic Security [P0]
**Статус:** `planned`
**Приоритет:** P0 (критичный)
**Сложность:** 4/10
**Влияние:** ★★★★★

**Описание:**
Базовая безопасность для production: rate limiting, CORS whitelist, security headers.

**Задачи:**
- [ ] Переместить `.env.docker` → `.env.docker.example`
- [ ] Добавить `slowapi` для rate limiting
- [ ] Настроить CORS whitelist через env
- [ ] Security headers (X-Content-Type-Options, X-Frame-Options)

---

### 0.4 Release Management [P0]
**Статус:** `planned`
**Приоритет:** P0
**Сложность:** 2/10

**Задачи:**
- [ ] Создать `CHANGELOG.md`
- [ ] Создать GitHub Release v1.0.0
- [ ] Добавить `CONTRIBUTING.md`

---

## Фаза 0.5: Monetization (P1)

> **Детали:** [docs/IMPROVEMENT_PLAN.md](docs/IMPROVEMENT_PLAN.md#phase-1-monetization-mvp-for-revenue)
>
> **Срок:** 3 недели | **Бюджет:** 180,000₽

### 0.5.1 Stripe/YooKassa Integration [P1]
**Статус:** `planned`
**Приоритет:** P1 (высокий)
**Сложность:** 6/10
**Влияние:** ★★★★★

**Описание:**
Интеграция с платёжными системами для подписок.

**Задачи:**
- [ ] Зарегистрировать Stripe/YooKassa аккаунт
- [ ] Создать `app/routers/billing.py`
- [ ] Добавить таблицу `subscriptions` в БД
- [ ] Webhook endpoint с верификацией подписи
- [ ] UI: страница тарифов в админке

**Тарифы:**
| План | Цена | Минуты/мес | Голоса | Fine-tuning |
|------|------|------------|--------|-------------|
| Basic | 990₽ | 100 | 2 | Нет |
| Pro | 2,990₽ | 500 | 5 | 1/мес |
| Enterprise | 9,990₽ | ∞ | ∞ | ∞ |

---

### 0.5.2 Usage Limits [P1]
**Статус:** `planned`
**Приоритет:** P1
**Сложность:** 5/10

**Задачи:**
- [ ] Таблица `usage_logs` (user_id, type, amount, timestamp)
- [ ] Middleware для подсчёта минут TTS/STT
- [ ] API endpoint `/admin/usage/stats`
- [ ] UI: dashboard с usage графиками
- [ ] Email уведомления при 80% и 100% лимита

---

### 0.5.3 Legal Compliance [P1]
**Статус:** `planned`
**Приоритет:** P1 (критичный для РФ)
**Сложность:** 3/10

**Задачи:**
- [ ] Политика конфиденциальности
- [ ] Согласие на обработку голоса
- [ ] Согласие на запись звонков (IVR)
- [ ] Право на удаление данных (GDPR)
- [ ] Шифрование голосовых записей (AES-256)

---

## Фаза 1: Core Enterprise (4-6 недель)

### 1.1 Audit Log + Export
**Статус:** `done`
**Приоритет:** P0 (критичный)
**Сложность:** 2/10
**Влияние:** ★★★★★

**Описание:**
Полное логирование действий пользователей с возможностью экспорта в JSON/CSV.

**Задачи:**
- [x] Создать persistent storage (SQLite) — `db/repositories/audit.py`
- [x] Модель `AuditLog` в `db/models.py`
- [x] `AuditRepository` с методами: `log()`, `get_logs()`, `get_recent()`
- [x] `AsyncAuditLogger` wrapper в `db/integration.py`
- [x] API эндпоинты: `GET /admin/audit/logs`, `GET /admin/audit/export`
- [x] Фильтрация по дате, пользователю, типу события
- [x] Таб "Audit" в админке с таблицей и экспортом (AuditView.vue)
- [ ] Ротация логов (retention policy) — опционально

**Файлы:**
```
db/models.py                    # AuditLog модель
db/repositories/audit.py        # AuditRepository
db/integration.py               # AsyncAuditLogger
admin/src/views/AuditView.vue   # UI
admin/src/api/audit.ts          # API client
```

---

### 1.2 Telephony Gateway (SIM7600)
**Статус:** `planned`
**Приоритет:** P0 (ключевой дифференциатор)
**Сложность:** 6/10
**Оценка:** 2-2.5 недели
**Влияние:** ★★★★★

**Описание:**
Интеграция с GSM модулем SIM7600G-H для приёма/совершения звонков.

**Задачи:**
- [ ] Создать `telephony_service.py` с AT-командами
- [ ] Обработка входящих звонков (RING detection)
- [ ] Исходящие звонки (ATD команда)
- [ ] SMS отправка/приём
- [ ] Audio streaming через USB audio interface
- [ ] Call state machine (idle → ringing → active → hangup)
- [ ] Интеграция с orchestrator
- [ ] Таб "Telephony" в админке

**AT-команды:**
```
AT+CPIN?        # Проверка SIM
AT+CSQ          # Уровень сигнала
AT+COPS?        # Оператор
ATA             # Ответить на звонок
ATH             # Положить трубку
ATD+7xxx;       # Исходящий звонок
AT+CMGS         # Отправить SMS
```

**Файлы:**
```
telephony_service.py      # Новый сервис
admin/src/views/TelephonyView.vue
admin/src/api/telephony.ts
```

**Зависимости:**
- pyserial
- aioserial (async)

---

### 1.3 Local STT (Vosk)
**Статус:** `done`
**Приоритет:** P0 (требуется для телефонии)
**Сложность:** 5/10
**Оценка:** 1-1.5 недели
**Влияние:** ★★★★☆

**Описание:**
Замена faster-whisper на Vosk для realtime офлайн распознавания речи.

**Задачи:**
- [x] Создать `stt_service.py` с Vosk (VoskSTTService, UnifiedSTTService)
- [ ] Скачать модель `vosk-model-ru-0.42` (~1.5GB) или `vosk-model-small-ru-0.22` (~45MB)
- [x] Streaming распознавание для телефонии (`stream_recognize()`)
- [x] Batch распознавание для записей (`transcribe()`)
- [ ] WebSocket endpoint для realtime STT
- [x] API endpoints: `/admin/stt/status`, `/admin/stt/transcribe`, `/admin/stt/test`

**Модели:**
| Модель | Размер | Качество | Использование |
|--------|--------|----------|---------------|
| vosk-model-ru-0.42 | 1.5GB | Высокое | Основная |
| vosk-model-small-ru-0.22 | 45MB | Среднее | Fallback |
| vosk-model-en-us-0.22 | 1.8GB | Высокое | English |

**Файлы:**
```
stt_service.py            # Новый сервис
models/vosk/              # Директория для моделей
```

**Зависимости:**
- vosk
- sounddevice (для микрофона)

---

### 1.4 Database Integration (SQLite + Redis)
**Статус:** `done`
**Приоритет:** P0 (критичный для надёжности)
**Сложность:** 6/10
**Влияние:** ★★★★★

**Описание:**
Миграция всех JSON файлов в SQLite для надёжного хранения с транзакциями.

**Задачи:**
- [x] Создать `db/` пакет с SQLAlchemy async
- [x] Модели: ChatSession, ChatMessage, FAQEntry, TTSPreset, SystemConfig, TelegramSession, AuditLog
- [x] Репозитории с CRUD операциями
- [x] Redis кэширование (опционально, graceful fallback)
- [x] Миграция существующих JSON данных
- [x] Обновить orchestrator.py
- [x] Backward-compatible sync с JSON
- [x] Health endpoint с БД статусом

**Архитектура:**
```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│ Orchestrator│───▶│ Repositories │───▶│   SQLite    │
│   API       │    │   (async)    │    │ + Redis     │
└─────────────┘    └──────────────┘    └─────────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │ JSON Sync   │
                   │ (compat)    │
                   └─────────────┘
```

**Файлы:**
```
db/
├── __init__.py
├── database.py           # SQLite engine
├── models.py             # 7 ORM models
├── redis_client.py       # Caching
├── integration.py        # Backward-compat managers
└── repositories/
    ├── base.py
    ├── chat.py
    ├── faq.py
    ├── preset.py
    ├── config.py
    ├── telegram.py
    └── audit.py

scripts/
├── migrate_json_to_db.py
├── test_db.py
└── setup_db.sh

data/
└── secretary.db          # ~72KB
```

---

### 1.5 Backup & Restore
**Статус:** `planned` (упростился благодаря единой БД)
**Приоритет:** P1
**Сложность:** 3/10 (теперь проще — одна SQLite база)
**Оценка:** 0.5-1 неделя
**Влияние:** ★★★★☆

**Описание:**
Полный бэкап системы одним кликом: конфигурация, FAQ, голоса, LoRA адаптеры.

**Задачи:**
- [ ] API: `POST /admin/backup/create`, `POST /admin/backup/restore`
- [ ] Создание ZIP архива со структурой
- [ ] Валидация при восстановлении
- [ ] Список бэкапов с метаданными
- [ ] UI в Settings или отдельный таб

**Структура бэкапа (упрощённая):**
```
backup_2026-01-26_143000.zip
├── manifest.json           # Версия, дата, checksums
├── data/
│   └── secretary.db        # ВСЕ данные в одной базе
├── voices/
│   ├── Гуля/
│   └── Лидия/
└── adapters/               # LoRA (опционально)
    └── lydia/
```

**Примечание:** Благодаря миграции на SQLite все данные (чаты, FAQ, конфиги, аудит) теперь в одном файле `data/secretary.db`.

**Файлы:**
```
backup_service.py         # Новый сервис
backups/                  # Директория для бэкапов
```

---

## Фаза 2: Voice Pipeline (3-4 недели)

### 2.1 Audio Pipeline Integration
**Статус:** `planned`
**Приоритет:** P1
**Сложность:** 6/10
**Оценка:** 1.5-2 недели

**Описание:**
Связка STT → LLM → TTS для телефонных звонков в realtime.

**Задачи:**
- [ ] PCM audio capture от SIM7600
- [ ] Streaming STT с VAD (Voice Activity Detection)
- [ ] Низколатентная генерация ответа
- [ ] Streaming TTS playback
- [ ] Echo cancellation (опционально)
- [ ] Буферизация для плавного аудио

**Latency targets:**
| Этап | Цель | Допустимо |
|------|------|-----------|
| STT | <500ms | <1s |
| LLM | <2s | <3s |
| TTS | <500ms | <1s |
| **Total** | **<3s** | **<5s** |

---

### 2.2 Call Recording & Transcription
**Статус:** `planned`
**Приоритет:** P1
**Сложность:** 4/10
**Оценка:** 1 неделя

**Задачи:**
- [ ] Запись звонков в WAV/MP3
- [ ] Автоматическая транскрипция после завершения
- [ ] Хранение: audio + transcript + metadata
- [ ] Просмотр записей в админке
- [ ] Поиск по транскрипциям

**Файлы:**
```
recordings/
├── 2026-01-26/
│   ├── call_143000_+79001234567.wav
│   ├── call_143000_+79001234567.json  # Metadata + transcript
```

---

### 2.3 IVR Builder
**Статус:** `planned`
**Приоритет:** P2
**Сложность:** 7/10
**Оценка:** 2-3 недели

**Описание:**
Визуальный редактор голосового меню (Interactive Voice Response).

**Задачи:**
- [ ] JSON-схема для IVR flow
- [ ] Визуальный редактор (drag & drop)
- [ ] Условия: время, номер, ключевые слова
- [ ] Действия: озвучить, переключить, записать, повесить
- [ ] Preview и тестирование

**Пример IVR:**
```json
{
  "entry": "greeting",
  "nodes": {
    "greeting": {
      "type": "speak",
      "text": "Здравствуйте! Скажите, чем могу помочь?",
      "next": "listen"
    },
    "listen": {
      "type": "listen",
      "timeout": 5,
      "intents": {
        "schedule": "handle_schedule",
        "support": "handle_support",
        "default": "ai_response"
      }
    },
    "ai_response": {
      "type": "ai",
      "persona": "gulya",
      "next": "listen"
    }
  }
}
```

---

## Фаза 3: Enterprise Features (4-6 недель)

### 3.1 Extended RBAC
**Статус:** `planned`
**Приоритет:** P1
**Сложность:** 5/10
**Оценка:** 1.5-2 недели

**Описание:**
Расширенная система ролей и прав доступа.

**Роли:**
| Роль | Права |
|------|-------|
| admin | Полный доступ |
| operator | Чат, звонки, просмотр FAQ |
| editor | Редактирование FAQ, персон |
| viewer | Только просмотр дашборда |

**Задачи:**
- [ ] Расширить `auth_manager.py`
- [ ] Гранулярные права на ресурсы
- [ ] UI управления пользователями
- [ ] Приглашения по email (опционально)

---

### 3.2 Multi-Persona per Department
**Статус:** `planned`
**Приоритет:** P2
**Сложность:** 6/10
**Оценка:** 2-3 недели

**Описание:**
Разные персоны, голоса и FAQ для разных отделов.

**Структура:**
```
departments/
├── sales/
│   ├── persona.json      # Персона "Лидия"
│   ├── faq.json          # FAQ для продаж
│   └── voice_config.json # Голос продаж
├── support/
│   ├── persona.json      # Персона "Гуля"
│   ├── faq.json          # FAQ техподдержки
│   └── voice_config.json
└── reception/
    └── ...
```

**Маршрутизация:**
- По номеру телефона (разные SIM или DID)
- По времени (рабочее/нерабочее)
- По ключевым словам в начале разговора

---

### 3.3 Call & Conversation Analytics
**Статус:** `planned`
**Приоритет:** P1
**Сложность:** 6/10
**Оценка:** 2 недели

**Задачи:**
- [ ] Dashboard с метриками звонков
- [ ] Графики: звонки/день, средняя длительность
- [ ] Топ-10 вопросов
- [ ] % успешного распознавания STT
- [ ] Sentiment analysis (опционально)
- [ ] Экспорт отчётов

**Метрики:**
```python
class CallMetrics:
    total_calls: int
    answered_calls: int
    missed_calls: int
    avg_duration: float
    avg_wait_time: float
    stt_accuracy: float      # % успешных распознаваний
    faq_hit_rate: float      # % ответов из FAQ
    top_intents: List[str]
```

---

### 3.4 Multi-Instance Bots & Widgets
**Статус:** `completed` ✅
**Приоритет:** P1
**Сложность:** 7/10
**Завершено:** 2026-01-27
**Влияние:** ★★★★★

**Описание:**
Возможность создавать неограниченное количество Telegram ботов и чат-виджетов. Каждый инстанс имеет собственные настройки: выбор LLM модели, системный промпт, персона, голос TTS.

**Задачи:**
- [x] Новые таблицы: `bot_instances`, `widget_instances`
- [x] CRUD API для ботов: `/admin/telegram/instances`, `/admin/telegram/instances/{id}`
- [x] CRUD API для виджетов: `/admin/widget/instances`, `/admin/widget/instances/{id}`
- [x] Настройки каждого инстанса:
  - Выбор LLM backend (vLLM/Gemini)
  - Системный промпт (кастомный)
  - Выбор голоса TTS
  - Персона секретаря
- [x] Параллельный запуск нескольких Telegram ботов (multi_bot_manager.py)
- [x] Динамическая генерация `/widget.js?instance=xxx`
- [x] UI для управления инстансами (TelegramView.vue)
- [x] Изоляция сессий по bot_id (composite key)
- [x] API URL поле для туннеля (cloudflare/ngrok)
- [ ] Статистика по каждому боту/виджету (backlog)

**Структура данных:**
```python
class BotInstance(Base):
    __tablename__ = "bot_instances"

    id: str                    # UUID
    name: str                  # "Sales Bot", "Support Bot"
    platform: str              # "telegram", "widget"
    enabled: bool

    # Telegram-specific
    bot_token: str
    allowed_users: List[int]
    admin_users: List[int]

    # LLM Settings
    llm_backend: str           # "vllm", "gemini"
    llm_model: str             # "lydia", "Qwen/Qwen2.5-7B-Instruct-AWQ"
    system_prompt: str         # Custom system prompt
    persona: str               # "gulya", "lidia", "custom"
    temperature: float
    max_tokens: int

    # TTS Settings
    tts_voice: str             # "gulya", "lidia", "dmitri", "irina"
    tts_preset: str            # "neutral", "expressive", etc.

    # Messages
    welcome_message: str
    error_message: str

    created_at: datetime
    updated_at: datetime
```

**UI компоненты:**
```
admin/src/views/
├── TelegramBotsView.vue      # Список ботов + создание
├── TelegramBotEditView.vue   # Редактирование бота
├── WidgetInstancesView.vue   # Список виджетов + создание
└── WidgetInstanceEditView.vue # Редактирование виджета
```

**API endpoints:**
```bash
# Telegram Bots
GET    /admin/telegram/bots              # Список ботов
POST   /admin/telegram/bots              # Создать бота
GET    /admin/telegram/bots/{id}         # Получить бота
PUT    /admin/telegram/bots/{id}         # Обновить бота
DELETE /admin/telegram/bots/{id}         # Удалить бота
POST   /admin/telegram/bots/{id}/start   # Запустить бота
POST   /admin/telegram/bots/{id}/stop    # Остановить бота
GET    /admin/telegram/bots/{id}/stats   # Статистика бота

# Widget Instances
GET    /admin/widget/instances           # Список виджетов
POST   /admin/widget/instances           # Создать виджет
GET    /admin/widget/instances/{id}      # Получить виджет
PUT    /admin/widget/instances/{id}      # Обновить виджет
DELETE /admin/widget/instances/{id}      # Удалить виджет
GET    /widget.js?instance={id}          # Скрипт виджета
```

**Пример использования:**
```javascript
// Разные виджеты для разных отделов
<script src="https://api.example.com/widget.js?instance=sales"></script>
<script src="https://api.example.com/widget.js?instance=support"></script>
```

**Примечание:** Эта фича позволит:
- Один сервер — много ботов с разными токенами
- Разные промпты/персоны для sales, support, reception
- A/B тестирование разных моделей
- Мультитенантность (разные клиенты, разные боты)

---

### 3.5 Calendar Integration
**Статус:** `planned`
**Приоритет:** P2
**Сложность:** 6/10
**Оценка:** 2-3 недели
**Влияние:** ★★★★☆

**Описание:**
Интеграция с календарями (Google Calendar, Outlook) для управления расписанием через голос и чат. Секретарь сможет проверять свободные слоты, создавать встречи, напоминать о событиях.

**Задачи:**
- [ ] OAuth2 авторизация для Google Calendar API
- [ ] OAuth2 авторизация для Microsoft Graph API (Outlook)
- [ ] Сервис `calendar_service.py`:
  - `get_events(date_range)` — получить события
  - `find_free_slots(duration, date_range)` — найти свободные слоты
  - `create_event(title, start, end, attendees)` — создать встречу
  - `update_event(id, changes)` — обновить событие
  - `delete_event(id)` — удалить событие
- [ ] Intent detection для календарных запросов
- [ ] NLU для парсинга дат/времени ("завтра в 3", "в следующий вторник")
- [ ] Подтверждение действий перед выполнением
- [ ] Таб "Calendar" в админке
- [ ] Настройка подключённых аккаунтов

**Примеры использования:**
```
Пользователь: "Что у меня завтра?"
Секретарь: "Завтра у вас 3 встречи: в 10:00 созвон с командой,
           в 14:00 встреча с клиентом, в 16:30 weekly sync."

Пользователь: "Запланируй встречу с Иваном на среду в 15:00"
Секретарь: "Создаю встречу 'Встреча с Иваном' на среду, 29 января,
           в 15:00. Продолжительность — 1 час. Подтверждаете?"
```

**Структура данных:**
```python
class CalendarAccount(Base):
    __tablename__ = "calendar_accounts"

    id: str                    # UUID
    provider: str              # "google", "outlook"
    email: str                 # Связанный email
    access_token: str          # OAuth2 token (encrypted)
    refresh_token: str
    token_expires: datetime
    enabled: bool
    created_at: datetime
```

**API endpoints:**
```bash
GET    /admin/calendar/accounts          # Список подключённых аккаунтов
POST   /admin/calendar/accounts/connect  # Начать OAuth2 flow
DELETE /admin/calendar/accounts/{id}     # Отключить аккаунт
GET    /admin/calendar/events            # События за период
POST   /admin/calendar/events            # Создать событие
```

**Зависимости:**
- google-api-python-client
- google-auth-oauthlib
- msal (Microsoft Authentication Library)

---

### 3.6 Document Text Recognition
**Статус:** `planned`
**Приоритет:** P2
**Сложность:** 5/10
**Оценка:** 1.5-2 недели
**Влияние:** ★★★★☆

**Описание:**
Распознавание и извлечение текста из загруженных документов: PDF, DOC/DOCX, Excel, изображения (JPEG/PNG), Google Docs. Позволяет секретарю отвечать на вопросы по содержимому документов.

**Задачи:**
- [ ] Сервис `document_service.py`:
  - `extract_text(file_path)` — извлечь текст из любого формата
  - `extract_text_from_url(url)` — для Google Docs/Sheets
  - `summarize(text, max_length)` — краткое содержание
- [ ] Поддержка форматов:
  - **PDF** — PyMuPDF (fitz) или pdfplumber
  - **DOC/DOCX** — python-docx
  - **XLS/XLSX** — openpyxl или pandas
  - **Изображения (OCR)** — Tesseract или EasyOCR
  - **Google Docs** — Google Drive API
- [ ] Upload endpoint: `POST /admin/documents/upload`
- [ ] Индексация для поиска (опционально)
- [ ] Хранение extracted text в БД
- [ ] Интеграция с LLM для Q&A по документу
- [ ] UI для загрузки и просмотра документов

**Примеры использования:**
```
Пользователь: [загружает contract.pdf]
Секретарь: "Документ 'contract.pdf' загружен. Что хотите узнать?"

Пользователь: "Какой срок действия договора?"
Секретарь: "Согласно пункту 8.1, срок действия договора —
           с 01.01.2026 по 31.12.2026 с автоматической пролонгацией."

Пользователь: [загружает invoice.jpg]
Секретарь: "Распознала счёт №12345 от ООО 'Поставщик' на сумму 150,000 руб."
```

**Структура данных:**
```python
class Document(Base):
    __tablename__ = "documents"

    id: str                    # UUID
    filename: str              # Оригинальное имя файла
    file_type: str             # "pdf", "docx", "xlsx", "image"
    file_path: str             # Путь к файлу
    file_size: int             # Размер в байтах
    extracted_text: str        # Извлечённый текст
    metadata: dict             # Доп. метаданные (страницы, автор и т.д.)
    session_id: str            # Привязка к чат-сессии (опционально)
    created_at: datetime
```

**API endpoints:**
```bash
POST   /admin/documents/upload           # Загрузить документ
GET    /admin/documents                  # Список документов
GET    /admin/documents/{id}             # Получить документ
DELETE /admin/documents/{id}             # Удалить документ
POST   /admin/documents/{id}/ask         # Задать вопрос по документу
```

**Зависимости:**
```bash
pip install PyMuPDF python-docx openpyxl pytesseract Pillow easyocr
# Для Tesseract (system):
sudo apt install tesseract-ocr tesseract-ocr-rus
```

**Примечание:** OCR на GPU (EasyOCR) даёт лучшее качество, но Tesseract работает на CPU и достаточен для большинства задач.

---

## Фаза 4: Scale & Reliability (опционально)

### 4.1 High Availability
**Статус:** `backlog`
**Приоритет:** P3
**Сложность:** 8/10
**Оценка:** 3-5 недель

**Задачи:**
- [ ] Health checks для всех сервисов
- [ ] Автоматический failover LLM
- [ ] Поддержка 2+ GPU нод
- [ ] Load balancing
- [ ] Redis для shared state

---

### 4.2 SSO/LDAP Integration
**Статус:** `backlog`
**Приоритет:** P3
**Сложность:** 7/10
**Оценка:** 2.5-4 недели

**Задачи:**
- [ ] LDAP bind для аутентификации
- [ ] SAML 2.0 (опционально)
- [ ] OAuth2 (Google, Azure AD)
- [ ] Sync групп AD → роли

**Примечание:** Актуально только если есть AD/LDAP инфраструктура.

---

### 4.3 API Rate Limiting
**Статус:** `backlog`
**Приоритет:** P3
**Сложность:** 5/10
**Оценка:** 1-2 недели

**Примечание:** Для офлайн системы менее критично. Реализовать при необходимости.

---

## Фаза 5: Technical Debt & Quality

### 5.1 Automated Testing
**Статус:** `planned`
**Приоритет:** P1
**Сложность:** 6/10
**Оценка:** 2-3 недели
**Влияние:** ★★★★★

**Описание:**
Покрытие кода автоматическими тестами для стабильности и уверенного рефакторинга.

**Задачи:**
- [ ] Unit-тесты для сервисов:
  - `test_vllm_llm_service.py`
  - `test_voice_clone_service.py`
  - `test_stt_service.py`
  - `test_telegram_bot_service.py`
- [ ] Integration-тесты для API:
  - `test_chat_api.py` — CRUD сессий, streaming
  - `test_faq_api.py` — CRUD FAQ
  - `test_tts_api.py` — синтез речи
  - `test_auth_api.py` — JWT flow
- [ ] E2E тесты для админки (Playwright/Cypress):
  - Login flow
  - Chat functionality
  - FAQ management
- [ ] CI/CD pipeline (GitHub Actions):
  - Lint (ruff, eslint)
  - Unit tests
  - Integration tests (с mock LLM)
- [ ] Coverage отчёты (>70% цель)
- [ ] Pre-commit hooks

**Структура тестов:**
```
tests/
├── unit/
│   ├── test_vllm_llm_service.py
│   ├── test_voice_clone_service.py
│   ├── test_stt_service.py
│   └── test_db_repositories.py
├── integration/
│   ├── test_chat_api.py
│   ├── test_faq_api.py
│   ├── test_tts_api.py
│   └── conftest.py          # Fixtures, test client
├── e2e/
│   └── admin/
│       ├── login.spec.ts
│       └── chat.spec.ts
└── conftest.py              # Global fixtures
```

**Зависимости:**
```bash
pip install pytest pytest-asyncio pytest-cov httpx
npm install -D @playwright/test  # или cypress
```

---

### 5.2 Code Quality & Linting ✅
**Статус:** `done`
**Приоритет:** P2
**Сложность:** 3/10
**Завершено:** 2026-01-27
**Влияние:** ★★★☆☆

**Выполнено:**
- [x] Настроен ruff (Python linter + formatter)
- [x] Настроен mypy для type checking
- [x] Настроены eslint + prettier для Vue
- [x] Pre-commit hooks для автоматической проверки
- [x] Исправлены критические lint ошибки (1300+ → 0)
- [x] Форматирование всех Python файлов (46 файлов)

**Созданные файлы:**
```
pyproject.toml           # ruff, mypy, pytest, coverage config
.pre-commit-config.yaml  # pre-commit hooks
admin/.eslintrc.cjs      # eslint config
admin/.prettierrc        # prettier config
.venv/                   # venv для lint tools
```

**Использование:**
```bash
# Активировать venv
source .venv/bin/activate

# Проверка линтером
ruff check .

# Автоисправление
ruff check . --fix

# Форматирование
ruff format .

# Pre-commit проверка
pre-commit run --all-files

# Vue linting
cd admin && npm run lint
```

---

### 5.3 Documentation
**Статус:** `planned`
**Приоритет:** P2
**Сложность:** 4/10
**Оценка:** 1-2 недели
**Влияние:** ★★★☆☆

**Задачи:**
- [ ] API документация (OpenAPI/Swagger уже есть, улучшить описания)
- [ ] Архитектурная диаграмма (обновить)
- [ ] Deployment guide (Docker, systemd)
- [ ] Troubleshooting guide
- [ ] Contributing guide для будущих контрибуторов

---

### 5.4 Performance Profiling
**Статус:** `planned`
**Приоритет:** P3
**Сложность:** 5/10
**Оценка:** 1 неделя
**Влияние:** ★★★☆☆

**Задачи:**
- [ ] Профилирование latency LLM → TTS pipeline
- [ ] Memory profiling (особенно XTTS)
- [ ] Оптимизация startup time
- [ ] Кэширование частых FAQ ответов (уже есть в Redis)
- [ ] Lazy loading моделей

---

### 5.5 Error Handling & Logging
**Статус:** `planned`
**Приоритет:** P2
**Сложность:** 4/10
**Оценка:** 1 неделя
**Влияние:** ★★★★☆

**Задачи:**
- [ ] Структурированное логирование (JSON format)
- [ ] Централизованный error handler
- [ ] Graceful degradation (LLM fallback уже есть)
- [ ] Health check improvements
- [ ] Alerting (опционально — Telegram notifications)

---

### 5.6 Docker Compose Deployment ✅
**Статус:** `done`
**Приоритет:** P0 (критичный для adoption)
**Сложность:** 6/10
**Завершено:** 2026-01-27
**Влияние:** ★★★★★

**Проблема (решена):**
Текущий процесс установки требовал: GPU с 12GB VRAM, CUDA, Python 3.11+, Node.js, ручной setup БД, ngrok для внешнего доступа. Создавал высокий барьер для новых пользователей.

**Выполнено:**
- [x] Создан `Dockerfile` с multi-stage build (GPU и CPU варианты)
- [x] Создан `docker-compose.yml` с сервисами:
  - `orchestrator` — основной сервер (FastAPI + Vue admin)
  - `redis` — кэширование
  - `vllm` — LLM inference (GPU)
- [x] Поддержка NVIDIA Container Toolkit
- [x] Multi-stage build: admin-builder → runtime (GPU) / cpu (CPU-only)
- [x] Health checks для всех сервисов
- [x] Volumes для persistence (data/, models/, logs/, tts_cache, hf_cache)
- [x] Environment файл `.env.docker`
- [x] CPU-only режим: `docker-compose.cpu.yml` (Piper + Gemini)
- [x] Entrypoint script с инициализацией БД

**Использование:**
```bash
# GPU режим (vLLM + XTTS)
cp .env.docker .env
docker compose up -d

# CPU режим (Piper + Gemini)
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d

# Просмотр логов
docker compose logs -f orchestrator

# Остановка
docker compose down
```

**Созданные файлы:**
```
Dockerfile              # Multi-stage build (runtime + cpu targets)
docker-compose.yml      # GPU mode (orchestrator + vllm + redis)
docker-compose.cpu.yml  # CPU override (disables vLLM)
.dockerignore           # Build exclusions
.env.docker             # Environment template
scripts/docker-entrypoint.sh  # Container initialization
```

---

### 5.7 Legacy JSON Removal ✅
**Статус:** `done`
**Приоритет:** P1 (технический долг)
**Сложность:** 4/10
**Оценка:** 1 неделя
**Влияние:** ★★★★☆

**Проблема (решена):**
В коде присутствовала двойная система хранения: SQLite + Redis + JSON-файлы с "backward compatibility". Это:
- Усложняло поддержку кода
- Создавало риск рассинхронизации данных
- Увеличивало когнитивную нагрузку на разработчиков

**Выполнено:**
- [x] Аудит всех мест использования JSON файлов
- [x] Удаление `_sync_to_legacy_file()` из репозиториев (faq, preset, config, telegram)
- [x] Обновление LLM сервисов для загрузки FAQ из БД через `reload_faq(dict)`
- [x] Обновление voice_clone_service для загрузки пресетов из БД через `reload_presets(dict)`
- [x] Удаление legacy ChatManager класса из orchestrator.py
- [x] Удаление legacy функций get/save_widget_config, get/save_telegram_config
- [x] Добавление startup warning при обнаружении deprecated JSON файлов
- [x] Добавление автоматической загрузки FAQ и пресетов из БД при старте

**Deprecated файлы (можно удалить после миграции):**
```
typical_responses.json      # → data/secretary.db (faq_entries)
custom_presets.json         # → data/secretary.db (tts_presets)
widget_config.json          # → data/secretary.db (system_config)
telegram_config.json        # → data/secretary.db (system_config)
chat_sessions.json          # → data/secretary.db (chat_sessions + chat_messages)
```

**Миграция:** Запустить `python scripts/migrate_json_to_db.py` перед удалением JSON файлов.

---

## Технические заметки

### Hardware Setup (SIM7600G-H)

```
Raspberry Pi 4/5 или USB к основному серверу
         │
         ├── USB0: AT-команды (/dev/ttyUSB0)
         ├── USB1: Modem/PPP (/dev/ttyUSB1)
         ├── USB2: AT-команды (/dev/ttyUSB2)
         └── USB Audio: PCM аудио
```

**Подключение:**
```bash
# Проверка подключения
ls /dev/ttyUSB*
# Ожидается: /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2

# Тест AT-команд
screen /dev/ttyUSB0 115200
AT
# Ответ: OK
```

### Модели для офлайн

| Компонент | Модель | Размер | Где взять |
|-----------|--------|--------|-----------|
| LLM | Qwen2.5-7B-AWQ | 4GB | HuggingFace |
| LLM (light) | Qwen2.5-3B-GGUF | 2GB | HuggingFace |
| STT | vosk-model-ru-0.42 | 1.5GB | alphacephei.com |
| TTS | XTTS v2 | 1.8GB | Coqui |
| TTS (CPU) | Piper ru_RU | 60MB | GitHub |

### Зависимости для новых модулей

```bash
# Telephony
pip install pyserial aioserial

# STT
pip install vosk sounddevice

# Analytics
pip install pandas plotly

# Backup
pip install zipfile36  # или стандартный zipfile
```

---

## Changelog

### 2026-01-28 (update 13) — CI/CD Pipeline
- **CI/CD Pipeline** — автоматизация проверки кода
  - `.github/workflows/ci.yml` с lint-backend, lint-frontend, security jobs
  - `.github/dependabot.yml` для автоматического обновления зависимостей
  - CI badge в README
- **PWA Fix** — исправлена установка админки как PWA
  - Добавлены PNG-иконки 192x192 и 512x512
  - Исправлены пути в manifest.json

### 2026-01-28 (update 12) — Consolidated Improvement Plan & Telegram Buttons
- **Consolidated Improvement Plan** — создан детальный план развития
  - [docs/IMPROVEMENT_PLAN.md](docs/IMPROVEMENT_PLAN.md) с timeline, budget, ROI
  - Phase 0: Foundation (CI/CD, restructuring, security)
  - Phase 0.5: Monetization (Stripe/YooKassa, usage limits, legal)
  - Phase 2: Telephony SIM7600G-H (modem service, call manager)
  - Phase 3: Observability (structured logging, Prometheus, testing)
  - Production readiness checklist
- **Telegram Action Buttons** — интерактивные кнопки в Telegram ботах
  - Три дефолтные кнопки: "Составление ТЗ", "Связь с менеджером", "Главное меню"
  - Переключение LLM backend для каждой кнопки
  - Индивидуальные system prompts
  - UI для управления кнопками в админке

### 2026-01-27 (update 11) — Code Quality & Linting
- **Code Quality Tools** — настроены инструменты для качества кода
  - ruff — Python linter + formatter (>1300 ошибок исправлено)
  - mypy — статическая проверка типов
  - eslint + prettier — для Vue/TypeScript
  - pre-commit hooks — автоматическая проверка при коммите
- **Новые файлы:**
  ```
  pyproject.toml           # ruff, mypy, pytest, coverage
  .pre-commit-config.yaml  # pre-commit hooks
  admin/.eslintrc.cjs      # eslint config
  admin/.prettierrc        # prettier config
  ```
- **Использование:**
  ```bash
  source .venv/bin/activate
  ruff check .              # Проверка
  ruff check . --fix        # Автоисправление
  ruff format .             # Форматирование
  pre-commit run --all-files # Все проверки
  ```

### 2026-01-27 (update 10) — Docker Compose Deployment
- **Docker Compose для production deployment** — one-command запуск всей системы
  - Multi-stage Dockerfile (admin-builder → runtime/cpu)
  - GPU режим: orchestrator + vLLM + Redis
  - CPU режим: orchestrator + Redis (Piper + Gemini)
  - NVIDIA Container Toolkit support
  - Health checks для всех сервисов
  - Volumes: data/, logs/, models/, tts_cache, hf_cache
- **Новые файлы:**
  ```
  Dockerfile              # Multi-stage build
  docker-compose.yml      # GPU mode
  docker-compose.cpu.yml  # CPU override
  .dockerignore           # Build exclusions
  .env.docker             # Environment template
  scripts/docker-entrypoint.sh  # Container init
  ```
- **Использование:**
  ```bash
  # GPU mode
  docker compose up -d

  # CPU mode
  docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d
  ```

### 2026-01-27 (update 9) — Legacy JSON Removal
- **Полная миграция на SQLite + Redis** — удалён весь legacy JSON код
  - Удалены `_sync_to_legacy_file()` из всех репозиториев
  - LLM сервисы загружают FAQ из БД через `reload_faq(dict)`
  - voice_clone_service загружает пресеты из БД через `reload_presets(dict)`
  - Удалён legacy ChatManager класс (175+ строк)
  - Удалены legacy функции get/save_widget_config, get/save_telegram_config
- **Startup improvements:**
  - Автоматическая загрузка FAQ и пресетов из БД при старте
  - Warning при обнаружении deprecated JSON файлов
- **Затронутые файлы:**
  ```
  db/repositories/faq.py        # Удалён sync
  db/repositories/preset.py     # Удалён sync
  db/repositories/config.py     # Удалён sync
  db/repositories/telegram.py   # Удалён sync
  llm_service.py               # reload_faq(dict)
  vllm_llm_service.py          # reload_faq(dict)
  cloud_llm_service.py         # reload_faq(dict)
  voice_clone_service.py       # reload_presets(dict)
  orchestrator.py              # Удалён ChatManager, добавлены helper функции
  ```

### 2026-01-27 (update 8) — Cloud LLM Providers
- **Cloud LLM Providers** — универсальная система управления облачными LLM
  - Поддержка 7 типов провайдеров: Gemini, Kimi, OpenAI, Claude, DeepSeek, OpenRouter, Custom
  - CRUD операции из админ-панели
  - Хранение credentials (API keys, URLs) в SQLite
  - Factory pattern для унифицированного интерфейса
  - Hot-switching между провайдерами (`cloud:{provider_id}`)
- **Новые файлы:**
  ```
  cloud_llm_service.py          # Factory service (GeminiProvider, OpenAICompatibleProvider)
  db/repositories/cloud_provider.py  # Repository для провайдеров
  db/models.py                  # CloudLLMProvider модель
  ```
- **API endpoints:**
  - `GET/POST /admin/llm/providers` — список/создание
  - `GET/PUT/DELETE /admin/llm/providers/{id}` — CRUD
  - `POST /admin/llm/providers/{id}/test` — тест соединения
  - `POST /admin/llm/providers/{id}/set-default` — установить по умолчанию
- **UI:** Секция "Cloud LLM Providers" в LlmView.vue
- Добавлены задачи в бэклог:
  - 5.6 Docker Compose Deployment (P0)
  - 5.7 Legacy JSON Removal (P1)

### 2026-01-27 (update 7) — Chat Voice & LLM Models
- **Voice Mode** — кнопка в хедере чата для auto-play TTS
  - Настройка сохраняется в localStorage
  - Автоматическое воспроизведение после получения ответа
- **Voice Input (STT)** — кнопка микрофона в поле ввода
  - Запись через MediaRecorder API
  - Транскрипция через `/admin/stt/transcribe`
  - Индикатор записи с пульсацией
- **Prompt Editor** — редактирование промптов из настроек чата
  - Две вкладки: Session Prompt / Default Prompt
  - Редактирование, сброс к оригиналу
- **DeepSeek LLM** — поддержка третьей модели
  - `./start_gpu.sh --deepseek` — DeepSeek-LLM-7B-Chat
  - `start_deepseek.sh` — standalone скрипт
  - Конфиг в `AVAILABLE_MODELS` (vllm_llm_service.py)
- **LLM Models UI** — секция в LlmView.vue
  - Карточки моделей с features, VRAM, start commands
  - Подсветка текущей активной модели
- **STT API** — новый клиент `admin/src/api/stt.ts`
- **Audit Log** — помечен как `done` (UI полностью реализован)

### 2026-01-27 (update 6) — Calendar, Documents, Tech Debt
- Добавлена секция **3.5 Calendar Integration**
  - Google Calendar и Outlook интеграция через OAuth2
  - Управление расписанием через голос и чат
  - Intent detection для календарных запросов
- Добавлена секция **3.6 Document Text Recognition**
  - OCR и парсинг: PDF, DOC/DOCX, Excel, JPEG/PNG, Google Docs
  - Q&A по загруженным документам через LLM
  - Поддержка Tesseract и EasyOCR
- Добавлена **Фаза 5: Technical Debt & Quality**
  - 5.1 Automated Testing — unit, integration, e2e тесты
  - 5.2 Code Quality — ruff, mypy, eslint, pre-commit
  - 5.3 Documentation — API docs, deployment guide
  - 5.4 Performance Profiling — latency, memory optimization
  - 5.5 Error Handling & Logging — structured logs, alerting

### 2026-01-27 (update 6) — Multi-Instance Implementation ✅
- **Реализована задача 3.4 Multi-Instance Bots & Widgets**
  - Новые таблицы: `bot_instances`, `widget_instances` (db/models.py)
  - Репозитории: `bot_instance.py`, `widget_instance.py`
  - Multi-bot manager: `multi_bot_manager.py` — subprocess на каждого бота
  - ~15 новых API endpoints для CRUD и управления инстансами
  - Изоляция сессий: composite key (bot_id, user_id) в telegram_sessions
  - UI: полный редизайн TelegramView.vue с sidebar списком ботов
  - Backward compatibility: старые endpoints работают с 'default' инстансом
  - Миграция: `scripts/migrate_to_instances.py`
  - API URL поле для настройки туннеля (cloudflare/ngrok)

### 2026-01-26 (update 5) — Multi-Instance Bots & Widgets (Planning)
- Добавлена задача **3.4 Multi-Instance Bots & Widgets** в Фазу 3
  - Масштабирование: создание неограниченного количества ботов и виджетов
  - Индивидуальные настройки: LLM модель, системный промпт, персона, голос
  - Новые таблицы: `bot_instances`, `widget_instances`
  - Динамическая генерация виджетов: `/widget.js?instance=xxx`
  - Мультитенантность и A/B тестирование моделей

### 2026-01-26 (update 4) — Database Integration
- **Полная миграция на SQLite + Redis**
  - Создан пакет `db/` с SQLAlchemy async моделями
  - 7 таблиц: chat_sessions, chat_messages, faq_entries, tts_presets, system_config, telegram_sessions, audit_log
  - Redis кэширование с graceful fallback
  - Backward-compatible sync с JSON файлами
- **Новые файлы:**
  ```
  db/__init__.py
  db/database.py           # SQLite connection
  db/models.py             # ORM models
  db/redis_client.py       # Redis helpers
  db/integration.py        # Async managers
  db/repositories/         # Data access layer
  scripts/migrate_json_to_db.py
  scripts/test_db.py
  scripts/setup_db.sh
  ```
- Health endpoint теперь включает статус БД
- Зависимости: aiosqlite, sqlalchemy[asyncio], alembic, redis

### 2026-01-26 (update 3)
- Добавлен Vosk STT в stt_service.py
  - `VoskSTTService` — realtime офлайн распознавание
  - `UnifiedSTTService` — автовыбор Vosk/Whisper
  - `stream_recognize()` — streaming для телефонии
  - `recognize_microphone()` — распознавание с микрофона
- API endpoints: `/admin/stt/status`, `/admin/stt/models`, `/admin/stt/transcribe`, `/admin/stt/test`
- Обновлены зависимости: vosk, sounddevice

### 2026-01-26 (update 2)
- Добавлена кнопка TTS playback в ChatView.vue
  - Иконка Volume2 для сообщений ассистента (появляется при наведении)
  - Состояния: готов → загрузка (Loader2) → воспроизведение (Square/stop)
  - Использует `/admin/tts/test` через `ttsApi.testSynthesize()`
- Обновлена документация CLAUDE.md

### 2026-01-26
- Создан BACKLOG.md
- Определены 4 фазы разработки
- Приоритизированы enterprise-функции для офлайн + телефония

---

## Контакты

**Вопросы по roadmap:** открыть issue в репозитории

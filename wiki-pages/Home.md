# AI Secretary System - Документация

Добро пожаловать в документацию **AI Secretary System** - виртуального секретаря с клонированием голоса и поддержкой локальных/облачных LLM.

## Демо

| Ресурс | Ссылка |
|--------|--------|
| **Демо** (полный режим) | [demo.ai-sekretar24.ru/full/](https://demo.ai-sekretar24.ru/full/) |
| **Демо** (облачный режим) | [demo.ai-sekretar24.ru/cloud/](https://demo.ai-sekretar24.ru/cloud/) |
| **Сайт проекта** | [ai-sekretar24.ru](https://ai-sekretar24.ru/) |
| **Чат-бот техподдержки** | [@shaerware_digital_bot](https://t.me/shaerware_digital_bot) |

## Возможности системы

- **Клонирование голоса** — XTTS v2, OpenVoice, Piper TTS
- **Локальный LLM** — vLLM + Qwen/Llama/DeepSeek с LoRA
- **Облачные LLM** — Gemini, OpenAI, Claude, DeepSeek, Kimi, OpenRouter + Claude Code CLI bridge
- **Telegram боты** — мультиинстанс с воронкой продаж и платежами
- **WhatsApp боты** — мультиинстанс через WhatsApp Cloud API с воронкой продаж
- **Веб-виджеты** — чат для сайтов (мультиинстанс)
- **amoCRM** — OAuth2 интеграция, контакты, сделки, воронки
- **GSM телефония** — SIM7600E-H, голосовые звонки, SMS
- **Fine-tuning** — LoRA для LLM + TTS fine-tuning (Qwen3-TTS)
- **Wiki RAG** — база знаний с BM25 поиском и стеммингом для контекста LLM
- **Rate Limiting** — per-instance лимиты для ботов и виджетов
- **Админ-панель** — Vue 3 PWA, i18n (ru/en), 4 роли (admin/user/web/guest)

## Навигация по документации

### Админ-панель

| Страница | Описание |
|----------|----------|
| [[Dashboard]] | Главная панель со статусами сервисов |
| [[Chat]] | Чат с ИИ, голосовой режим, управление сессиями |
| [[Services]] | Управление vLLM сервисом |
| [[LLM]] | Настройки LLM, персоны, облачные провайдеры |
| [[TTS]] | Настройки синтеза речи, пресеты голосов |
| [[FAQ]] | Управление быстрыми ответами |
| [[Finetune]] | Дообучение моделей (LoRA для LLM, TTS fine-tuning) |
| [[Monitoring]] | Мониторинг GPU/CPU, логи |
| [[Models]] | Управление моделями HuggingFace |
| [[Widget]] | Настройка веб-виджетов (мультиинстанс) |
| [[Telegram]] | Управление Telegram ботами (мультиинстанс) |
| [[WhatsApp]] | Управление WhatsApp ботами (Cloud API, мультиинстанс) |
| [[GSM]] | GSM телефония (звонки, SMS) |
| [[Sales]] | Воронка продаж Telegram ботов (квиз, сегменты, follow-up) |
| [[CRM]] | Интеграция с amoCRM (контакты, сделки, воронки) |
| [[Usage]] | Статистика использования, лимиты, аналитика |
| [[Audit]] | Аудит действий пользователей |
| [[Settings]] | Профиль, настройки, бэкапы, язык, тема |

### Интеграции и справка

| Страница | Описание |
|----------|----------|
| [[Cloud-LLM-Providers]] | Настройка облачных LLM провайдеров |
| [[VLESS-Proxy]] | Настройка VLESS прокси для Gemini |
| [[Payments]] | Платежи: Telegram Stars, YooKassa, YooMoney |
| [[Personas]] | Персоны секретаря (Анна, Марина), промпты |
| [[Prompts]] | Карта системных промптов: приоритеты, хранение, редактирование |
| [[Wiki-RAG]] | База знаний: документы, BM25 поиск |
| [[Backup]] | Экспорт/импорт конфигурации |
| [[Deployment-Profiles]] | Профили развёртывания (full/cloud/local) |
| [[API-Reference]] | Справочник API (REST, OpenAI-совместимый) |
| [[Installation]] | Руководство по установке (Docker и локально) |
| [[Cloud-AI-Training]] | Wiki RAG — обучение облачных LLM на документации |
| [[Troubleshooting]] | Решение типичных проблем |

---

## Быстрый старт

### Docker (рекомендуется)

```bash
# GPU режим
cp .env.docker.example .env && docker compose up -d

# CPU режим
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d
```

### Доступ к админ-панели

- URL: `http://localhost:8002/admin/`
- Логин: `admin` / Пароль: `admin`
- Демо (только чтение): `demo` / `demo`

### Роли пользователей

| Роль | Доступ |
|------|--------|
| **admin** | Полный доступ ко всем функциям |
| **user** | Чтение + запись своих ресурсов |
| **web** | Как user, но скрыты: Dashboard, Services, vLLM, XTTS, Models, Finetune |
| **guest** | Только чтение (демо-доступ) |

---

**Версия документации:** 2.0
**Последнее обновление:** Февраль 2026

# System Prompts

Справочник всех системных промптов, используемых в проекте AI Secretary.

## Структура

| Файл | Описание | Источники в коде |
|------|----------|------------------|
| [secretary-personas.md](secretary-personas.md) | Персоны секретарей (Анна, Марина, Lydia) | `vllm_llm_service.py`, `llm_service.py`, `db/models.py`, `prepare_telegram.py` |
| [chat-and-rag.md](chat-and-rag.md) | Промпты чата, RAG, дефолты ботов | `app/routers/chat.py`, `telegram_bot/config.py`, `whatsapp_bot/config.py` |
| [tz-generator.md](tz-generator.md) | Генерация ТЗ (sales + freelancer) | `telegram_bot/handlers/tz.py`, `scripts/seed_tz_generator.py` |
| [sales-agents.md](sales-agents.md) | Агенты воронки продаж (14 промптов) | `db/models.py` (`DEFAULT_AGENT_PROMPTS`) |
| [stalkerelectric-sales.md](stalkerelectric-sales.md) | Продавец-консультант StalkerElectric v2 (WooCommerce + RAG) | Telegram `stalkerelectricbot` + widget `stalkerelectric` + коллекция каталога `woocommerce` (id 6) |
| [action-buttons.md](action-buttons.md) | Кнопки действий Telegram-бота | `db/models.py` (`DEFAULT_ACTION_BUTTONS`) |
| [bridge-service.md](bridge-service.md) | CLI-OpenAI bridge (tool use, summarize) | `services/bridge/src/utils/tools.py`, `services/bridge/src/utils/summarize.py` |
| [github-webhook.md](github-webhook.md) | PR-комментарии и рассылки | `app/routers/github_webhook.py` |
| [seed-tz-bot.md](seed-tz-bot.md) | TZ-генератор бот фрилансера (seed) | `scripts/seed_tz_generator.py` |

## Как промпты используются

```
Пользователь → Telegram/WhatsApp/Widget/Admin Chat
                        │
                        ▼
              ┌─────────────────┐
              │  Bot Instance   │ ← per-instance system_prompt (DB)
              │  или Chat API   │ ← fallback: LLM preset (anna/marina)
              └────────┬────────┘
                       │
         ┌─────────────┼──────────────┐
         ▼             ▼              ▼
   Sales Funnel   RAG Context    Direct Chat
   (agent prompt) (wiki-pages)   (persona prompt)
```

- **Персоны** (Анна/Марина) — базовые промпты для всех каналов
- **RAG prompt** — добавляется автоматически при наличии wiki-pages контекста
- **Sales agents** — выбираются по сегменту пользователя в воронке
- **Action buttons** — переключают system_prompt при нажатии кнопки в Telegram
- **Bridge prompts** — техническая обвязка для CLI-to-OpenAI bridge

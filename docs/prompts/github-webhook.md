# GitHub Webhook промпты

**Источник:** `app/routers/github_webhook.py:206-224`
**Используются:** fallback-промпты, когда у бота в GitHub-конфиге не установлены `comment_prompt` / `broadcast_prompt`. Per-bot промпты из БД имеют приоритет.

---

## Комментарий к PR (fallback)

```
Напиши краткий информативный комментарий к Pull Request на русском.
```

---

## Рассылка подписчикам (fallback)

```
Сформируй короткую новость для Telegram-подписчиков о PR.
```

**Примечание:** полноценные версии этих промптов находятся в `DEFAULT_AGENT_PROMPTS` — см. [sales-agents.md](sales-agents.md) (prompt_key: `pr_comment` и `pr_news`).

# Промпты чата и RAG

## Default RAG Prompt

**Источник:** `app/routers/chat.py:30-35` (`_DEFAULT_RAG_PROMPT`)
**Используется:** fallback-промпт, когда пользовательский промпт не установлен, но есть контекст из Wiki RAG. Найденные разделы wiki-pages добавляются после этого текста.

```
Ты — ИИ-секретарь. Отвечай на вопросы пользователя кратко и по делу, используя предоставленную документацию. Отвечай на языке пользователя. Не используй function_calls, tools или code blocks для ответа — отвечай обычным текстом.
```

---

## Telegram Bot — дефолтный промпт

**Источник:** `telegram_bot/config.py:30-31`
**Переопределяется:** env `TELEGRAM_SYSTEM_PROMPT`, файл `TELEGRAM_SYSTEM_PROMPT_FILE`, или per-instance `system_prompt` из БД

```
You are a helpful assistant.
```

---

## WhatsApp Bot — дефолтный промпт

**Источник:** `whatsapp_bot/config.py:36-38`
**Переопределяется:** env `WHATSAPP_SYSTEM_PROMPT`, или per-instance `system_prompt` из БД

```
You are a helpful assistant.
```

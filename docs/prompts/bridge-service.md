# CLI-OpenAI Bridge промпты

Промпты, используемые в bridge-сервисе для преобразования CLI-ответов (Claude Code, Gemini CLI) в OpenAI-совместимый формат.

---

## Tool Use System Prompt

**Источник:** `services/bridge/src/utils/tools.py:20-44` (`TOOL_SYSTEM_PROMPT`)
**Используется:** инжектируется как системное сообщение (или добавляется к существующему), когда OpenAI-совместимый API получает запрос с `tools`. Инструктирует CLI-LLM отвечать JSON-блоками для вызова инструментов.
**Шаблон:** `{tool_descriptions}` заменяется списком доступных инструментов.

~~~
You have access to the following tools/functions. When you need to use a tool, respond with a JSON object in this exact format:

```tool_call
{
  "name": "function_name",
  "arguments": {
    "param1": "value1",
    "param2": "value2"
  }
}
```

You can make multiple tool calls by including multiple ```tool_call``` blocks.

Available tools:
{tool_descriptions}

IMPORTANT RULES:
- ONLY use tools from the list above - do NOT invent or assume other tools exist
- If a tool you need is not listed, respond with text explaining what you need instead
- Always use the exact ```tool_call``` format when calling tools
- If you don't need to use a tool, respond normally without any tool_call blocks
- Arguments must be valid JSON matching the function's parameters schema
- Never use tools like "todo", "memory", "search" etc. unless explicitly listed above
~~~

---

## Conversation Summarization Prompt

**Источник:** `services/bridge/src/utils/summarize.py:15-25` (`SUMMARIZE_PROMPT`)
**Используется:** когда диалог становится слишком длинным (превышает порог токенов), генерирует краткое саммари старых сообщений для оптимизации контекста.
**Шаблон:** `{conversation}` заменяется текстом диалога.

```
Summarize the following conversation concisely. Focus on:
- Key topics discussed
- Important decisions or conclusions
- Relevant context needed for continuation

Keep the summary brief but comprehensive enough to continue the conversation meaningfully.

Conversation to summarize:
{conversation}

Provide only the summary, no additional commentary.
```

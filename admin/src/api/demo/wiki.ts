import type { DemoRoute } from './types'

interface WikiDoc {
  id: number
  filename: string
  title: string
  source_type: string
  file_size_bytes: number
  section_count: number
  collection_id: number | null
  owner_id: number | null
  created: string
  updated: string
}

const mockDocs: WikiDoc[] = [
  {
    id: 1,
    filename: '01-architecture.md',
    title: 'Архитектура системы',
    source_type: 'wiki',
    file_size_bytes: 4200,
    section_count: 8,
    collection_id: null,
    owner_id: null,
    created: '2025-12-01T10:00:00Z',
    updated: '2026-01-15T14:30:00Z',
  },
  {
    id: 2,
    filename: '02-deployment.md',
    title: 'Руководство по деплою',
    source_type: 'wiki',
    file_size_bytes: 3100,
    section_count: 6,
    collection_id: null,
    owner_id: null,
    created: '2025-12-05T09:00:00Z',
    updated: '2026-01-20T11:00:00Z',
  },
  {
    id: 3,
    filename: '03-llm-config.md',
    title: 'Настройка LLM',
    source_type: 'wiki',
    file_size_bytes: 2800,
    section_count: 5,
    collection_id: null,
    owner_id: null,
    created: '2025-12-10T08:00:00Z',
    updated: '2026-02-01T16:00:00Z',
  },
  {
    id: 4,
    filename: '04-telegram-bot.md',
    title: 'Telegram бот',
    source_type: 'wiki',
    file_size_bytes: 3500,
    section_count: 7,
    collection_id: null,
    owner_id: null,
    created: '2025-12-15T12:00:00Z',
    updated: '2026-02-10T09:00:00Z',
  },
  {
    id: 5,
    filename: '05-faq-system.md',
    title: 'Система FAQ и быстрых ответов',
    source_type: 'wiki',
    file_size_bytes: 1900,
    section_count: 4,
    collection_id: null,
    owner_id: null,
    created: '2026-01-05T10:00:00Z',
    updated: '2026-02-15T13:00:00Z',
  },
]

const mockContents: Record<number, string> = {
  1: `# Архитектура системы

## Обзор

AI-секретарь — это модульная система для автоматизации коммуникаций с клиентами. Система состоит из нескольких ключевых компонентов.

## Основные компоненты

- **Оркестратор** — FastAPI-сервер, координирующий все модули
- **LLM-сервис** — обработка естественного языка (Claude / локальная модель)
- **TTS-сервис** — синтез речи (XTTS v2)
- **Wiki-RAG** — поиск по базе знаний (BM25)
- **Telegram-бот** — интеграция с Telegram
- **Чат-виджет** — встраиваемый виджет для сайта

## Потоки данных

\`\`\`
Пользователь → Канал (Telegram/Widget/GSM)
  → Оркестратор
    → FAQ-матчинг (быстрый ответ)
    → Wiki-RAG (поиск контекста)
    → LLM (генерация ответа)
  → Ответ пользователю
\`\`\`

## База данных

Используется SQLite с асинхронным доступом через \`aiosqlite\`. Основные таблицы:

| Таблица | Описание |
|---------|----------|
| users | Пользователи системы |
| chat_sessions | Сессии чата |
| messages | Сообщения |
| knowledge_documents | Документы базы знаний |
| faq_entries | Быстрые ответы |

## Конфигурация

Все настройки хранятся в \`.env\` файле и доступны через admin-панель.
`,
  2: `# Руководство по деплою

## Требования

- Python 3.12+
- Node.js 20+
- SQLite 3
- systemd (для production)

## Быстрый старт

\`\`\`bash
git clone https://github.com/user/ai-secretary.git
cd ai-secretary
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
\`\`\`

## Production деплой

### Systemd сервис

\`\`\`ini
[Unit]
Description=AI Secretary
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ai-secretary
EnvironmentFile=/opt/ai-secretary/.env
ExecStart=/opt/ai-secretary/venv/bin/python -m uvicorn app.main:app --port 8002

[Install]
WantedBy=multi-user.target
\`\`\`

### Nginx

Nginx используется как reverse proxy для API и для раздачи статики admin-панели.

## Обновление

\`\`\`bash
cd /opt/ai-secretary && bash deploy.sh
\`\`\`

Скрипт \`deploy.sh\` выполняет полный цикл: backup → git pull → build → restart → health check.
`,
  3: `# Настройка LLM

## Поддерживаемые бэкенды

1. **Cloud (Claude)** — через Claude API или Claude Code bridge
2. **Локальная модель** — llama.cpp / vLLM на GPU

## Cloud режим

\`\`\`env
LLM_BACKEND=cloud:claude-bridge-stalkerelectric
DEPLOYMENT_MODE=cloud
\`\`\`

В cloud-режиме используется Claude через bridge-сервис. Не требует GPU.

## Промпт-система

Промпт собирается из нескольких частей:

1. **Системный промпт** — базовые инструкции
2. **Wiki-контекст** — релевантные фрагменты из базы знаний
3. **История чата** — последние сообщения
4. **Пользовательский запрос**

> Порядок сборки промпта критичен для качества ответов.

## Параметры генерации

| Параметр | Значение | Описание |
|----------|----------|----------|
| temperature | 0.7 | Креативность ответа |
| max_tokens | 2048 | Максимальная длина |
| top_p | 0.9 | Nucleus sampling |
`,
  4: `# Telegram бот

## Настройка

1. Создайте бота через [@BotFather](https://t.me/BotFather)
2. Получите токен
3. Укажите токен в настройках admin-панели

## Мультибот

Система поддерживает несколько Telegram-ботов одновременно. Каждый бот может:

- Иметь свой **системный промпт**
- Использовать свою **коллекцию** базы знаний
- Работать с отдельными настройками LLM

## Команды

- \`/start\` — начало работы
- \`/help\` — справка
- \`/reset\` — сброс контекста

## Webhook vs Polling

В production рекомендуется использовать **webhook** для надёжности. Polling подходит для разработки.

\`\`\`python
# Webhook URL формат
https://your-domain.com/webhooks/telegram/{bot_id}
\`\`\`

## Inline-кнопки

Бот поддерживает inline-клавиатуры для интерактивных сценариев (запись, выбор услуги, оплата).
`,
  5: `# Система FAQ и быстрых ответов

## Принцип работы

FAQ-система обрабатывает входящие сообщения **до** отправки в LLM. Если найдено совпадение, ответ возвращается мгновенно.

## Матчинг

Используется **нечёткое сравнение** (fuzzy matching):

- Регистронезависимый поиск
- Частичное совпадение подстроки
- Приоритет точного совпадения

## Шаблонные переменные

В ответах FAQ можно использовать переменные:

- \`{current_time}\` — текущее время
- \`{current_date}\` — текущая дата
- \`{day_of_week}\` — день недели

## Управление

FAQ управляется через API (\`/admin/faq\`). Записи хранятся в SQLite и кэшируются в памяти для быстрого доступа.

> **Совет:** Добавляйте в FAQ часто задаваемые вопросы, чтобы снизить нагрузку на LLM и ускорить ответы.
`,
}

export const wikiRoutes: DemoRoute[] = [
  {
    method: 'GET',
    pattern: /^\/admin\/wiki-rag\/documents$/,
    handler: ({ searchParams }) => {
      const collectionId = searchParams.get('collection_id')
      let docs = mockDocs
      if (collectionId) {
        docs = docs.filter(d => d.collection_id === Number(collectionId))
      }
      return { documents: docs, synced: docs.length }
    },
  },
  {
    method: 'GET',
    pattern: /^\/admin\/wiki-rag\/documents\/(\d+)$/,
    handler: ({ matches }) => {
      const id = Number(matches[1])
      const doc = mockDocs.find(d => d.id === id)
      if (!doc) {
        throw new Error('Document not found')
      }
      return {
        document: doc,
        content_preview: mockContents[id] || '# No content\n\nContent not available.',
      }
    },
  },
]

import type { DemoRoute } from './types'
import { getStore, generateId, nowISO, daysAgo, minutesAgo } from './store'
import type { ChatSessionData } from './store'

const defaultSessions: ChatSessionData[] = [
  {
    id: 'session-admin-1',
    title: 'Тест админки',
    pinned: true,
    source: 'admin',
    source_id: undefined,
    created: daysAgo(2),
    updated: minutesAgo(30),
    messages: [
      { id: 'msg-1', role: 'user', content: 'Привет! Проверяю как работает чат.', timestamp: daysAgo(2) },
      { id: 'msg-2', role: 'assistant', content: 'Здравствуйте! Я — Анна, ваш AI-секретарь. Чат работает корректно. Чем могу помочь?', timestamp: daysAgo(2) },
      { id: 'msg-3', role: 'user', content: 'Какие функции у тебя есть?', timestamp: minutesAgo(35) },
      { id: 'msg-4', role: 'assistant', content: 'Я умею:\n• Отвечать на вопросы клиентов 24/7\n• Синтезировать речь (TTS)\n• Распознавать речь (STT)\n• Работать в Telegram и на сайте\n• Записывать на приём\n• Принимать оплату\n\nЧто именно вас интересует?', timestamp: minutesAgo(34) },
    ],
  },
  {
    id: 'session-tg-1',
    title: 'Клиент Telegram: Алексей',
    pinned: false,
    source: 'telegram',
    source_id: '123456789',
    created: daysAgo(1),
    updated: minutesAgo(120),
    messages: [
      { id: 'msg-5', role: 'user', content: 'Добрый день! Сколько стоит подключение?', timestamp: daysAgo(1) },
      { id: 'msg-6', role: 'assistant', content: 'Добрый день, Алексей! Наши тарифы:\n\n• Базовый — 5 000 ₽/мес\n• Бизнес — 15 000 ₽/мес\n• Премиум — 30 000 ₽/мес\n\nКакой тариф вас интересует?', timestamp: daysAgo(1) },
      { id: 'msg-7', role: 'user', content: 'Бизнес тариф. Что в него входит?', timestamp: minutesAgo(125) },
      { id: 'msg-8', role: 'assistant', content: 'Тариф «Бизнес» (15 000 ₽/мес) включает:\n\n✅ До 3 ботов (Telegram/сайт)\n✅ Клонирование голоса (XTTS v2)\n✅ Приоритетная поддержка\n✅ 10 000 сообщений/мес\n✅ Аналитика и отчёты\n\nОформить подключение?', timestamp: minutesAgo(124) },
    ],
  },
  {
    id: 'session-widget-1',
    title: 'Посетитель сайта',
    pinned: false,
    source: 'widget',
    source_id: 'widget-main',
    created: daysAgo(0),
    updated: minutesAgo(15),
    messages: [
      { id: 'msg-9', role: 'user', content: 'Здравствуйте, хочу узнать о вашем продукте', timestamp: minutesAgo(20) },
      { id: 'msg-10', role: 'assistant', content: 'Здравствуйте! AI-секретарь — это виртуальный помощник для бизнеса. Он работает 24/7, отвечает на звонки и сообщения, записывает клиентов и принимает оплату.\n\nЧто вас интересует больше всего?', timestamp: minutesAgo(19) },
      { id: 'msg-11', role: 'user', content: 'Можно попробовать демо?', timestamp: minutesAgo(16) },
      { id: 'msg-12', role: 'assistant', content: 'Конечно! Вы можете:\n\n1. Попробовать демо-версию прямо сейчас на ai-sekretar24.ru\n2. Написать нашему боту @ai_support_bot в Telegram\n3. Заказать бесплатную консультацию\n\nВыбирайте удобный вариант!', timestamp: minutesAgo(15) },
    ],
  },
]

export function initChatData() {
  const store = getStore()
  if (store.chatSessions.length === 0) {
    store.chatSessions = defaultSessions.map(s => ({ ...s, messages: [...s.messages] }))
  }
}

function sessionToSummary(s: ChatSessionData) {
  return {
    id: s.id,
    title: s.title,
    pinned: s.pinned,
    message_count: s.messages.length,
    last_message: s.messages[s.messages.length - 1]?.content?.slice(0, 100),
    source: s.source,
    source_id: s.source_id,
    created: s.created,
    updated: s.updated,
  }
}

function sortByPinned<T extends { pinned?: boolean; updated?: string }>(arr: T[]): T[] {
  return [...arr].sort((a, b) => {
    if (a.pinned && !b.pinned) return -1
    if (!a.pinned && b.pinned) return 1
    return (b.updated || '').localeCompare(a.updated || '')
  })
}

export const chatRoutes: DemoRoute[] = [
  {
    method: 'GET',
    pattern: /^\/admin\/chat\/sessions$/,
    handler: ({ searchParams }) => {
      initChatData()
      const store = getStore()
      const sorted = sortByPinned(store.chatSessions)
      if (searchParams.get('group_by') === 'source') {
        const grouped = { admin: [] as unknown[], telegram: [] as unknown[], widget: [] as unknown[], unknown: [] as unknown[] }
        for (const s of sorted) {
          const key = s.source && s.source in grouped ? s.source : 'unknown'
          grouped[key as keyof typeof grouped].push(sessionToSummary(s))
        }
        return { sessions: grouped, grouped: true }
      }
      return { sessions: sorted.map(sessionToSummary) }
    },
  },
  {
    method: 'GET',
    pattern: /^\/admin\/chat\/sessions\/([^/?]+)$/,
    handler: ({ matches }) => {
      initChatData()
      const session = getStore().chatSessions.find(s => s.id === matches[1])
      return { session: session || getStore().chatSessions[0] }
    },
  },
  {
    method: 'POST',
    pattern: /^\/admin\/chat\/sessions\/bulk-delete$/,
    handler: ({ body }) => {
      const { session_ids } = body as { session_ids: string[] }
      const store = getStore()
      store.chatSessions = store.chatSessions.filter(s => !session_ids.includes(s.id))
      return { status: 'ok', deleted: session_ids.length }
    },
  },
  {
    method: 'POST',
    pattern: /^\/admin\/chat\/sessions\/([^/]+)\/messages\/([^/]+)\/regenerate$/,
    handler: () => ({
      response: {
        id: generateId(),
        role: 'assistant',
        content: 'Пожалуйста, уточните ваш вопрос, и я постараюсь помочь!',
        timestamp: nowISO(),
      },
    }),
  },
  {
    method: 'POST',
    pattern: /^\/admin\/chat\/sessions\/([^/]+)\/messages\/([^/]+)\/summarize$/,
    handler: () => ({
      summary: '# Итоги диалога\n\n## Основные темы\n- Обсуждение функциональности системы\n\n## Ключевые решения\n- Принято решение о реализации\n\n## Выводы\n- Задача выполнена успешно\n\n## Открытые вопросы\n- Нет',
    }),
  },
  {
    method: 'POST',
    pattern: /^\/admin\/chat\/sessions\/([^/]+)\/stream$/,
    handler: () => '__STREAM__',
  },
  {
    method: 'POST',
    pattern: /^\/admin\/chat\/sessions\/([^/]+)\/messages$/,
    handler: ({ matches, body }) => {
      initChatData()
      const store = getStore()
      const session = store.chatSessions.find(s => s.id === matches[1])
      const { content } = body as { content: string }
      const userMsg = { id: generateId(), role: 'user' as const, content, timestamp: nowISO() }
      const assistantMsg = {
        id: generateId(),
        role: 'assistant' as const,
        content: 'Спасибо за ваше сообщение! Я обработала ваш запрос. Чем ещё могу помочь?',
        timestamp: nowISO(),
      }
      if (session) {
        session.messages.push(userMsg, assistantMsg)
        session.updated = nowISO()
      }
      return { message: userMsg, response: assistantMsg }
    },
  },
  {
    method: 'PUT',
    pattern: /^\/admin\/chat\/sessions\/([^/]+)\/messages\/([^/]+)$/,
    handler: ({ matches, body }) => {
      const { content } = body as { content: string }
      return {
        message: { id: matches[2], role: 'user', content, timestamp: nowISO(), edited: true },
      }
    },
  },
  {
    method: 'DELETE',
    pattern: /^\/admin\/chat\/sessions\/([^/]+)\/messages\/([^/]+)$/,
    handler: ({ matches }) => {
      const store = getStore()
      const session = store.chatSessions.find(s => s.id === matches[1])
      if (session) {
        session.messages = session.messages.filter(m => m.id !== matches[2])
      }
      return { status: 'ok' }
    },
  },
  {
    method: 'POST',
    pattern: /^\/admin\/chat\/sessions$/,
    handler: ({ body }) => {
      initChatData()
      const data = body as Record<string, string>
      const session: ChatSessionData = {
        id: generateId(),
        title: data.title || 'Новая сессия',
        messages: [],
        system_prompt: data.system_prompt,
        pinned: false,
        source: (data.source as 'admin') || 'admin',
        created: nowISO(),
        updated: nowISO(),
      }
      getStore().chatSessions.push(session)
      return { session }
    },
  },
  {
    method: 'PUT',
    pattern: /^\/admin\/chat\/sessions\/([^/?]+)$/,
    handler: ({ matches, body }) => {
      initChatData()
      const store = getStore()
      const session = store.chatSessions.find(s => s.id === matches[1])
      if (session) {
        Object.assign(session, body, { updated: nowISO() })
        return { session }
      }
      return { session: { id: matches[1], ...(body as object) } }
    },
  },
  {
    method: 'DELETE',
    pattern: /^\/admin\/chat\/sessions\/([^/?]+)$/,
    handler: ({ matches }) => {
      const store = getStore()
      store.chatSessions = store.chatSessions.filter(s => s.id !== matches[1])
      return { status: 'ok' }
    },
  },
]

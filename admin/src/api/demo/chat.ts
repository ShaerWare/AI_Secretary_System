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
  {
    id: 'session-wa-1',
    title: 'WhatsApp: Мария',
    pinned: false,
    source: 'whatsapp',
    source_id: '79001234567',
    created: daysAgo(1),
    updated: minutesAgo(45),
    messages: [
      { id: 'msg-13', role: 'user', content: 'Привет! Видела рекламу, хочу узнать подробнее', timestamp: daysAgo(1) },
      { id: 'msg-14', role: 'assistant', content: 'Привет, Мария! Рада, что заинтересовались. AI-секретарь — это виртуальный помощник, который работает 24/7: отвечает клиентам, записывает на приём, принимает оплату.\n\nЧто вас интересует?', timestamp: daysAgo(1) },
      { id: 'msg-15', role: 'user', content: 'Какая цена?', timestamp: minutesAgo(50) },
      { id: 'msg-16', role: 'assistant', content: 'Тарифы:\n\n*Базовый* — 5 000 ₽/мес\n*Бизнес* — 15 000 ₽/мес\n*Премиум* — 30 000 ₽/мес\n\nЕсть бесплатный пробный период 7 дней. Хотите попробовать?', timestamp: minutesAgo(49) },
    ],
  },
]

export function initChatData() {
  const store = getStore()
  if (store.chatSessions.length === 0) {
    store.chatSessions = defaultSessions.map(s => ({ ...s, messages: [...s.messages] }))
  }
}

// Demo share storage
const demoShares: Record<string, Array<{ id: number; session_id: string; user_id: number; permission: string; shared_by: number; shared_at: string; username: string; display_name: string | null }>> = {}
let shareIdCounter = 100

const demoShareableUsers = [
  { id: 2, username: 'operator', display_name: 'Оператор Иван', role: 'user' },
  { id: 3, username: 'manager', display_name: 'Менеджер Анна', role: 'user' },
  { id: 4, username: 'viewer', display_name: null, role: 'user' },
]

function sessionToSummary(s: ChatSessionData) {
  return {
    id: s.id,
    title: s.title,
    pinned: s.pinned,
    message_count: s.messages.length,
    last_message: s.messages[s.messages.length - 1]?.content?.slice(0, 100),
    source: s.source,
    source_id: s.source_id,
    owner_id: null,
    created: s.created,
    updated: s.updated,
    is_shared_with_me: false,
    share_permission: 'owner',
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
      let filtered = store.chatSessions
      const source = searchParams.get('source')
      const excludeSource = searchParams.get('exclude_source')
      if (source) {
        filtered = filtered.filter(s => s.source === source)
      }
      if (excludeSource) {
        filtered = filtered.filter(s => s.source !== excludeSource && s.source != null)
      }
      const sorted = sortByPinned(filtered)
      if (searchParams.get('group_by') === 'source') {
        const grouped = { admin: [] as unknown[], telegram: [] as unknown[], widget: [] as unknown[], whatsapp: [] as unknown[], unknown: [] as unknown[] }
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
      const session = getStore().chatSessions.find(s => s.id === matches[1]) || getStore().chatSessions[0]
      if (session) {
        const tokens = session.messages.reduce((sum, m) => sum + Math.ceil(m.content.length / 4), 0) + 200
        const context_window = 200_000
        const shares = demoShares[session.id] || []
        return {
          session: {
            ...session,
            owner_id: null,
            is_shared_with_me: false,
            share_permission: 'owner',
            share_count: shares.length,
            token_usage: {
              tokens,
              context_window,
              percent: Math.round(tokens / context_window * 1000) / 10,
              trimmed: false,
            },
          },
        }
      }
      return { session }
    },
  },
  // Shareable users
  {
    method: 'GET',
    pattern: /^\/admin\/chat\/shareable-users$/,
    handler: () => ({ users: demoShareableUsers }),
  },
  // Get shares
  {
    method: 'GET',
    pattern: /^\/admin\/chat\/sessions\/([^/]+)\/shares$/,
    handler: ({ matches }) => {
      const sessionId = matches[1]
      return { shares: demoShares[sessionId] || [] }
    },
  },
  // Add share
  {
    method: 'POST',
    pattern: /^\/admin\/chat\/sessions\/([^/]+)\/shares$/,
    handler: ({ matches, body }) => {
      const sessionId = matches[1]
      const { user_id, permission } = body as { user_id: number; permission: string }
      const user = demoShareableUsers.find(u => u.id === user_id)
      const share = {
        id: ++shareIdCounter,
        session_id: sessionId,
        user_id,
        permission: permission || 'read',
        shared_by: 1,
        shared_at: nowISO(),
        username: user?.username || 'unknown',
        display_name: user?.display_name || null,
      }
      if (!demoShares[sessionId]) demoShares[sessionId] = []
      demoShares[sessionId].push(share)
      return { share }
    },
  },
  // Update share permission
  {
    method: 'PUT',
    pattern: /^\/admin\/chat\/sessions\/([^/]+)\/shares\/(\d+)$/,
    handler: ({ matches, body }) => {
      const sessionId = matches[1]
      const userId = parseInt(matches[2])
      const { permission } = body as { permission: string }
      const shares = demoShares[sessionId] || []
      const share = shares.find(s => s.user_id === userId)
      if (share) share.permission = permission
      return { status: 'ok' }
    },
  },
  // Delete share
  {
    method: 'DELETE',
    pattern: /^\/admin\/chat\/sessions\/([^/]+)\/shares\/(\d+)$/,
    handler: ({ matches }) => {
      const sessionId = matches[1]
      const userId = parseInt(matches[2])
      if (demoShares[sessionId]) {
        demoShares[sessionId] = demoShares[sessionId].filter(s => s.user_id !== userId)
      }
      return { status: 'ok' }
    },
  },
  // Fork session
  {
    method: 'POST',
    pattern: /^\/admin\/chat\/sessions\/([^/]+)\/fork$/,
    handler: ({ matches, body }) => {
      initChatData()
      const store = getStore()
      const source = store.chatSessions.find(s => s.id === matches[1])
      const { title } = (body || {}) as { title?: string }
      if (source) {
        const forked: ChatSessionData = {
          id: generateId(),
          title: title || `${source.title} (fork)`,
          messages: source.messages.map(m => ({ ...m, id: generateId() })),
          pinned: false,
          source: 'admin',
          created: nowISO(),
          updated: nowISO(),
        }
        store.chatSessions.push(forked)
        return { session: forked }
      }
      return { session: null }
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
    pattern: /^\/admin\/chat\/sessions\/([^/]+)\/branches\/new$/,
    handler: ({ matches }) => {
      initChatData()
      const session = getStore().chatSessions.find(s => s.id === matches[1])
      if (session) session.messages = []
      return { status: 'ok', session }
    },
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
      initChatData()
      const { content } = body as { content: string }
      const store = getStore()
      const session = store.chatSessions.find(s => s.id === matches[1])
      const originalMsg = session?.messages.find(m => m.id === matches[2])
      const role = originalMsg?.role || 'user'
      const editedMsg = { id: matches[2], role, content, timestamp: nowISO(), edited: true }
      if (role === 'assistant') {
        // Assistant edit: no LLM regeneration
        return { message: editedMsg }
      }
      return { message: editedMsg }
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

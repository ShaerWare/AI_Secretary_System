import type { DemoRoute } from './types'
import { getStore, generateId, nowISO, daysAgo } from './store'
import type { BotInstanceData } from './store'

const defaultBots: BotInstanceData[] = [
  {
    id: 'bot-support',
    name: 'AI Поддержка',
    description: 'Бот техподдержки с AI-ответами',
    enabled: true,
    bot_token_masked: '7890****...XYZ',
    api_url: 'https://api.telegram.org',
    allowed_users: [],
    admin_users: [123456789],
    welcome_message: 'Здравствуйте! Я — AI-помощник техподдержки. Задайте ваш вопрос.',
    typing_enabled: true,
    llm_backend: 'vllm',
    llm_persona: 'anna',
    system_prompt: 'Ты — Анна, AI-секретарь техподдержки. Помогай клиентам решать проблемы.',
    tts_engine: 'xtts',
    tts_voice: 'anna',
    tts_preset: 'natural',
    rag_mode: 'all',
    knowledge_collection_id: null,
    action_buttons: [
      { id: 'btn-1', label: 'FAQ', icon: '❓', enabled: true, order: 1 },
      { id: 'btn-2', label: 'Оператор', icon: '👨‍💼', enabled: true, order: 2 },
      { id: 'btn-3', label: 'Оплата', icon: '💳', enabled: true, order: 3 },
    ],
    payment_enabled: true,
    stars_enabled: true,
    payment_products: [
      { id: 'prod-1', title: 'Консультация', description: 'Консультация специалиста 30 мин', price_rub: 200000, price_stars: 100 },
      { id: 'prod-2', title: 'Тариф Базовый', description: 'Подписка на месяц', price_rub: 500000, price_stars: 250 },
    ],
    payment_success_message: 'Спасибо за оплату! Ваш доступ активирован.',
    yoomoney_configured: true,
    running: true,
    pid: 2345,
    created: daysAgo(30),
    updated: daysAgo(1),
  },
  {
    id: 'bot-sales',
    name: 'AI Продажи',
    description: 'Бот продаж с квизом и воронкой',
    enabled: true,
    bot_token_masked: '1234****...ABC',
    api_url: 'https://api.telegram.org',
    allowed_users: [],
    admin_users: [123456789],
    welcome_message: 'Привет! Хотите узнать, как AI-секретарь поможет вашему бизнесу?',
    typing_enabled: true,
    llm_backend: 'cloud:gemini-flash-1',
    llm_persona: 'marina',
    system_prompt: 'Ты — Марина, менеджер по продажам AI-секретаря. Помогай клиентам выбрать тариф.',
    tts_engine: 'xtts',
    tts_voice: 'marina',
    tts_preset: 'expressive',
    rag_mode: 'none',
    knowledge_collection_id: null,
    action_buttons: [
      { id: 'btn-4', label: 'Тарифы', icon: '📋', enabled: true, order: 1 },
      { id: 'btn-5', label: 'Демо', icon: '🎯', enabled: true, order: 2 },
      { id: 'btn-6', label: 'Отзывы', icon: '⭐', enabled: true, order: 3 },
    ],
    payment_enabled: true,
    stars_enabled: false,
    payment_products: [
      { id: 'prod-3', title: 'Тариф Бизнес', description: 'Подписка на месяц (3 бота)', price_rub: 1500000, price_stars: 750 },
    ],
    running: true,
    pid: 2346,
    created: daysAgo(14),
    updated: daysAgo(0),
  },
]

const sessions = [
  { bot_id: 'bot-support', user_id: 100001, chat_session_id: 'tg-s1', username: 'aleksey_k', first_name: 'Алексей', last_name: 'К.', created: daysAgo(5), updated: daysAgo(1) },
  { bot_id: 'bot-support', user_id: 100002, chat_session_id: 'tg-s2', username: 'maria_p', first_name: 'Мария', last_name: 'П.', created: daysAgo(3), updated: daysAgo(0) },
  { bot_id: 'bot-support', user_id: 100003, chat_session_id: 'tg-s3', username: null, first_name: 'Иван', last_name: 'С.', created: daysAgo(2), updated: daysAgo(0) },
  { bot_id: 'bot-sales', user_id: 200001, chat_session_id: 'tg-s4', username: 'business_owner', first_name: 'Дмитрий', last_name: 'В.', created: daysAgo(7), updated: daysAgo(2) },
  { bot_id: 'bot-sales', user_id: 200002, chat_session_id: 'tg-s5', username: 'elena_m', first_name: 'Елена', last_name: 'М.', created: daysAgo(1), updated: daysAgo(0) },
]

const payments = [
  { id: 1, bot_id: 'bot-support', user_id: 100001, username: 'aleksey_k', payment_type: 'yookassa', product_id: 'prod-1', amount: 200000, currency: 'RUB', status: 'completed', created: daysAgo(3) },
  { id: 2, bot_id: 'bot-support', user_id: 100002, username: 'maria_p', payment_type: 'stars', product_id: 'prod-2', amount: 250, currency: 'XTR', status: 'completed', created: daysAgo(1) },
  { id: 3, bot_id: 'bot-sales', user_id: 200001, username: 'business_owner', payment_type: 'yookassa', product_id: 'prod-3', amount: 1500000, currency: 'RUB', status: 'completed', created: daysAgo(5) },
]

export function initTelegramData() {
  const store = getStore()
  if (store.botInstances.length === 0) {
    store.botInstances = defaultBots.map(b => ({ ...b, action_buttons: [...b.action_buttons], payment_products: [...b.payment_products] }))
  }
}

export const telegramRoutes: DemoRoute[] = [
  // Legacy config
  {
    method: 'GET',
    pattern: /^\/admin\/telegram\/config$/,
    handler: () => ({
      config: {
        enabled: true,
        bot_token: '',
        bot_token_masked: '****',
        api_url: 'https://api.telegram.org',
        allowed_users: [],
        admin_users: [123456789],
        welcome_message: 'Здравствуйте!',
        unauthorized_message: 'Доступ запрещён',
        error_message: 'Произошла ошибка',
        typing_enabled: true,
      },
    }),
  },
  {
    method: 'POST',
    pattern: /^\/admin\/telegram\/config$/,
    handler: ({ body }) => ({ status: 'ok', config: body }),
  },
  {
    method: 'GET',
    pattern: /^\/admin\/telegram\/status$/,
    handler: () => ({
      status: { running: true, enabled: true, has_token: true, active_sessions: 5, allowed_users_count: 0, admin_users_count: 1, pid: 2345 },
    }),
  },
  {
    method: 'POST',
    pattern: /^\/admin\/telegram\/(start|stop|restart)$/,
    handler: () => ({ status: 'ok', pid: 2345 }),
  },
  {
    method: 'GET',
    pattern: /^\/admin\/telegram\/sessions$/,
    handler: () => ({ sessions: { '100001': 'session-1', '100002': 'session-2' } }),
  },
  {
    method: 'DELETE',
    pattern: /^\/admin\/telegram\/sessions$/,
    handler: () => ({ status: 'ok', message: 'Sessions cleared' }),
  },
  // Bot instances
  {
    method: 'GET',
    pattern: /^\/admin\/telegram\/instances$/,
    handler: () => {
      initTelegramData()
      return { instances: getStore().botInstances }
    },
  },
  {
    method: 'GET',
    pattern: /^\/admin\/telegram\/instances\/([^/]+)\/status$/,
    handler: ({ matches }) => {
      initTelegramData()
      const bot = getStore().botInstances.find(b => b.id === matches[1])
      return {
        status: {
          running: bot?.running ?? false,
          enabled: bot?.enabled ?? true,
          has_token: true,
          active_sessions: sessions.filter(s => s.bot_id === matches[1]).length,
          allowed_users_count: bot?.allowed_users?.length ?? 0,
          admin_users_count: bot?.admin_users?.length ?? 1,
          pid: bot?.pid ?? null,
        },
      }
    },
  },
  {
    method: 'GET',
    pattern: /^\/admin\/telegram\/instances\/([^/]+)\/sessions$/,
    handler: ({ matches }) => ({
      sessions: sessions.filter(s => s.bot_id === matches[1]),
    }),
  },
  {
    method: 'DELETE',
    pattern: /^\/admin\/telegram\/instances\/([^/]+)\/sessions$/,
    handler: () => ({ status: 'ok', message: 'Sessions cleared' }),
  },
  {
    method: 'GET',
    pattern: /^\/admin\/telegram\/instances\/([^/]+)\/logs/,
    handler: () => ({
      logs: '[2024-01-15 12:00] Bot started\n[2024-01-15 12:01] Connected to Telegram API\n[2024-01-15 12:05] Message from @aleksey_k\n[2024-01-15 12:05] Response sent (42ms)',
    }),
  },
  {
    method: 'GET',
    pattern: /^\/admin\/telegram\/instances\/([^/]+)\/payments\/stats$/,
    handler: ({ matches }) => {
      const botPayments = payments.filter(p => p.bot_id === matches[1])
      const byCurrency: Record<string, { count: number; total_amount: number }> = {}
      for (const p of botPayments) {
        if (!byCurrency[p.currency]) byCurrency[p.currency] = { count: 0, total_amount: 0 }
        byCurrency[p.currency].count++
        byCurrency[p.currency].total_amount += p.amount
      }
      return { stats: { total_count: botPayments.length, by_currency: byCurrency } }
    },
  },
  {
    method: 'GET',
    pattern: /^\/admin\/telegram\/instances\/([^/]+)\/payments$/,
    handler: ({ matches }) => ({
      payments: payments.filter(p => p.bot_id === matches[1]),
    }),
  },
  {
    method: 'GET',
    pattern: /^\/admin\/telegram\/instances\/([^/]+)\/yoomoney\/auth-url$/,
    handler: () => ({ url: 'https://yoomoney.ru/oauth/authorize?demo=true' }),
  },
  {
    method: 'POST',
    pattern: /^\/admin\/telegram\/instances\/([^/]+)\/yoomoney\/disconnect$/,
    handler: () => ({ status: 'ok' }),
  },
  {
    method: 'GET',
    pattern: /^\/admin\/telegram\/instances\/([^/?]+)$/,
    handler: ({ matches }) => {
      initTelegramData()
      const instance = getStore().botInstances.find(b => b.id === matches[1])
      return { instance: instance || getStore().botInstances[0] }
    },
  },
  {
    method: 'POST',
    pattern: /^\/admin\/telegram\/instances\/([^/]+)\/(start|stop|restart)$/,
    handler: ({ matches }) => {
      initTelegramData()
      const store = getStore()
      const bot = store.botInstances.find(b => b.id === matches[1])
      if (bot) {
        bot.running = matches[2] !== 'stop'
        bot.pid = matches[2] !== 'stop' ? 2347 : undefined
      }
      return { status: 'ok', pid: 2347, instance_id: matches[1] }
    },
  },
  {
    method: 'POST',
    pattern: /^\/admin\/telegram\/instances$/,
    handler: ({ body }) => {
      initTelegramData()
      const data = body as Partial<BotInstanceData>
      const instance: BotInstanceData = {
        id: generateId(),
        name: data.name || 'New Bot',
        enabled: true,
        allowed_users: [],
        admin_users: [],
        typing_enabled: true,
        llm_backend: 'vllm',
        llm_persona: 'anna',
        tts_engine: 'xtts',
        tts_voice: 'anna',
        rag_mode: 'all',
        knowledge_collection_id: null,
        action_buttons: [],
        payment_enabled: false,
        stars_enabled: false,
        payment_products: [],
        ...data,
        created: nowISO(),
        updated: nowISO(),
      }
      getStore().botInstances.push(instance)
      return { instance }
    },
  },
  {
    method: 'PUT',
    pattern: /^\/admin\/telegram\/instances\/([^/]+)$/,
    handler: ({ matches, body }) => {
      initTelegramData()
      const store = getStore()
      const idx = store.botInstances.findIndex(b => b.id === matches[1])
      if (idx >= 0) {
        Object.assign(store.botInstances[idx], body, { updated: nowISO() })
        return { instance: store.botInstances[idx] }
      }
      return { instance: body }
    },
  },
  {
    method: 'DELETE',
    pattern: /^\/admin\/telegram\/instances\/([^/]+)$/,
    handler: ({ matches }) => {
      const store = getStore()
      store.botInstances = store.botInstances.filter(b => b.id !== matches[1])
      return { status: 'ok', message: 'Instance deleted' }
    },
  },
  // Shareable users
  {
    method: 'GET',
    pattern: /^\/admin\/telegram\/shareable-users$/,
    handler: () => ({
      users: [
        { id: 1, username: 'admin', display_name: 'Администратор', role: 'admin' },
        { id: 2, username: 'operator', display_name: 'Оператор', role: 'user' },
      ],
    }),
  },
  // Instance shares
  {
    method: 'GET',
    pattern: /^\/admin\/telegram\/instances\/([^/]+)\/shares$/,
    handler: () => ({ shares: [] }),
  },
  {
    method: 'POST',
    pattern: /^\/admin\/telegram\/instances\/([^/]+)\/shares$/,
    handler: ({ body }) => ({
      share: { id: Date.now(), ...(body as Record<string, unknown>), shared_at: new Date().toISOString(), username: 'user', display_name: null },
    }),
  },
  {
    method: 'PUT',
    pattern: /^\/admin\/telegram\/instances\/([^/]+)\/shares\/(\d+)$/,
    handler: () => ({ status: 'ok' }),
  },
  {
    method: 'DELETE',
    pattern: /^\/admin\/telegram\/instances\/([^/]+)\/shares\/(\d+)$/,
    handler: () => ({ status: 'ok' }),
  },
]

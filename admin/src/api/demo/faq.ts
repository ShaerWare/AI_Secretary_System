import type { DemoRoute } from './types'
import { getStore } from './store'

const defaultFaq: Record<string, string> = {
  'привет': 'Здравствуйте! Я — виртуальный AI-секретарь. Чем могу помочь?',
  'здравствуйте': 'Добрый день! Рада вас приветствовать. Задайте ваш вопрос.',
  'цены': 'Наши тарифы:\n• Базовый — 5 000 ₽/мес (1 бот, FAQ, базовый LLM)\n• Бизнес — 15 000 ₽/мес (3 бота, голосовой клон, приоритетная поддержка)\n• Премиум — 30 000 ₽/мес (безлимит ботов, выделенный GPU, SLA 99.9%)',
  'функции': 'AI-секретарь умеет:\n• Отвечать на вопросы 24/7\n• Клонировать голос (XTTS v2)\n• Принимать звонки (GSM)\n• Работать в Telegram, на сайте и по телефону\n• Вести CRM и принимать оплату',
  'часы работы': 'AI-секретарь работает круглосуточно, 24/7, без выходных и праздников.',
  'запись': 'Для записи напишите дату и время, удобные вам, и я передам менеджеру. Или позвоните по телефону +7 (999) 123-45-67.',
  'оплата': 'Принимаем оплату:\n• Банковские карты (Visa, MasterCard, МИР)\n• YooKassa / YooMoney\n• Telegram Stars\n• Безналичный расчёт для юр. лиц',
  'интеграции': 'Поддерживаемые интеграции:\n• Telegram (мультибот)\n• Чат-виджет для сайта\n• GSM телефония (SIM7600E-H)\n• amoCRM (в разработке)\n• Произвольные webhook',
  'голосовой клон': 'Мы клонируем голос с помощью XTTS v2. Нужно 5-10 минут аудиозаписей хорошего качества. Результат готов за 2-4 часа обучения на GPU.',
  'техподдержка': 'Техподдержка доступна:\n• Telegram: @ai_support_bot\n• Email: support@ai-sekretar24.ru\n• Время ответа: до 30 минут в рабочее время',
  'демо': 'Вы сейчас находитесь в демо-версии! Все функции доступны для просмотра, но данные не сохраняются между сессиями.',
  'подключение': 'Этапы подключения:\n1. Заявка на сайте или в Telegram\n2. Консультация и выбор тарифа\n3. Настройка системы (1-3 дня)\n4. Обучение и клонирование голоса\n5. Запуск и мониторинг',
}

export function initFaqData() {
  const store = getStore()
  if (Object.keys(store.faq).length === 0) {
    Object.assign(store.faq, defaultFaq)
  }
}

export const faqRoutes: DemoRoute[] = [
  {
    method: 'GET',
    pattern: /^\/admin\/faq$/,
    handler: () => {
      initFaqData()
      return { faq: getStore().faq }
    },
  },
  {
    method: 'POST',
    pattern: /^\/admin\/faq$/,
    handler: ({ body }) => {
      initFaqData()
      const { trigger, response } = body as { trigger: string; response: string }
      getStore().faq[trigger] = response
      return { status: 'ok', trigger }
    },
  },
  {
    method: 'PUT',
    pattern: /^\/admin\/faq\/([^/]+)$/,
    handler: ({ matches, body }) => {
      initFaqData()
      const oldTrigger = decodeURIComponent(matches[1])
      const { trigger, response } = body as { trigger: string; response: string }
      const store = getStore()
      delete store.faq[oldTrigger]
      store.faq[trigger] = response
      return { status: 'ok', trigger }
    },
  },
  {
    method: 'DELETE',
    pattern: /^\/admin\/faq\/([^/]+)$/,
    handler: ({ matches }) => {
      initFaqData()
      const trigger = decodeURIComponent(matches[1])
      delete getStore().faq[trigger]
      return { status: 'ok', deleted: trigger }
    },
  },
  {
    method: 'POST',
    pattern: /^\/admin\/faq\/reload$/,
    handler: () => {
      initFaqData()
      return { status: 'ok', count: Object.keys(getStore().faq).length }
    },
  },
  {
    method: 'POST',
    pattern: /^\/admin\/faq\/test$/,
    handler: ({ body }) => {
      initFaqData()
      const { text } = body as { text: string }
      const lower = text.toLowerCase()
      const store = getStore()
      for (const [trigger, response] of Object.entries(store.faq)) {
        if (lower.includes(trigger.toLowerCase())) {
          return { match: true, response }
        }
      }
      return { match: false, response: null }
    },
  },
]

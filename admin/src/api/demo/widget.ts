import type { DemoRoute } from './types'
import { getStore, generateId, nowISO, daysAgo } from './store'
import type { WidgetInstanceData } from './store'

const defaultWidgets: WidgetInstanceData[] = [
  {
    id: 'widget-main',
    name: 'Основной виджет',
    description: 'Виджет для главного сайта ai-sekretar24.ru',
    enabled: true,
    title: 'AI-Секретарь',
    greeting: 'Здравствуйте! Я — AI-секретарь. Чем могу помочь?',
    placeholder: 'Введите сообщение...',
    placeholder_color: '',
    placeholder_font: '',
    primary_color: '#c2410c',
    button_icon: 'chat',
    button_size: 60,
    button_offset_bottom: 20,
    button_offset_side: 20,
    position: 'right',
    allowed_domains: ['ai-sekretar24.ru', 'localhost'],
    tunnel_url: 'https://ai-sekretar24.ru',
    llm_backend: 'vllm',
    llm_persona: 'anna',
    tts_engine: 'xtts',
    tts_voice: 'anna',
    tts_preset: 'natural',
    rag_mode: 'all',
    knowledge_collection_id: null,
    created: daysAgo(30),
    updated: daysAgo(2),
  },
]

export function initWidgetData() {
  const store = getStore()
  if (store.widgetInstances.length === 0) {
    store.widgetInstances = [...defaultWidgets]
  }
}

export const widgetRoutes: DemoRoute[] = [
  // Legacy
  {
    method: 'GET',
    pattern: /^\/admin\/widget\/config$/,
    handler: () => ({
      config: {
        enabled: true,
        title: 'AI-Секретарь',
        greeting: 'Здравствуйте!',
        placeholder: 'Введите сообщение...',
        primary_color: '#c2410c',
        position: 'right',
        allowed_domains: ['ai-sekretar24.ru'],
        tunnel_url: '',
      },
    }),
  },
  {
    method: 'POST',
    pattern: /^\/admin\/widget\/config$/,
    handler: ({ body }) => ({ status: 'ok', config: body }),
  },
  // Instances
  {
    method: 'GET',
    pattern: /^\/admin\/widget\/instances$/,
    handler: () => {
      initWidgetData()
      return { instances: getStore().widgetInstances }
    },
  },
  {
    method: 'GET',
    pattern: /^\/admin\/widget\/instances\/([^/?]+)$/,
    handler: ({ matches }) => {
      initWidgetData()
      const instance = getStore().widgetInstances.find(w => w.id === matches[1])
      return { instance: instance || getStore().widgetInstances[0] }
    },
  },
  {
    method: 'POST',
    pattern: /^\/admin\/widget\/instances$/,
    handler: ({ body }) => {
      initWidgetData()
      const data = body as Partial<WidgetInstanceData>
      const instance: WidgetInstanceData = {
        id: generateId(),
        name: data.name || 'New Widget',
        enabled: true,
        title: 'AI-Секретарь',
        placeholder: 'Введите сообщение...',
        placeholder_color: '',
        placeholder_font: '',
        primary_color: '#c2410c',
        button_icon: 'chat',
        button_size: 60,
        button_offset_bottom: 20,
        button_offset_side: 20,
        position: 'right',
        allowed_domains: [],
        llm_backend: 'vllm',
        llm_persona: 'anna',
        tts_engine: 'xtts',
        tts_voice: 'anna',
        rag_mode: 'all',
        knowledge_collection_id: null,
        ...data,
        created: nowISO(),
        updated: nowISO(),
      }
      getStore().widgetInstances.push(instance)
      return { instance }
    },
  },
  {
    method: 'PUT',
    pattern: /^\/admin\/widget\/instances\/([^/?]+)$/,
    handler: ({ matches, body }) => {
      initWidgetData()
      const store = getStore()
      const idx = store.widgetInstances.findIndex(w => w.id === matches[1])
      if (idx >= 0) {
        Object.assign(store.widgetInstances[idx], body, { updated: nowISO() })
        return { instance: store.widgetInstances[idx] }
      }
      return { instance: body }
    },
  },
  {
    method: 'DELETE',
    pattern: /^\/admin\/widget\/instances\/([^/?]+)$/,
    handler: ({ matches }) => {
      const store = getStore()
      store.widgetInstances = store.widgetInstances.filter(w => w.id !== matches[1])
      return { status: 'ok', message: 'Widget deleted' }
    },
  },
  // Instance shares
  {
    method: 'GET',
    pattern: /^\/admin\/widget\/instances\/([^/]+)\/shares$/,
    handler: () => ({ shares: [] }),
  },
  {
    method: 'POST',
    pattern: /^\/admin\/widget\/instances\/([^/]+)\/shares$/,
    handler: ({ body }) => ({
      share: { id: Date.now(), ...(body as Record<string, unknown>), shared_at: new Date().toISOString(), username: 'user', display_name: null },
    }),
  },
  {
    method: 'PUT',
    pattern: /^\/admin\/widget\/instances\/([^/]+)\/shares\/(\d+)$/,
    handler: () => ({ status: 'ok' }),
  },
  {
    method: 'DELETE',
    pattern: /^\/admin\/widget\/instances\/([^/]+)\/shares\/(\d+)$/,
    handler: () => ({ status: 'ok' }),
  },
]

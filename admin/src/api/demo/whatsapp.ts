import type { DemoRoute } from './types'
import type { WhatsAppInstanceData } from './store'
import { daysAgo, generateId, getStore, minutesAgo, nowISO } from './store'

const defaultInstances: WhatsAppInstanceData[] = [
  {
    id: 'wa_demo_main',
    name: 'AI Секретарь',
    description: 'Основной WhatsApp бот для продаж и поддержки',
    enabled: true,
    auto_start: true,
    phone_number_id: '100200300400500',
    waba_id: 'WABA_001',
    access_token_masked: 'EAAx...***...Xz9',
    verify_token: 'demo_verify_token',
    webhook_port: 8003,
    llm_backend: 'cloud:gemini-1',
    system_prompt: 'Ты — AI-секретарь компании. Отвечай вежливо и по делу.',
    tts_enabled: false,
    tts_engine: 'piper',
    tts_voice: 'anna',
    rag_mode: 'all',
    knowledge_collection_id: null,
    allowed_phones: [],
    blocked_phones: [],
    rate_limit_count: 30,
    rate_limit_hours: 1,
    running: true,
    pid: 4521,
    created: daysAgo(14),
    updated: minutesAgo(30),
  },
  {
    id: 'wa_demo_support',
    name: 'Техподдержка',
    description: 'Бот для техподдержки клиентов',
    enabled: true,
    auto_start: false,
    phone_number_id: '100200300400501',
    waba_id: 'WABA_001',
    access_token_masked: 'EAAy...***...Ab2',
    verify_token: 'demo_verify_token_2',
    webhook_port: 8004,
    llm_backend: 'vllm',
    system_prompt: 'Ты — техподдержка. Помогай решать проблемы с установкой и настройкой.',
    tts_enabled: false,
    tts_engine: 'piper',
    tts_voice: 'anna',
    rag_mode: 'collection',
    knowledge_collection_id: 1,
    allowed_phones: [],
    blocked_phones: [],
    rate_limit_count: 60,
    rate_limit_hours: 1,
    running: false,
    pid: undefined,
    created: daysAgo(7),
    updated: daysAgo(1),
  },
]

export function initWhatsAppData() {
  const store = getStore()
  if (!store.whatsappInstances || store.whatsappInstances.length === 0) {
    store.whatsappInstances = defaultInstances.map(i => ({ ...i }))
  }
}

const demoLogs = `[2026-02-12 10:00:01] INFO WhatsApp bot starting up
[2026-02-12 10:00:01] INFO WhatsApp sales database initialized: data/wa_sales_wa_demo_main.db
[2026-02-12 10:00:02] INFO Starting WhatsApp webhook server on 0.0.0.0:8003
[2026-02-12 10:00:02] INFO Webhook verified successfully
[2026-02-12 10:00:15] INFO Incoming text message from 79001234567
[2026-02-12 10:00:15] INFO Interactive reply from 79001234567: sales:start_quiz (type=button_reply)
[2026-02-12 10:00:16] INFO Interactive reply from 79001234567: sales:qt_diy (type=button_reply)
[2026-02-12 10:00:18] INFO Interactive reply from 79001234567: sales:qi_gpu (type=list_reply)
[2026-02-12 10:00:20] INFO Interactive reply from 79001234567: sales:gpu_rtx_30xx_low (type=list_reply)
[2026-02-12 10:00:22] INFO Interactive reply from 79001234567: sales:diy_github (type=button_reply)
`

export const whatsappRoutes: DemoRoute[] = [
  // List instances
  {
    method: 'GET',
    pattern: /^\/admin\/whatsapp\/instances$/,
    handler: () => {
      initWhatsAppData()
      return { instances: getStore().whatsappInstances }
    },
  },

  // Get instance
  {
    method: 'GET',
    pattern: /^\/admin\/whatsapp\/instances\/([^/]+)$/,
    handler: ({ matches }) => {
      initWhatsAppData()
      const instance = getStore().whatsappInstances.find(
        (i: WhatsAppInstanceData) => i.id === matches[1],
      )
      return { instance: instance || getStore().whatsappInstances[0] }
    },
  },

  // Create instance
  {
    method: 'POST',
    pattern: /^\/admin\/whatsapp\/instances$/,
    handler: ({ body }) => {
      initWhatsAppData()
      const store = getStore()
      const newInstance: WhatsAppInstanceData = {
        id: `wa_${generateId()}`,
        name: 'Новый WhatsApp бот',
        enabled: true,
        auto_start: false,
        phone_number_id: '',
        webhook_port: 8005,
        llm_backend: 'vllm',
        tts_enabled: false,
        tts_engine: 'piper',
        tts_voice: 'anna',
        rag_mode: 'all',
        knowledge_collection_id: null,
        allowed_phones: [],
        blocked_phones: [],
        rate_limit_count: 30,
        rate_limit_hours: 1,
        running: false,
        created: nowISO(),
        updated: nowISO(),
        ...(body as object),
      }
      store.whatsappInstances.push(newInstance)
      return { instance: newInstance }
    },
  },

  // Update instance
  {
    method: 'PUT',
    pattern: /^\/admin\/whatsapp\/instances\/([^/]+)$/,
    handler: ({ matches, body }) => {
      initWhatsAppData()
      const store = getStore()
      const idx = store.whatsappInstances.findIndex(
        (i: WhatsAppInstanceData) => i.id === matches[1],
      )
      if (idx >= 0) {
        Object.assign(store.whatsappInstances[idx], body, { updated: nowISO() })
        return { instance: store.whatsappInstances[idx] }
      }
      return { instance: body }
    },
  },

  // Delete instance
  {
    method: 'DELETE',
    pattern: /^\/admin\/whatsapp\/instances\/([^/]+)$/,
    handler: ({ matches }) => {
      initWhatsAppData()
      const store = getStore()
      store.whatsappInstances = store.whatsappInstances.filter(
        (i: WhatsAppInstanceData) => i.id !== matches[1],
      )
      return { status: 'ok', message: 'Instance deleted' }
    },
  },

  // Start / Stop / Restart
  {
    method: 'POST',
    pattern: /^\/admin\/whatsapp\/instances\/([^/]+)\/(start|stop|restart)$/,
    handler: ({ matches }) => {
      initWhatsAppData()
      const store = getStore()
      const instance = store.whatsappInstances.find(
        (i: WhatsAppInstanceData) => i.id === matches[1],
      )
      if (instance) {
        instance.running = matches[2] !== 'stop'
        instance.pid = matches[2] !== 'stop' ? 4521 : undefined
      }
      return { status: 'ok', pid: 4521, instance_id: matches[1] }
    },
  },

  // Get status
  {
    method: 'GET',
    pattern: /^\/admin\/whatsapp\/instances\/([^/]+)\/status$/,
    handler: ({ matches }) => {
      initWhatsAppData()
      const instance = getStore().whatsappInstances.find(
        (i: WhatsAppInstanceData) => i.id === matches[1],
      )
      return {
        status: {
          running: instance?.running ?? false,
          enabled: instance?.enabled ?? false,
          pid: instance?.pid ?? null,
        },
      }
    },
  },

  // Get logs
  {
    method: 'GET',
    pattern: /^\/admin\/whatsapp\/instances\/([^/]+)\/logs$/,
    handler: () => ({ logs: demoLogs }),
  },
]

import type { DemoRoute, HttpMethod, RouteParams } from './types'
import { initStore } from './store'
import { authRoutes } from './auth'
import { servicesRoutes } from './services'
import { monitorRoutes } from './monitor'
import { llmRoutes, initLlmData } from './llm'
import { ttsRoutes, createMinimalWav } from './tts'
import { faqRoutes, initFaqData } from './faq'
import { chatRoutes, initChatData } from './chat'
import { telegramRoutes, initTelegramData } from './telegram'
import { widgetRoutes, initWidgetData } from './widget'
import { gsmRoutes } from './gsm'
import { auditRoutes, initAuditData } from './audit'
import { modelsRoutes } from './models'
import { finetuneRoutes } from './finetune'
import { usageRoutes, initUsageData } from './usage'
import { sttRoutes } from './stt'
import { ttsFinetueRoutes } from './ttsFinetune'
import { botSalesRoutes } from './botSales'
import { amocrmRoutes } from './amocrm'
import { whatsappRoutes, initWhatsAppData } from './whatsapp'
import { claudeCodeRoutes } from './claudeCode'

// All routes — order matters: more specific patterns first
const allRoutes: DemoRoute[] = [
  ...claudeCodeRoutes,
  ...authRoutes,
  ...amocrmRoutes,
  ...botSalesRoutes,  // Must be before telegramRoutes (more specific patterns)
  ...telegramRoutes,
  ...whatsappRoutes,
  ...widgetRoutes,
  ...chatRoutes,
  ...faqRoutes,
  ...llmRoutes,
  ...ttsRoutes,
  ...servicesRoutes,
  ...monitorRoutes,
  ...gsmRoutes,
  ...auditRoutes,
  ...modelsRoutes,
  ...finetuneRoutes,
  ...usageRoutes,
  ...sttRoutes,
  ...ttsFinetueRoutes,
]

function matchDemoRoute(url: string, method: HttpMethod): { route: DemoRoute; matches: RegExpExecArray } | null {
  // Strip query string for pattern matching
  const pathOnly = url.split('?')[0]

  for (const route of allRoutes) {
    const methods = Array.isArray(route.method) ? route.method : [route.method]
    if (!methods.includes(method)) continue

    const matches = route.pattern.exec(pathOnly)
    if (matches) return { route, matches }
  }
  return null
}

function randomDelay(): Promise<void> {
  const ms = 100 + Math.random() * 200
  return new Promise(resolve => setTimeout(resolve, ms))
}

function createStreamResponse(content: string): Response {
  const encoder = new TextEncoder()
  const chunks = content.split(/(?<=[.!?。])\s*/g).filter(Boolean)

  const stream = new ReadableStream({
    async start(controller) {
      // User message echo
      controller.enqueue(encoder.encode('data: {"type":"user_message","content":""}\n\n'))
      await new Promise(r => setTimeout(r, 50))

      // Stream content chunk by chunk
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(`data: {"type":"content","content":"${chunk.replace(/"/g, '\\"')} "}\n\n`))
        await new Promise(r => setTimeout(r, 80))
      }

      // Done
      controller.enqueue(encoder.encode(`data: {"type":"message","message":{"id":"${Date.now()}","role":"assistant","content":"${content.replace(/"/g, '\\"')}","timestamp":"${new Date().toISOString()}"}}\n\n`))
      controller.enqueue(encoder.encode('data: [DONE]\n\n'))
      controller.close()
    },
  })

  return new Response(stream, {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    },
  })
}

function createBlobResponse(): Response {
  const wav = createMinimalWav()
  return new Response(wav, {
    status: 200,
    headers: {
      'Content-Type': 'audio/wav',
      'Content-Length': wav.byteLength.toString(),
    },
  })
}

export function setupDemoInterceptor() {
  // Initialize all stores
  initStore({})
  initFaqData()
  initChatData()
  initTelegramData()
  initWhatsAppData()
  initWidgetData()
  initLlmData()
  initAuditData()
  initUsageData()

  const originalFetch = window.fetch.bind(window)

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === 'string'
      ? input
      : input instanceof URL
        ? input.pathname + input.search
        : input.url
    const method = (init?.method || 'GET').toUpperCase() as HttpMethod

    // Only intercept API routes
    const isApiRoute = url.startsWith('/admin/') || url.startsWith('/v1/') || url.startsWith('/health')
    if (!isApiRoute) {
      return originalFetch(input, init)
    }

    const result = matchDemoRoute(url, method)
    if (!result) {
      // Fallback: return a generic success for unmatched API routes
      await randomDelay()
      return new Response(JSON.stringify({ status: 'ok' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    const { route, matches } = result

    // Parse body
    let body: unknown = null
    if (init?.body) {
      try {
        if (typeof init.body === 'string') {
          body = JSON.parse(init.body)
        } else if (init.body instanceof FormData) {
          body = init.body
        }
      } catch {
        body = init.body
      }
    }

    // Parse search params
    const urlObj = new URL(url, window.location.origin)
    const searchParams = urlObj.searchParams

    const params: RouteParams = { url, method, body, matches, searchParams }

    await randomDelay()

    try {
      const data = await route.handler(params)

      // Special return values
      if (data === '__BLOB__') {
        return createBlobResponse()
      }

      if (data === '__STREAM__') {
        return createStreamResponse(
          'Спасибо за ваше сообщение! Я обработала ваш запрос. Чем ещё могу помочь?'
        )
      }

      return new Response(JSON.stringify(data), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Demo error'
      return new Response(JSON.stringify({ detail: message }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      })
    }
  }

  console.log('🎭 Demo mode: API interceptor active')
}

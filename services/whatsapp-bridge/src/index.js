/**
 * AI Secretary — self-hosted WhatsApp provider.
 *
 * Links a regular phone (WhatsApp / WhatsApp Business app) over the multi-device
 * protocol via QR, and exposes it as a small REST + webhook API that the Python
 * `whatsapp_bot` subprocess drives. This is the same role Wazzup / Green API
 * play, only running on our own host.
 *
 * Env:
 *   WHATSAPP_BRIDGE_PORT   listen port (default 8005)
 *   WHATSAPP_BRIDGE_TOKEN  shared secret, required — also signs webhooks
 *   WHATSAPP_BRIDGE_DATA   credentials dir (default ./data)
 *   WHATSAPP_BRIDGE_HOST   bind address (default 127.0.0.1)
 *   LOG_LEVEL              pino level (default info)
 */

import crypto from 'node:crypto'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import express from 'express'
import pino from 'pino'

import { SessionManager } from './sessions.js'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const PORT = Number(process.env.WHATSAPP_BRIDGE_PORT ?? 8005)
const HOST = process.env.WHATSAPP_BRIDGE_HOST ?? '127.0.0.1'
const TOKEN = process.env.WHATSAPP_BRIDGE_TOKEN ?? ''
const DATA_DIR =
  process.env.WHATSAPP_BRIDGE_DATA ?? path.resolve(__dirname, '..', 'data')

const logger = pino({
  level: process.env.LOG_LEVEL ?? 'info',
  base: { service: 'whatsapp-bridge' },
})

if (!TOKEN) {
  logger.error('WHATSAPP_BRIDGE_TOKEN is not set — refusing to start')
  process.exit(1)
}

const manager = new SessionManager({ dataDir: DATA_DIR, token: TOKEN, logger })

const app = express()
app.use(express.json({ limit: '2mb' }))

// ─── Auth ────────────────────────────────────────────────────────────

function timingSafeEqual(a, b) {
  const bufA = Buffer.from(a)
  const bufB = Buffer.from(b)
  if (bufA.length !== bufB.length) return false
  return crypto.timingSafeEqual(bufA, bufB)
}

app.use((req, res, next) => {
  if (req.path === '/health') return next()

  const header = req.get('X-Bridge-Token') ?? ''
  const bearer = (req.get('Authorization') ?? '').replace(/^Bearer\s+/i, '')
  const provided = header || bearer

  if (!provided || !timingSafeEqual(provided, TOKEN)) {
    return res.status(401).json({ error: 'unauthorized' })
  }
  return next()
})

// Session ids land in a filesystem path — keep them boring.
const SESSION_ID_RE = /^[A-Za-z0-9_-]{1,64}$/

app.param('id', (req, res, next, id) => {
  if (!SESSION_ID_RE.test(id)) {
    return res.status(400).json({ error: 'invalid session id' })
  }
  return next()
})

/** Wrap an async handler so rejections become JSON errors instead of hangs. */
const wrap = (handler) => (req, res, next) => Promise.resolve(handler(req, res)).catch(next)

// ─── Routes ──────────────────────────────────────────────────────────

app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'whatsapp-bridge',
    sessions: manager.list(),
  })
})

app.get(
  '/sessions',
  wrap(async (req, res) => {
    res.json({ sessions: manager.list() })
  }),
)

/** Open (or re-open) a session. Body: {webhook_url}. */
app.post(
  '/sessions/:id/start',
  wrap(async (req, res) => {
    const session = manager.get(req.params.id, { create: true })
    const state = await session.start(req.body?.webhook_url)
    res.json(state)
  }),
)

app.get(
  '/sessions/:id',
  wrap(async (req, res) => {
    res.json(manager.get(req.params.id, { create: true }).toJSON())
  }),
)

app.post(
  '/sessions/:id/stop',
  wrap(async (req, res) => {
    res.json(await manager.get(req.params.id).stop())
  }),
)

/** Unlink the phone and wipe credentials. Next start requires a fresh QR. */
app.post(
  '/sessions/:id/logout',
  wrap(async (req, res) => {
    res.json(await manager.get(req.params.id).logout())
  }),
)

/**
 * Send a message.
 * Body: {to, type: 'text'|'image'|'video'|'audio'|'document', text, url,
 *        caption, filename, mimetype, voice}
 */
app.post(
  '/sessions/:id/messages',
  wrap(async (req, res) => {
    const session = manager.get(req.params.id)
    const { to, type = 'text', text, url, caption, filename, mimetype, voice } = req.body ?? {}

    if (!to) return res.status(400).json({ error: 'field "to" is required' })

    if (type === 'text') {
      if (!text) return res.status(400).json({ error: 'field "text" is required' })
      return res.json(await session.sendText(to, text))
    }

    if (!url) return res.status(400).json({ error: 'field "url" is required for media' })
    return res.json(
      await session.sendMedia(to, { mediaType: type, url, caption, filename, mimetype, voice }),
    )
  }),
)

/** Blue checkmarks. Body: {message_id}. */
app.post(
  '/sessions/:id/read',
  wrap(async (req, res) => {
    const { message_id: messageId } = req.body ?? {}
    if (!messageId) return res.status(400).json({ error: 'field "message_id" is required' })
    return res.json(await manager.get(req.params.id).markRead(messageId))
  }),
)

/** Typing indicator. Body: {to, state}. */
app.post(
  '/sessions/:id/presence',
  wrap(async (req, res) => {
    const { to, state = 'composing' } = req.body ?? {}
    if (!to) return res.status(400).json({ error: 'field "to" is required' })
    return res.json(await manager.get(req.params.id).sendPresence(to, state))
  }),
)

/** Download media from an incoming message (voice notes, photos, documents). */
app.get(
  '/sessions/:id/media/:messageId',
  wrap(async (req, res) => {
    const session = manager.get(req.params.id)
    const { buffer, mimetype, filename } = await session.downloadMedia(req.params.messageId)
    res.setHeader('Content-Type', mimetype)
    res.setHeader('Content-Disposition', `inline; filename="${encodeURIComponent(filename)}"`)
    res.send(buffer)
  }),
)

// ─── Error handling ──────────────────────────────────────────────────

// eslint-disable-next-line no-unused-vars -- express identifies error handlers by arity
app.use((err, req, res, next) => {
  const status = err.statusCode ?? 500
  if (status >= 500) {
    logger.error({ err: err.message, path: req.path }, 'request failed')
  } else {
    logger.warn({ err: err.message, path: req.path }, 'request rejected')
  }
  res.status(status).json({ error: err.message })
})

// ─── Lifecycle ───────────────────────────────────────────────────────

await mkdir(DATA_DIR, { recursive: true })

const server = app.listen(PORT, HOST, () => {
  logger.info({ port: PORT, host: HOST, dataDir: DATA_DIR }, 'whatsapp bridge listening')
})

async function shutdown(signal) {
  logger.info({ signal }, 'shutting down')
  server.close()
  await manager.stopAll()
  process.exit(0)
}

process.on('SIGTERM', () => shutdown('SIGTERM'))
process.on('SIGINT', () => shutdown('SIGINT'))

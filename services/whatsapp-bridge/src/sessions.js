/**
 * WhatsApp session manager (Baileys multi-device).
 *
 * One Session == one linked phone == one WhatsAppInstance row on the Python
 * side. Credentials live on disk under DATA_DIR/<id>/ so a restart re-attaches
 * without a new QR scan.
 */

import { rm } from 'node:fs/promises'
import path from 'node:path'

// Baileys 6.x ships CommonJS: the default export is makeWASocket itself, while
// helpers are named exports (they are NOT properties of the default).
import makeWASocket, {
  Browsers,
  DisconnectReason,
  downloadMediaMessage,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
  useMultiFileAuthState,
} from 'baileys'
import QRCode from 'qrcode'

import { deliver } from './webhook.js'

const RECONNECT_BASE_DELAY_MS = 2000
const RECONNECT_MAX_DELAY_MS = 60000
const MAX_RECONNECT_ATTEMPTS = 12
const RECENT_MESSAGE_CACHE = 300

/** Statuses exposed to the Python side. */
export const Status = {
  IDLE: 'idle',
  STARTING: 'starting',
  QR: 'qr',
  CONNECTED: 'connected',
  DISCONNECTED: 'disconnected',
  LOGGED_OUT: 'logged_out',
}

/** Turn "+7 (900) 123-45-67" or a bare JID into a WhatsApp JID. */
export function toJid(to) {
  if (!to) throw new Error('recipient is required')
  const value = String(to)
  if (value.includes('@')) return value
  const digits = value.replace(/\D/g, '')
  if (!digits) throw new Error(`invalid recipient: ${to}`)
  return `${digits}@s.whatsapp.net`
}

/** Phone number part of a JID, without the server suffix or device id. */
function jidToPhone(jid) {
  if (!jid) return ''
  return jid.split('@')[0].split(':')[0]
}

/** Unwrap the ephemeral/view-once/document-caption envelopes Baileys nests. */
function unwrap(message) {
  if (!message) return null
  return (
    message.ephemeralMessage?.message ??
    message.viewOnceMessage?.message ??
    message.viewOnceMessageV2?.message ??
    message.viewOnceMessageV2Extension?.message ??
    message.documentWithCaptionMessage?.message ??
    message
  )
}

/**
 * Flatten a Baileys message into the shape the Python bot consumes.
 * Returns null for messages that carry nothing actionable (reactions,
 * protocol/system messages, empty payloads).
 */
export function normalize(raw) {
  const content = unwrap(raw.message)
  if (!content) return null

  const jid = raw.key.remoteJid ?? ''
  const isGroup = jid.endsWith('@g.us')
  const contextInfo =
    content.extendedTextMessage?.contextInfo ??
    content.imageMessage?.contextInfo ??
    content.videoMessage?.contextInfo ??
    content.documentMessage?.contextInfo ??
    null

  const base = {
    id: raw.key.id,
    jid,
    // In groups the author is `participant`; in DMs it's the chat itself.
    from: jidToPhone(isGroup ? (raw.key.participant ?? '') : jid),
    chat_type: isGroup ? 'group' : 'direct',
    sender_name: raw.pushName ?? '',
    timestamp: Number(raw.messageTimestamp ?? 0),
    quoted_id: contextInfo?.stanzaId ?? null,
  }

  // ─── Interactive replies ──────────────────────────────────────────
  const buttonReply =
    content.buttonsResponseMessage?.selectedButtonId ??
    content.templateButtonReplyMessage?.selectedId
  if (buttonReply) {
    return {
      ...base,
      type: 'button_reply',
      reply_id: buttonReply,
      text:
        content.buttonsResponseMessage?.selectedDisplayText ??
        content.templateButtonReplyMessage?.selectedDisplayText ??
        '',
    }
  }

  const listReply = content.listResponseMessage?.singleSelectReply?.selectedRowId
  if (listReply) {
    return {
      ...base,
      type: 'list_reply',
      reply_id: listReply,
      text: content.listResponseMessage?.title ?? '',
    }
  }

  // ─── Plain text ───────────────────────────────────────────────────
  const text = content.conversation ?? content.extendedTextMessage?.text
  if (text) return { ...base, type: 'text', text }

  // ─── Media ────────────────────────────────────────────────────────
  const mediaKinds = [
    ['image', content.imageMessage],
    ['video', content.videoMessage],
    ['audio', content.audioMessage],
    ['document', content.documentMessage],
    ['sticker', content.stickerMessage],
  ]
  for (const [type, node] of mediaKinds) {
    if (!node) continue
    return {
      ...base,
      type,
      text: node.caption ?? '',
      media: {
        mimetype: node.mimetype ?? '',
        filename: node.fileName ?? '',
        seconds: node.seconds ?? 0,
        // WhatsApp voice notes ("push to talk") vs an attached audio file.
        voice: Boolean(node.ptt),
        size: Number(node.fileLength ?? 0),
      },
    }
  }

  if (content.locationMessage) {
    const loc = content.locationMessage
    return {
      ...base,
      type: 'location',
      text: loc.name ?? '',
      location: { latitude: loc.degreesLatitude, longitude: loc.degreesLongitude },
    }
  }

  if (content.contactMessage || content.contactsArrayMessage) {
    return { ...base, type: 'contact', text: content.contactMessage?.displayName ?? '' }
  }

  // Reactions, protocol updates, polls, and anything we don't model yet.
  return null
}

export class Session {
  constructor(id, { dataDir, token, logger }) {
    this.id = id
    this.authDir = path.join(dataDir, id)
    this.token = token
    this.logger = logger.child({ session: id })

    this.status = Status.IDLE
    this.qr = null // data-URL, valid only while status === 'qr'
    this.phone = null
    this.lastError = null
    this.webhookUrl = null
    this.connectedAt = null

    this.sock = null
    this.reconnectAttempts = 0
    this.reconnectTimer = null
    this.stopping = false
    this.starting = false
    /** @type {Map<string, object>} recent raw messages, for media download + read receipts */
    this.recent = new Map()
  }

  toJSON() {
    return {
      session_id: this.id,
      status: this.status,
      phone: this.phone,
      qr: this.status === Status.QR ? this.qr : null,
      last_error: this.lastError,
      connected_at: this.connectedAt,
      webhook_url: this.webhookUrl,
    }
  }

  _remember(raw) {
    if (!raw?.key?.id) return
    this.recent.set(raw.key.id, raw)
    if (this.recent.size > RECENT_MESSAGE_CACHE) {
      // Map preserves insertion order — drop the oldest entry.
      this.recent.delete(this.recent.keys().next().value)
    }
  }

  _emit(event, payload) {
    return deliver(
      this.webhookUrl,
      this.token,
      { event, session_id: this.id, ...payload },
      this.logger,
    )
  }

  _setStatus(status, extra = {}) {
    const changed = this.status !== status
    this.status = status
    if (status !== Status.QR) this.qr = null
    if (!changed) return

    this.logger.info({ status, ...extra }, 'session status changed')
    // The Python side polls status for the QR screen, but connection drops must
    // also reach it unsolicited so it can surface "phone disconnected". Only
    // transitions are published — stop() and the socket's own close event would
    // otherwise report the same drop twice.
    this._emit('connection', {
      status,
      phone: this.phone,
      last_error: this.lastError,
      ...extra,
    })
  }

  /** Delete the linked-device credentials from disk. */
  async _wipeCreds() {
    await rm(this.authDir, { recursive: true, force: true })
    this.phone = null
    this.recent.clear()
  }

  /**
   * Open the WhatsApp socket. Idempotent: calling it on a live session only
   * updates the webhook URL.
   *
   * @param {string} [webhookUrl] where to deliver incoming messages
   * @param {{force?: boolean}} [opts] force = a human explicitly asked to link
   *   (the admin panel button). Only a forced start may discard dead
   *   credentials and begin a fresh pairing.
   */
  async start(webhookUrl, { force = false } = {}) {
    if (webhookUrl) this.webhookUrl = webhookUrl

    if (this.starting) return this.toJSON()
    if (this.sock && (this.status === Status.CONNECTED || this.status === Status.QR)) {
      return this.toJSON()
    }

    // WhatsApp answers 401 to every login with credentials it has revoked.
    // A restarting bot calling start() in a loop would hammer the server with
    // failed logins — which looks exactly like an attack. Wait for a human to
    // ask for a new QR instead.
    if (this.status === Status.LOGGED_OUT) {
      if (!force) {
        this.logger.warn(
          'session is logged out — refusing to reopen with dead credentials; ' +
            'relink the phone from the admin panel',
        )
        return this.toJSON()
      }
      this.logger.info('forced start on a logged-out session — wiping dead credentials')
      await this._wipeCreds()
    }

    this.starting = true
    this.stopping = false
    this.lastError = null

    try {
      const { state, saveCreds } = await useMultiFileAuthState(this.authDir)
      const { version } = await fetchLatestBaileysVersion()

      this.logger.info({ waVersion: version }, 'opening WhatsApp socket')
      this._setStatus(Status.STARTING)

      const sock = makeWASocket({
        version,
        auth: {
          creds: state.creds,
          keys: makeCacheableSignalKeyStore(state.keys, this.logger),
        },
        logger: this.logger,
        printQRInTerminal: false,
        // Keep the phone's own notifications working — if we announce ourselves
        // as online, WhatsApp stops pushing alerts to the handset.
        markOnlineOnConnect: false,
        syncFullHistory: false,
        browser: Browsers?.ubuntu?.('Chrome') ?? ['AI Secretary', 'Chrome', '1.0.0'],
        generateHighQualityLinkPreview: false,
      })

      this.sock = sock
      sock.ev.on('creds.update', saveCreds)
      sock.ev.on('connection.update', (update) => this._onConnectionUpdate(update))
      sock.ev.on('messages.upsert', (upsert) => this._onMessages(upsert))
    } catch (err) {
      this.lastError = err.message
      this.logger.error({ err: err.message }, 'failed to open socket')
      this._setStatus(Status.DISCONNECTED)
      throw err
    } finally {
      this.starting = false
    }

    return this.toJSON()
  }

  async _onConnectionUpdate({ connection, lastDisconnect, qr }) {
    if (qr) {
      try {
        this.qr = await QRCode.toDataURL(qr, { margin: 1, width: 320 })
        // A fresh QR means the socket is healthy and waiting for a human, not
        // failing. Without this reset an unscanned QR burns through the retry
        // budget, and the mandatory post-pairing restart later gets vetoed.
        this.reconnectAttempts = 0
        this._setStatus(Status.QR)
      } catch (err) {
        this.logger.error({ err: err.message }, 'failed to render QR')
      }
      return
    }

    if (connection === 'open') {
      this.reconnectAttempts = 0
      this.phone = jidToPhone(this.sock?.user?.id ?? '')
      this.connectedAt = new Date().toISOString()
      this.lastError = null
      this._setStatus(Status.CONNECTED)
      return
    }

    if (connection !== 'close') return

    const code = lastDisconnect?.error?.output?.statusCode
    this.lastError = lastDisconnect?.error?.message ?? null
    this.sock = null

    if (this.stopping) {
      this._setStatus(Status.DISCONNECTED)
      return
    }

    // The phone unlinked us (or creds were invalidated) — a reconnect loop here
    // would spin forever against a dead credential set.
    if (code === DisconnectReason.loggedOut) {
      this.logger.warn('logged out by the phone, credentials are dead')
      this._setStatus(Status.LOGGED_OUT)
      return
    }

    // Another WhatsApp Web session replaced ours. Reconnecting would kick the
    // user right back out, so stay down and let an operator decide.
    if (code === DisconnectReason.connectionReplaced) {
      this.logger.warn('connection replaced by another session')
      this._setStatus(Status.DISCONNECTED)
      return
    }

    // Emitted right after a successful pairing — the socket MUST be recreated
    // immediately, otherwise the freshly scanned QR never finishes linking.
    // This is a handshake step, not a failure: it bypasses the retry budget
    // entirely, because refusing it strands a phone that the user just linked.
    if (code === DisconnectReason.restartRequired) {
      this.logger.info('restart required after pairing, reopening')
      this.reconnectAttempts = 0
      this._scheduleReconnect(0)
      return
    }

    this._setStatus(Status.DISCONNECTED, { code })
    this._scheduleReconnect()
  }

  _scheduleReconnect(delayOverride) {
    if (this.stopping) return
    if (this.reconnectTimer) return

    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      this.logger.error(
        { attempts: this.reconnectAttempts },
        'giving up reconnecting, manual start required',
      )
      return
    }

    const delay =
      delayOverride ??
      Math.min(
        RECONNECT_BASE_DELAY_MS * 2 ** this.reconnectAttempts,
        RECONNECT_MAX_DELAY_MS,
      )
    this.reconnectAttempts += 1
    this.logger.info({ delay, attempt: this.reconnectAttempts }, 'scheduling reconnect')

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.start().catch((err) => {
        this.logger.error({ err: err.message }, 'reconnect failed')
        this._scheduleReconnect()
      })
    }, delay)
  }

  async _onMessages({ messages, type }) {
    // 'append' carries history sync / older messages; only 'notify' is live.
    if (type !== 'notify') return

    for (const raw of messages) {
      if (raw.key?.fromMe) continue
      if (raw.key?.remoteJid === 'status@broadcast') continue

      this._remember(raw)
      const message = normalize(raw)
      if (!message) continue

      this.logger.info(
        { from: message.from, type: message.type },
        'incoming message',
      )
      await this._emit('message', { message })
    }
  }

  _requireSocket() {
    if (!this.sock || this.status !== Status.CONNECTED) {
      const err = new Error(`session ${this.id} is not connected (status: ${this.status})`)
      err.statusCode = 409
      throw err
    }
    return this.sock
  }

  async sendText(to, text) {
    const sock = this._requireSocket()
    const jid = toJid(to)
    const result = await sock.sendMessage(jid, { text })
    return { message_id: result?.key?.id ?? null, jid }
  }

  /**
   * Send media by URL. Baileys streams the URL itself, so the file never has to
   * be buffered through this process.
   */
  async sendMedia(to, { mediaType, url, caption, filename, mimetype, voice }) {
    const sock = this._requireSocket()
    const jid = toJid(to)

    let content
    switch (mediaType) {
      case 'image':
        content = { image: { url }, caption: caption || undefined }
        break
      case 'video':
        content = { video: { url }, caption: caption || undefined }
        break
      case 'audio':
        content = {
          audio: { url },
          mimetype: mimetype || 'audio/ogg; codecs=opus',
          ptt: voice !== false,
        }
        break
      case 'document':
        content = {
          document: { url },
          mimetype: mimetype || 'application/octet-stream',
          fileName: filename || 'file',
          caption: caption || undefined,
        }
        break
      default: {
        const err = new Error(`unsupported media type: ${mediaType}`)
        err.statusCode = 400
        throw err
      }
    }

    const result = await sock.sendMessage(jid, content)
    return { message_id: result?.key?.id ?? null, jid }
  }

  async markRead(messageId) {
    const sock = this._requireSocket()
    const raw = this.recent.get(messageId)
    if (!raw) return { marked: false, reason: 'message not in cache' }
    await sock.readMessages([raw.key])
    return { marked: true }
  }

  /** state: 'composing' | 'recording' | 'paused' | 'available' */
  async sendPresence(to, state) {
    const sock = this._requireSocket()
    const jid = toJid(to)
    await sock.sendPresenceUpdate(state, jid)
    return { ok: true }
  }

  async downloadMedia(messageId) {
    this._requireSocket()
    const raw = this.recent.get(messageId)
    if (!raw) {
      const err = new Error('message not found in cache')
      err.statusCode = 404
      throw err
    }
    const buffer = await downloadMediaMessage(
      raw,
      'buffer',
      {},
      { logger: this.logger, reuploadRequest: this.sock.updateMediaMessage },
    )
    const normalized = normalize(raw)
    return {
      buffer,
      mimetype: normalized?.media?.mimetype || 'application/octet-stream',
      filename: normalized?.media?.filename || messageId,
    }
  }

  /** Close the socket but keep credentials, so start() re-attaches silently. */
  async stop() {
    this.stopping = true
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.sock) {
      try {
        this.sock.end(undefined)
      } catch (err) {
        this.logger.debug({ err: err.message }, 'error while closing socket')
      }
      this.sock = null
    }
    this._setStatus(Status.DISCONNECTED)
    return this.toJSON()
  }

  /** Unlink the phone and wipe credentials — the next start needs a new QR. */
  async logout() {
    this.stopping = true
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.sock) {
      try {
        await this.sock.logout()
      } catch (err) {
        this.logger.warn({ err: err.message }, 'logout call failed, wiping creds anyway')
      }
      try {
        this.sock.end(undefined)
      } catch {
        /* already closed */
      }
      this.sock = null
    }
    await this._wipeCreds()
    this._setStatus(Status.LOGGED_OUT)
    return this.toJSON()
  }
}

export class SessionManager {
  constructor({ dataDir, token, logger }) {
    this.dataDir = dataDir
    this.token = token
    this.logger = logger
    /** @type {Map<string, Session>} */
    this.sessions = new Map()
  }

  get(id, { create = false } = {}) {
    let session = this.sessions.get(id)
    if (!session && create) {
      session = new Session(id, {
        dataDir: this.dataDir,
        token: this.token,
        logger: this.logger,
      })
      this.sessions.set(id, session)
    }
    if (!session) {
      const err = new Error(`unknown session: ${id}`)
      err.statusCode = 404
      throw err
    }
    return session
  }

  list() {
    return [...this.sessions.values()].map((s) => s.toJSON())
  }

  async stopAll() {
    await Promise.allSettled([...this.sessions.values()].map((s) => s.stop()))
  }
}

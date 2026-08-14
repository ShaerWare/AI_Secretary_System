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
  isLidUser,
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
  /** Waiting for an 8-character code to be typed on the phone. */
  PAIRING: 'pairing',
  CONNECTED: 'connected',
  DISCONNECTED: 'disconnected',
  LOGGED_OUT: 'logged_out',
}

/** WhatsApp needs a few seconds of live socket before it will issue a code. */
const PAIRING_CODE_DELAY_MS = 4000

/**
 * How long each pairing ref stays valid (Baileys default: 60s).
 *
 * WhatsApp hands out a finite list of refs; when they run out the socket dies
 * with "QR refs attempts ended". At the default that gave a ~2.5 minute window
 * — not enough for a human to read the code, unlock the phone, walk through
 * Settings → Linked devices and type it. Three minutes per ref makes the whole
 * window comfortably longer than the task.
 */
const LINK_WINDOW_MS = 180000

/** How many times to silently re-open a link window before giving up. */
const MAX_LINK_CYCLES = 5

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

  // WhatsApp addresses a growing share of users by an opaque "@lid" instead of
  // a phone number. Rebuilding an address out of its digits yields a JID that
  // does not exist: replies vanish silently, and a freshly linked device that
  // sends to one gets revoked (stream:error 401, conflict device_removed).
  // So `from` carries something we can always send back to, while `phone` holds
  // the real number when WhatsApp discloses it.
  const authorJid = isGroup ? (raw.key.participant ?? '') : jid
  const senderPn = raw.key.senderPn ?? raw.key.participantPn ?? null

  const base = {
    id: raw.key.id,
    jid,
    from: isLidUser(authorJid) ? authorJid : jidToPhone(authorJid),
    phone: senderPn ? jidToPhone(senderPn) : isLidUser(authorJid) ? null : jidToPhone(authorJid),
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
    this.pairingCode = null // 8 chars, valid only while status === 'pairing'
    this.pairingPhone = null // number the code was requested for
    this.phone = null
    this.lastError = null
    this.webhookUrl = null
    this.connectedAt = null

    this.sock = null
    this.reconnectAttempts = 0
    this.reconnectTimer = null
    this.stopping = false
    this.starting = false
    /** Link windows opened since the operator asked to link (see MAX_LINK_CYCLES). */
    this.linkCycles = 0
    /** @type {Map<string, object>} recent raw messages, for media download + read receipts */
    this.recent = new Map()
  }

  toJSON() {
    return {
      session_id: this.id,
      status: this.status,
      phone: this.phone,
      qr: this.status === Status.QR ? this.qr : null,
      pairing_code: this.status === Status.PAIRING ? this.pairingCode : null,
      pairing_phone: this.pairingPhone,
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
    if (status !== Status.PAIRING) this.pairingCode = null
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
   * @param {{force?: boolean, pairingPhone?: string}} [opts] force = a human
   *   explicitly asked to link (the admin panel button); only a forced start
   *   may discard dead credentials and begin a fresh pairing. pairingPhone
   *   switches from a QR to an 8-character code typed on that number's phone.
   */
  async start(webhookUrl, { force = false, pairingPhone } = {}) {
    if (webhookUrl) this.webhookUrl = webhookUrl

    if (this.starting) return this.toJSON()

    // `undefined` means "keep whatever mode we're in" — reconnects call start()
    // with no arguments and must not lose the number we're pairing with.
    const requestedPhone =
      pairingPhone === undefined
        ? undefined
        : pairingPhone
          ? String(pairingPhone).replace(/\D/g, '')
          : null

    if (this.sock && this.status === Status.CONNECTED) return this.toJSON()

    if (this.sock && (this.status === Status.QR || this.status === Status.PAIRING)) {
      // A live link window exists. Reuse it unless the operator switched
      // methods — swapping QR for a code needs a new socket.
      if (requestedPhone === undefined || requestedPhone === this.pairingPhone) {
        return this.toJSON()
      }
      this.logger.info('link method changed, reopening the socket')
      await this.stop()
    }

    if (requestedPhone !== undefined) {
      this.pairingPhone = requestedPhone
      this.pairingCode = null
    }

    // WhatsApp answers 401 to every login with credentials it has revoked.
    // A restarting bot calling start() in a loop would hammer the server with
    // failed logins — which looks exactly like an attack. Wait for a human to
    // ask for a new link instead.
    if (this.status === Status.LOGGED_OUT && !force) {
      this.logger.warn(
        'session is logged out — refusing to reopen with dead credentials; ' +
          'relink the phone from the admin panel',
      )
      return this.toJSON()
    }

    // A forced start is a human asking to link this phone. Always begin from a
    // clean slate: credentials may be poisoned without the status saying so —
    // requestPairingCode marks them "registered" up front, so an expired window
    // leaves a set that looks valid and gets 401 on first use.
    if (force) {
      this.logger.info('forced start — wiping credentials to begin a clean pairing')
      await this._wipeCreds()
      this.linkCycles = 0
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
        qrTimeout: LINK_WINDOW_MS,
      })

      this.sock = sock
      sock.ev.on('creds.update', saveCreds)
      sock.ev.on('connection.update', (update) => this._onConnectionUpdate(update))
      sock.ev.on('messages.upsert', (upsert) => this._onMessages(upsert))

      // Code pairing replaces the QR entirely: WhatsApp shows the user a prompt
      // on the number itself, so nobody has to point a camera at a screen.
      if (this.pairingPhone && !state.creds.registered) {
        this._requestPairingCode(sock).catch((err) =>
          this.logger.error({ err: err.message }, 'pairing code request failed'),
        )
      }
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

  /**
   * Ask WhatsApp for an 8-character linking code for `this.pairingPhone`.
   * The socket must be live first, hence the delay.
   */
  async _requestPairingCode(sock) {
    await new Promise((resolve) => setTimeout(resolve, PAIRING_CODE_DELAY_MS))
    if (this.sock !== sock) return // socket was replaced while we waited

    const code = await sock.requestPairingCode(this.pairingPhone)
    this.pairingCode = code
    this.qr = null
    this.logger.info({ phone: this.pairingPhone }, 'pairing code issued')
    // Force the event even if the status was already PAIRING — the code itself
    // is what changed, and the admin panel is waiting for it.
    this.status = Status.STARTING
    this._setStatus(Status.PAIRING)
  }

  async _onConnectionUpdate({ connection, lastDisconnect, qr }) {
    // With code pairing there is nothing to scan; a QR here is just Baileys
    // offering the other method.
    if (qr && this.pairingPhone) return

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
      this.linkCycles = 0
      this.pairingPhone = null // linked; a later reconnect must not re-request a code
      this.phone = jidToPhone(this.sock?.user?.id ?? '')
      this.connectedAt = new Date().toISOString()
      this.lastError = null
      this._setStatus(Status.CONNECTED)
      return
    }

    if (connection !== 'close') return

    const code = lastDisconnect?.error?.output?.statusCode
    this.lastError = lastDisconnect?.error?.message ?? null
    const wasLinking = this.status === Status.QR || this.status === Status.PAIRING
    this.sock = null

    if (this.stopping) {
      this._setStatus(Status.DISCONNECTED)
      return
    }

    // The link window ran out of refs before anyone finished pairing.
    // Credentials are half-written at this point (requestPairingCode marks them
    // "registered" the moment the code is issued), so logging in with them
    // would earn a 401 and strand the session. Wipe and open a fresh window
    // instead — the operator is still standing at the linking screen.
    if (wasLinking && code === DisconnectReason.timedOut) {
      if (this.linkCycles >= MAX_LINK_CYCLES) {
        this.logger.warn(
          { cycles: this.linkCycles },
          'link window expired too many times — press link again to retry',
        )
        await this._wipeCreds()
        this._setStatus(Status.DISCONNECTED)
        return
      }
      this.linkCycles += 1
      this.logger.info(
        { cycle: this.linkCycles },
        'link window expired, wiping unconfirmed credentials and reopening',
      )
      await this._wipeCreds()
      this.reconnectAttempts = 0
      this._scheduleReconnect(0)
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
        { from: message.from, phone: message.phone, type: message.type },
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

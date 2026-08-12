/**
 * Signed webhook delivery to the Python bot.
 *
 * Every payload is signed with HMAC-SHA256 over the exact JSON body using the
 * shared bridge token, so the receiver can reject anything not coming from us
 * (the bot's webhook port is reachable from localhost by any process).
 */

import crypto from 'node:crypto'

const MAX_ATTEMPTS = 3
const BASE_DELAY_MS = 500
const TIMEOUT_MS = 15000

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

export function sign(body, secret) {
  return 'sha256=' + crypto.createHmac('sha256', secret).update(body).digest('hex')
}

/**
 * POST a payload to the webhook URL, retrying transient failures.
 *
 * Never throws — a dead consumer must not take the WhatsApp socket down with it.
 */
export async function deliver(url, secret, payload, logger) {
  if (!url) {
    logger.debug({ event: payload.event }, 'no webhook url configured, dropping event')
    return false
  }

  const body = JSON.stringify(payload)
  const headers = {
    'Content-Type': 'application/json',
    'X-Bridge-Signature': sign(body, secret),
    'X-Bridge-Event': payload.event,
  }

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers,
        body,
        signal: AbortSignal.timeout(TIMEOUT_MS),
      })

      if (resp.ok) return true

      // 4xx (except 429) means the consumer rejected the payload — retrying
      // the same body will not change the answer.
      if (resp.status >= 400 && resp.status < 500 && resp.status !== 429) {
        logger.warn(
          { status: resp.status, event: payload.event },
          'webhook rejected, not retrying',
        )
        return false
      }

      logger.warn({ status: resp.status, attempt }, 'webhook delivery failed')
    } catch (err) {
      logger.warn({ err: err.message, attempt }, 'webhook delivery error')
    }

    if (attempt < MAX_ATTEMPTS) await sleep(BASE_DELAY_MS * 2 ** (attempt - 1))
  }

  return false
}

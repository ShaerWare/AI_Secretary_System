# WhatsApp Bridge — self-hosted provider

Links a regular phone (WhatsApp or WhatsApp Business app) over the multi-device
protocol via QR and exposes it as a small REST + webhook API. This is the role
Wazzup / Green API / Radist play, except it runs on our own host — no third-party
contract and no message content leaving the server.

Built on [Baileys](https://github.com/WhiskeySockets/Baileys) (WebSocket, no
Chromium, no Puppeteer).

```
phone ──QR──► whatsapp-bridge (:8005) ──webhook──► whatsapp_bot (:8003)
                    ▲                                     │
                    └────────── REST: send / read ─────────┘
```

## Run

```bash
cd services/whatsapp-bridge
npm install
WHATSAPP_BRIDGE_TOKEN=$(openssl rand -hex 24) npm start
```

Put the same token in the project's `.env` so the orchestrator and the bot can
talk to the bridge:

```bash
WHATSAPP_PROVIDER=bridge              # only needed for standalone bot mode
WHATSAPP_BRIDGE_URL=http://127.0.0.1:8005
WHATSAPP_BRIDGE_TOKEN=<same token>
WHATSAPP_BRIDGE_CALLBACK_HOST=127.0.0.1   # where the bridge reaches the bot
```

Docker:

```bash
docker build -t ai-secretary-whatsapp-bridge services/whatsapp-bridge
docker run -d --name wa-bridge -p 8005:8005 \
  -e WHATSAPP_BRIDGE_TOKEN=<token> \
  -v wa-bridge-data:/data \
  ai-secretary-whatsapp-bridge
```

The `/data` volume holds linked-device credentials — **without it every restart
demands a fresh QR scan**.

### Environment

| Variable | Default | Meaning |
|---|---|---|
| `WHATSAPP_BRIDGE_TOKEN` | — | Shared secret, **required**. Also signs webhooks. |
| `WHATSAPP_BRIDGE_PORT` | `8005` | Listen port. |
| `WHATSAPP_BRIDGE_HOST` | `127.0.0.1` | Bind address (`0.0.0.0` in Docker). |
| `WHATSAPP_BRIDGE_DATA` | `./data` | Credentials directory, one subdir per session. |
| `LOG_LEVEL` | `info` | pino level. |

## Linking a phone

In the admin panel: WhatsApp → instance with `provider = bridge` → **Подключить
телефон** → scan the QR from *Settings → Linked devices*. Credentials persist,
so the bot re-attaches silently after a restart.

The whole flow is also reachable over the orchestrator API:
`POST /admin/whatsapp/instances/{id}/bridge/start`, `GET …/bridge/status`,
`POST …/bridge/stop`, `POST …/bridge/logout`.

## API

Every route except `/health` requires `X-Bridge-Token` (or `Authorization:
Bearer`). One session id == one WhatsApp instance id.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness + all session states. |
| `GET` | `/sessions` | List sessions. |
| `POST` | `/sessions/:id/start` | Open the socket. Body: `{webhook_url}`. |
| `GET` | `/sessions/:id` | State: `idle`/`starting`/`qr`/`connected`/`disconnected`/`logged_out` (+ `qr` data-URL while pairing). |
| `POST` | `/sessions/:id/stop` | Close the socket, keep credentials. |
| `POST` | `/sessions/:id/logout` | Unlink the phone and wipe credentials. |
| `POST` | `/sessions/:id/messages` | Send. Body: `{to, type, text \| url, caption, filename, mimetype, voice}`. |
| `POST` | `/sessions/:id/read` | Blue checkmarks. Body: `{message_id}`. |
| `POST` | `/sessions/:id/presence` | Typing indicator. Body: `{to, state}`. |
| `GET` | `/sessions/:id/media/:messageId` | Download media from an incoming message. |

## Webhooks

The bridge POSTs to the `webhook_url` given at start, signing the raw body with
HMAC-SHA256 in `X-Bridge-Signature: sha256=<hex>`. Delivery retries 3 times with
backoff; a dead consumer never takes the WhatsApp socket down.

```jsonc
// event: "message"
{
  "event": "message",
  "session_id": "support-wa",
  "message": {
    "id": "3EB0…", "from": "79001234567", "jid": "79001234567@s.whatsapp.net",
    "chat_type": "direct", "sender_name": "Иван", "timestamp": 1712345678,
    "type": "text",              // text | button_reply | list_reply | image | audio | document | video | sticker | location | contact
    "text": "здравствуйте",
    "reply_id": null,            // set for button_reply / list_reply
    "quoted_id": null
  }
}

// event: "connection"
{"event": "connection", "session_id": "support-wa", "status": "connected", "phone": "79991112233", "last_error": null}
```

## Limits worth knowing

* **No interactive buttons or list pickers.** They are a Cloud API feature; a
  linked phone can't render them. The Python side emulates them as a numbered
  text menu (`whatsapp_bot/services/choices.py`) and maps the reply back to the
  original `reply_id`, so existing funnels keep working.
* **No message templates** and no 24-hour window — a linked phone just sends
  messages. `send_template` degrades to plain text.
* **Unofficial protocol.** This is the same mechanism every QR-based provider
  uses. WhatsApp can unlink or ban a number that behaves like a spammer; keep
  the assistant reactive (reply to inbound), not a broadcaster.
* **One phone, one session.** Opening WhatsApp Web elsewhere with the same
  account can replace this connection — the bridge detects that and stays down
  rather than fighting for the slot.
* **Group chats are ignored** by the bot to avoid pulling the assistant into
  every group the phone belongs to.

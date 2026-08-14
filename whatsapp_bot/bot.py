"""WhatsApp bot entry point.

Run with:  python -m whatsapp_bot

Starts a FastAPI webhook server that receives messages from WhatsApp Cloud API
and routes them through the LLM pipeline.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import BackgroundTasks, FastAPI, Query, Request, Response

from .config import (
    get_wa_instance_id,
    get_whatsapp_settings,
    load_config_from_api,
)
from .handlers.interactive import handle_interactive_reply
from .handlers.messages import handle_text_message
from .services import choices
from .services.whatsapp_client import get_whatsapp_client
from .state import get_bot_config, set_bot_config


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("WhatsApp bot starting up")
    # Initialize sales database
    from .sales.database import close_sales_db, get_sales_db

    await get_sales_db()

    # Self-hosted provider: tell the bridge where to deliver incoming messages.
    # Deferred to a task so the webhook endpoint is already accepting requests
    # by the time the bridge replays the session's connection state.
    bridge_task: asyncio.Task | None = None
    if _is_bridge_provider():
        bridge_task = asyncio.create_task(_register_with_bridge())

    yield

    # Cleanup
    if bridge_task and not bridge_task.done():
        bridge_task.cancel()
    await close_sales_db()
    client = get_whatsapp_client()
    await client.close()
    logger.info("WhatsApp bot shut down")


def _is_bridge_provider() -> bool:
    """True when this instance is served by the self-hosted bridge."""
    bot_config = get_bot_config()
    if bot_config:
        return bot_config.provider == "bridge"
    return get_whatsapp_settings().provider == "bridge"


def _bridge_webhook_url() -> str:
    """URL the bridge should POST incoming messages to."""
    settings = get_whatsapp_settings()
    bot_config = get_bot_config()
    port = bot_config.webhook_port if bot_config else settings.webhook_port
    return f"http://{settings.bridge_callback_host}:{port}/bridge/webhook"


async def _register_with_bridge(delay: float = 1.0) -> None:
    """Open (or re-attach) the bridge session for this instance."""
    await asyncio.sleep(delay)
    client = get_whatsapp_client()
    webhook_url = _bridge_webhook_url()

    try:
        state = await client.start_session(webhook_url)
        logger.info(
            "Bridge session %s registered (status=%s, phone=%s)",
            state.get("session_id"),
            state.get("status"),
            state.get("phone"),
        )
        if state.get("status") == "qr":
            logger.warning(
                "Bridge session is waiting for a QR scan — "
                "open the WhatsApp instance in the admin panel to link the phone"
            )
    except Exception:
        logger.exception("Failed to register with the WhatsApp bridge at %s", webhook_url)


app = FastAPI(title="WhatsApp Bot Webhook", lifespan=lifespan)


@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
) -> Response:
    """Webhook verification endpoint for Meta.

    Meta sends a GET request with hub.mode, hub.verify_token, and hub.challenge.
    We verify the token and return the challenge to confirm the webhook.
    """
    bot_config = get_bot_config()
    settings = get_whatsapp_settings()
    expected_token = bot_config.verify_token if bot_config else settings.verify_token

    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        logger.info("Webhook verified successfully")
        return Response(content=hub_challenge, media_type="text/plain")

    logger.warning("Webhook verification failed: invalid token")
    return Response(content="Forbidden", status_code=403)


@app.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    """Receive incoming messages from WhatsApp Cloud API.

    Returns 200 immediately and processes messages in the background
    to avoid webhook timeout (Meta expects response within 5s).
    """
    body = await request.body()

    # Verify signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    client = get_whatsapp_client()
    if not client.verify_webhook_signature(body, signature):
        logger.warning("Invalid webhook signature")
        return {"status": "error", "message": "Invalid signature"}

    data = await request.json()

    # Extract messages from webhook payload
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            # Process incoming messages
            for message in value.get("messages", []):
                background_tasks.add_task(_dispatch_message, message)

            # Log delivery statuses (optional)
            for status in value.get("statuses", []):
                _log_status(status)

    return {"status": "ok"}


@app.post("/bridge/webhook")
async def receive_bridge_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    """Receive events from the self-hosted bridge (`services/whatsapp-bridge`).

    Payload: ``{"event": "message"|"connection", "session_id": ..., ...}``,
    signed with HMAC-SHA256 over the raw body in ``X-Bridge-Signature``.
    """
    body = await request.body()

    client = get_whatsapp_client()
    signature = request.headers.get("X-Bridge-Signature", "")
    if not client.verify_webhook_signature(body, signature):
        logger.warning("Invalid bridge webhook signature")
        return {"status": "error", "message": "Invalid signature"}

    data = await request.json()
    event = data.get("event", "")

    if event == "message":
        message = data.get("message") or {}
        if message:
            background_tasks.add_task(_dispatch_bridge_message, message)
    elif event == "connection":
        logger.info(
            "Bridge session %s: status=%s phone=%s%s",
            data.get("session_id"),
            data.get("status"),
            data.get("phone"),
            f" error={data['last_error']}" if data.get("last_error") else "",
        )
    else:
        logger.debug("Unhandled bridge event: %s", event)

    return {"status": "ok"}


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    bot_config = get_bot_config()
    return {
        "status": "ok",
        "service": "whatsapp_bot",
        "instance_id": bot_config.instance_id if bot_config else None,
        "name": bot_config.name if bot_config else "standalone",
    }


async def _dispatch_message(message: dict[str, Any]) -> None:
    """Route an incoming message to the appropriate handler."""
    msg_type = message.get("type", "")
    phone = message.get("from", "")
    message_id = message.get("id", "")

    if not phone:
        return

    logger.info("Incoming %s message from %s", msg_type, phone)

    if msg_type == "text":
        text = message.get("text", {}).get("body", "")
        if text:
            await handle_text_message(phone, text, message_id)

    elif msg_type == "interactive":
        interactive = message.get("interactive", {})
        await handle_interactive_reply(phone, interactive)

    # TODO (WA-12): Handle audio/voice messages
    # elif msg_type == "audio":
    #     await handle_audio_message(phone, message, message_id)

    else:
        logger.debug("Unhandled message type: %s from %s", msg_type, phone)


async def _dispatch_bridge_message(message: dict[str, Any]) -> None:
    """Route a normalized message coming from the self-hosted bridge."""
    msg_type = message.get("type", "")
    # `from` is the address we can reply to — a phone number, or an opaque
    # "@lid" JID for users WhatsApp no longer exposes a number for. `phone` is
    # the real number when disclosed, and is only for logging and identity.
    phone = message.get("from", "")
    real_phone = message.get("phone")
    message_id = message.get("id", "")
    text = message.get("text", "") or ""

    if not phone:
        return

    # Group chats would pull the assistant into every unrelated conversation the
    # linked phone belongs to.
    if message.get("chat_type") == "group":
        logger.debug("Ignoring group message from %s", phone)
        return

    logger.info(
        "Incoming %s message from %s%s (bridge)",
        msg_type,
        phone,
        f" (phone {real_phone})" if real_phone and real_phone != phone else "",
    )

    if msg_type == "text":
        # A linked phone can't render buttons, so menus are sent as numbered
        # text — map "2" back to the reply_id the funnel expects.
        resolved = choices.resolve(phone, text)
        if resolved:
            kind, reply_id = resolved
            await handle_interactive_reply(
                phone, {"type": kind, kind: {"id": reply_id, "title": text}}
            )
            return
        await handle_text_message(phone, text, message_id)

    elif msg_type in ("button_reply", "list_reply"):
        reply_id = message.get("reply_id", "")
        if reply_id:
            choices.clear(phone)
            await handle_interactive_reply(
                phone, {"type": msg_type, msg_type: {"id": reply_id, "title": text}}
            )

    elif msg_type in ("image", "audio", "video", "document", "sticker"):
        # TODO (WA-13): download via the bridge and run through STT / file extraction.
        logger.info("Unsupported media type %s from %s", msg_type, phone)
        if text:
            # A caption still carries intent — treat it as the message.
            await handle_text_message(phone, text, message_id)
        else:
            client = get_whatsapp_client()
            await client.send_text(
                to=phone,
                text="Пока я понимаю только текстовые сообщения. Напишите, пожалуйста, текстом.",
            )

    else:
        logger.debug("Unhandled bridge message type: %s from %s", msg_type, phone)


def _log_status(status: dict[str, Any]) -> None:
    """Log message delivery status updates."""
    recipient = status.get("recipient_id", "?")
    status_value = status.get("status", "?")
    logger.debug("Status update: %s → %s", recipient, status_value)


async def main() -> None:
    """Main entry point — load config and start webhook server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Check for multi-instance mode
    instance_id = get_wa_instance_id()

    if instance_id:
        logger.info(f"Multi-instance mode: loading config for {instance_id}")
        try:
            bot_config = await load_config_from_api(instance_id)
            set_bot_config(bot_config)
            logger.info(f"Loaded config for WhatsApp bot: {bot_config.name}")
            logger.info(f"LLM backend: {bot_config.llm_backend}")
            logger.info(f"Provider: {bot_config.provider}")
            if bot_config.provider == "bridge":
                logger.info(f"Bridge URL: {bot_config.bridge_url}")
            else:
                logger.info(f"Phone Number ID: {bot_config.phone_number_id}")
        except Exception as e:
            logger.error(f"Failed to load config from API: {e}")
            logger.info("Falling back to .env configuration")
    else:
        logger.info("Standalone mode: using .env configuration")

    settings = get_whatsapp_settings()
    bot_config = get_bot_config()
    port = bot_config.webhook_port if bot_config else settings.webhook_port

    # Meta must reach the webhook from the internet, so the Cloud provider binds
    # whatever the settings say (0.0.0.0 by default, behind nginx). The bridge
    # provider is a local process talking to a local process — a public bind
    # there just hands the internet an open port to scan.
    if _is_bridge_provider() and settings.webhook_host == "0.0.0.0":
        host = "127.0.0.1"
        logger.info("Bridge provider: binding webhook to 127.0.0.1 (local-only)")
    else:
        host = settings.webhook_host

    logger.info(f"Starting WhatsApp webhook server on {host}:{port}")

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


def run() -> None:
    """Entry point for ``python -m whatsapp_bot``."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

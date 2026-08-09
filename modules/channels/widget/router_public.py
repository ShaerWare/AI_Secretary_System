"""Public widget endpoints — no authentication required.

Serves the embeddable widget JS, chat sessions, streaming responses,
and contact form submissions. CRM integration (amoCRM lead/contact
creation) is handled reactively via EventBus — see modules/crm/startup.py.
"""

import html
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from cloud_llm_service import CloudLLMService
from modules.channels.widget.service import widget_instance_service
from modules.chat.service import chat_service
from modules.core.service import config_service
from modules.llm.persona import normalize_persona_id
from modules.llm.service import cloud_provider_service


logger = logging.getLogger(__name__)

router = APIRouter(tags=["widget-public"])


# ============== Helpers ==============


def _escape_js_string(s: str) -> str:
    """Escape a string for safe use in JavaScript."""
    return s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")


# ============== Endpoints ==============


@router.get("/widget.js")
async def get_widget_script(request: Request, instance: Optional[str] = None):
    """Динамически генерируемый скрипт виджета.

    Args:
        instance: Optional widget instance ID. If not provided, uses legacy config or 'default' instance.
    """
    config = None

    # Try to load from widget instance if specified
    if instance:
        instance_data = await widget_instance_service.get_instance(instance)
        if instance_data:
            config = instance_data
        else:
            return Response(
                content=f"// Widget instance '{instance}' not found",
                media_type="application/javascript",
                status_code=404,
            )
    else:
        # Try default instance first, fallback to legacy config
        instance_data = await widget_instance_service.get_instance("default")
        if instance_data:
            config = instance_data
        else:
            # Fallback to legacy config
            config = await config_service.get_widget()

    # Проверяем включен ли виджет
    if not config.get("enabled", False):
        return Response(content="// Widget is disabled", media_type="application/javascript")

    # Проверяем домен (если указаны разрешенные)
    origin = request.headers.get("origin", "") or request.headers.get("referer", "")
    allowed_domains = config.get("allowed_domains", [])
    if allowed_domains and origin:
        origin_domain = (
            origin.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
        )
        # Normalize allowed_domains: strip protocol prefix for comparison
        normalized = [
            d.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
            for d in allowed_domains
        ]
        if not any(d in origin_domain for d in normalized):
            return Response(
                content=f"// Widget not allowed for domain: {origin_domain}",
                media_type="application/javascript",
            )

    # Определяем API URL
    api_url = config.get("tunnel_url", "").strip()
    if not api_url:
        # Используем текущий хост если tunnel_url не указан
        api_url = str(request.base_url).rstrip("/")

    # Читаем базовый скрипт виджета
    widget_path = Path(__file__).parents[3] / "web-widget" / "ai-chat-widget.js"
    if not widget_path.exists():
        return Response(
            content="// Widget script not found",
            media_type="application/javascript",
            status_code=404,
        )

    widget_js = widget_path.read_text(encoding="utf-8")

    # Генерируем скрипт с настройками
    instance_id = instance or config.get("id", "default")
    settings_js = f"""
// Auto-generated widget settings
// Instance: {instance_id}
window.aiChatSettings = {{
  apiUrl: '{api_url}',
  instanceId: '{instance_id}',
  title: '{config.get("title", "AI Ассистент")}',
  greeting: '{_escape_js_string(config.get("greeting") or "")}',
  placeholder: '{_escape_js_string(config.get("placeholder") or "")}',
  primaryColor: '{config.get("primary_color", "#c2410c")}',
  placeholderColor: '{config.get("placeholder_color") or ""}',
  placeholderFont: '{_escape_js_string(config.get("placeholder_font") or "")}',
  buttonIcon: '{config.get("button_icon") or "chat"}',
  position: '{config.get("position", "right")}',
  buttonSize: {config.get("button_size", 60)},
  buttonOffsetBottom: {config.get("button_offset_bottom", 20)},
  buttonOffsetSide: {config.get("button_offset_side", 20)}
}};

"""
    full_script = settings_js + widget_js

    return Response(
        content=full_script,
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/widget/status")
async def get_widget_status(instance: Optional[str] = None):
    """Public endpoint — check if a widget instance is enabled.

    Used by the widget JS at runtime to hide itself when disabled.
    No authentication required.
    """
    instance_id = instance or "default"
    instance_data = await widget_instance_service.get_instance(instance_id)
    if not instance_data:
        return {"enabled": False}
    return {"enabled": bool(instance_data.get("enabled", False))}


@router.post("/widget/chat/session")
async def widget_create_session(request: Request):
    """Public: create a chat session for a widget instance."""
    body = await request.json()
    instance_id = body.get("source_id", "default")

    # Verify widget instance exists and is enabled
    instance_data = await widget_instance_service.get_instance(instance_id)
    if not instance_data or not instance_data.get("enabled"):
        raise HTTPException(status_code=404, detail="Widget not found or disabled")

    system_prompt = instance_data.get("system_prompt")
    session = await chat_service.create_session(
        None,
        system_prompt,
        "widget",
        instance_id,
        llm_persona=normalize_persona_id(instance_data.get("llm_persona")),
    )

    # Collect visitor metadata (server-side + client-side)
    client_metadata = body.get("metadata") or {}
    visitor_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or request.headers.get("x-real-ip")
        or (request.client.host if request.client else None)
    )
    metadata = {
        "ip": visitor_ip,
        "user_agent": request.headers.get("user-agent"),
        "page_url": client_metadata.get("page_url"),
        "page_title": client_metadata.get("page_title"),
        "referrer": client_metadata.get("referrer"),
        "utm_source": client_metadata.get("utm_source"),
        "utm_medium": client_metadata.get("utm_medium"),
        "utm_campaign": client_metadata.get("utm_campaign"),
        "language": client_metadata.get("language"),
        "screen": client_metadata.get("screen"),
    }
    # Remove None values for compact storage
    metadata = {k: v for k, v in metadata.items() if v}

    # Save visitor_metadata to session
    if metadata:
        try:
            from db.database import AsyncSessionLocal
            from db.models import ChatSession as ChatSessionModel

            async with AsyncSessionLocal() as db_session:
                from sqlalchemy import update

                await db_session.execute(
                    update(ChatSessionModel)
                    .where(ChatSessionModel.id == session["id"])
                    .values(visitor_metadata=json.dumps(metadata, ensure_ascii=False))
                )
                await db_session.commit()
            session["visitor_metadata"] = metadata
        except Exception:
            logger.debug("Failed to save visitor metadata for session %s", session.get("id"))

    # Track widget visitor as user identity
    try:
        from modules.core.service import user_identity_service

        await user_identity_service.find_or_create(
            provider="widget",
            provider_uid=session["id"],
            display_name=f"Widget visitor ({instance_id})",
            metadata_dict=metadata if metadata else None,
        )
    except Exception:
        logger.debug(
            "Failed to track widget identity for session %s", session.get("id"), exc_info=True
        )

    return {"session": session}


@router.get("/widget/chat/session/{session_id}")
async def widget_get_session(session_id: str):
    """Public: retrieve widget session with message history."""
    session = await chat_service.get_session(session_id)
    if not session or session.get("source") != "widget":
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session}


@router.post("/widget/chat/session/{session_id}/stream")
async def widget_stream_message(request: Request, session_id: str):
    """Public: send a message and get streaming response for widget."""
    body = await request.json()
    content = body.get("content", "")
    instance_id = body.get("widget_instance_id", "default")

    if not content:
        raise HTTPException(status_code=400, detail="Message content required")

    session = await chat_service.get_session(session_id)
    if not session or session.get("source") != "widget":
        raise HTTPException(status_code=404, detail="Session not found")

    # Determine LLM from widget config
    from app.dependencies import get_container

    container = get_container()
    active_llm = container.llm_service
    custom_prompt = None
    # Persona (LLM preset) backing this widget — supplies the system prompt when
    # the instance has none of its own, and always supplies generation params.
    persona_id = None
    gen_params = None

    widget = await widget_instance_service.get_instance(instance_id)

    # Per-instance rate limiting
    if widget:
        rl_count = widget.get("rate_limit_count")
        rl_hours = widget.get("rate_limit_hours")
        if rl_count and rl_hours:
            since = datetime.utcnow() - timedelta(hours=rl_hours)
            msg_count = await chat_service.count_messages(session_id, "user", since)
            if msg_count >= rl_count:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded: {rl_count} messages per {rl_hours}h",
                )

    if widget:
        backend = widget.get("llm_backend")
        if backend and backend.startswith("cloud:"):
            provider_id = backend.split(":", 1)[1]
            try:
                provider_config = await cloud_provider_service.get_provider_with_key(provider_id)
                if provider_config:
                    active_llm = CloudLLMService(provider_config)
            except Exception as e:
                logger.warning(f"Widget LLM override failed: {e}")
        custom_prompt = widget.get("system_prompt")
        persona_id = normalize_persona_id(widget.get("llm_persona"))
        gen_params = widget.get("llm_params")

    if not active_llm:
        raise HTTPException(status_code=503, detail="LLM service not available")

    user_msg = await chat_service.add_message(session_id, "user", content)

    # Publish WidgetSessionCreated on first message (fire-and-forget → CRM creates lead)
    if not session.get("amocrm_lead_id"):
        import asyncio

        from app.dependencies import get_container
        from modules.channels.widget.events import WidgetSessionCreated

        metadata = session.get("visitor_metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        asyncio.create_task(
            get_container().event_bus.publish(
                WidgetSessionCreated(
                    session_id=session_id,
                    first_message=content,
                    visitor_metadata=metadata,
                )
            )
        )

    # Resolve RAG (collections) + web_search from the widget instance config,
    # then delegate generation to the shared chat facade so the widget gets the
    # same agentic RAG (knowledge_search) + web_search loop as the admin/mobile
    # chat path. (The old bare LLM call ignored the widget's collections.)
    from modules.chat.facade import ChatServiceImpl, chat_service_facade
    from modules.chat.router import _resolve_rag_config

    rag_mode, collection_ids = await _resolve_rag_config(session, widget_instance_id=instance_id)
    web_search = bool(widget.get("web_search_enabled")) if widget else False

    facade = chat_service_facade or ChatServiceImpl(container)

    # Capture lead_id for note-writing after stream completes
    lead_id = session.get("amocrm_lead_id")

    async def generate_stream():
        full_response: list[str] = []
        try:
            async for chunk in facade.stream_message(
                session_id,
                content,
                llm_service=active_llm,
                session_data=session,
                user_msg=user_msg,
                system_prompt=custom_prompt,
                persona_id=persona_id,
                gen_params=gen_params,
                rag_mode=rag_mode,
                collection_ids=collection_ids,
                web_search=web_search,
            ):
                if chunk.get("type") == "chunk" and chunk.get("content"):
                    full_response.append(chunk["content"])
                # Serialize StreamChunk to the widget's SSE wire format. `done`
                # becomes the [DONE] sentinel the embed JS expects; tool_start/
                # tool_end pass through (embed JS ignores unknown event types).
                if chunk.get("done"):
                    yield "data: [DONE]\n\n"
                else:
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

            response_text = "".join(full_response)

            # Publish WidgetMessageSent (fire-and-forget → CRM appends note)
            if lead_id and response_text:
                import asyncio

                from modules.channels.widget.events import WidgetMessageSent

                asyncio.create_task(
                    container.event_bus.publish(
                        WidgetMessageSent(
                            session_id=session_id,
                            lead_id=lead_id,
                            user_message=content,
                            assistant_response=response_text,
                        )
                    )
                )
        except Exception as e:
            logger.error(f"❌ Widget chat stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/widget/chat/session/{session_id}/contacts")
async def widget_submit_contacts(request: Request, session_id: str):
    """Public: submit contact info from widget lead form.

    Publishes WidgetContactSubmitted event; CRM domain handles amoCRM
    contact/lead creation reactively.
    """
    body = await request.json()
    name = body.get("name", "").strip()
    phone = body.get("phone", "").strip()
    email = body.get("email", "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if not phone and not email:
        raise HTTPException(status_code=400, detail="Phone or email is required")

    session = await chat_service.get_session(session_id)
    if not session or session.get("source") != "widget":
        raise HTTPException(status_code=404, detail="Session not found")

    from app.dependencies import get_container
    from modules.channels.widget.events import WidgetContactSubmitted

    metadata = session.get("visitor_metadata") or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)

    try:
        await get_container().event_bus.publish(
            WidgetContactSubmitted(
                session_id=session_id,
                contact_name=name,
                phone=phone,
                email=email,
                visitor_metadata=metadata,
            )
        )
    except Exception:
        logger.error(
            "Failed to publish WidgetContactSubmitted for session %s",
            session_id,
            exc_info=True,
        )

    return {"ok": True}


# ============== Landing lead form → Telegram ==============

# Mounted under the already nginx-proxied /widget/ prefix so the static landing
# site can POST here without a dedicated nginx location block.
_LEAD_LOCALE_NAMES = {"ru": "🇷🇺 RU", "en": "🇬🇧 EN", "kk": "🇰🇿 KK"}


@router.post("/widget/lead")
async def submit_landing_lead(request: Request):
    """Public: landing-page lead form → notify owner via Telegram.

    Reads bot token + target chat id from env (LEAD_TELEGRAM_BOT_TOKEN,
    LEAD_TELEGRAM_CHAT_ID) so no secrets live in the static site. Anti-spam:
    a hidden honeypot field ("company") — bots fill it, humans don't.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Honeypot: silently accept (so the bot thinks it succeeded) but drop it.
    if (body.get("company") or "").strip():
        logger.info("Landing lead dropped (honeypot triggered)")
        return {"ok": True}

    name = (body.get("name") or "").strip()[:200]
    contact = (body.get("contact") or "").strip()[:200]
    role = (body.get("role") or "").strip()[:200]
    locale = (body.get("locale") or "").strip().lower()[:8]
    page = (body.get("page") or "").strip()[:300]

    if not name or not contact:
        raise HTTPException(status_code=400, detail="Name and contact are required")

    token = os.getenv("LEAD_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("LEAD_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        logger.error("Landing lead delivery not configured (LEAD_TELEGRAM_* missing)")
        raise HTTPException(status_code=503, detail="Lead delivery is not configured")

    visitor_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or request.headers.get("x-real-ip")
        or (request.client.host if request.client else "")
    )

    lines = [
        "🔔 <b>Новая заявка с лендинга</b>",
        "",
        f"👤 <b>Имя:</b> {html.escape(name)}",
        f"📞 <b>Контакт:</b> {html.escape(contact)}",
    ]
    if role:
        lines.append(f"🎯 <b>Какой ассистент:</b> {html.escape(role)}")
    lines.append(f"🌐 <b>Язык:</b> {_LEAD_LOCALE_NAMES.get(locale, locale or '—')}")
    if page:
        lines.append(f"🔗 <b>Страница:</b> {html.escape(page)}")
    if visitor_ip:
        lines.append(f"🖥 <b>IP:</b> {html.escape(visitor_ip)}")
    lines.append(f"🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    text = "\n".join(lines)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
        if resp.status_code != 200:
            logger.error("Telegram lead notify failed: %s %s", resp.status_code, resp.text[:300])
            raise HTTPException(status_code=502, detail="Failed to deliver lead")
    except HTTPException:
        raise
    except Exception:
        logger.error("Telegram lead notify error", exc_info=True)
        raise HTTPException(status_code=502, detail="Failed to deliver lead")

    logger.info("Landing lead delivered to Telegram (locale=%s, role=%s)", locale, role or "-")
    return {"ok": True}

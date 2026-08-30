"""CRM domain startup: event subscriptions for channel → amoCRM integration."""

import logging


logger = logging.getLogger(__name__)


async def setup_crm_event_subscriptions(event_bus) -> None:
    """Register CRM event handlers for the widget and WhatsApp channels."""
    from modules.channels.whatsapp.events import (
        WhatsAppMessageSent,
        WhatsAppSessionCreated,
    )
    from modules.channels.widget.events import (
        WidgetContactSubmitted,
        WidgetMessageSent,
        WidgetSessionCreated,
    )

    async def on_widget_session_created(event: WidgetSessionCreated) -> None:
        """Create amoCRM lead on first widget message."""
        await _handle_widget_session_created(event)

    async def on_widget_message_sent(event: WidgetMessageSent) -> None:
        """Append conversation turn to amoCRM lead notes."""
        await _handle_widget_message_sent(event)

    async def on_widget_contact_submitted(event: WidgetContactSubmitted) -> None:
        """Create amoCRM contact and link to lead."""
        await _handle_widget_contact_submitted(event)

    async def on_whatsapp_session_created(event: WhatsAppSessionCreated) -> None:
        """Create amoCRM contact + lead for a new WhatsApp conversation."""
        await _handle_whatsapp_session_created(event)

    async def on_whatsapp_message_sent(event: WhatsAppMessageSent) -> None:
        """Append conversation turn to amoCRM lead notes."""
        await _handle_widget_message_sent(event)

    event_bus.subscribe(WidgetSessionCreated, on_widget_session_created)
    event_bus.subscribe(WidgetMessageSent, on_widget_message_sent)
    event_bus.subscribe(WidgetContactSubmitted, on_widget_contact_submitted)
    event_bus.subscribe(WhatsAppSessionCreated, on_whatsapp_session_created)
    event_bus.subscribe(WhatsAppMessageSent, on_whatsapp_message_sent)
    logger.info("CRM event subscriptions registered (Widget + WhatsApp → amoCRM)")


async def _get_amocrm_config() -> dict | None:
    """Load amoCRM config with secrets. Returns None if not connected."""
    from modules.crm.service import amocrm_service

    config = await amocrm_service.get_config_with_secrets()
    if not config or not config.get("access_token"):
        return None
    return config


async def _save_session_field(session_id: str, **fields) -> None:
    """Persist amoCRM IDs on a chat session."""
    from sqlalchemy import update as sa_update

    from db.database import AsyncSessionLocal
    from db.models import ChatSession as ChatSessionModel

    async with AsyncSessionLocal() as db_session:
        await db_session.execute(
            sa_update(ChatSessionModel).where(ChatSessionModel.id == session_id).values(**fields)
        )
        await db_session.commit()


async def _handle_widget_session_created(event) -> None:
    """Create amoCRM lead for a new widget session."""
    try:
        from app.services import amocrm_service

        config = await _get_amocrm_config()
        if not config or not config.get("auto_create_lead"):
            return

        subdomain = config["subdomain"]
        access_token = config["access_token"]
        pipeline_id = config.get("lead_pipeline_id")
        status_id = config.get("lead_status_id")

        metadata = event.visitor_metadata or {}
        page_title = metadata.get("page_title", "")
        page_url = metadata.get("page_url", "")
        lead_name = f"Виджет: {page_title or page_url or event.session_id[:8]}"

        result = await amocrm_service.create_lead(
            subdomain, access_token, lead_name, pipeline_id, status_id
        )

        lead_id = None
        if result and "_embedded" in result and "leads" in result["_embedded"]:
            lead_id = result["_embedded"]["leads"][0].get("id")

        if not lead_id:
            logger.warning("amoCRM create_lead returned no lead ID: %s", result)
            return

        await _save_session_field(event.session_id, amocrm_lead_id=lead_id)

        # Add first message + metadata as note
        note_parts = [f"Первое сообщение: {event.first_message}"]
        if metadata.get("page_url"):
            note_parts.append(f"Страница: {metadata['page_url']}")
        if metadata.get("ip"):
            note_parts.append(f"IP: {metadata['ip']}")
        utm_parts = []
        for key in ("utm_source", "utm_medium", "utm_campaign"):
            if metadata.get(key):
                utm_parts.append(f"{key}={metadata[key]}")
        if utm_parts:
            note_parts.append(f"UTM: {', '.join(utm_parts)}")
        if metadata.get("referrer"):
            note_parts.append(f"Referrer: {metadata['referrer']}")

        await amocrm_service.add_note_to_lead(
            subdomain, access_token, lead_id, "\n".join(note_parts)
        )
        logger.info("Created amoCRM lead %s for widget session %s", lead_id, event.session_id)

    except Exception:
        logger.debug(
            "Failed to create amoCRM lead for session %s",
            event.session_id,
            exc_info=True,
        )


async def _handle_whatsapp_session_created(event) -> None:
    """Create an amoCRM contact + lead for a new WhatsApp conversation.

    Unlike the widget — which only learns a phone if the visitor fills the lead
    form — WhatsApp hands us the sender's number with the very first message. So
    the contact is created up front and linked: a lead a manager cannot call
    back on is not worth much.
    """
    try:
        from app.services import amocrm_service

        config = await _get_amocrm_config()
        if not config or not config.get("auto_create_lead"):
            return

        subdomain = config["subdomain"]
        access_token = config["access_token"]

        # An "@lid" sender discloses no phone; still worth a lead, just without
        # a callable contact.
        is_phone = event.sender.isdigit()
        display = f"+{event.sender}" if is_phone else event.sender

        contact_id = None
        if is_phone:
            contact_result = await amocrm_service.create_contact(
                subdomain,
                access_token,
                display,
                [{"field_code": "PHONE", "values": [{"value": display}]}],
            )
            embedded = (contact_result or {}).get("_embedded", {})
            if embedded.get("contacts"):
                contact_id = embedded["contacts"][0].get("id")

        result = await amocrm_service.create_lead(
            subdomain,
            access_token,
            f"WhatsApp: {display}",
            config.get("lead_pipeline_id"),
            config.get("lead_status_id"),
        )
        embedded = (result or {}).get("_embedded", {})
        lead_id = embedded["leads"][0].get("id") if embedded.get("leads") else None

        if not lead_id:
            logger.warning("amoCRM create_lead returned no lead ID: %s", result)
            return

        fields = {"amocrm_lead_id": lead_id}
        if contact_id:
            fields["amocrm_contact_id"] = contact_id
        await _save_session_field(event.session_id, **fields)

        if contact_id:
            try:
                await amocrm_service.link_contact_to_lead(
                    subdomain, access_token, lead_id, contact_id
                )
            except Exception:
                # A lead without its contact attached is still useful; the number
                # is in the note below either way.
                logger.debug("Failed to link contact %s to lead %s", contact_id, lead_id)

        note = "\n".join(
            [
                f"Канал: WhatsApp ({event.instance_id})",
                f"Отправитель: {display}",
                f"Первое сообщение: {event.first_message}",
            ]
        )
        await amocrm_service.add_note_to_lead(subdomain, access_token, lead_id, note)
        logger.info("Created amoCRM lead %s for WhatsApp session %s", lead_id, event.session_id)

    except Exception:
        logger.debug(
            "Failed to create amoCRM lead for WhatsApp session %s",
            event.session_id,
            exc_info=True,
        )


async def _handle_widget_message_sent(event) -> None:
    """Append conversation turn to amoCRM lead notes."""
    try:
        from app.services import amocrm_service

        config = await _get_amocrm_config()
        if not config:
            return

        note = f"Пользователь: {event.user_message}\nAI: {event.assistant_response}"
        await amocrm_service.add_note_to_lead(
            config["subdomain"], config["access_token"], event.lead_id, note
        )
    except Exception:
        logger.debug("Failed to add note to lead %s", event.lead_id, exc_info=True)


async def _handle_widget_contact_submitted(event) -> None:
    """Create amoCRM contact, link to lead, or create lead with contact."""
    try:
        from app.services import amocrm_service

        config = await _get_amocrm_config()
        if not config:
            return

        subdomain = config["subdomain"]
        access_token = config["access_token"]

        # Build custom_fields for phone/email
        custom_fields = []
        if event.phone:
            custom_fields.append({"field_code": "PHONE", "values": [{"value": event.phone}]})
        if event.email:
            custom_fields.append({"field_code": "EMAIL", "values": [{"value": event.email}]})

        # Create contact
        result = await amocrm_service.create_contact(
            subdomain, access_token, event.contact_name, custom_fields
        )

        contact_id = None
        if result and "_embedded" in result and "contacts" in result["_embedded"]:
            contact_id = result["_embedded"]["contacts"][0].get("id")

        if not contact_id:
            logger.warning("amoCRM create_contact returned no contact ID: %s", result)
            return

        await _save_session_field(event.session_id, amocrm_contact_id=contact_id)

        # Get current session to check for existing lead
        from modules.chat.service import chat_service

        session = await chat_service.get_session(event.session_id)
        lead_id = session.get("amocrm_lead_id") if session else None

        if lead_id:
            # Link contact to existing lead
            await amocrm_service.link_contact_to_lead(subdomain, access_token, lead_id, contact_id)
            note_parts = [f"Контакт оставлен: {event.contact_name}"]
            if event.phone:
                note_parts.append(f"Телефон: {event.phone}")
            if event.email:
                note_parts.append(f"Email: {event.email}")
            await amocrm_service.add_note_to_lead(
                subdomain, access_token, lead_id, "\n".join(note_parts)
            )
        else:
            # No lead yet — create one with this contact
            pipeline_id = config.get("lead_pipeline_id")
            status_id = config.get("lead_status_id")
            metadata = event.visitor_metadata or {}
            page_title = metadata.get("page_title", "")
            page_url = metadata.get("page_url", "")
            lead_name = (
                f"Виджет: {event.contact_name} ({page_title or page_url or event.session_id[:8]})"
            )

            lead_result = await amocrm_service.create_lead(
                subdomain, access_token, lead_name, pipeline_id, status_id, contact_id
            )
            new_lead_id = None
            if lead_result and "_embedded" in lead_result and "leads" in lead_result["_embedded"]:
                new_lead_id = lead_result["_embedded"]["leads"][0].get("id")

            if new_lead_id:
                await _save_session_field(event.session_id, amocrm_lead_id=new_lead_id)

        logger.info(
            "Widget contact submitted: %s (contact=%s, lead=%s)",
            event.contact_name,
            contact_id,
            lead_id,
        )

    except Exception:
        logger.error(
            "Failed to create amoCRM contact for session %s",
            event.session_id,
            exc_info=True,
        )

"""Interactive message handler — button and list replies.

Handles responses to quick-reply buttons and list selections.
This is the WhatsApp equivalent of Telegram's callback_query handler.

Routing by reply_id prefix:
  sales:*  → sales funnel (quiz, DIY, basic, custom paths)
  faq:*    → full FAQ navigation
  tz:*     → TZ quiz (placeholder)
  nav:*    → generic navigation (welcome, menu)
"""

import logging
from typing import Any

from ..sales import keyboards as kb
from ..sales.texts import (
    COMING_SOON_TEXT,
    FAQ_ANSWERS,
    FAQ_INSTALL_INTRO,
    FAQ_KEY_TO_SECTION,
    FAQ_MENU_TEXT,
    FAQ_PRICING_INTRO,
    FAQ_PRODUCT_INTRO,
    MENU_TEXT,
    WELCOME_TEXT,
)
from ..services.whatsapp_client import get_whatsapp_client
from ..state import sales_funnel_enabled


logger = logging.getLogger(__name__)


# ─── Send helpers ─────────────────────────────────────────────


async def _send_buttons(phone: str, body: str, keyboard: dict[str, Any]) -> None:
    """Extract buttons from keyboard dict and send via WhatsApp client."""
    wa = get_whatsapp_client()
    buttons = [
        {"id": b["reply"]["id"], "title": b["reply"]["title"]}
        for b in keyboard["action"]["buttons"]
    ]
    header = keyboard.get("header", {}).get("text", "")
    footer = keyboard.get("footer", {}).get("text", "")
    await wa.send_buttons(
        to=phone,
        body=body,
        buttons=buttons,
        header=header,
        footer=footer,
    )


async def _send_list(phone: str, body: str, keyboard: dict[str, Any]) -> None:
    """Extract sections from keyboard dict and send via WhatsApp client."""
    wa = get_whatsapp_client()
    button_text = keyboard["action"]["button"]
    sections = keyboard["action"]["sections"]
    header = keyboard.get("header", {}).get("text", "")
    footer = keyboard.get("footer", {}).get("text", "")
    await wa.send_list(
        to=phone,
        body=body,
        button_text=button_text,
        sections=sections,
        header=header,
        footer=footer,
    )


# ─── Main router ──────────────────────────────────────────────


async def handle_interactive_reply(phone: str, reply: dict[str, Any]) -> None:
    """Handle an interactive reply (button press or list selection).

    Args:
        phone: Sender phone number
        reply: Interactive reply payload from webhook.
            For buttons: {"type": "button_reply", "button_reply": {"id": "...", "title": "..."}}
            For lists:   {"type": "list_reply", "list_reply": {"id": "...", "title": "...", ...}}
    """
    reply_type = reply.get("type", "")
    reply_id = ""
    title = ""

    if reply_type == "button_reply":
        reply_id = reply.get("button_reply", {}).get("id", "")
        title = reply.get("button_reply", {}).get("title", "")
    elif reply_type == "list_reply":
        reply_id = reply.get("list_reply", {}).get("id", "")
        title = reply.get("list_reply", {}).get("title", "")

    # Every interactive flow here belongs to our own product funnel (pitch,
    # platform FAQ, TZ quiz). A client's bot never sends those menus, so a
    # reply can only be a stale button from before the funnel was switched
    # off — answer it as an ordinary message instead of pitching our product.
    if not sales_funnel_enabled():
        from .messages import handle_text_message

        logger.info("Funnel disabled; treating interactive reply from %s as text", phone)
        if title or reply_id:
            await handle_text_message(phone, title or reply_id, "")
        return

    if not reply_id:
        logger.warning("Interactive reply with no ID from %s: %s", phone, reply)
        return

    logger.info("Interactive reply from %s: %s (type=%s)", phone, reply_id, reply_type)

    prefix, _, action = reply_id.partition(":")
    if not action:
        logger.warning("Invalid reply_id format (no prefix): %s", reply_id)
        return

    if prefix == "sales":
        await _handle_sales(phone, action)
    elif prefix == "faq":
        await _handle_faq(phone, action)
    elif prefix == "tz":
        await _handle_tz(phone, action)
    elif prefix == "nav":
        await _handle_nav(phone, action)
    else:
        logger.warning("Unknown prefix %r in reply_id %s", prefix, reply_id)


# ─── Sales flow ───────────────────────────────────────────────


async def _handle_sales(phone: str, action: str) -> None:
    """Route sales:* callbacks to the sales handler package."""
    from .sales.router import route_sales_action

    await route_sales_action(phone, action)


# ─── FAQ flow ─────────────────────────────────────────────────


async def _handle_faq(phone: str, action: str) -> None:
    """Handle faq:* callbacks — full FAQ navigation."""
    wa = get_whatsapp_client()

    # Category selection
    if action == "cat_product":
        await _send_list(phone, FAQ_PRODUCT_INTRO, kb.faq_product_list())

    elif action == "cat_install":
        await _send_list(phone, FAQ_INSTALL_INTRO, kb.faq_install_list())

    elif action == "cat_pricing":
        await _send_list(phone, FAQ_PRICING_INTRO, kb.faq_pricing_list())

    # Back navigation
    elif action == "back_menu":
        await _send_buttons(phone, FAQ_MENU_TEXT, kb.faq_menu_buttons())

    elif action == "back_product":
        await _send_list(phone, FAQ_PRODUCT_INTRO, kb.faq_product_list())

    elif action == "back_install":
        await _send_list(phone, FAQ_INSTALL_INTRO, kb.faq_install_list())

    elif action == "back_pricing":
        await _send_list(phone, FAQ_PRICING_INTRO, kb.faq_pricing_list())

    # FAQ answer lookup
    elif action in FAQ_ANSWERS:
        answer_text = FAQ_ANSWERS[action]
        section = FAQ_KEY_TO_SECTION.get(action, "product")
        # Send answer as text (may exceed 1024 char button-body limit)
        await wa.send_text(to=phone, text=answer_text)
        # Then send back-navigation buttons
        await _send_buttons(
            phone,
            "Выберите действие 👇",
            kb.faq_back_buttons(section),
        )

    else:
        logger.warning("Unknown FAQ action: %s", action)


# ─── TZ flow (WA-10 placeholder) ─────────────────────────────


async def _handle_tz(phone: str, action: str) -> None:
    """Handle tz:* callbacks — placeholder for WA-10."""
    logger.info("Unhandled TZ action: %s (WA-10 placeholder)", action)
    await _send_buttons(phone, COMING_SOON_TEXT, kb.menu_buttons())


# ─── Navigation ──────────────────────────────────────────────


async def _handle_nav(phone: str, action: str) -> None:
    """Handle nav:* callbacks — generic navigation."""
    if action == "welcome":
        await _send_buttons(phone, WELCOME_TEXT, kb.welcome_buttons())
    elif action == "menu":
        await _send_buttons(phone, MENU_TEXT, kb.menu_buttons())
    else:
        logger.warning("Unknown nav action: %s", action)

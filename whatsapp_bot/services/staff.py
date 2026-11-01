"""Messages from the managers' own numbers are commands, not client questions.

The director gets КП notifications on WhatsApp and answers them («ок 18»,
«отмена 18»). Those answers must not reach the assistant — it would consult
the director as a customer and open a deal in amoCRM. The orchestrator owns
the staff list (``kp_settings``) and the commands (``modules/kp/messenger``),
so the bot only asks and relays the reply.
"""

import logging
from typing import Optional

from ..state import get_bot_config
from .llm_router import get_llm_router


logger = logging.getLogger(__name__)

# Approving sends the КП to the client through the PIM and WhatsApp — slower
# than an ordinary API call.
TIMEOUT = 90


async def staff_reply(sender: str, phone: Optional[str], text: str) -> Optional[str]:
    """The reply to send back, or None — not a staff number, handle as usual."""
    if not get_bot_config():  # standalone .env mode — no orchestrator settings
        return None
    router = get_llm_router()
    try:
        client = await router._get_client()
        resp = await client.post(
            f"{router.orchestrator_url}/admin/kp/staff-message",
            json={"sender": sender, "phone": phone, "text": text},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("Staff command check failed for %s: %s", sender, e)
        return None
    if not data.get("handled"):
        return None
    return data.get("reply") or ""

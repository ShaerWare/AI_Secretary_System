"""Ask the orchestrator whether a reply may go to the client right away.

The approval decision lives in the orchestrator (``modules/outbound``), not in
the bot: the mode is switched from the admin panel and has to take effect
without restarting the bot process.
"""

import logging
from typing import Any

from ..state import get_bot_config


logger = logging.getLogger(__name__)

# Last mode the orchestrator reported. If the submit call itself fails, the bot
# keeps behaving the way it last knew instead of guessing — an instance under
# approval must not start answering clients on its own because of a hiccup.
_last_mode: str = "auto"


async def submit_reply(router: Any, target: str, client_text: str, reply: str) -> dict[str, Any]:
    """Return ``{"action": "send"}`` or ``{"action": "queued", "ack_text": ...}``.

    *router* is the bot's ``LLMRouter``: it already holds the authenticated
    orchestrator client and the conversation → session mapping.
    """
    global _last_mode

    bot_config = get_bot_config()
    if not bot_config:  # standalone .env mode — no instance, no queue
        return {"action": "send"}

    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            payload = {
                "channel": "whatsapp",
                "instance_id": bot_config.instance_id,
                "target": target,
                "text": reply,
                "session_id": router._session_map.get(target),
                "client_text": client_text,
            }
            client = await router._get_client()
            resp = await client.post(
                f"{router.orchestrator_url}/admin/outbound/submit", json=payload
            )
            resp.raise_for_status()
            decision = resp.json()
            _last_mode = decision.get("mode") or _last_mode
            return decision
        except Exception as e:
            last_error = e
    logger.error("Outbound submit failed for %s (last mode %s): %s", target, _last_mode, last_error)
    if _last_mode == "approval":
        # Can't queue and mustn't send: the reply is still in the chat history,
        # and the monitor shows the dialogue as unanswered.
        return {"action": "drop"}
    return {"action": "send"}

"""WhatsApp channel domain events.

Mirrors the widget events: the bot itself runs in a separate process and has no
access to the in-process EventBus, so these are published by the orchestrator's
chat router when it recognises a WhatsApp-sourced session. That recognition is
only possible because sessions now carry ``source="whatsapp"`` and a per-sender
``source_id`` — before that every WhatsApp turn looked like a Telegram one.
"""

from dataclasses import dataclass

from modules.core.events import BaseEvent


@dataclass
class WhatsAppSessionCreated(BaseEvent):
    """Emitted on the first user message of a WhatsApp conversation.

    CRM domain subscribes to create a contact (carrying the sender's number, so
    a manager can actually call back) and an amoCRM lead.
    """

    session_id: str = ""
    instance_id: str = ""
    sender: str = ""
    first_message: str = ""


@dataclass
class WhatsAppMessageSent(BaseEvent):
    """Emitted after each conversation turn in a WhatsApp session.

    CRM domain subscribes to append the turn to the lead's notes.
    """

    session_id: str = ""
    lead_id: int = 0
    sender: str = ""
    user_message: str = ""
    assistant_response: str = ""

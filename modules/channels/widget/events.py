"""Widget channel domain events."""

from dataclasses import dataclass, field

from modules.core.events import BaseEvent


@dataclass
class WidgetSessionCreated(BaseEvent):
    """Emitted on first user message in a widget chat session.

    CRM domain subscribes to auto-create a lead in amoCRM.
    """

    session_id: str = ""
    first_message: str = ""
    visitor_metadata: dict = field(default_factory=dict)


@dataclass
class WidgetMessageSent(BaseEvent):
    """Emitted after each conversation turn in a widget chat session.

    CRM domain subscribes to append notes to an amoCRM lead.
    """

    session_id: str = ""
    lead_id: int = 0
    user_message: str = ""
    assistant_response: str = ""


@dataclass
class WidgetContactSubmitted(BaseEvent):
    """Emitted when a visitor submits contact info via widget lead form.

    CRM domain subscribes to create an amoCRM contact and link to a lead.
    """

    session_id: str = ""
    contact_name: str = ""
    phone: str = ""
    email: str = ""
    visitor_metadata: dict = field(default_factory=dict)

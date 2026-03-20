"""Knowledge domain events."""

from dataclasses import dataclass

from modules.core.events import BaseEvent


@dataclass
class KnowledgeUpdated(BaseEvent):
    """Emitted when a knowledge resource (FAQ, wiki, collection) changes."""

    kind: str = ""  # "faq", "wiki", "collection"
    action: str = ""  # "created", "updated", "deleted", "reloaded"
    item_id: int | None = None

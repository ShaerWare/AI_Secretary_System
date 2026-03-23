"""Target Protocol interfaces for the Chat domain.

These Protocols describe the *ideal* service contracts.  Currently
session CRUD lives in ``service.py`` while LLM generation and
streaming live in the orchestrator; the Protocols define the target
unified facade.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from modules.chat.schemas import (
        MessageInfo,
        SessionInfo,
        SessionSummary,
        ShareInfo,
        StreamChunk,
    )
    from modules.llm.schemas import LLMConfig


@runtime_checkable
class ChatService(Protocol):
    """Unified facade for chat sessions, messages, and generation.

    Combines session/message CRUD (currently ``modules/chat/service.py``)
    with LLM generation (currently orchestrator) into a single contract.
    """

    # -- Sessions -------------------------------------------------------------

    async def create_session(
        self,
        *,
        source: str = "admin",
        source_id: str | None = None,
        title: str | None = None,
        system_prompt: str | None = None,
        owner_id: int | None = None,
        workspace_id: int = 1,
    ) -> SessionInfo:
        """Create a new chat session."""
        ...

    async def get_session(self, session_id: str) -> SessionInfo | None:
        """Look up a session by ID."""
        ...

    async def list_sessions(
        self,
        *,
        owner_id: int | None = None,
        workspace_id: int | None = None,
    ) -> list[SessionSummary]:
        """List sessions as compact summaries."""
        ...

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages."""
        ...

    # -- Messages (CRUD) ------------------------------------------------------

    async def get_history(self, session_id: str) -> list[MessageInfo]:
        """Return the active message branch for a session."""
        ...

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        parent_id: str | None = None,
    ) -> MessageInfo:
        """Append a message to the session."""
        ...

    # -- Generation (LLM) ----------------------------------------------------

    async def send_message(
        self,
        session_id: str,
        content: str,
        *,
        llm_config: LLMConfig | None = None,
    ) -> MessageInfo:
        """Send a user message and return the assistant reply."""
        ...

    async def stream_message(
        self,
        session_id: str,
        content: str,
        *,
        llm_config: LLMConfig | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Send a user message and stream the assistant reply."""
        ...

    # -- Sharing --------------------------------------------------------------

    async def share_session(
        self,
        session_id: str,
        user_id: int,
        *,
        permission: str = "read",
    ) -> ShareInfo:
        """Grant another user access to a session."""
        ...

    async def unshare_session(
        self,
        session_id: str,
        user_id: int,
    ) -> bool:
        """Revoke a user's access to a session."""
        ...

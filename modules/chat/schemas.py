"""Ideal data shapes for the Chat domain.

These TypedDicts describe the *target* API contract for chat sessions,
messages, and sharing.
"""

from __future__ import annotations

from typing import TypedDict


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class SessionInfo(TypedDict):
    """Read-only view of a chat session."""

    id: str
    title: str
    system_prompt: str | None
    pinned: bool
    source: str | None  # "admin" | "telegram" | "widget" | "whatsapp" | "mobile"
    source_id: str | None
    owner_id: int | None
    rag_mode: str | None  # "all" | "selected" | "collection" | "none"
    collection_ids: list[int] | None
    created: str | None
    updated: str | None


class SessionSummary(TypedDict):
    """Compact session view for listing (no messages, no system_prompt)."""

    id: str
    title: str
    pinned: bool
    message_count: int
    last_message: str | None  # first 100 chars
    source: str | None
    owner_id: int | None
    created: str | None
    updated: str | None


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class MessageInfo(TypedDict):
    """Read-only view of a chat message."""

    id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    edited: bool
    timestamp: str | None
    parent_id: str | None
    is_active: bool
    metadata: dict | None


class StreamChunk(TypedDict, total=False):
    """A single chunk from ChatService.stream_message().

    Event types:
    - ``user_message`` — echoes saved user message (``message`` field)
    - ``chunk`` — text delta from the model (``content`` field)
    - ``tool_start`` — agentic RAG tool invoked (``name``, ``query``)
    - ``tool_end`` — tool finished (``name``, ``found``)
    - ``assistant_message`` — full saved response (``message``, ``token_usage``)
    - ``done`` — stream finished
    - ``error`` — generation error (``content``)
    """

    type: str
    content: str
    message: dict
    name: str
    query: str
    found: bool
    done: bool
    token_usage: TokenUsage | None


class TokenUsage(TypedDict):
    """Token budget information."""

    tokens: int
    context_window: int
    percent: float
    trimmed: bool


# ---------------------------------------------------------------------------
# Sharing
# ---------------------------------------------------------------------------


class ShareInfo(TypedDict):
    """Read-only view of a session share entry."""

    id: int
    session_id: str
    user_id: int
    permission: str  # "read" | "write"
    shared_by: int | None
    shared_at: str | None

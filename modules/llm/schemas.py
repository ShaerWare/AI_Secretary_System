"""Ideal data shapes for the LLM domain.

These TypedDicts describe the *target* API contract for LLM
configuration, provider metadata, and generation results.
"""

from __future__ import annotations

from typing import TypedDict


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class LLMConfig(TypedDict, total=False):
    """Parameters passed to LLMService.generate() / stream().

    All fields are optional — unset keys inherit from the provider or
    system defaults.
    """

    backend: str  # "vllm" | "cloud:<provider-id>"
    system_prompt: str
    temperature: float
    max_tokens: int
    top_p: float
    repetition_penalty: float
    rag_mode: str  # "all" | "selected" | "collection" | "none"
    collection_ids: list[int]


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class ProviderInfo(TypedDict):
    """Read-only view of a cloud LLM provider."""

    id: str
    name: str
    provider_type: str  # "gemini" | "openai" | "claude" | "deepseek" | "openrouter" | ...
    model_name: str
    enabled: bool
    is_default: bool
    base_url: str | None
    description: str | None
    config: LLMParams
    created: str | None
    updated: str | None


class LLMParams(TypedDict, total=False):
    """Runtime generation parameters stored in provider config."""

    temperature: float
    max_tokens: int
    top_p: float
    repetition_penalty: float


# ---------------------------------------------------------------------------
# Generation result
# ---------------------------------------------------------------------------


class StreamChunk(TypedDict, total=False):
    """A single chunk from LLMService.stream().

    Either ``content`` (text delta) or ``tool_calls`` is present.
    """

    type: str  # "content" | "tool_calls"
    content: str
    tool_calls: list[ToolCall]


class ToolCall(TypedDict):
    """OpenAI-compatible tool/function call."""

    id: str
    type: str  # "function"
    function: ToolCallFunction


class ToolCallFunction(TypedDict):
    """Function name + serialised arguments inside a ToolCall."""

    name: str
    arguments: str  # JSON string


# ---------------------------------------------------------------------------
# Token usage
# ---------------------------------------------------------------------------


class TokenUsage(TypedDict):
    """Token budget information returned alongside generation."""

    tokens: int
    context_window: int
    percent: float
    trimmed: bool

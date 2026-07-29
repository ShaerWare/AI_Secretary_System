"""OpenAI-compatible schema models for the CLI-OpenAI bridge.

Reconstructed package (`src/models`) — the original was gitignored
(`.gitignore` pattern `models/`) and lost when the source server went down.
Exposes the exact surface imported by:
  - src/server/routes/chat.py
  - src/server/routes/models.py
  - src/providers/manager.py

Serialization mirrors the OpenAI Chat Completions API so the orchestrator's
OpenAICompatibleProvider parses responses/chunks unchanged, plus a few
bridge-specific extras (provider, conversation_id, estimated_cost_usd,
supports_streaming/supports_thinking).
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "Message",
    "Thinking",
    "ChatCompletionRequest",
    "ChoiceMessage",
    "Choice",
    "Usage",
    "ChatCompletionResponse",
    "ChunkDelta",
    "ChunkChoice",
    "ChatCompletionChunk",
    "Model",
    "ModelList",
    "ErrorDetail",
    "ErrorResponse",
    "create_error",
    "create_chunk",
    "create_response",
    "create_tool_call_chunks",
]


def _new_id(prefix: str = "chatcmpl") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:24]}"


def _now() -> int:
    return int(time.time())


# ─────────────────────────── request models ───────────────────────────


class Message(BaseModel):
    """A single chat message (OpenAI shape, permissive)."""

    model_config = ConfigDict(extra="allow")

    role: str
    content: Optional[Any] = None
    name: Optional[str] = None
    tool_calls: Optional[list[Any]] = None
    tool_call_id: Optional[str] = None


class Thinking(BaseModel):
    """Extended-thinking directive (permissive — only .model_dump() is used)."""

    model_config = ConfigDict(extra="allow")

    type: Optional[str] = None
    budget_tokens: Optional[int] = None
    effort: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    """Incoming /v1/chat/completions request. Extra OpenAI fields are ignored."""

    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[Message]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tools: Optional[list[Any]] = None
    tool_choice: Optional[Any] = None
    thinking: Optional[Thinking] = None
    conversation_id: Optional[str] = None


# ─────────────────────────── response models ───────────────────────────


class ChoiceMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str = "assistant"
    content: Optional[Any] = None
    tool_calls: Optional[list[Any]] = None
    thinking: Optional[Any] = None


class Choice(BaseModel):
    model_config = ConfigDict(extra="allow")

    index: int = 0
    message: ChoiceMessage
    finish_reason: Optional[str] = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=_new_id)
    object: str = "chat.completion"
    created: int = Field(default_factory=_now)
    model: str
    choices: list[Choice] = Field(default_factory=list)
    usage: Optional[Usage] = None
    # bridge extras
    provider: Optional[str] = None
    conversation_id: Optional[str] = None
    estimated_cost_usd: Optional[float] = None


# ─────────────────────────── streaming models ───────────────────────────


class ChunkDelta(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: Optional[str] = None
    content: Optional[str] = None
    tool_calls: Optional[list[Any]] = None
    thinking: Optional[Any] = None


class ChunkChoice(BaseModel):
    model_config = ConfigDict(extra="allow")

    index: int = 0
    delta: ChunkDelta = Field(default_factory=ChunkDelta)
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: _new_id())
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=_now)
    model: str
    choices: list[ChunkChoice] = Field(default_factory=list)
    provider: Optional[str] = None


# ─────────────────────────── model listing ───────────────────────────


class Model(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    object: str = "model"
    created: int = Field(default_factory=_now)
    owned_by: str = "bridge"
    supports_streaming: bool = True
    supports_thinking: bool = False


class ModelList(BaseModel):
    object: str = "list"
    data: list[Model] = Field(default_factory=list)


# ─────────────────────────── errors ───────────────────────────


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: str
    type: str = "server_error"
    param: Optional[str] = None
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ─────────────────────────── factory helpers ───────────────────────────


def create_error(message: str, error_type: str = "server_error", code: Optional[str] = None) -> ErrorResponse:
    return ErrorResponse(error=ErrorDetail(message=message, type=error_type, code=code))


def create_chunk(
    content: Optional[str] = None,
    model: str = "",
    provider: Optional[str] = None,
    thinking: Optional[Any] = None,
    finish_reason: Optional[str] = None,
    chunk_id: Optional[str] = None,
) -> ChatCompletionChunk:
    delta = ChunkDelta()
    if content is not None:
        delta.content = content
    if thinking is not None:
        delta.thinking = thinking
    return ChatCompletionChunk(
        id=chunk_id or _new_id(),
        model=model,
        provider=provider,
        choices=[ChunkChoice(index=0, delta=delta, finish_reason=finish_reason)],
    )


def create_tool_call_chunks(
    tool_calls: list[Any],
    model: str = "",
    provider: Optional[str] = None,
    chunk_id: Optional[str] = None,
) -> list[ChatCompletionChunk]:
    """Emit tool calls as streaming delta chunks (OpenAI shape)."""
    delta_tool_calls: list[dict[str, Any]] = []
    for i, tc in enumerate(tool_calls):
        tc_dict = tc.model_dump() if hasattr(tc, "model_dump") else dict(tc)
        fn = tc_dict.get("function", tc_dict)
        name = fn.get("name") if isinstance(fn, dict) else None
        args = fn.get("arguments") if isinstance(fn, dict) else None
        if args is not None and not isinstance(args, str):
            import json as _json

            args = _json.dumps(args, ensure_ascii=False)
        delta_tool_calls.append(
            {
                "index": i,
                "id": tc_dict.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {"name": name or "", "arguments": args or ""},
            }
        )
    delta = ChunkDelta(tool_calls=delta_tool_calls)
    return [
        ChatCompletionChunk(
            id=chunk_id or _new_id(),
            model=model,
            provider=provider,
            choices=[ChunkChoice(index=0, delta=delta, finish_reason=None)],
        )
    ]


def create_response(
    content: Optional[str] = None,
    model: str = "",
    provider: Optional[str] = None,
    thinking: Optional[Any] = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    conversation_id: Optional[str] = None,
    estimated_cost_usd: Optional[float] = None,
    finish_reason: str = "stop",
) -> ChatCompletionResponse:
    return ChatCompletionResponse(
        model=model,
        provider=provider,
        conversation_id=conversation_id,
        estimated_cost_usd=estimated_cost_usd,
        choices=[
            Choice(
                index=0,
                message=ChoiceMessage(content=content, thinking=thinking),
                finish_reason=finish_reason,
            )
        ],
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )

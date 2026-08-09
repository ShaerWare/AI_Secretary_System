"""OpenAI-compatible chat completion models."""

from typing import Literal, Any, Union
from pydantic import BaseModel, Field, field_validator
import time
import uuid


class TextContent(BaseModel):
    """Text content part."""

    type: Literal["text"] = "text"
    text: str


class FileContent(BaseModel):
    """File reference content part."""

    type: Literal["file"] = "file"
    file_id: str


class ImageUrlContent(BaseModel):
    """Image URL content part (base64 or URL)."""

    type: Literal["image_url"] = "image_url"
    image_url: dict[str, str]  # {"url": "data:image/png;base64,..."}


# Content can be a string or list of parts
ContentPart = Union[TextContent, FileContent, ImageUrlContent]
MessageContent = Union[str, list[ContentPart]]


class Message(BaseModel):
    """Chat message with support for multi-part content and tool calls.

    Supports:
    - system: System prompt
    - user: User message
    - assistant: Assistant response (may include tool_calls)
    - tool: Tool result (requires tool_call_id)
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: MessageContent | None = None  # Can be None for assistant with only tool_calls
    name: str | None = None

    # For tool result messages (role="tool")
    tool_call_id: str | None = None

    # For assistant messages that made tool calls
    tool_calls: list[dict[str, Any]] | None = None

    def get_text_content(self) -> str:
        """Extract text content from message."""
        if self.content is None:
            return ""
        if isinstance(self.content, str):
            return self.content

        # Multi-part content - extract text parts
        texts = []
        for part in self.content:
            if isinstance(part, TextContent):
                texts.append(part.text)
            elif isinstance(part, dict) and part.get("type") == "text":
                texts.append(part.get("text", ""))
        return "\n".join(texts)

    def get_file_ids(self) -> list[str]:
        """Extract file IDs from message."""
        if self.content is None:
            return []
        if isinstance(self.content, str):
            return []

        file_ids = []
        for part in self.content:
            if isinstance(part, FileContent):
                file_ids.append(part.file_id)
            elif isinstance(part, dict) and part.get("type") == "file":
                file_ids.append(part.get("file_id", ""))
        return file_ids


class ThinkingConfig(BaseModel):
    """Configuration for thinking/reasoning mode."""

    enabled: bool = False
    budget_tokens: int = Field(default=10000, ge=1, le=100000)


class FunctionDefinition(BaseModel):
    """Function definition for tools."""

    name: str
    description: str | None = None
    parameters: dict[str, Any] | None = None


class Tool(BaseModel):
    """Tool definition (OpenAI format)."""

    type: Literal["function"] = "function"
    function: FunctionDefinition


class ToolChoiceFunction(BaseModel):
    """Specific function choice."""

    name: str


class ToolChoiceObject(BaseModel):
    """Tool choice object for specific function."""

    type: Literal["function"] = "function"
    function: ToolChoiceFunction


# Tool choice can be string or object
ToolChoice = Union[Literal["none", "auto", "required"], ToolChoiceObject]


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""

    model: str
    messages: list[Message]
    temperature: float = Field(default=1.0, ge=0, le=2)
    top_p: float = Field(default=1.0, ge=0, le=1)
    n: int = Field(default=1, ge=1, le=1)  # Only support n=1 for CLI
    stream: bool = False
    stop: str | list[str] | None = None
    max_tokens: int | None = None
    presence_penalty: float = Field(default=0, ge=-2, le=2)
    frequency_penalty: float = Field(default=0, ge=-2, le=2)
    user: str | None = None

    # Tools support (OpenAI function calling)
    tools: list[Tool] | None = None
    tool_choice: ToolChoice | None = None

    # Extended: thinking mode support
    thinking: ThinkingConfig | None = None

    # Extended: conversation/session management
    # If provided, continues an existing conversation using CLI session
    conversation_id: str | None = None


class FunctionCall(BaseModel):
    """Function call in assistant message."""

    name: str
    arguments: str


class ToolCall(BaseModel):
    """Tool call in assistant message."""

    id: str
    type: Literal["function"] = "function"
    function: FunctionCall


class ChoiceMessage(BaseModel):
    """Message in completion choice."""

    role: Literal["assistant"] = "assistant"
    content: str | None = None
    tool_calls: list[ToolCall] | None = None

    # Extended: thinking content
    thinking: str | None = None


class Choice(BaseModel):
    """Completion choice."""

    index: int = 0
    message: ChoiceMessage
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter"] | None = "stop"


class Usage(BaseModel):
    """Token usage statistics."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""

    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[Choice]
    usage: Usage = Field(default_factory=Usage)

    # Extended: provider info
    provider: str | None = None

    # Extended: conversation/session management
    # Use this ID in subsequent requests to continue the conversation
    conversation_id: str | None = None

    # Extended: cost tracking (informational - based on CLI subscription usage)
    estimated_cost_usd: float | None = None


# Streaming models


class DeltaToolCallFunction(BaseModel):
    """Function info in streaming tool call delta."""

    name: str | None = None
    arguments: str | None = None


class DeltaToolCall(BaseModel):
    """Tool call delta for streaming."""

    index: int
    id: str | None = None
    type: Literal["function"] | None = None
    function: DeltaToolCallFunction | None = None


class DeltaMessage(BaseModel):
    """Delta content for streaming."""

    role: Literal["assistant"] | None = None
    content: str | None = None
    tool_calls: list[DeltaToolCall] | None = None

    # Extended: thinking delta
    thinking: str | None = None


class StreamChoice(BaseModel):
    """Streaming choice."""

    index: int = 0
    delta: DeltaMessage
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter"] | None = None


class ChatCompletionChunk(BaseModel):
    """OpenAI-compatible streaming chunk."""

    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[StreamChoice]

    # Extended: provider info
    provider: str | None = None


# Helper functions


def create_response(
    content: str,
    model: str,
    provider: str | None = None,
    thinking: str | None = None,
    finish_reason: str = "stop",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    conversation_id: str | None = None,
    estimated_cost_usd: float | None = None,
) -> ChatCompletionResponse:
    """Create a chat completion response."""
    return ChatCompletionResponse(
        model=model,
        provider=provider,
        conversation_id=conversation_id,
        estimated_cost_usd=estimated_cost_usd,
        choices=[
            Choice(
                message=ChoiceMessage(
                    content=content,
                    thinking=thinking,
                ),
                finish_reason=finish_reason,
            )
        ],
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


def create_chunk(
    content: str | None = None,
    model: str = "",
    provider: str | None = None,
    thinking: str | None = None,
    finish_reason: str | None = None,
    chunk_id: str | None = None,
    tool_calls: list[DeltaToolCall] | None = None,
) -> ChatCompletionChunk:
    """Create a streaming chunk."""
    return ChatCompletionChunk(
        id=chunk_id or f"chatcmpl-{uuid.uuid4().hex[:12]}",
        model=model,
        provider=provider,
        choices=[
            StreamChoice(
                delta=DeltaMessage(
                    content=content,
                    thinking=thinking,
                    tool_calls=tool_calls,
                ),
                finish_reason=finish_reason,
            )
        ],
    )


def create_tool_call_chunks(
    tool_calls: list[dict[str, Any]],
    model: str = "",
    provider: str | None = None,
    chunk_id: str | None = None,
) -> list[ChatCompletionChunk]:
    """Create streaming chunks for tool calls.

    Emits one chunk per tool call with the full tool call info.
    In a real streaming scenario, this would be chunked by argument characters.

    Args:
        tool_calls: List of tool calls from parse_tool_calls
        model: Model name
        provider: Provider name
        chunk_id: Shared chunk ID

    Returns:
        List of chunks for the tool calls
    """
    chunks = []
    chunk_id = chunk_id or f"chatcmpl-{uuid.uuid4().hex[:12]}"

    for idx, tc in enumerate(tool_calls):
        func = tc.get("function", {})
        delta_tc = DeltaToolCall(
            index=idx,
            id=tc.get("id"),
            type="function",
            function=DeltaToolCallFunction(
                name=func.get("name"),
                arguments=func.get("arguments", ""),
            ),
        )
        chunk = ChatCompletionChunk(
            id=chunk_id,
            model=model,
            provider=provider,
            choices=[
                StreamChoice(
                    delta=DeltaMessage(tool_calls=[delta_tc]),
                    finish_reason=None,
                )
            ],
        )
        chunks.append(chunk)

    return chunks

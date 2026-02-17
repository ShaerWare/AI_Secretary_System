"""Token counting and context window management."""

import logging
from typing import Any


logger = logging.getLogger(__name__)

# Lazy import tiktoken to avoid import errors if not installed
_tiktoken = None


def _get_tiktoken():
    """Lazy load tiktoken."""
    global _tiktoken
    if _tiktoken is None:
        try:
            import tiktoken

            _tiktoken = tiktoken
        except ImportError:
            logger.warning("tiktoken not installed, token counting will use approximations")
            _tiktoken = False
    return _tiktoken


class TokenCounter:
    """
    Token counter supporting multiple model families.

    Uses tiktoken for accurate counting when available,
    falls back to character-based approximation otherwise.
    """

    # Model family to tiktoken encoding mapping
    ENCODING_MAP = {
        "gpt-4": "cl100k_base",
        "gpt-4o": "o200k_base",
        "gpt-4-turbo": "cl100k_base",
        "gpt-3.5-turbo": "cl100k_base",
        "o1": "o200k_base",
        "o1-mini": "o200k_base",
        "o1-preview": "o200k_base",
        "claude": "cl100k_base",
        "sonnet": "cl100k_base",
        "opus": "cl100k_base",
        "haiku": "cl100k_base",
        "gemini": "cl100k_base",
    }

    CHARS_PER_TOKEN = 4

    def __init__(self):
        self._encodings: dict[str, Any] = {}

    def _get_encoding(self, model: str) -> Any | None:
        """Get tiktoken encoding for a model."""
        tiktoken = _get_tiktoken()
        if not tiktoken:
            return None

        encoding_name = None
        model_lower = model.lower()
        for prefix, enc in self.ENCODING_MAP.items():
            if model_lower.startswith(prefix):
                encoding_name = enc
                break

        if not encoding_name:
            encoding_name = "cl100k_base"

        if encoding_name not in self._encodings:
            try:
                self._encodings[encoding_name] = tiktoken.get_encoding(encoding_name)
            except Exception as e:
                logger.warning(f"Failed to get encoding {encoding_name}: {e}")
                return None

        return self._encodings[encoding_name]

    def count_text(self, text: str, model: str = "gpt-4") -> int:
        if not text:
            return 0

        encoding = self._get_encoding(model)
        if encoding:
            try:
                return len(encoding.encode(text))
            except Exception as e:
                logger.warning(f"Token encoding failed, using approximation: {e}")

        return len(text) // self.CHARS_PER_TOKEN

    def count_messages(self, messages: list[dict[str, Any]], model: str = "gpt-4") -> int:
        total = 0
        message_overhead = 4

        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.count_text(content, model)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        total += self.count_text(part.get("text", ""), model)
            total += message_overhead

        total += 3
        return total


# Singleton
_counter: TokenCounter | None = None


def get_token_counter() -> TokenCounter:
    global _counter
    if _counter is None:
        _counter = TokenCounter()
    return _counter


def count_tokens(text: str, model: str = "gpt-4") -> int:
    return get_token_counter().count_text(text, model)


def count_message_tokens(messages: list[dict[str, Any]], model: str = "gpt-4") -> int:
    return get_token_counter().count_messages(messages, model)


# ============== Context Window Management ==============

CONTEXT_WINDOWS = {
    "claude": 200_000,
    "sonnet": 200_000,
    "opus": 200_000,
    "haiku": 200_000,
    "gemini-2": 1_048_576,
    "gemini-1": 1_048_576,
    "kimi": 131_072,
    "moonshot": 131_072,
    "gpt-4o": 128_000,
    "gpt-4": 128_000,
    "gpt-3.5": 16_385,
    "deepseek": 64_000,
}
DEFAULT_CONTEXT_WINDOW = 128_000


def get_context_window(model: str) -> int:
    model_lower = model.lower()
    for prefix, size in CONTEXT_WINDOWS.items():
        if model_lower.startswith(prefix):
            return size
    return DEFAULT_CONTEXT_WINDOW


def trim_messages(
    messages: list[dict], context_window: int, reserve_output: int = 4096
) -> tuple[list[dict], bool]:
    """Trim oldest message pairs to fit context window.

    Returns (trimmed_messages, was_trimmed).
    """
    max_input = context_window - reserve_output
    if count_message_tokens(messages) <= max_input:
        return messages, False

    system = [messages[0]] if messages and messages[0]["role"] == "system" else []
    conversation = messages[len(system) :]

    while count_message_tokens(system + conversation) > max_input and len(conversation) > 2:
        conversation = conversation[2:]  # drop oldest user+assistant pair

    return system + conversation, True

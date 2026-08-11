"""Token counting and context window management."""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

# tiktoken downloads its BPE file (~1.7 MB) on first use of an encoding and
# caches it under tempfile.gettempdir()/data-gym-cache by default — i.e. in
# /tmp, which is wiped on reboot and not persisted in containers. Point it at
# a directory inside the project so the download happens at most once per
# install instead of once per boot.
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "models" / "tiktoken"

# How long to wait before retrying an encoding load that failed (usually a
# blocked/proxied download). Without this every single request would re-try
# the network call.
_ENCODING_RETRY_SECONDS = 600.0


def _configure_cache_dir() -> None:
    """Give tiktoken a persistent cache dir unless the env already sets one."""
    if os.environ.get("TIKTOKEN_CACHE_DIR") or os.environ.get("DATA_GYM_CACHE_DIR"):
        return
    try:
        _DEFAULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        os.environ["TIKTOKEN_CACHE_DIR"] = str(_DEFAULT_CACHE_DIR)
    except OSError as e:  # read-only install dir — fall back to tiktoken's default
        logger.warning(f"tiktoken cache dir {_DEFAULT_CACHE_DIR} unavailable: {e}")


# Lazy import tiktoken to avoid import errors if not installed
_tiktoken = None


def _get_tiktoken():
    """Lazy load tiktoken."""
    global _tiktoken
    if _tiktoken is None:
        try:
            _configure_cache_dir()
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
        self._lock = threading.Lock()
        self._loading: set[str] = set()
        self._failed_at: dict[str, float] = {}

    def _encoding_name(self, model: str) -> str:
        model_lower = model.lower()
        for prefix, enc in self.ENCODING_MAP.items():
            if model_lower.startswith(prefix):
                return enc
        return "cl100k_base"

    def _load_encoding(self, encoding_name: str) -> Any | None:
        """Load an encoding — may block for seconds on the first download."""
        tiktoken = _get_tiktoken()
        enc = None
        if tiktoken:
            try:
                enc = tiktoken.get_encoding(encoding_name)
            except Exception as e:
                logger.warning(f"Failed to get encoding {encoding_name}: {e}")
        with self._lock:
            self._loading.discard(encoding_name)
            if enc is not None:
                self._encodings[encoding_name] = enc
                self._failed_at.pop(encoding_name, None)
            else:
                self._failed_at[encoding_name] = time.monotonic()
        return enc

    def _get_encoding(self, model: str, *, blocking: bool = False) -> Any | None:
        """Get a tiktoken encoding without ever blocking the caller.

        The first `get_encoding` call downloads the BPE file over the network,
        which under a dead/slow proxy hangs for tens of seconds — and this runs
        inside FastAPI request handlers, i.e. on the event loop, freezing the
        whole orchestrator. So callers never wait: the load is kicked off in a
        background thread and the character-based approximation is used until
        it is ready. Failures are remembered for `_ENCODING_RETRY_SECONDS` so a
        blocked download isn't retried on every request.

        `blocking=True` is for the startup prewarm, which runs off the loop.
        """
        if not _get_tiktoken():
            return None

        encoding_name = self._encoding_name(model)

        with self._lock:
            enc = self._encodings.get(encoding_name)
            if enc is not None:
                return enc
            if encoding_name in self._loading:
                return None
            failed_at = self._failed_at.get(encoding_name)
            if failed_at is not None and time.monotonic() - failed_at < _ENCODING_RETRY_SECONDS:
                return None
            self._loading.add(encoding_name)

        if blocking:
            return self._load_encoding(encoding_name)

        threading.Thread(
            target=self._load_encoding,
            args=(encoding_name,),
            name=f"tiktoken-load-{encoding_name}",
            daemon=True,
        ).start()
        return None

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


def prewarm_token_encodings(models: tuple[str, ...] = ("claude", "gpt-4o")) -> None:
    """Load tiktoken encodings in the background at startup.

    Off the request path the first-use download costs nothing user-visible;
    on it, it used to add seconds (or a hang) to every chat-session fetch.
    """
    counter = get_token_counter()

    def _warm() -> None:
        for model in models:
            counter._get_encoding(model, blocking=True)

    threading.Thread(target=_warm, name="tiktoken-prewarm", daemon=True).start()


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
    # Для коротких окон (локальный vLLM с max-model-len 4096) фиксированный
    # резерв в 4096 съел бы весь бюджет — ограничиваем его четвертью окна.
    reserve_output = min(reserve_output, context_window // 4)
    max_input = context_window - reserve_output
    if count_message_tokens(messages) <= max_input:
        return messages, False

    system = [messages[0]] if messages and messages[0]["role"] == "system" else []
    conversation = messages[len(system) :]

    while count_message_tokens(system + conversation) > max_input and len(conversation) > 2:
        conversation = conversation[2:]  # drop oldest user+assistant pair

    return system + conversation, True

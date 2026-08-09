#!/usr/bin/env python3
"""
Generic Cloud LLM Service supporting multiple providers.

Supports:
- Google Gemini (via google-generativeai SDK)
- Moonshot Kimi (OpenAI-compatible API)
- OpenAI (OpenAI-compatible API)
- Anthropic Claude (OpenAI-compatible API)
- DeepSeek (OpenAI-compatible API)
- OpenRouter (aggregator with many free models)
- Custom OpenAI-compatible endpoints
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Dict, Generator, List, Optional, Union


if TYPE_CHECKING:
    from xray_proxy_manager import XrayProxyManager, XrayProxyManagerWithFallback

import httpx


# Gemini SDK (optional)
try:
    import google.generativeai as genai

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None

# VLESS Proxy Manager (optional)
try:
    from xray_proxy_manager import (
        XrayProxyManager,
        XrayProxyManagerWithFallback,
        validate_vless_url,
    )

    XRAY_AVAILABLE = True
except ImportError:
    XRAY_AVAILABLE = False
    XrayProxyManager = None
    XrayProxyManagerWithFallback = None
    validate_vless_url = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Provider type configuration (also defined in db/models.py)
PROVIDER_TYPES = {
    "gemini": {
        "name": "Google Gemini",
        "default_base_url": None,
        "default_models": ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"],
        "requires_base_url": False,
    },
    "kimi": {
        "name": "Moonshot Kimi",
        "default_base_url": "https://api.moonshot.ai/v1",
        "default_models": ["kimi-k2", "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "requires_base_url": True,
    },
    "openai": {
        "name": "OpenAI",
        "default_base_url": "https://api.openai.com/v1",
        "default_models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        "requires_base_url": True,
    },
    "claude": {
        "name": "Anthropic Claude",
        "default_base_url": "https://api.anthropic.com/v1",
        "default_models": ["claude-opus-4-5-20251101", "claude-sonnet-4-20250514"],
        "requires_base_url": True,
    },
    "deepseek": {
        "name": "DeepSeek",
        "default_base_url": "https://api.deepseek.com/v1",
        "default_models": ["deepseek-chat", "deepseek-coder"],
        "requires_base_url": True,
    },
    "openrouter": {
        "name": "OpenRouter",
        "default_base_url": "https://openrouter.ai/api/v1",
        "default_models": [
            "anthropic/claude-sonnet-4.6",
            "openai/gpt-4o",
            "google/gemini-2.5-pro",
            "google/gemini-2.5-flash",
            "deepseek/deepseek-chat-v3-0324",
            "openai/gpt-4o-mini",
            "qwen/qwen3-235b-a22b",
            "google/gemini-2.0-flash-001",
            "meta-llama/llama-4-maverick",
        ],
        "requires_base_url": True,
    },
    "custom": {
        "name": "Custom OpenAI-Compatible",
        "default_base_url": "",
        "default_models": [],
        "requires_base_url": True,
    },
    "claude_bridge": {
        "name": "Claude Bridge (Local CLI)",
        "default_base_url": "http://127.0.0.1:8787/v1",
        "default_models": ["sonnet", "opus", "haiku"],
        "requires_base_url": False,
    },
}


def _safe_resp_text(response) -> str:
    """Safely extract response body for logging.

    httpx raises 'Attempted to access streaming response content, without
    having called read()' when `.text` is read inside a streaming context
    manager before the body is consumed. This helper calls `.read()` first
    when needed and never crashes — returns "" on failure.
    """
    try:
        return response.text
    except Exception:
        try:
            return response.read().decode("utf-8", errors="replace")
        except Exception:
            return ""


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    supports_tools: bool = False

    def __init__(self, config: dict):
        self.config = config
        self.api_key = config.get("api_key", "")
        self.model_name = config.get("model_name", "")
        self.base_url = config.get("base_url", "")
        self.provider_id = config.get("id", "unknown")
        self.provider_type = config.get("provider_type", "custom")

        # Runtime parameters
        self.runtime_params = config.get("config", {}) or {}
        if not self.runtime_params:
            self.runtime_params = {
                "temperature": 0.7,
                "max_tokens": 1024,
                "top_p": 0.9,
            }

    @abstractmethod
    def generate_response(
        self, user_message: str, system_prompt: str = None, history: List[Dict] = None
    ) -> str:
        """Generate a response synchronously."""
        pass

    @abstractmethod
    def generate_response_stream(
        self, user_message: str, system_prompt: str = None, history: List[Dict] = None
    ) -> Generator[str, None, None]:
        """Generate a response with streaming."""
        pass

    @abstractmethod
    def generate_response_from_messages(
        self, messages: List[Dict[str, str]], stream: bool = False, params: Optional[Dict] = None
    ) -> Union[str, Generator[str, None, None]]:
        """Generate response from OpenAI-format messages.

        params — per-call generation parameters (chat/instance persona),
        overriding the provider's runtime defaults.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available."""
        pass

    def set_params(self, **kwargs):
        """Set runtime parameters."""
        for key, value in kwargs.items():
            if value is not None:
                self.runtime_params[key] = value
        logger.info(f"[{self.provider_id}] Parameters updated: {self.runtime_params}")

    def get_params(self) -> Dict:
        """Get runtime parameters."""
        return self.runtime_params.copy()


class OpenAICompatibleProvider(BaseLLMProvider):
    """
    Provider for OpenAI-compatible APIs.
    Supports: Kimi (Moonshot), OpenAI, DeepSeek, Claude*, Custom endpoints.

    *Note: Claude has its own API format, but can be used via OpenAI-compatible proxy.
    """

    supports_tools: bool = True

    def __init__(self, config: dict):
        super().__init__(config)

        # Bridge CLI runs with --tools "" (no tool access), so tool calls
        # are silently ignored. Disable supports_tools to fall back to
        # one-shot RAG injection instead of agentic loop.
        if self.provider_type == "claude_bridge":
            self.supports_tools = False

        # Per-provider override via config (DB column `config` json blob).
        # Useful for OpenRouter free chains where most models reject the
        # `tools` payload with HTTP 404 — set "supports_tools": false to
        # force one-shot RAG injection instead of agentic tool-loop.
        if "supports_tools" in self.runtime_params:
            self.supports_tools = bool(self.runtime_params["supports_tools"])

        # Bridge runs on localhost — must bypass global VLESS/HTTP proxy.
        # GeminiProvider sets HTTP_PROXY globally for xray; httpx picks it up
        # and routes localhost requests through the proxy, which fails.
        # Set NO_PROXY BEFORE creating httpx.Client so it respects it.
        if self.provider_type == "claude_bridge":
            self._ensure_no_proxy_for_localhost()

        # Claude bridge needs longer timeouts: CLI warmup (7-30s) + complex
        # prompt processing can exceed 60s before first token arrives.
        # Bridge itself allows 600s per-chunk; match that on client side.
        # write bumped to 30s so large prompts (big context files, agentic RAG)
        # finish uploading before the client gives up.
        if self.provider_type == "claude_bridge":
            self.client = httpx.Client(
                timeout=httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0)
            )
            # Bridge/Claude can handle much longer responses than default 512
            self.runtime_params.setdefault("max_tokens", 4096)
        else:
            self.client = httpx.Client(timeout=60.0)

        # Validate required fields (bridge uses CLI auth, no API key needed)
        if not self.api_key and self.provider_type != "claude_bridge":
            raise ValueError(f"API key required for provider {self.provider_id}")

        # Set default base URL if not provided
        if not self.base_url:
            default_url = PROVIDER_TYPES.get(self.provider_type, {}).get("default_base_url", "")
            if default_url:
                self.base_url = default_url
            else:
                raise ValueError(f"Base URL required for provider {self.provider_id}")

        # Model fallback chain: primary model + fallback_models from config
        self.fallback_models: List[str] = self.runtime_params.get("fallback_models", [])
        self._model_chain: List[str] = [self.model_name] + [
            m for m in self.fallback_models if m != self.model_name
        ]

        # Token usage from the most recent generation (for per-user accounting).
        # Shape: {"input_tokens": int, "output_tokens": int, "total_tokens": int,
        #         "model": str, "estimated": bool} or None.
        self.last_usage: Optional[dict] = None

        logger.info(
            f"[{self.provider_id}] Initialized OpenAI-compatible provider: {self.base_url}"
            + (
                f" (fallback chain: {len(self._model_chain)} models)"
                if self.fallback_models
                else ""
            )
        )

    # HTTP status codes that trigger model fallback
    # 402 = Payment Required (OpenRouter: model too expensive for account tier)
    _RETRIABLE_STATUSES = {402, 404, 429, 500, 502, 503}

    def _capture_usage(self, usage: Optional[dict], model: str, *, estimated: bool) -> None:
        """Normalize provider usage payload into self.last_usage."""
        if not usage:
            self.last_usage = None
            return
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        self.last_usage = {
            "input_tokens": prompt,
            "output_tokens": completion,
            "total_tokens": prompt + completion,
            "model": model,
            "estimated": estimated,
        }

    def _estimate_usage(self, messages: List[Dict], output_text: str, model: str) -> None:
        """Fallback when provider doesn't return usage (streaming Claude bridge)."""
        try:
            from app.utils.tokens import count_message_tokens, count_tokens

            prompt = int(count_message_tokens(messages, model))
            completion = int(count_tokens(output_text, model)) if output_text else 0
            self.last_usage = {
                "input_tokens": prompt,
                "output_tokens": completion,
                "total_tokens": prompt + completion,
                "model": model,
                "estimated": True,
            }
        except Exception as e:  # pragma: no cover — defensive
            logger.debug(f"[{self.provider_id}] usage estimate failed: {e}")
            self.last_usage = None

    @staticmethod
    def _ensure_no_proxy_for_localhost():
        """Add 127.0.0.1 and localhost to NO_PROXY so httpx bypasses VLESS proxy."""
        bypass = {"127.0.0.1", "localhost"}
        for key in ("NO_PROXY", "no_proxy"):
            current = os.environ.get(key, "")
            existing = {h.strip() for h in current.split(",") if h.strip()}
            missing = bypass - existing
            if missing:
                new_val = ",".join(sorted(existing | bypass))
                os.environ[key] = new_val

    def _get_headers(self) -> dict:
        headers: dict = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def is_available(self) -> bool:
        try:
            response = self.client.get(
                f"{self.base_url}/models", headers=self._get_headers(), timeout=10.0
            )
            # 200 = success, 401/403 = auth issue but API reachable
            return response.status_code in [200, 401, 403]
        except Exception as e:
            logger.warning(f"[{self.provider_id}] Health check failed: {e}")
            return False

    def generate_response(
        self, user_message: str, system_prompt: str = None, history: List[Dict] = None
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        return self._generate_non_stream(messages)

    def generate_response_stream(
        self, user_message: str, system_prompt: str = None, history: List[Dict] = None
    ) -> Generator[str, None, None]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        yield from self._generate_stream(messages)

    def generate_response_from_messages(
        self, messages: List[Dict[str, str]], stream: bool = False, params: Optional[Dict] = None
    ) -> Union[str, Generator[str, None, None]]:
        if stream:
            return self._generate_stream(messages, params=params)
        return self._generate_non_stream(messages, params=params)

    def generate_with_tools(
        self,
        messages: List[Dict],
        tools: List[Dict],
        stream: bool = False,
        params: Optional[Dict] = None,
    ) -> Union[dict, str, Generator]:
        """Generate response with tool-calling support.

        Non-stream: returns str (text) or dict with tool_calls.
        Stream: yields dicts {"type": "content", "content": "..."} or
                {"type": "tool_calls", "tool_calls": [...]}.
        """
        if stream:
            return self._generate_stream_with_tools(messages, tools, params=params)
        return self._generate_non_stream_with_tools(messages, tools, params=params)

    def _generate_non_stream_with_tools(
        self, messages: List[Dict], tools: List[Dict], params: Optional[Dict] = None
    ):
        """Non-stream generation with tools. Returns str or dict with tool_calls."""
        last_error_msg = "Извините, произошла техническая ошибка."

        for model in self._model_chain:
            try:
                response = self.client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._get_headers(),
                    json=self._build_request_json(
                        model, messages, stream=False, tools=tools, params=params
                    ),
                )
                response.raise_for_status()
                result = response.json()
                choice = result["choices"][0]
                finish_reason = choice.get("finish_reason")
                if finish_reason == "length":
                    logger.warning(
                        f"[{self.provider_id}] Response truncated (finish_reason=length) "
                        f"with model '{model}'. Consider increasing max_tokens."
                    )
                message = choice["message"]
                tool_calls = message.get("tool_calls")
                if tool_calls:
                    return message  # dict with role, content, tool_calls
                return (message.get("content") or "").strip()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                logger.warning(
                    f"[{self.provider_id}] Model '{model}' tools failed: "
                    f"HTTP {status} - {_safe_resp_text(e.response)[:200]}"
                )
                if status in self._RETRIABLE_STATUSES and model != self._model_chain[-1]:
                    continue
                last_error_msg = f"Error: HTTP {status}"
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                logger.warning(f"[{self.provider_id}] Model '{model}' timeout/connect: {e}")
                if model != self._model_chain[-1]:
                    continue
                last_error_msg = "Извините, произошла техническая ошибка."
            except Exception as e:
                logger.error(f"[{self.provider_id}] Error with model '{model}': {e}")
                last_error_msg = "Извините, произошла техническая ошибка."
                break

        return last_error_msg

    def _generate_stream_with_tools(
        self, messages: List[Dict], tools: List[Dict], params: Optional[Dict] = None
    ) -> Generator:
        """Stream generation with tools. Yields typed dicts."""
        for model in self._model_chain:
            try:
                with self.client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._get_headers(),
                    json=self._build_request_json(
                        model, messages, stream=True, tools=tools, params=params
                    ),
                ) as response:
                    response.raise_for_status()

                    # Accumulate tool_calls from delta chunks
                    tool_calls_acc: Dict[int, dict] = {}
                    has_tool_calls = False
                    finish_reason = None

                    for line in response.iter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                choice = chunk["choices"][0]
                                delta = choice.get("delta", {})

                                # Track finish_reason for truncation detection
                                fr = choice.get("finish_reason")
                                if fr:
                                    finish_reason = fr

                                # Content chunk
                                content = delta.get("content")
                                if content:
                                    yield {"type": "content", "content": content}

                                # Tool call chunks (streamed incrementally)
                                tc_deltas = delta.get("tool_calls")
                                if tc_deltas:
                                    has_tool_calls = True
                                    for tc in tc_deltas:
                                        idx = tc.get("index", 0)
                                        if idx not in tool_calls_acc:
                                            tool_calls_acc[idx] = {
                                                "id": tc.get("id", ""),
                                                "type": "function",
                                                "function": {"name": "", "arguments": ""},
                                            }
                                        acc = tool_calls_acc[idx]
                                        if tc.get("id"):
                                            acc["id"] = tc["id"]
                                        fn = tc.get("function", {})
                                        if fn.get("name"):
                                            acc["function"]["name"] = fn["name"]
                                        if fn.get("arguments"):
                                            acc["function"]["arguments"] += fn["arguments"]
                            except json.JSONDecodeError:
                                continue

                    # Detect truncated response (max_tokens hit)
                    if finish_reason == "length":
                        logger.warning(
                            f"[{self.provider_id}] Response truncated (finish_reason=length) "
                            f"with model '{model}'. Consider increasing max_tokens."
                        )

                    # Emit accumulated tool_calls at the end
                    if has_tool_calls and tool_calls_acc:
                        # Validate tool call arguments are parseable JSON
                        valid_tool_calls = []
                        for i in sorted(tool_calls_acc):
                            tc = tool_calls_acc[i]
                            args_str = tc["function"]["arguments"]
                            try:
                                json.loads(args_str)
                                valid_tool_calls.append(tc)
                            except json.JSONDecodeError:
                                logger.warning(
                                    f"[{self.provider_id}] Truncated tool call arguments "
                                    f"(index={i}, fn={tc['function']['name']}): {args_str[:100]}"
                                )
                        if valid_tool_calls:
                            yield {
                                "type": "tool_calls",
                                "tool_calls": valid_tool_calls,
                            }
                    return  # Stream completed successfully
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                logger.warning(
                    f"[{self.provider_id}] Stream tools model '{model}' failed: "
                    f"HTTP {status} - {_safe_resp_text(e.response)[:200]}"
                )
                if status in self._RETRIABLE_STATUSES and model != self._model_chain[-1]:
                    continue
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                logger.warning(
                    f"[{self.provider_id}] Stream tools model '{model}' timeout/connect: {e}"
                )
                if model != self._model_chain[-1]:
                    continue
            except Exception as e:
                logger.error(f"[{self.provider_id}] Stream tools error with model '{model}': {e}")
                break

        yield {"type": "content", "content": "Извините, произошла техническая ошибка."}

    def _build_request_json(
        self,
        model: str,
        messages: List[Dict],
        stream: bool,
        tools: Optional[List[Dict]] = None,
        params: Optional[Dict] = None,
    ) -> dict:
        default_max_tokens = 512
        # Tool-calling (agentic RAG) needs much more tokens: text + JSON tool calls
        # + accumulated context from prior search results
        if tools:
            default_max_tokens = 4096
        # Per-call params (persona) win over the provider's runtime defaults
        effective = dict(self.runtime_params)
        if params:
            effective.update({k: v for k, v in params.items() if v is not None})
        payload = {
            "model": model,
            "messages": messages,
            "temperature": effective.get("temperature", 0.7),
            "max_tokens": effective.get("max_tokens", default_max_tokens),
            "top_p": effective.get("top_p", 0.9),
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    def _generate_non_stream(
        self, messages: List[Dict[str, str]], params: Optional[Dict] = None
    ) -> str:
        last_error_msg = "Извините, произошла техническая ошибка."

        for model in self._model_chain:
            try:
                response = self.client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._get_headers(),
                    json=self._build_request_json(model, messages, stream=False, params=params),
                )
                response.raise_for_status()
                result = response.json()
                content = result["choices"][0]["message"]["content"].strip()
                self._capture_usage(result.get("usage"), model, estimated=False)
                if model != self._model_chain[0]:
                    logger.info(f"[{self.provider_id}] Fallback succeeded with model: {model}")
                return content
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                logger.warning(
                    f"[{self.provider_id}] Model '{model}' failed: "
                    f"HTTP {status} - {_safe_resp_text(e.response)[:200]}"
                )
                if status in self._RETRIABLE_STATUSES and model != self._model_chain[-1]:
                    continue
                error_messages = {
                    401: "Invalid API key",
                    402: "Insufficient credits - top up account or use free models",
                    403: "Access denied - check API key permissions",
                    404: f"Model '{model}' not found - check model name",
                    429: "Rate limit exceeded - wait or upgrade plan",
                    500: "Provider server error",
                    502: "Provider gateway error",
                    503: "Provider temporarily unavailable",
                }
                last_error_msg = f"Error: {error_messages.get(status, f'HTTP {status}')}"
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                logger.warning(f"[{self.provider_id}] Model '{model}' timeout/connect: {e}")
                if model != self._model_chain[-1]:
                    continue
                last_error_msg = "Извините, произошла техническая ошибка."
            except Exception as e:
                logger.error(f"[{self.provider_id}] Error with model '{model}': {e}")
                last_error_msg = "Извините, произошла техническая ошибка."
                break  # Unknown error — don't retry

        return last_error_msg

    def _generate_stream(
        self, messages: List[Dict[str, str]], params: Optional[Dict] = None
    ) -> Generator[str, None, None]:
        for model in self._model_chain:
            try:
                with self.client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._get_headers(),
                    json=self._build_request_json(model, messages, stream=True, params=params),
                ) as response:
                    response.raise_for_status()
                    if model != self._model_chain[0]:
                        logger.info(
                            f"[{self.provider_id}] Fallback stream opened with model: {model}"
                        )
                    accumulated: list[str] = []
                    final_usage: Optional[dict] = None
                    for line in response.iter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                # OpenAI-compat: final chunk may carry `usage`
                                if chunk.get("usage"):
                                    final_usage = chunk["usage"]
                                choices = chunk.get("choices") or []
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        accumulated.append(content)
                                        yield content
                            except json.JSONDecodeError:
                                continue
                    if final_usage:
                        self._capture_usage(final_usage, model, estimated=False)
                    else:
                        self._estimate_usage(messages, "".join(accumulated), model)
                    return  # Stream completed successfully
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                logger.warning(
                    f"[{self.provider_id}] Stream model '{model}' failed: "
                    f"HTTP {status} - {_safe_resp_text(e.response)[:200]}"
                )
                if status in self._RETRIABLE_STATUSES and model != self._model_chain[-1]:
                    continue
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                logger.warning(f"[{self.provider_id}] Stream model '{model}' timeout/connect: {e}")
                if model != self._model_chain[-1]:
                    continue
            except Exception as e:
                logger.error(f"[{self.provider_id}] Stream error with model '{model}': {e}")
                break  # Unknown error — don't retry

        yield "Извините, произошла техническая ошибка."


class GeminiProvider(BaseLLMProvider):
    """
    Provider for Google Gemini API.
    Uses the google-generativeai SDK.
    Supports optional VLESS proxy via xray-core with fallback support.
    """

    def __init__(self, config: dict):
        super().__init__(config)

        if not GEMINI_AVAILABLE:
            raise ImportError(
                "google-generativeai package not installed. Install with: pip install google-generativeai"
            )

        if not self.api_key:
            raise ValueError("API key required for Gemini provider")

        # Initialize VLESS proxy BEFORE configuring genai (so HTTP client uses proxy)
        self.proxy_manager: Optional[Union["XrayProxyManager", "XrayProxyManagerWithFallback"]] = (
            None
        )
        self._setup_vless_proxy()

        # Start proxy and set env vars BEFORE genai.configure()
        # This ensures the HTTP client is created with proxy settings
        if self.proxy_manager:
            self.proxy_manager.start()
            proxy_url = f"http://127.0.0.1:{self.proxy_manager.http_port}"
            os.environ["HTTP_PROXY"] = proxy_url
            os.environ["HTTPS_PROXY"] = proxy_url
            os.environ["http_proxy"] = proxy_url
            os.environ["https_proxy"] = proxy_url
            logger.info(f"[{self.provider_id}] Proxy env set: {proxy_url}")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(model_name=self.model_name or "gemini-2.0-flash")

        logger.info(f"[{self.provider_id}] Initialized Gemini provider: {self.model_name}")

    def _setup_vless_proxy(self):
        """Setup VLESS proxy if configured in runtime_params.

        Supports:
        - vless_url: single URL (backward compatible)
        - vless_urls: list of URLs with automatic fallback
        """
        # Check for list of URLs first (new format with fallback)
        vless_urls = self.runtime_params.get("vless_urls", [])
        vless_url = self.runtime_params.get("vless_url", "")

        # Normalize to list
        if vless_urls:
            urls = vless_urls if isinstance(vless_urls, list) else [vless_urls]
        elif vless_url:
            urls = [vless_url]
        else:
            return

        if not XRAY_AVAILABLE:
            logger.warning(
                f"[{self.provider_id}] VLESS URL configured but xray_proxy_manager not available"
            )
            return

        # Use fallback manager if multiple URLs, otherwise simple manager
        if len(urls) > 1:
            self.proxy_manager = XrayProxyManagerWithFallback()
            count = self.proxy_manager.configure_proxies(urls)
            if count > 0:
                logger.info(
                    f"[{self.provider_id}] VLESS proxy configured with {count} fallback servers"
                )
            else:
                logger.warning(f"[{self.provider_id}] No valid VLESS URLs configured")
                self.proxy_manager = None
        else:
            # Single URL - use simple manager
            is_valid, error = validate_vless_url(urls[0])
            if not is_valid:
                logger.error(f"[{self.provider_id}] Invalid VLESS URL: {error}")
                return

            self.proxy_manager = XrayProxyManager()
            if self.proxy_manager.configure(urls[0]):
                logger.info(f"[{self.provider_id}] VLESS proxy configured")
            else:
                logger.warning(f"[{self.provider_id}] Failed to configure VLESS proxy")
                self.proxy_manager = None

    def get_proxy_status(self) -> dict:
        """Get VLESS proxy status."""
        if not self.proxy_manager:
            return {
                "configured": False,
                "xray_available": XRAY_AVAILABLE and XrayProxyManager is not None,
                "fallback_enabled": False,
            }
        status = self.proxy_manager.get_status()
        status["fallback_enabled"] = isinstance(self.proxy_manager, XrayProxyManagerWithFallback)
        return status

    def test_proxy_connection(self, index: int = -1) -> dict:
        """Test VLESS proxy connection to Google API.

        Args:
            index: Proxy index to test (-1 for current/all)
        """
        if not self.proxy_manager:
            return {"success": False, "error": "No VLESS proxy configured"}

        if isinstance(self.proxy_manager, XrayProxyManagerWithFallback):
            if index >= 0:
                return self.proxy_manager.test_proxy(index)
            return {"results": self.proxy_manager.test_all_proxies()}

        return self.proxy_manager.test_connection("https://generativelanguage.googleapis.com")

    def mark_proxy_failed(self):
        """Mark current proxy as failed and switch to next (fallback mode only)."""
        if isinstance(self.proxy_manager, XrayProxyManagerWithFallback):
            self.proxy_manager.mark_current_failed()

    def reset_proxies(self):
        """Reset all proxies to enabled state (fallback mode only)."""
        if isinstance(self.proxy_manager, XrayProxyManagerWithFallback):
            self.proxy_manager.reset_all_proxies()

    def is_available(self) -> bool:
        """Check if provider is available. Proxy is already running if configured."""
        try:
            # Proxy env vars are set in __init__, just test the API
            list(genai.list_models())
            return True
        except Exception as e:
            logger.warning(f"[{self.provider_id}] Health check failed: {e}")
            return False

    def _gemini_generation_config(self, params: Optional[Dict] = None) -> Optional[Dict]:
        """Map generic generation params onto Gemini's naming.

        repetition_penalty has no Gemini equivalent and is dropped.
        """
        effective = dict(self.runtime_params)
        if params:
            effective.update({k: v for k, v in params.items() if v is not None})
        config = {}
        if effective.get("temperature") is not None:
            config["temperature"] = effective["temperature"]
        if effective.get("top_p") is not None:
            config["top_p"] = effective["top_p"]
        if effective.get("max_tokens") is not None:
            config["max_output_tokens"] = effective["max_tokens"]
        return config or None

    def generate_response(
        self,
        user_message: str,
        system_prompt: str = None,
        history: List[Dict] = None,
        params: Optional[Dict] = None,
    ) -> str:
        """Generate response. Proxy is already running if configured."""
        try:
            # Rebuild model with system instruction if provided
            if system_prompt:
                model = genai.GenerativeModel(
                    model_name=self.model_name or "gemini-2.0-flash",
                    system_instruction=system_prompt,
                )
            else:
                model = self.model

            # Convert history to Gemini format
            gemini_history = []
            if history:
                for msg in history:
                    role = "model" if msg["role"] == "assistant" else msg["role"]
                    if role not in ["user", "model"]:
                        continue
                    gemini_history.append({"role": role, "parts": [msg["content"]]})

            chat = model.start_chat(history=gemini_history)
            response = chat.send_message(
                user_message, generation_config=self._gemini_generation_config(params)
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"[{self.provider_id}] Error: {e}")
            return "Извините, произошла техническая ошибка."

    def generate_response_stream(
        self,
        user_message: str,
        system_prompt: str = None,
        history: List[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Generator[str, None, None]:
        """Generate streaming response. Proxy is already running if configured."""
        try:
            if system_prompt:
                model = genai.GenerativeModel(
                    model_name=self.model_name or "gemini-2.0-flash",
                    system_instruction=system_prompt,
                )
            else:
                model = self.model

            gemini_history = []
            if history:
                for msg in history:
                    role = "model" if msg["role"] == "assistant" else msg["role"]
                    if role not in ["user", "model"]:
                        continue
                    gemini_history.append({"role": role, "parts": [msg["content"]]})

            chat = model.start_chat(history=gemini_history)
            response = chat.send_message(
                user_message,
                stream=True,
                generation_config=self._gemini_generation_config(params),
            )

            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"[{self.provider_id}] Stream error: {e}")
            yield "Извините, произошла техническая ошибка."

    def generate_response_from_messages(
        self, messages: List[Dict[str, str]], stream: bool = False, params: Optional[Dict] = None
    ) -> Union[str, Generator[str, None, None]]:
        # Extract system prompt and convert to Gemini format
        system_prompt = None
        history = []
        last_user = ""

        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            elif msg["role"] == "user":
                last_user = msg["content"]
                history.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                history.append({"role": "assistant", "content": msg["content"]})

        # Remove last user message from history (will be sent)
        if history and history[-1]["role"] == "user":
            history = history[:-1]

        if stream:
            return self.generate_response_stream(last_user, system_prompt, history, params=params)
        return self.generate_response(last_user, system_prompt, history, params=params)


class CloudLLMService:
    """
    Main service class for cloud LLM providers.
    Manages provider instances and provides unified interface.

    Compatible with LLMService and VLLMLLMService interfaces.
    """

    # Provider class mapping
    PROVIDER_CLASSES = {
        "gemini": GeminiProvider,
        "kimi": OpenAICompatibleProvider,
        "openai": OpenAICompatibleProvider,
        "claude": OpenAICompatibleProvider,
        "deepseek": OpenAICompatibleProvider,
        "openrouter": OpenAICompatibleProvider,
        "custom": OpenAICompatibleProvider,
        "claude_bridge": OpenAICompatibleProvider,
    }

    def __init__(self, provider_config: dict):
        """
        Initialize with provider configuration from database.

        Args:
            provider_config: Dict with id, provider_type, api_key, base_url, model_name, config
        """
        self.config = provider_config
        self.provider_type = provider_config.get("provider_type", "custom")
        self.provider_id = provider_config.get("id", "unknown")

        # Get provider class and instantiate
        provider_class = self.PROVIDER_CLASSES.get(self.provider_type, OpenAICompatibleProvider)
        self.provider: BaseLLMProvider = provider_class(provider_config)

        # For compatibility with existing code
        self.model_name = provider_config.get("model_name", "")
        self.api_url = provider_config.get("base_url", "")
        self.backend_type = "cloud"  # Отличает от vLLM

        # FAQ (загружается через reload_faq из БД)
        self.faq: Dict[str, str] = {}

        # Conversation history
        self.conversation_history: List[Dict[str, str]] = []

        # System prompt (for secretary persona)
        self.system_prompt = provider_config.get("system_prompt", "")

        logger.info(f"CloudLLMService initialized: {self.provider_id} ({self.provider_type})")

    @property
    def last_usage(self) -> Optional[dict]:
        """Token usage from the most recent LLM call (proxied from provider)."""
        return getattr(self.provider, "last_usage", None)

    def _normalize_faq(self, faq_dict: Dict[str, str]) -> Dict[str, str]:
        """Нормализует ключи FAQ (lowercase, strip)"""
        return {k.lower().strip(): v for k, v in faq_dict.items()}

    def _check_faq(self, user_message: str) -> Optional[str]:
        if not self.faq:
            return None
        normalized = user_message.lower().strip().rstrip("?!.,")
        if normalized in self.faq:
            return self._apply_faq_templates(self.faq[normalized])
        for key, response in self.faq.items():
            if key in normalized or normalized in key:
                return self._apply_faq_templates(response)
        return None

    def _apply_faq_templates(self, response: str) -> str:
        now = datetime.now()
        replacements = {
            "{current_time}": now.strftime("%H:%M"),
            "{current_date}": now.strftime("%d.%m.%Y"),
            "{day_of_week}": [
                "понедельник",
                "вторник",
                "среда",
                "четверг",
                "пятница",
                "суббота",
                "воскресенье",
            ][now.weekday()],
        }
        for placeholder, value in replacements.items():
            response = response.replace(placeholder, value)
        return response

    def reload_faq(self, faq_dict: Dict[str, str] = None):
        """
        Перезагружает FAQ (hot reload).

        Args:
            faq_dict: FAQ словарь из БД. Если не передан, FAQ очищается.
        """
        if faq_dict:
            self.faq = self._normalize_faq(faq_dict)
        else:
            self.faq = {}
        logger.info(f"🔄 FAQ перезагружен: {len(self.faq)} записей")

    def get_system_prompt(self) -> str:
        """Return the system prompt configured for this provider."""
        return self.system_prompt or ""

    def is_available(self) -> bool:
        """Check if provider is available."""
        return self.provider.is_available()

    def generate_response(self, user_message: str, use_history: bool = True) -> str:
        """Generate response (compatible with LLMService/VLLMLLMService)."""
        # Check FAQ first
        faq_response = self._check_faq(user_message)
        if faq_response:
            if use_history:
                self.conversation_history.append({"role": "user", "content": user_message})
                self.conversation_history.append({"role": "assistant", "content": faq_response})
            return faq_response

        history = self.conversation_history if use_history else []
        response = self.provider.generate_response(user_message, self.system_prompt, history)

        if use_history:
            self.conversation_history.append({"role": "user", "content": user_message})
            self.conversation_history.append({"role": "assistant", "content": response})

        return response

    def generate_response_stream(
        self, user_message: str, use_history: bool = True
    ) -> Generator[str, None, None]:
        """Generate streaming response (compatible with LLMService/VLLMLLMService)."""
        # Check FAQ first
        faq_response = self._check_faq(user_message)
        if faq_response:
            if use_history:
                self.conversation_history.append({"role": "user", "content": user_message})
                self.conversation_history.append({"role": "assistant", "content": faq_response})
            yield faq_response
            return

        history = self.conversation_history if use_history else []
        full_response = ""

        for chunk in self.provider.generate_response_stream(
            user_message, self.system_prompt, history
        ):
            full_response += chunk
            yield chunk

        if use_history and full_response:
            self.conversation_history.append({"role": "user", "content": user_message})
            self.conversation_history.append({"role": "assistant", "content": full_response})

    def generate_response_from_messages(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False,
        tools: Optional[List[Dict]] = None,
        params: Optional[Dict] = None,
    ) -> Union[str, Generator[str, None, None]]:
        """Generate response from OpenAI-format messages (compatible with orchestrator).

        params — per-call generation parameters (chat/instance persona).
        """
        # Tool-calling mode: skip FAQ, delegate to provider
        if tools and getattr(self.provider, "supports_tools", False):
            return self.provider.generate_with_tools(messages, tools, stream, params=params)

        # Check FAQ for single-message requests
        user_messages = [m for m in messages if m.get("role") == "user"]
        if len(user_messages) == 1:
            faq_response = self._check_faq(user_messages[0]["content"])
            if faq_response:
                if stream:

                    def gen():
                        yield faq_response

                    return gen()
                return faq_response

        return self.provider.generate_response_from_messages(messages, stream, params=params)

    def reset_conversation(self):
        """Clear conversation history."""
        self.conversation_history = []

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Get conversation history."""
        return self.conversation_history

    def set_params(self, **kwargs):
        """Set runtime parameters."""
        self.provider.set_params(**kwargs)

    def get_params(self) -> Dict:
        """Get runtime parameters."""
        return self.provider.get_params()

    # For compatibility with VLLMLLMService persona system
    @property
    def runtime_params(self) -> Dict:
        return self.provider.runtime_params

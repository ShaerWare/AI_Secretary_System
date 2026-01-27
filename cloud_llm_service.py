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
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Generator, List, Optional, Union

import httpx


# Gemini SDK (optional)
try:
    import google.generativeai as genai

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None

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
            "google/gemma-2-9b-it:free",
            "meta-llama/llama-3.2-3b-instruct:free",
            "qwen/qwen-2-7b-instruct:free",
            "mistralai/mistral-7b-instruct:free",
            "nousresearch/hermes-3-llama-3.1-405b:free",
        ],
        "requires_base_url": True,
    },
    "custom": {
        "name": "Custom OpenAI-Compatible",
        "default_base_url": "",
        "default_models": [],
        "requires_base_url": True,
    },
}


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

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
                "max_tokens": 512,
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
        self, messages: List[Dict[str, str]], stream: bool = False
    ) -> Union[str, Generator[str, None, None]]:
        """Generate response from OpenAI-format messages."""
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

    def __init__(self, config: dict):
        super().__init__(config)
        self.client = httpx.Client(timeout=60.0)

        # Validate required fields
        if not self.api_key:
            raise ValueError(f"API key required for provider {self.provider_id}")

        # Set default base URL if not provided
        if not self.base_url:
            default_url = PROVIDER_TYPES.get(self.provider_type, {}).get("default_base_url", "")
            if default_url:
                self.base_url = default_url
            else:
                raise ValueError(f"Base URL required for provider {self.provider_id}")

        logger.info(f"[{self.provider_id}] Initialized OpenAI-compatible provider: {self.base_url}")

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

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
        self, messages: List[Dict[str, str]], stream: bool = False
    ) -> Union[str, Generator[str, None, None]]:
        if stream:
            return self._generate_stream(messages)
        return self._generate_non_stream(messages)

    def _generate_non_stream(self, messages: List[Dict[str, str]]) -> str:
        try:
            response = self.client.post(
                f"{self.base_url}/chat/completions",
                headers=self._get_headers(),
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "temperature": self.runtime_params.get("temperature", 0.7),
                    "max_tokens": self.runtime_params.get("max_tokens", 512),
                    "top_p": self.runtime_params.get("top_p", 0.9),
                    "stream": False,
                },
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"[{self.provider_id}] HTTP error: {e.response.status_code} - {e.response.text}"
            )
            return f"Error: API returned {e.response.status_code}"
        except Exception as e:
            logger.error(f"[{self.provider_id}] Error: {e}")
            return "Извините, произошла техническая ошибка."

    def _generate_stream(self, messages: List[Dict[str, str]]) -> Generator[str, None, None]:
        try:
            with self.client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._get_headers(),
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "temperature": self.runtime_params.get("temperature", 0.7),
                    "max_tokens": self.runtime_params.get("max_tokens", 512),
                    "top_p": self.runtime_params.get("top_p", 0.9),
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"[{self.provider_id}] Stream error: {e}")
            yield "Извините, произошла техническая ошибка."


class GeminiProvider(BaseLLMProvider):
    """
    Provider for Google Gemini API.
    Uses the google-generativeai SDK.
    """

    def __init__(self, config: dict):
        super().__init__(config)

        if not GEMINI_AVAILABLE:
            raise ImportError(
                "google-generativeai package not installed. Install with: pip install google-generativeai"
            )

        if not self.api_key:
            raise ValueError("API key required for Gemini provider")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(model_name=self.model_name or "gemini-2.0-flash")

        logger.info(f"[{self.provider_id}] Initialized Gemini provider: {self.model_name}")

    def is_available(self) -> bool:
        try:
            # Simple test - list models
            list(genai.list_models())
            return True
        except Exception as e:
            logger.warning(f"[{self.provider_id}] Health check failed: {e}")
            return False

    def generate_response(
        self, user_message: str, system_prompt: str = None, history: List[Dict] = None
    ) -> str:
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
            response = chat.send_message(user_message)
            return response.text.strip()
        except Exception as e:
            logger.error(f"[{self.provider_id}] Error: {e}")
            return "Извините, произошла техническая ошибка."

    def generate_response_stream(
        self, user_message: str, system_prompt: str = None, history: List[Dict] = None
    ) -> Generator[str, None, None]:
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
            response = chat.send_message(user_message, stream=True)

            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"[{self.provider_id}] Stream error: {e}")
            yield "Извините, произошла техническая ошибка."

    def generate_response_from_messages(
        self, messages: List[Dict[str, str]], stream: bool = False
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
            return self.generate_response_stream(last_user, system_prompt, history)
        return self.generate_response(last_user, system_prompt, history)


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

        # FAQ (загружается через reload_faq из БД)
        self.faq: Dict[str, str] = {}

        # Conversation history
        self.conversation_history: List[Dict[str, str]] = []

        # System prompt (for secretary persona)
        self.system_prompt = provider_config.get("system_prompt", "")

        logger.info(f"CloudLLMService initialized: {self.provider_id} ({self.provider_type})")

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
        self, messages: List[Dict[str, str]], stream: bool = False
    ) -> Union[str, Generator[str, None, None]]:
        """Generate response from OpenAI-format messages (compatible with orchestrator)."""
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

        return self.provider.generate_response_from_messages(messages, stream)

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

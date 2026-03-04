"""
LLM Router — routes requests to Claude or Qwen based on task type.

Cost optimization strategy:
- Claude (Claude Code CLI bridge): TZ generation ONLY (~5% of requests)
- Qwen 2.5 (vLLM local): Everything else (~95% of requests)

This saves ~95% on LLM costs while maintaining quality for critical tasks.
"""

import json
import logging
from enum import Enum
from typing import AsyncIterator, Optional

import httpx


logger = logging.getLogger(__name__)


class LLMBackend(Enum):
    """Available LLM backends."""

    CLAUDE = "claude"  # Claude Code CLI bridge (expensive, smart)
    QWEN = "qwen"  # Local Qwen 2.5 via vLLM (free, fast)


class LLMRouter:
    """
    Routes LLM requests to appropriate backend.

    Decision logic:
    - TZ generation → Claude (needs complex reasoning)
    - Custom quotes → Claude (business analysis)
    - Everything else → Qwen (fast, free)
    """

    def __init__(
        self,
        orchestrator_url: str = "http://localhost:8002",
        claude_provider_id: str = "claude-bridge",
        default_backend: str = "vllm",
    ):
        """
        Initialize router.

        Args:
            orchestrator_url: URL of AI Secretary orchestrator API
            claude_provider_id: ID of Claude provider in cloud_llm_providers table
            default_backend: Default LLM backend for general chat (from bot config)
        """
        self.orchestrator_url = orchestrator_url.rstrip("/")
        self.claude_provider_id = claude_provider_id
        self.default_backend = default_backend
        self._http_client: Optional[httpx.AsyncClient] = None
        self._session_map: dict[str, str] = {}  # bot session_id → orchestrator session_id

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with auth from BOT_INTERNAL_TOKEN."""
        if self._http_client is None or self._http_client.is_closed:
            import os

            headers = {}
            internal_token = os.environ.get("BOT_INTERNAL_TOKEN")
            if internal_token:
                headers["Authorization"] = f"Bearer {internal_token}"
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=10.0), headers=headers
            )
        return self._http_client

    async def _ensure_session(
        self,
        client: httpx.AsyncClient,
        session_id: Optional[str],
        source_id: Optional[str] = None,
    ) -> str:
        """Ensure a chat session exists in the orchestrator DB.

        If *session_id* is given, check whether it already exists.
        Create a new orchestrator session when needed and cache the mapping
        so subsequent calls reuse the same DB session.

        Args:
            client: HTTP client.
            session_id: Optional local session ID.
            source_id: Optional source identifier (e.g. ``bot_id:user_id``).
        """
        # Already resolved earlier in this process?
        if session_id and session_id in self._session_map:
            return self._session_map[session_id]

        # Check if the session exists on the orchestrator
        if session_id:
            resp = await client.get(f"{self.orchestrator_url}/admin/chat/sessions/{session_id}")
            if resp.status_code == 200:
                return session_id

        # Create a new session on the orchestrator
        try:
            body: dict = {"title": "Telegram Bot", "source": "telegram_bot"}
            if source_id:
                body["source_id"] = source_id
            create_resp = await client.post(
                f"{self.orchestrator_url}/admin/chat/sessions",
                json=body,
            )
            create_resp.raise_for_status()
            new_id = create_resp.json()["session"]["id"]
            if session_id:
                self._session_map[session_id] = new_id
            logger.info(f"Created orchestrator session {new_id} (bot session: {session_id})")
            return new_id
        except Exception as e:
            logger.error(f"Failed to create orchestrator session: {e}")
            raise

    def _get_backend_string(self, backend: LLMBackend) -> str:
        """Convert backend enum to API string."""
        if backend == LLMBackend.CLAUDE:
            return f"cloud:{self.claude_provider_id}"
        return self.default_backend

    async def generate_stream(
        self,
        messages: list[dict],
        backend: LLMBackend = LLMBackend.QWEN,
        session_id: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Generate response using specified backend with streaming.

        Args:
            messages: Chat messages in OpenAI format
            backend: Which LLM to use
            session_id: Optional session ID for context
            user_id: Optional Telegram user ID for source tracking

        Yields:
            Response text chunks
        """
        client = await self._get_client()
        llm_backend = self._get_backend_string(backend)

        logger.info(f"LLM Router: using backend={backend.value} ({llm_backend})")

        # Extract system prompt and user message
        system_prompt = None
        user_content = ""
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            elif msg["role"] == "user":
                user_content = msg["content"]

        # Build request payload
        payload = {
            "content": user_content,
            "llm_override": {
                "llm_backend": llm_backend,
                "system_prompt": system_prompt,
            },
        }

        # Build source_id from bot instance + user
        source_id: Optional[str] = None
        if user_id:
            from ..config import get_bot_instance_id

            instance_id = get_bot_instance_id()
            if instance_id:
                source_id = f"{instance_id}:{user_id}"

        # Ensure session exists in orchestrator DB
        session_id = await self._ensure_session(client, session_id, source_id=source_id)
        endpoint = f"{self.orchestrator_url}/admin/chat/sessions/{session_id}/stream"

        try:
            async with client.stream("POST", endpoint, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            if data.get("type") == "chunk" and data.get("content"):
                                yield data["content"]
                            elif data.get("type") == "error":
                                yield f"\n\nError: {data.get('content', 'Unknown error')}"
                                break
                        except json.JSONDecodeError:
                            pass
        except httpx.HTTPError as e:
            logger.error(f"HTTP error during streaming: {e}")
            yield f"Error: {e}"

    async def generate(
        self,
        messages: list[dict],
        backend: LLMBackend = LLMBackend.QWEN,
    ) -> str:
        """
        Generate complete response (non-streaming).

        Args:
            messages: Chat messages in OpenAI format
            backend: Which LLM to use

        Returns:
            Complete response text
        """
        full_text = ""
        async for chunk in self.generate_stream(messages, backend):
            full_text += chunk
        return full_text.strip()

    # ─── Convenience Methods ─────────────────────────────────────

    async def generate_tz(
        self,
        system_prompt: str,
        user_message: str,
    ) -> str:
        """
        Generate TZ document using Claude.

        This is the ONLY place where Claude should be used.
        TZ generation requires complex reasoning and document structuring.

        Args:
            system_prompt: System prompt with TZ format instructions
            user_message: User's project requirements

        Returns:
            Generated TZ document
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        logger.info("Generating TZ document using Claude")
        return await self.generate(messages, backend=LLMBackend.CLAUDE)

    async def generate_news_post(
        self,
        system_prompt: str,
        pr_data: str,
    ) -> str:
        """
        Generate SMM news post using Qwen.

        News generation is template-based and doesn't require Claude's
        advanced reasoning. Qwen handles it well.

        Args:
            system_prompt: SMM prompt with format instructions
            pr_data: PR data as JSON string

        Returns:
            Generated news post
        """
        user_message = f"""Сгенерируй новостной пост для этого Pull Request:

```json
{pr_data}
```

Напиши только текст поста, без пояснений."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        logger.info("Generating news post using Qwen")
        return await self.generate(messages, backend=LLMBackend.QWEN)

    async def chat_stream(
        self,
        messages: list[dict],
        session_id: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        General chat using Qwen with streaming.

        Args:
            messages: Chat history
            session_id: Optional session ID
            user_id: Optional Telegram user ID for source tracking

        Yields:
            Response chunks
        """
        async for chunk in self.generate_stream(
            messages, backend=LLMBackend.QWEN, session_id=session_id, user_id=user_id
        ):
            yield chunk

    async def chat(
        self,
        messages: list[dict],
    ) -> str:
        """
        General chat using Qwen (non-streaming).

        Args:
            messages: Chat history

        Returns:
            Complete response
        """
        return await self.generate(messages, backend=LLMBackend.QWEN)

    async def close(self):
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None


# ─── Singleton ─────────────────────────────────────────────────


_router: Optional[LLMRouter] = None


def get_llm_router(
    orchestrator_url: Optional[str] = None,
    claude_provider_id: Optional[str] = None,
) -> LLMRouter:
    """
    Get or create the singleton LLM router.

    Args:
        orchestrator_url: Override orchestrator URL
        claude_provider_id: Override Claude provider ID

    Returns:
        LLMRouter instance
    """
    global _router
    if _router is None:
        import os

        from ..state import get_bot_config

        url = orchestrator_url or os.environ.get("ORCHESTRATOR_URL", "http://localhost:8002")
        provider_id = claude_provider_id or os.environ.get("CLAUDE_PROVIDER_ID", "claude-bridge")

        # Use bot instance's llm_backend if available (multi-instance mode)
        default_backend = "vllm"
        bot_config = get_bot_config()
        if bot_config and bot_config.llm_backend:
            default_backend = bot_config.llm_backend
            logger.info(f"LLM Router: using bot config backend: {default_backend}")

        _router = LLMRouter(
            orchestrator_url=url,
            claude_provider_id=provider_id,
            default_backend=default_backend,
        )
    return _router

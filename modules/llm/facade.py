"""LLMService facade — unified entry point for LLM generation.

Implements the ``LLMService`` Protocol from ``modules.llm.protocols``.
Delegates to existing services (Strangler Fig pattern):
- Generation → ``CloudLLMService`` / ``VLLMLLMService`` (via ServiceContainer, lazy)
- Provider CRUD → ``CloudProviderService``

Existing ``container.llm_service`` (CloudLLMService/VLLMLLMService instance)
remains for backward compatibility — this facade wraps it, not replaces.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from modules.llm.schemas import (
    LLMConfig,
    LLMParams,
    ProviderInfo,
    StreamChunk,
)


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.dependencies import ServiceContainer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# dict → TypedDict converters
# ---------------------------------------------------------------------------


def _to_provider_info(d: dict) -> ProviderInfo:
    """Convert a CloudProviderService dict to ProviderInfo TypedDict."""
    config = d.get("config") or {}
    return ProviderInfo(
        id=d["id"],
        name=d["name"],
        provider_type=d.get("provider_type", "custom"),
        model_name=d.get("model_name", ""),
        enabled=d.get("enabled", True),
        is_default=d.get("is_default", False),
        base_url=d.get("base_url"),
        description=d.get("description"),
        config=LLMParams(
            temperature=config.get("temperature", 0.7),
            max_tokens=config.get("max_tokens", 1024),
            top_p=config.get("top_p", 0.9),
            repetition_penalty=config.get("repetition_penalty", 1.0),
        ),
        created=d.get("created"),
        updated=d.get("updated"),
    )


def _to_stream_chunk(raw) -> StreamChunk:
    """Normalize a provider stream item to StreamChunk TypedDict.

    Provider yields either:
    - ``str`` (plain content from _generate_stream)
    - ``dict`` with ``type``/``content``/``tool_calls`` (from _generate_stream_with_tools)
    """
    if isinstance(raw, str):
        return StreamChunk(type="content", content=raw)
    # dict from generate_with_tools stream
    return StreamChunk(
        type=raw.get("type", "content"),
        content=raw.get("content", ""),
        tool_calls=raw.get("tool_calls", []),
    )


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------


class LLMServiceImpl:
    """Facade implementing the LLMService Protocol.

    Receives ``ServiceContainer`` to lazily access ``llm_service``
    (the underlying CloudLLMService/VLLMLLMService, which may change
    at runtime when InternetMonitor switches backends).
    """

    def __init__(self, container: ServiceContainer) -> None:
        self._container = container

    # -- Generation -----------------------------------------------------------

    async def generate(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig | None = None,
    ) -> str:
        """Single-shot generation. Returns the full assistant reply."""
        llm = self._resolve_llm(config)
        if not llm:
            return ""

        tools = None
        if config and config.get("tools"):
            tools = config["tools"]

        result = await asyncio.to_thread(
            llm.generate_response_from_messages, messages, False, *([tools] if tools else [])
        )

        # generate_with_tools may return dict (tool_calls message) — stringify
        if isinstance(result, dict):
            return result.get("content") or ""
        return result or ""

    async def stream(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming generation. Yields content/tool-call chunks."""
        llm = self._resolve_llm(config)
        if not llm:
            return

        tools = None
        if config and config.get("tools"):
            tools = config["tools"]

        sync_gen = llm.generate_response_from_messages(messages, True, *([tools] if tools else []))

        # Wrap sync generator in async iteration via thread
        for chunk in await asyncio.to_thread(list, sync_gen):
            yield _to_stream_chunk(chunk)

    # -- Provider resolution --------------------------------------------------

    async def resolve_backend(self, backend_id: str) -> ProviderInfo | None:
        """Look up a cloud provider by its ID."""
        from modules.llm.service import cloud_provider_service

        raw = await cloud_provider_service.get_provider(backend_id)
        if raw is None:
            return None
        return _to_provider_info(raw)

    async def list_providers(
        self,
        *,
        enabled_only: bool = False,
        workspace_id: int | None = None,
    ) -> list[ProviderInfo]:
        """List registered cloud LLM providers."""
        from modules.llm.service import cloud_provider_service

        raw = await cloud_provider_service.list_providers(
            enabled_only=enabled_only, workspace_id=workspace_id
        )
        return [_to_provider_info(p) for p in raw]

    # -- Internal helpers -----------------------------------------------------

    def _resolve_llm(self, config: LLMConfig | None = None):
        """Get the active LLM service, applying config params if provided."""
        llm = self._container.llm_service
        if not llm:
            return None

        # Apply runtime params from config if provided
        if config:
            params = {}
            for key in ("temperature", "max_tokens", "top_p", "repetition_penalty"):
                if key in config:
                    params[key] = config[key]
            if params and hasattr(llm, "set_params"):
                llm.set_params(**params)

        return llm


# Module-level singleton — NOT created here because it needs ServiceContainer.
# Created in startup and set via: llm_service_facade = LLMServiceImpl(container)
llm_service_facade: Optional[LLMServiceImpl] = None

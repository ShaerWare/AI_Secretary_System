"""Target Protocol interfaces for the LLM domain.

These Protocols describe the *ideal* service contracts.  Currently
generation logic lives in ``cloud_llm_service.py`` and the
orchestrator; the Protocols define the target facade.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from modules.llm.schemas import LLMConfig, ProviderInfo, StreamChunk


@runtime_checkable
class LLMService(Protocol):
    """High-level facade for LLM generation.

    Encapsulates backend resolution, prompt assembly, RAG context
    injection, and token accounting — currently spread across
    ``orchestrator.py`` and ``cloud_llm_service.py``.
    """

    async def generate(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig | None = None,
    ) -> str:
        """Single-shot generation.  Returns the full assistant reply."""
        ...

    async def stream(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming generation.  Yields content/tool-call chunks."""
        ...

    async def resolve_backend(self, backend_id: str) -> ProviderInfo | None:
        """Look up a cloud provider by its ID (e.g. ``"gemini-default"``)."""
        ...

    async def list_providers(
        self,
        *,
        enabled_only: bool = False,
        workspace_id: int | None = None,
    ) -> list[ProviderInfo]:
        """List registered cloud LLM providers."""
        ...

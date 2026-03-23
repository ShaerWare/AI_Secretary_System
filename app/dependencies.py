# app/dependencies.py
"""
Dependency injection container for services.

This module provides FastAPI dependencies that give routers access to
shared services (TTS, LLM, STT, etc.) without global state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from modules.core.events import EventBus


if TYPE_CHECKING:
    from typing import Any

    from piper_tts_service import PiperTTSService
    from stt_service import STTService
    from voice_clone_service import VoiceCloneService


class ServiceContainer:
    """
    Container holding references to all initialized services.

    This replaces the global variables from orchestrator.py with a
    centralized service registry that can be injected into routers.
    """

    def __init__(self):
        # Event bus (singleton, available to all services)
        self.event_bus: EventBus = EventBus()

        # TTS services
        self.voice_service: VoiceCloneService | None = None  # XTTS Марина
        self.anna_voice_service: VoiceCloneService | None = None  # XTTS Анна
        self.piper_service: PiperTTSService | None = None  # Piper CPU
        self.openvoice_service = None  # OpenVoice v2

        # LLM service (VLLMLLMService or CloudLLMService)
        self.llm_service: Any = None

        # STT service
        self.stt_service: STTService | None = None

        # GSM telephony service
        self.gsm_service = None

        # Streaming TTS manager
        self.streaming_tts_manager = None

        # Wiki RAG service
        self.wiki_rag_service = None

        # Vector Search client (HTTP → microservice)
        self.vector_search_client = None

        # Current voice configuration
        self.current_voice_config = {
            "engine": "xtts",
            "voice": "anna",
        }

    def get_current_voice_service(self) -> VoiceCloneService | None:
        """Get the currently active voice service based on config."""
        engine = self.current_voice_config.get("engine", "xtts")
        voice = self.current_voice_config.get("voice", "anna")

        if engine == "xtts":
            if voice == "anna" and self.anna_voice_service:
                return self.anna_voice_service
            elif voice == "marina" and self.voice_service:
                return self.voice_service
        elif engine == "piper":
            return self.piper_service
        elif engine == "openvoice":
            return self.openvoice_service

        # Fallback
        return self.anna_voice_service or self.voice_service or self.piper_service


# Global service container instance
_container: ServiceContainer | None = None


def get_container() -> ServiceContainer:
    """Get or create the service container."""
    global _container
    if _container is None:
        _container = ServiceContainer()
    return _container


def reset_container() -> None:
    """Reset the container (for testing)."""
    global _container
    _container = None


# FastAPI dependencies for routers


def get_llm_service():
    """Dependency: Get LLM service."""
    return get_container().llm_service


def get_voice_service():
    """Dependency: Get current voice service (XTTS/Piper/OpenVoice)."""
    return get_container().get_current_voice_service()


def get_piper_service():
    """Dependency: Get Piper TTS service."""
    return get_container().piper_service


def get_stt_service():
    """Dependency: Get STT service."""
    return get_container().stt_service


def get_voice_config():
    """Dependency: Get current voice configuration."""
    return get_container().current_voice_config


def get_streaming_tts_manager():
    """Dependency: Get streaming TTS manager."""
    return get_container().streaming_tts_manager


def get_gsm_service():
    """Dependency: Get GSM telephony service."""
    return get_container().gsm_service


def get_vector_search_client():
    """Dependency: Get Vector Search microservice client."""
    return get_container().vector_search_client

# app/dependencies.py
"""
Dependency injection container for services.

This module provides FastAPI dependencies that give routers access to
shared services (TTS, LLM, STT, etc.) without global state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from llm_service import LLMService
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
        # TTS services
        self.voice_service: VoiceCloneService | None = None  # XTTS Лидия
        self.gulya_voice_service: VoiceCloneService | None = None  # XTTS Гуля
        self.piper_service: PiperTTSService | None = None  # Piper CPU
        self.openvoice_service = None  # OpenVoice v2

        # LLM service
        self.llm_service: LLMService | None = None

        # STT service
        self.stt_service: STTService | None = None

        # Streaming TTS manager
        self.streaming_tts_manager = None

        # Current voice configuration
        self.current_voice_config = {
            "engine": "xtts",
            "voice": "gulya",
        }

    def get_current_voice_service(self) -> VoiceCloneService | None:
        """Get the currently active voice service based on config."""
        engine = self.current_voice_config.get("engine", "xtts")
        voice = self.current_voice_config.get("voice", "gulya")

        if engine == "xtts":
            if voice == "gulya" and self.gulya_voice_service:
                return self.gulya_voice_service
            elif voice == "lidia" and self.voice_service:
                return self.voice_service
        elif engine == "piper":
            return self.piper_service
        elif engine == "openvoice":
            return self.openvoice_service

        # Fallback
        return self.gulya_voice_service or self.voice_service or self.piper_service


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

"""Speech domain startup: TTS/STT service init + voice preset reload."""

import logging
from typing import Any


logger = logging.getLogger(__name__)

# Optional TTS imports (GPU services may not be installed)
try:
    from piper_tts_service import PiperTTSService

    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False
    PiperTTSService = None

try:
    from voice_clone_service import VoiceCloneService

    XTTS_AVAILABLE = True
except ImportError:
    XTTS_AVAILABLE = False
    VoiceCloneService = None

try:
    from openvoice_service import OpenVoiceService

    OPENVOICE_AVAILABLE = True
except ImportError:
    OPENVOICE_AVAILABLE = False
    OpenVoiceService = None


def init_tts_services(deployment_mode: str) -> dict[str, Any]:
    """Initialize TTS services based on deployment mode.

    Returns dict with keys: voice_service, anna_voice_service, piper_service,
    openvoice_service, current_voice_config.
    """
    result: dict[str, Any] = {
        "voice_service": None,
        "anna_voice_service": None,
        "piper_service": None,
        "openvoice_service": None,
        "current_voice_config": {"engine": "xtts", "voice": "anna"},
    }

    if deployment_mode == "cloud":
        logger.info("☁️ Cloud mode: пропускаем TTS/GPU сервисы")
        result["current_voice_config"] = {"engine": "none", "voice": "none"}
        return result

    # Piper TTS (Dmitri, Irina) - CPU, загружаем первым
    if PIPER_AVAILABLE:
        logger.info("📦 Загрузка Piper TTS Service (CPU)...")
        try:
            result["piper_service"] = PiperTTSService()
        except Exception as e:
            logger.warning(f"⚠️ Piper TTS недоступен: {e}")
    else:
        logger.info("⏭️ Piper TTS не установлен (пропускаем)")

    # OpenVoice v2 (Марина) - GPU CC 6.1+ (P104-100)
    if OPENVOICE_AVAILABLE:
        logger.info("📦 Загрузка OpenVoice TTS Service (GPU CC 6.1+)...")
        try:
            result["openvoice_service"] = OpenVoiceService()
            logger.info("✅ OpenVoice v2 загружен (P104-100)")
        except Exception as e:
            logger.warning(f"⚠️ OpenVoice недоступен: {e}")
    else:
        logger.info("⏭️ OpenVoice не установлен (пропускаем)")

    # XTTS (Анна) - GPU CC >= 7.0, по умолчанию
    if XTTS_AVAILABLE:
        logger.info("📦 Загрузка Voice Clone Service (XTTS - Анна)...")
        try:
            svc = VoiceCloneService(voice_samples_dir="./Анна")
            result["anna_voice_service"] = svc
            logger.info(f"✅ XTTS (Анна): {len(svc.voice_samples)} образцов")
        except Exception as e:
            logger.warning(f"⚠️ XTTS (Анна) недоступен: {e}")
    else:
        logger.info("⏭️ XTTS не установлен (пропускаем)")

    # XTTS (Марина) - GPU CC >= 7.0, опционально
    if XTTS_AVAILABLE:
        logger.info("📦 Загрузка Voice Clone Service (XTTS - Марина)...")
        try:
            svc = VoiceCloneService(voice_samples_dir="./Марина")
            result["voice_service"] = svc
            logger.info(f"✅ XTTS (Марина): {len(svc.voice_samples)} образцов")
        except Exception as e:
            logger.warning(f"⚠️ XTTS (Марина) недоступен: {e}")

    # Устанавливаем голос по умолчанию
    if result["anna_voice_service"]:
        result["current_voice_config"] = {"engine": "xtts", "voice": "anna"}
        logger.info("🎤 Голос по умолчанию: Анна (XTTS)")
    elif result["voice_service"]:
        result["current_voice_config"] = {"engine": "xtts", "voice": "marina"}
        logger.info("🎤 Голос по умолчанию: Марина (XTTS)")
    elif result["piper_service"]:
        result["current_voice_config"] = {"engine": "piper", "voice": "dmitri"}
        logger.info("🎤 Голос по умолчанию: Дмитрий (Piper)")

    return result


def init_stt_service():
    """Initialize STT (Vosk) service. Returns service instance or None."""
    try:
        from stt_service import VoskSTTService

        svc = VoskSTTService(language="ru", model_size="small")
        logger.info("✅ STT (Vosk) initialized")
        return svc
    except Exception as e:
        logger.warning(f"⚠️ STT not available: {e}")
        return None


def init_streaming_tts_manager():
    """Create StreamingTTSManager instance."""
    from modules.speech.streaming import StreamingTTSManager

    logger.info("📦 Инициализация Streaming TTS Manager...")
    return StreamingTTSManager(max_cache_size=50, cache_ttl=300)


async def reload_voice_presets(container) -> None:
    """Load TTS presets from DB and update voice services."""
    from db.integration import async_preset_manager

    presets_dict = await async_preset_manager.get_custom()
    for svc in [container.voice_service, container.anna_voice_service]:
        if svc and hasattr(svc, "reload_presets"):
            svc.reload_presets(presets_dict)

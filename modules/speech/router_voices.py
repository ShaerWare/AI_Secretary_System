"""Voice selection and testing endpoints.

Manages active voice configuration (XTTS/OpenVoice/Piper).
GPU-only — not registered in cloud deployment mode.
"""

import logging
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.dependencies import get_container


logger = logging.getLogger(__name__)

router = APIRouter(tags=["voices"])

TEMP_DIR = Path("./temp")
TEMP_DIR.mkdir(exist_ok=True)


class VoiceRequest(BaseModel):
    voice: str  # anna / marina / marina_openvoice / dmitri / irina


@router.get("/admin/voices")
async def admin_get_voices():
    """Получить список всех доступных голосов"""
    container = get_container()
    voices = []

    # XTTS голос (Анна) - требует GPU CC >= 7.0 (по умолчанию)
    if container.anna_voice_service:
        voices.append(
            {
                "id": "anna",
                "name": "Анна (XTTS)",
                "engine": "xtts",
                "description": "Клонированный голос Гули (XTTS v2, GPU CC >= 7.0)",
                "available": True,
                "samples_count": len(container.anna_voice_service.voice_samples),
                "default": True,
            }
        )

    # XTTS голос (Марина) - требует GPU CC >= 7.0
    if container.voice_service:
        voices.append(
            {
                "id": "marina",
                "name": "Марина (XTTS)",
                "engine": "xtts",
                "description": "Клонированный голос Лидии (XTTS v2, GPU CC >= 7.0)",
                "available": True,
                "samples_count": len(container.voice_service.voice_samples),
            }
        )

    # OpenVoice голос (Марина) - работает на GPU CC 6.1+
    if container.openvoice_service:
        voices.append(
            {
                "id": "marina_openvoice",
                "name": "Марина (OpenVoice)",
                "engine": "openvoice",
                "description": "Клонированный голос (OpenVoice v2, GPU CC 6.1+)",
                "available": True,
                "samples_count": len(container.openvoice_service.voice_samples)
                if container.openvoice_service.voice_samples
                else 0,
            }
        )

    # Piper голоса (CPU)
    if container.piper_service:
        piper_voices = container.piper_service.get_available_voices()
        for voice_id, info in piper_voices.items():
            voices.append(
                {
                    "id": voice_id,
                    "name": info["name"],
                    "engine": "piper",
                    "description": info["description"],
                    "available": info["available"],
                }
            )

    return {
        "voices": voices,
        "current": container.current_voice_config,
    }


@router.get("/admin/voice")
async def admin_get_current_voice():
    """Получить текущий выбранный голос"""
    container = get_container()
    return container.current_voice_config


@router.post("/admin/voice")
async def admin_set_voice(request: VoiceRequest):
    """Установить активный голос"""
    container = get_container()
    voice_id = request.voice.lower()

    if voice_id == "anna":
        if not container.anna_voice_service:
            raise HTTPException(
                status_code=503, detail="XTTS service (Анна) not available (requires GPU CC >= 7.0)"
            )
        new_config = {"engine": "xtts", "voice": "anna"}
        logger.info("🎤 Голос изменён на: Анна (XTTS)")

    elif voice_id == "marina":
        if not container.voice_service:
            raise HTTPException(
                status_code=503,
                detail="XTTS service (Марина) not available (requires GPU CC >= 7.0)",
            )
        new_config = {"engine": "xtts", "voice": "marina"}
        logger.info("🎤 Голос изменён на: Марина (XTTS)")

    elif voice_id == "marina_openvoice":
        if not container.openvoice_service:
            raise HTTPException(status_code=503, detail="OpenVoice service not available")
        new_config = {"engine": "openvoice", "voice": "marina_openvoice"}
        logger.info("🎤 Голос изменён на: Марина (OpenVoice)")

    elif voice_id in ["dmitri", "irina"]:
        if not container.piper_service:
            raise HTTPException(status_code=503, detail="Piper TTS service not available")
        piper_voices = container.piper_service.get_available_voices()
        if voice_id not in piper_voices or not piper_voices[voice_id]["available"]:
            raise HTTPException(status_code=400, detail=f"Voice model not found: {voice_id}")
        new_config = {"engine": "piper", "voice": voice_id}
        logger.info(f"🎤 Голос изменён на: {piper_voices[voice_id]['name']} (Piper)")

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown voice: {voice_id}. Available: anna, marina, marina_openvoice, dmitri, irina",
        )

    container.current_voice_config = new_config
    return {"status": "ok", **new_config}


@router.post("/admin/voice/test")
async def admin_test_voice(request: VoiceRequest):
    """Тестовый синтез выбранным голосом"""
    container = get_container()
    voice_id = request.voice.lower()
    test_text = "Здравствуйте! Это тестовое сообщение для проверки голоса."

    output_path = TEMP_DIR / f"voice_test_{voice_id}_{int(time.time())}.wav"

    try:
        if voice_id == "anna":
            if not container.anna_voice_service:
                raise HTTPException(
                    status_code=503, detail="XTTS (Анна) not available (requires GPU CC >= 7.0)"
                )
            container.anna_voice_service.synthesize_to_file(
                test_text, str(output_path), preset="natural"
            )

        elif voice_id == "marina":
            if not container.voice_service:
                raise HTTPException(
                    status_code=503, detail="XTTS (Марина) not available (requires GPU CC >= 7.0)"
                )
            container.voice_service.synthesize_to_file(
                test_text, str(output_path), preset="natural"
            )

        elif voice_id == "marina_openvoice":
            if not container.openvoice_service:
                raise HTTPException(status_code=503, detail="OpenVoice not available")
            container.openvoice_service.synthesize_to_file(
                test_text, str(output_path), language="ru"
            )

        elif voice_id in ["dmitri", "irina"]:
            if not container.piper_service:
                raise HTTPException(status_code=503, detail="Piper not available")
            container.piper_service.synthesize_to_file(test_text, str(output_path), voice=voice_id)

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown voice: {voice_id}. Available: anna, marina, marina_openvoice, dmitri, irina",
            )

        return FileResponse(output_path, media_type="audio/wav", filename=f"test_{voice_id}.wav")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка тестового синтеза: {e}")
        raise HTTPException(status_code=500, detail=str(e))

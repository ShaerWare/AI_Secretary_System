# app/routers/tts.py
"""TTS configuration router - presets, params, test synthesis, cache."""

import logging
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.dependencies import get_container
from db.integration import async_preset_manager
from voice_clone_service import INTONATION_PRESETS


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/tts", tags=["tts"])

# Temp directory for test audio files
TEMP_DIR = Path("./temp")
TEMP_DIR.mkdir(exist_ok=True)


# ============== Pydantic Models ==============


class AdminTTSPresetRequest(BaseModel):
    """Запрос на изменение пресета TTS"""

    preset: str  # warm, calm, energetic, natural, neutral


class AdminTTSTestRequest(BaseModel):
    """Запрос на тестовый синтез"""

    text: str
    preset: str = "natural"


class AdminXTTSParamsRequest(BaseModel):
    temperature: Optional[float] = None
    repetition_penalty: Optional[float] = None
    top_k: Optional[int] = None
    top_p: Optional[float] = None
    speed: Optional[float] = None
    gpt_cond_len: Optional[int] = None
    gpt_cond_chunk_len: Optional[int] = None


class AdminPiperParamsRequest(BaseModel):
    speed: float = 1.0


class AdminCustomPresetRequest(BaseModel):
    name: str
    params: dict


# XTTS param overrides storage
_xtts_param_overrides: dict = {}


# ============== Helper Functions ==============


async def _reload_voice_presets():
    """Загружает пресеты из БД и обновляет voice сервисы."""
    container = get_container()
    presets_dict = await async_preset_manager.get_custom()
    # Reload for all XTTS voice services
    for svc in [container.voice_service, container.gulya_voice_service]:
        if svc and hasattr(svc, "reload_presets"):
            svc.reload_presets(presets_dict)


# ============== Presets Endpoints ==============


@router.get("/presets")
async def admin_tts_presets():
    """Список доступных TTS пресетов"""
    container = get_container()
    presets = {}
    for name, preset in INTONATION_PRESETS.items():
        presets[name] = {
            "display_name": preset.name,
            "temperature": preset.temperature,
            "repetition_penalty": preset.repetition_penalty,
            "top_k": preset.top_k,
            "top_p": preset.top_p,
            "speed": preset.speed,
        }

    xtts_svc = container.gulya_voice_service or container.voice_service
    current = xtts_svc.default_preset if xtts_svc else "natural"

    return {
        "presets": presets,
        "current": current,
    }


@router.post("/preset")
async def admin_set_tts_preset(request: AdminTTSPresetRequest):
    """Установить текущий пресет TTS"""
    container = get_container()
    if request.preset not in INTONATION_PRESETS:
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестный пресет: {request.preset}. Доступные: {list(INTONATION_PRESETS.keys())}",
        )

    xtts_svc = container.gulya_voice_service or container.voice_service
    if xtts_svc:
        xtts_svc.default_preset = request.preset
        preset = INTONATION_PRESETS[request.preset]
        return {
            "status": "ok",
            "preset": request.preset,
            "display_name": preset.name,
            "settings": {
                "temperature": preset.temperature,
                "speed": preset.speed,
            },
        }

    raise HTTPException(status_code=503, detail="No XTTS voice service available")


# ============== Test Endpoint ==============


@router.post("/test")
async def admin_tts_test(request: AdminTTSTestRequest):
    """Тестовый синтез речи - возвращает аудио-файл для воспроизведения в браузере"""
    import time as t

    container = get_container()
    # Используем текущий голос
    engine = container.current_voice_config.get("engine", "xtts")
    voice = container.current_voice_config.get("voice", "gulya")

    try:
        start = t.time()
        output_file = TEMP_DIR / f"admin_test_{datetime.now().timestamp()}.wav"

        # Выбираем TTS сервис в зависимости от текущего движка
        if engine == "piper" and container.piper_service:
            # Piper TTS (CPU)
            container.piper_service.synthesize_to_file(
                text=request.text,
                output_path=str(output_file),
                voice=voice,
            )
            logger.info(f"🔊 Piper TTS test: voice={voice}")
        elif engine == "openvoice" and container.openvoice_service:
            # OpenVoice v2
            container.openvoice_service.synthesize_to_file(
                text=request.text, output_path=str(output_file), language="ru"
            )
            logger.info("🔊 OpenVoice TTS test")
        elif engine == "xtts":
            # XTTS v2
            tts_service = None
            if voice == "gulya" and container.gulya_voice_service:
                tts_service = container.gulya_voice_service
            elif voice == "lidia" and container.voice_service:
                tts_service = container.voice_service
            elif container.gulya_voice_service:
                tts_service = container.gulya_voice_service
            elif container.voice_service:
                tts_service = container.voice_service

            if not tts_service:
                raise HTTPException(status_code=503, detail="No XTTS voice service available")

            tts_service.synthesize_to_file(
                text=request.text,
                output_path=str(output_file),
                preset=request.preset,
                language="ru",
            )
            logger.info(f"🔊 XTTS TTS test: voice={voice}, preset={request.preset}")
        # Fallback - попробуем любой доступный сервис
        elif container.piper_service:
            container.piper_service.synthesize_to_file(
                text=request.text, output_path=str(output_file), voice="dmitri"
            )
        elif container.gulya_voice_service:
            container.gulya_voice_service.synthesize_to_file(
                text=request.text,
                output_path=str(output_file),
                preset=request.preset,
                language="ru",
            )
        else:
            raise HTTPException(status_code=503, detail="No TTS service available")

        elapsed = t.time() - start

        # Получаем длительность аудио
        with wave.open(str(output_file), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            duration = frames / float(rate)

        logger.info(
            f"🔊 TTS test: {duration:.2f}s audio in {elapsed:.2f}s (RTF: {elapsed / duration:.2f})"
        )

        return FileResponse(
            path=str(output_file),
            media_type="audio/wav",
            filename="test_synthesis.wav",
            headers={
                "X-Duration-Sec": str(round(duration, 2)),
                "X-Synthesis-Time-Sec": str(round(elapsed, 2)),
                "X-RTF": str(round(elapsed / duration, 2) if duration > 0 else 0),
            },
        )

    except Exception as e:
        logger.error(f"❌ Admin TTS test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Cache Endpoints ==============


@router.get("/cache")
async def admin_tts_cache():
    """Статистика кэша streaming TTS"""
    container = get_container()
    if container.streaming_tts_manager:
        return container.streaming_tts_manager.get_stats()
    return {"cache_size": 0, "active_sessions": 0}


@router.delete("/cache")
async def admin_clear_tts_cache():
    """Очистить кэш streaming TTS"""
    container = get_container()
    if container.streaming_tts_manager:
        with container.streaming_tts_manager._cache_lock:
            count = len(container.streaming_tts_manager._cache)
            container.streaming_tts_manager._cache.clear()
        return {"status": "ok", "cleared_items": count}
    return {"status": "ok", "cleared_items": 0}


# ============== XTTS Params Endpoints ==============


@router.get("/xtts/params")
async def admin_get_xtts_params():
    """Получить параметры XTTS"""
    container = get_container()
    service = container.gulya_voice_service or container.voice_service
    if not service:
        raise HTTPException(status_code=503, detail="XTTS service not available")

    preset = service.get_preset(service.default_preset)
    return {
        "default_preset": service.default_preset,
        "current_params": {
            "temperature": preset.temperature,
            "repetition_penalty": preset.repetition_penalty,
            "top_k": preset.top_k,
            "top_p": preset.top_p,
            "speed": preset.speed,
            "gpt_cond_len": preset.gpt_cond_len,
            "gpt_cond_chunk_len": preset.gpt_cond_chunk_len,
        },
    }


@router.post("/xtts/params")
async def admin_set_xtts_params(request: AdminXTTSParamsRequest):
    """Установить параметры XTTS (для следующего синтеза)"""
    params = {k: v for k, v in request.model_dump().items() if v is not None}
    _xtts_param_overrides.update(params)
    return {"status": "ok", "params": _xtts_param_overrides}


# ============== Piper Params Endpoints ==============


@router.get("/piper/params")
async def admin_get_piper_params():
    """Получить параметры Piper TTS"""
    container = get_container()
    if not container.piper_service:
        raise HTTPException(status_code=503, detail="Piper service not available")

    return {
        "speed": getattr(container.piper_service, "speed", 1.0),
        "voices": container.piper_service.get_available_voices(),
    }


@router.post("/piper/params")
async def admin_set_piper_params(request: AdminPiperParamsRequest):
    """Установить параметры Piper TTS"""
    container = get_container()
    if not container.piper_service:
        raise HTTPException(status_code=503, detail="Piper service not available")

    container.piper_service.speed = request.speed
    return {"status": "ok", "speed": request.speed}


# ============== Custom Presets Endpoints ==============


@router.get("/presets/custom")
async def admin_get_custom_presets():
    """Получить пользовательские пресеты TTS"""
    presets = await async_preset_manager.get_custom()
    return {"presets": presets}


@router.post("/presets/custom")
async def admin_create_custom_preset(request: AdminCustomPresetRequest):
    """Создать пользовательский пресет TTS"""
    await async_preset_manager.create(request.name, request.params)
    await _reload_voice_presets()
    return {"status": "ok", "preset": request.name}


@router.put("/presets/custom/{name}")
async def admin_update_custom_preset(name: str, request: AdminCustomPresetRequest):
    """Обновить пользовательский пресет TTS"""
    result = await async_preset_manager.update(name, request.params)
    if not result:
        raise HTTPException(status_code=404, detail=f"Preset not found: {name}")

    await _reload_voice_presets()
    return {"status": "ok", "preset": name}


@router.delete("/presets/custom/{name}")
async def admin_delete_custom_preset(name: str):
    """Удалить пользовательский пресет TTS"""
    if not await async_preset_manager.delete(name):
        raise HTTPException(status_code=404, detail=f"Preset not found: {name}")

    await _reload_voice_presets()
    return {"status": "ok", "deleted": name}

"""TTS configuration router - presets, params, test synthesis, cache, streaming."""

import asyncio
import logging
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.dependencies import get_container
from app.rate_limiter import RATE_LIMIT_TTS, limiter
from auth_manager import User, require_permission, workspace_context
from modules.speech.service import preset_service
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


class StreamingTTSRequest(BaseModel):
    """Запрос на потоковый синтез речи для телефонии"""

    text: str
    language: str = "ru"
    preset: str = "natural"
    voice: str = "anna"  # anna, marina
    target_sample_rate: Optional[int] = 8000  # 8000 для GSM, None для 24kHz
    stream_chunk_size: int = 20  # Размер чанка XTTS (меньше = быстрее первый чанк)
    output_format: str = "pcm16"  # pcm16, float32


# XTTS param overrides storage
_xtts_param_overrides: dict = {}


# ============== Helper Functions ==============


async def _reload_voice_presets():
    """Загружает пресеты из БД и обновляет voice сервисы."""
    container = get_container()
    presets_dict = await preset_service.get_custom()
    # Reload for all XTTS voice services
    for svc in [container.voice_service, container.anna_voice_service]:
        if svc and hasattr(svc, "reload_presets"):
            svc.reload_presets(presets_dict)


# ============== Presets Endpoints ==============


@router.get("/presets")
async def admin_tts_presets(user: User = Depends(require_permission("speech", "view"))):
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

    xtts_svc = container.anna_voice_service or container.voice_service
    current = xtts_svc.default_preset if xtts_svc else "natural"

    return {
        "presets": presets,
        "current": current,
    }


@router.post("/preset")
async def admin_set_tts_preset(
    request: AdminTTSPresetRequest, user: User = Depends(require_permission("speech", "edit"))
):
    """Установить текущий пресет TTS"""
    container = get_container()
    if request.preset not in INTONATION_PRESETS:
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестный пресет: {request.preset}. Доступные: {list(INTONATION_PRESETS.keys())}",
        )

    xtts_svc = container.anna_voice_service or container.voice_service
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
@limiter.limit(RATE_LIMIT_TTS)
async def admin_tts_test(
    request: Request,
    tts_request: AdminTTSTestRequest,
    user: User = Depends(require_permission("speech", "view")),
):
    """Тестовый синтез речи - возвращает аудио-файл для воспроизведения в браузере"""
    import time as t

    container = get_container()
    # Используем текущий голос
    engine = container.current_voice_config.get("engine", "xtts")
    voice = container.current_voice_config.get("voice", "anna")

    try:
        start = t.time()
        output_file = TEMP_DIR / f"admin_test_{datetime.now().timestamp()}.wav"

        # Выбираем TTS сервис в зависимости от текущего движка
        if engine == "piper" and container.piper_service:
            # Piper TTS (CPU)
            container.piper_service.synthesize_to_file(
                text=tts_request.text,
                output_path=str(output_file),
                voice=voice,
            )
            logger.info(f"🔊 Piper TTS test: voice={voice}")
        elif engine == "openvoice" and container.openvoice_service:
            # OpenVoice v2
            container.openvoice_service.synthesize_to_file(
                text=tts_request.text, output_path=str(output_file), language="ru"
            )
            logger.info("🔊 OpenVoice TTS test")
        elif engine == "xtts":
            # XTTS v2
            tts_service = None
            if voice == "anna" and container.anna_voice_service:
                tts_service = container.anna_voice_service
            elif voice == "marina" and container.voice_service:
                tts_service = container.voice_service
            elif container.anna_voice_service:
                tts_service = container.anna_voice_service
            elif container.voice_service:
                tts_service = container.voice_service

            if not tts_service:
                raise HTTPException(status_code=503, detail="No XTTS voice service available")

            tts_service.synthesize_to_file(
                text=tts_request.text,
                output_path=str(output_file),
                preset=tts_request.preset,
                language="ru",
            )
            logger.info(f"🔊 XTTS TTS test: voice={voice}, preset={tts_request.preset}")
        # Fallback - попробуем любой доступный сервис
        elif container.piper_service:
            container.piper_service.synthesize_to_file(
                text=tts_request.text, output_path=str(output_file), voice="dmitri"
            )
        elif container.anna_voice_service:
            container.anna_voice_service.synthesize_to_file(
                text=tts_request.text,
                output_path=str(output_file),
                preset=tts_request.preset,
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
async def admin_tts_cache(user: User = Depends(require_permission("speech", "view"))):
    """Статистика кэша streaming TTS"""
    container = get_container()
    if container.streaming_tts_manager:
        return container.streaming_tts_manager.get_stats()
    return {"cache_size": 0, "active_sessions": 0}


@router.delete("/cache")
async def admin_clear_tts_cache(user: User = Depends(require_permission("speech", "edit"))):
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
async def admin_get_xtts_params(user: User = Depends(require_permission("speech", "view"))):
    """Получить параметры XTTS"""
    container = get_container()
    service = container.anna_voice_service or container.voice_service
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
async def admin_set_xtts_params(
    request: AdminXTTSParamsRequest, user: User = Depends(require_permission("speech", "edit"))
):
    """Установить параметры XTTS (для следующего синтеза)"""
    params = {k: v for k, v in request.model_dump().items() if v is not None}
    _xtts_param_overrides.update(params)
    return {"status": "ok", "params": _xtts_param_overrides}


# ============== Piper Params Endpoints ==============


@router.get("/piper/params")
async def admin_get_piper_params(user: User = Depends(require_permission("speech", "view"))):
    """Получить параметры Piper TTS"""
    container = get_container()
    if not container.piper_service:
        raise HTTPException(status_code=503, detail="Piper service not available")

    return {
        "speed": getattr(container.piper_service, "speed", 1.0),
        "voices": container.piper_service.get_available_voices(),
    }


@router.post("/piper/params")
async def admin_set_piper_params(
    request: AdminPiperParamsRequest, user: User = Depends(require_permission("speech", "edit"))
):
    """Установить параметры Piper TTS"""
    container = get_container()
    if not container.piper_service:
        raise HTTPException(status_code=503, detail="Piper service not available")

    container.piper_service.speed = request.speed
    return {"status": "ok", "speed": request.speed}


# ============== Custom Presets Endpoints ==============


@router.get("/presets/custom")
async def admin_get_custom_presets(user: User = Depends(require_permission("speech", "view"))):
    """Получить пользовательские пресеты TTS"""
    owner_id, ws_id = workspace_context(user, "speech")
    presets = await preset_service.get_custom(owner_id=owner_id, workspace_id=ws_id)
    return {"presets": presets}


@router.post("/presets/custom")
async def admin_create_custom_preset(
    request: AdminCustomPresetRequest, user: User = Depends(require_permission("speech", "edit"))
):
    """Создать пользовательский пресет TTS"""
    owner_id, ws_id = workspace_context(user, "speech")
    await preset_service.create(request.name, request.params, owner_id=owner_id, workspace_id=ws_id)
    await _reload_voice_presets()
    return {"status": "ok", "preset": request.name}


@router.put("/presets/custom/{name}")
async def admin_update_custom_preset(
    name: str,
    request: AdminCustomPresetRequest,
    user: User = Depends(require_permission("speech", "edit")),
):
    """Обновить пользовательский пресет TTS"""
    _owner_id, ws_id = workspace_context(user, "speech")
    result = await preset_service.update(name, request.params, workspace_id=ws_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Preset not found: {name}")

    await _reload_voice_presets()
    return {"status": "ok", "preset": name}


@router.delete("/presets/custom/{name}")
async def admin_delete_custom_preset(
    name: str, user: User = Depends(require_permission("speech", "edit"))
):
    """Удалить пользовательский пресет TTS"""
    _owner_id, ws_id = workspace_context(user, "speech")
    if not await preset_service.delete(name, workspace_id=ws_id):
        raise HTTPException(status_code=404, detail=f"Preset not found: {name}")

    await _reload_voice_presets()
    return {"status": "ok", "deleted": name}


# ============== Streaming TTS Endpoints ==============


@router.post("/stream")
@limiter.limit(RATE_LIMIT_TTS)
async def tts_stream(
    request: Request,
    stream_request: StreamingTTSRequest,
    user: User = Depends(require_permission("speech", "view")),
):
    """
    Потоковый синтез речи - выдаёт аудио чанки по мере генерации.

    Оптимизирован для телефонии через SIM7600G-H GSM модем.
    Target: <500ms до первого аудио чанка.

    Returns:
        StreamingResponse с audio/octet-stream
        Headers:
        - X-Sample-Rate: частота дискретизации
        - X-First-Chunk-Ms: время до первого чанка в мс
    """
    container = get_container()

    # Выбираем XTTS сервис по голосу
    tts_service = None
    if stream_request.voice == "anna" and container.anna_voice_service:
        tts_service = container.anna_voice_service
    elif stream_request.voice == "marina" and container.voice_service:
        tts_service = container.voice_service
    elif container.anna_voice_service:
        tts_service = container.anna_voice_service
    elif container.voice_service:
        tts_service = container.voice_service

    if not tts_service:
        raise HTTPException(status_code=503, detail="No XTTS voice service available")

    # Проверяем наличие streaming метода
    if not hasattr(tts_service, "synthesize_streaming"):
        raise HTTPException(
            status_code=501,
            detail="Streaming synthesis not available. Use /test endpoint for batch synthesis.",
        )

    # Метрики
    first_chunk_time = None
    start_time = time.time()

    def on_first_chunk():
        nonlocal first_chunk_time
        first_chunk_time = (time.time() - start_time) * 1000  # мс

    async def generate_audio_chunks():
        """Генератор аудио чанков для StreamingResponse"""
        nonlocal first_chunk_time

        try:
            # Запускаем потоковый синтез в thread pool (XTTS синхронный)
            loop = asyncio.get_event_loop()

            # Создаём итератор в отдельном потоке
            def run_streaming():
                return list(
                    tts_service.synthesize_streaming(
                        text=stream_request.text,
                        language=stream_request.language,
                        preset=stream_request.preset,
                        stream_chunk_size=stream_request.stream_chunk_size,
                        target_sample_rate=stream_request.target_sample_rate,
                        on_first_chunk=on_first_chunk,
                    )
                )

            # Выполняем синтез
            chunks = await loop.run_in_executor(None, run_streaming)

            # Отдаём чанки
            for audio_chunk, sample_rate in chunks:
                # Конвертируем в нужный формат
                if stream_request.output_format == "pcm16":
                    # float32 -> int16
                    import numpy as np

                    audio_int16 = (audio_chunk * 32767).astype(np.int16)
                    yield audio_int16.tobytes()
                else:
                    # float32 as-is
                    yield audio_chunk.tobytes()

        except Exception as e:
            logger.error(f"❌ Streaming TTS error: {e}")
            raise

    # Определяем sample rate для заголовка
    output_rate = stream_request.target_sample_rate or 24000

    headers = {
        "X-Sample-Rate": str(output_rate),
        "X-Channels": "1",
        "X-Format": stream_request.output_format,
    }

    # Создаём response
    response = StreamingResponse(
        generate_audio_chunks(),
        media_type="application/octet-stream",
        headers=headers,
    )

    return response


@router.websocket("/ws/stream")
async def websocket_tts_stream(websocket: WebSocket):
    """
    WebSocket endpoint для real-time TTS стриминга.

    Protocol:
    1. Client sends JSON: {"text": "...", "voice": "anna", "preset": "natural", ...}
    2. Server sends binary audio chunks as they're generated
    3. Server sends JSON: {"done": true, "first_chunk_ms": 123, "total_ms": 456}

    Оптимизирован для двунаправленной связи с GSM модемом.
    """
    await websocket.accept()
    container = get_container()

    try:
        while True:
            # Ждём запрос от клиента
            data = await websocket.receive_json()

            text = data.get("text", "")
            if not text:
                await websocket.send_json({"error": "text is required"})
                continue

            voice = data.get("voice", "anna")
            language = data.get("language", "ru")
            preset = data.get("preset", "natural")
            target_sample_rate = data.get("target_sample_rate", 8000)
            stream_chunk_size = data.get("stream_chunk_size", 20)
            output_format = data.get("output_format", "pcm16")

            # Выбираем TTS сервис
            tts_service = None
            if voice == "anna" and container.anna_voice_service:
                tts_service = container.anna_voice_service
            elif voice == "marina" and container.voice_service:
                tts_service = container.voice_service
            elif container.anna_voice_service:
                tts_service = container.anna_voice_service
            elif container.voice_service:
                tts_service = container.voice_service

            if not tts_service or not hasattr(tts_service, "synthesize_streaming"):
                await websocket.send_json({"error": "Streaming TTS not available"})
                continue

            # Отправляем статус начала
            await websocket.send_json(
                {"status": "starting", "sample_rate": target_sample_rate or 24000}
            )

            # Метрики
            start_time = time.time()
            first_chunk_time = None
            chunk_count = 0

            # Capture variables for closure (fix B023)
            _start_time = start_time
            _tts_service = tts_service
            _text = text
            _language = language
            _preset = preset
            _stream_chunk_size = stream_chunk_size
            _target_sample_rate = target_sample_rate

            def on_first_chunk(_start=_start_time):
                nonlocal first_chunk_time
                first_chunk_time = (time.time() - _start) * 1000

            # Запускаем синтез в executor
            loop = asyncio.get_event_loop()

            def run_streaming(
                svc=_tts_service,
                txt=_text,
                lang=_language,
                pres=_preset,
                chunk_sz=_stream_chunk_size,
                rate=_target_sample_rate,
                on_first=on_first_chunk,
            ):
                return list(
                    svc.synthesize_streaming(
                        text=txt,
                        language=lang,
                        preset=pres,
                        stream_chunk_size=chunk_sz,
                        target_sample_rate=rate,
                        on_first_chunk=on_first,
                    )
                )

            chunks = await loop.run_in_executor(None, run_streaming)

            # Отправляем чанки
            for audio_chunk, sample_rate in chunks:
                import numpy as np

                if output_format == "pcm16":
                    audio_int16 = (audio_chunk * 32767).astype(np.int16)
                    await websocket.send_bytes(audio_int16.tobytes())
                else:
                    await websocket.send_bytes(audio_chunk.tobytes())
                chunk_count += 1

            # Отправляем статус завершения
            total_time = (time.time() - start_time) * 1000
            await websocket.send_json(
                {
                    "done": True,
                    "first_chunk_ms": round(first_chunk_time, 1) if first_chunk_time else None,
                    "total_ms": round(total_time, 1),
                    "chunks": chunk_count,
                }
            )

            logger.info(
                f"🔊 WebSocket TTS: {chunk_count} chunks, "
                f"first={first_chunk_time:.0f}ms, total={total_time:.0f}ms"
            )

    except WebSocketDisconnect:
        logger.info("📱 WebSocket TTS client disconnected")
    except Exception as e:
        logger.error(f"❌ WebSocket TTS error: {e}")
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass

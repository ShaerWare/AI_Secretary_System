# app/routers/stt.py
"""Speech-to-Text router - transcription and STT status."""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.dependencies import get_container
from stt_service import UnifiedSTTService, VoskSTTService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/stt", tags=["stt"])

# Lazy-initialized STT services
_vosk_service: Optional[VoskSTTService] = None
_unified_stt: Optional[UnifiedSTTService] = None


def get_vosk_service() -> Optional[VoskSTTService]:
    """Получить Vosk STT сервис (ленивая инициализация)"""
    global _vosk_service
    if _vosk_service is None:
        try:
            _vosk_service = VoskSTTService(language="ru", model_size="small")
            logger.info("✅ Vosk STT инициализирован")
        except Exception as e:
            logger.warning(f"⚠️ Vosk STT недоступен: {e}")
    return _vosk_service


def get_unified_stt() -> Optional[UnifiedSTTService]:
    """Получить унифицированный STT сервис"""
    global _unified_stt
    if _unified_stt is None:
        try:
            _unified_stt = UnifiedSTTService(language="ru", prefer_vosk=True)
            logger.info("✅ Unified STT инициализирован")
        except Exception as e:
            logger.warning(f"⚠️ Unified STT недоступен: {e}")
    return _unified_stt


@router.get("/status")
async def admin_stt_status():
    """Статус STT сервисов"""
    vosk_available = False
    whisper_available = False
    vosk_model = None

    # Проверяем Vosk
    try:
        vosk = get_vosk_service()
        if vosk:
            vosk_available = True
            vosk_model = str(vosk.model_path.name) if vosk.model_path else None
    except Exception:
        pass

    # Проверяем Whisper
    try:
        whisper_available = True
    except Exception:
        pass

    return {
        "vosk": {
            "available": vosk_available,
            "model": vosk_model,
            "realtime": True,
            "offline": True,
        },
        "whisper": {"available": whisper_available, "realtime": False, "offline": True},
        "preferred_engine": "vosk"
        if vosk_available
        else ("whisper" if whisper_available else None),
    }


@router.get("/models")
async def admin_stt_models():
    """Список доступных моделей STT"""
    models_dir = Path("models/vosk")
    models = []

    if models_dir.exists():
        for path in models_dir.iterdir():
            if path.is_dir() and "model" in path.name.lower():
                # Определяем размер модели
                size_bytes = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                models.append(
                    {
                        "name": path.name,
                        "path": str(path),
                        "size_mb": round(size_bytes / (1024 * 1024), 1),
                        "language": "ru"
                        if "ru" in path.name
                        else ("en" if "en" in path.name else "unknown"),
                    }
                )

    return {
        "models_dir": str(models_dir),
        "models": models,
        "download_url": "https://alphacephei.com/vosk/models",
    }


@router.post("/transcribe")
async def admin_stt_transcribe(
    file: UploadFile = File(...), language: str = "ru", engine: str = "auto"
):
    """
    Распознать речь из загруженного аудио файла

    Args:
        file: WAV/MP3 аудио файл
        language: Язык (ru, en)
        engine: Движок (auto, vosk, whisper)
    """
    import tempfile

    # Сохраняем файл
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Выбираем движок
        if engine == "vosk" or (engine == "auto" and get_vosk_service()):
            vosk = get_vosk_service()
            if not vosk:
                raise HTTPException(status_code=503, detail="Vosk STT недоступен")
            result = vosk.transcribe(tmp_path, language)
            result["engine"] = "vosk"

        elif engine == "whisper":
            unified = get_unified_stt()
            if not unified:
                raise HTTPException(status_code=503, detail="Whisper STT недоступен")
            result = unified.transcribe(tmp_path, language, use_whisper=True)
            result["engine"] = "whisper"

        else:
            unified = get_unified_stt()
            if not unified:
                raise HTTPException(status_code=503, detail="STT сервисы недоступны")
            result = unified.transcribe(tmp_path, language)
            result["engine"] = "auto"

        return result

    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/test")
async def admin_stt_test(text_to_speak: str = "Привет, это тест распознавания речи"):
    """
    Тест STT: синтезируем речь через TTS, затем распознаём обратно

    Полезно для проверки качества STT
    """
    import tempfile

    # Сначала синтезируем речь
    container = get_container()
    tts_service = container.gulya_voice_service or container.voice_service
    if not tts_service:
        raise HTTPException(status_code=503, detail="TTS сервис недоступен")

    vosk = get_vosk_service()
    if not vosk:
        raise HTTPException(status_code=503, detail="Vosk STT недоступен")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Синтезируем
        tts_service.synthesize(text_to_speak, tmp_path)

        # Распознаём
        result = vosk.transcribe(tmp_path)

        return {
            "original_text": text_to_speak,
            "recognized_text": result["text"],
            "match": text_to_speak.lower().strip() == result["text"].lower().strip(),
            "words_count": len(result.get("words", [])),
        }

    finally:
        Path(tmp_path).unlink(missing_ok=True)

"""TTS fine-tuning endpoints.

Voice sample management, transcription, dataset preparation, and training control.
GPU-only — not registered in cloud deployment mode.
"""

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile


logger = logging.getLogger(__name__)

try:
    from tts_finetune_manager import get_tts_finetune_manager

    TTS_FINETUNE_AVAILABLE = True
except ImportError:
    TTS_FINETUNE_AVAILABLE = False
    get_tts_finetune_manager = None

router = APIRouter(prefix="/admin/tts-finetune", tags=["finetune-tts"])


@router.get("/config")
async def admin_get_tts_finetune_config():
    """Получить конфигурацию TTS fine-tuning"""
    manager = get_tts_finetune_manager()
    return {"config": manager.get_config()}


@router.post("/config")
async def admin_set_tts_finetune_config(config: dict):
    """Обновить конфигурацию TTS fine-tuning"""
    manager = get_tts_finetune_manager()
    return {"status": "ok", "config": manager.set_config(config)}


@router.get("/samples")
async def admin_get_tts_samples():
    """Получить список образцов голоса"""
    manager = get_tts_finetune_manager()
    return {"samples": manager.get_samples()}


@router.post("/samples/upload")
async def admin_upload_tts_sample(file: UploadFile = File(...)):
    """Загрузить образец голоса"""
    manager = get_tts_finetune_manager()
    content = await file.read()
    sample = manager.add_sample(file.filename, content)
    return {
        "status": "ok",
        "sample": {
            "filename": sample.filename,
            "path": sample.path,
            "duration_sec": sample.duration_sec,
            "size_kb": sample.size_kb,
        },
    }


@router.delete("/samples/{filename}")
async def admin_delete_tts_sample(filename: str):
    """Удалить образец голоса"""
    manager = get_tts_finetune_manager()
    if manager.delete_sample(filename):
        return {"status": "ok", "message": f"Sample {filename} deleted"}
    raise HTTPException(status_code=404, detail="Sample not found")


@router.put("/samples/{filename}/transcript")
async def admin_update_tts_transcript(filename: str, request: dict):
    """Обновить транскрипцию образца"""
    manager = get_tts_finetune_manager()
    transcript = request.get("transcript", "")
    sample = manager.update_transcript(filename, transcript)
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    return {
        "status": "ok",
        "sample": {
            "filename": sample.filename,
            "transcript": sample.transcript,
            "transcript_edited": sample.transcript_edited,
        },
    }


@router.post("/transcribe")
async def admin_transcribe_tts_samples():
    """Запустить транскрибацию образцов через Whisper"""
    manager = get_tts_finetune_manager()
    if manager.transcribe_samples():
        return {"status": "ok", "message": "Transcription started"}
    return {"status": "error", "message": "Already running or no samples to transcribe"}


@router.post("/prepare")
async def admin_prepare_tts_dataset():
    """Подготовить датасет (извлечь audio_codes)"""
    manager = get_tts_finetune_manager()
    if manager.prepare_dataset():
        return {"status": "ok", "message": "Dataset preparation started"}
    return {"status": "error", "message": "Already running or no samples with transcripts"}


@router.get("/processing-status")
async def admin_get_tts_processing_status():
    """Получить статус обработки"""
    manager = get_tts_finetune_manager()
    return {"status": manager.get_processing_status()}


@router.post("/train/start")
async def admin_start_tts_training():
    """Запустить обучение TTS"""
    manager = get_tts_finetune_manager()
    if manager.start_training():
        return {"status": "ok", "message": "Training started"}
    return {"status": "error", "message": "Already running or dataset not prepared"}


@router.post("/train/stop")
async def admin_stop_tts_training():
    """Остановить обучение TTS"""
    manager = get_tts_finetune_manager()
    if manager.stop_training():
        return {"status": "ok", "message": "Training stopped"}
    return {"status": "error", "message": "Training not running"}


@router.get("/train/status")
async def admin_get_tts_training_status():
    """Получить статус обучения TTS"""
    manager = get_tts_finetune_manager()
    return {"status": manager.get_training_status()}


@router.get("/train/log")
async def admin_get_tts_training_log():
    """Получить лог обучения TTS"""
    manager = get_tts_finetune_manager()
    return {"log": manager.get_training_log()}


@router.get("/models")
async def admin_get_tts_trained_models():
    """Получить список обученных TTS моделей"""
    manager = get_tts_finetune_manager()
    return {"models": manager.get_trained_models()}

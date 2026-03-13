"""LLM fine-tuning endpoints.

Dataset management, training control, and LoRA adapter management.
GPU-only — not registered in cloud deployment mode.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth_manager import User, require_permission
from finetune_manager import get_finetune_manager


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/finetune", tags=["finetune-llm"])


# ============== Pydantic Models ==============


class DatasetProcessRequest(BaseModel):
    owner_name: Optional[str] = None
    transcribe_voice: Optional[bool] = None
    min_dialog_messages: Optional[int] = None
    max_message_length: Optional[int] = None
    max_dialog_length: Optional[int] = None
    include_groups: Optional[bool] = None
    output_name: Optional[str] = None


class GenerateProjectDatasetRequest(BaseModel):
    include_tz: bool = True
    include_faq: bool = True
    include_docs: bool = True
    include_escalation: bool = True
    include_code: bool = True  # Python код и Markdown документация
    github_repo_url: Optional[str] = None  # URL публичного GitHub/GitLab репозитория
    github_branch: str = "main"  # Ветка для клонирования
    output_name: str = "project_dataset"


class FinetuneConfigRequest(BaseModel):
    lora_rank: Optional[int] = None
    lora_alpha: Optional[int] = None
    batch_size: Optional[int] = None
    gradient_accumulation_steps: Optional[int] = None
    learning_rate: Optional[float] = None
    num_epochs: Optional[int] = None
    max_seq_length: Optional[int] = None
    output_dir: Optional[str] = None


class AdapterRequest(BaseModel):
    adapter: str


# ============== Dataset Endpoints ==============


@router.post("/dataset/upload")
async def admin_upload_dataset(file: UploadFile = File(...)):
    """Загрузить датасет (Telegram export JSON)"""
    manager = get_finetune_manager()
    content = await file.read()
    return await manager.upload_dataset(content, file.filename)


@router.post("/dataset/process")
async def admin_process_dataset(request: Optional[DatasetProcessRequest] = None):
    """Обработать загруженный датасет"""
    manager = get_finetune_manager()
    config = request.model_dump(exclude_none=True) if request else None
    return await manager.process_dataset(config)


@router.get("/dataset/config")
async def admin_get_dataset_config():
    """Получить конфигурацию обработки датасета"""
    manager = get_finetune_manager()
    return {"config": manager.get_dataset_config()}


@router.post("/dataset/config")
async def admin_set_dataset_config(request: DatasetProcessRequest):
    """Установить конфигурацию обработки датасета"""
    manager = get_finetune_manager()
    return manager.set_dataset_config(**request.model_dump(exclude_none=True))


@router.get("/dataset/processing-status")
async def admin_get_processing_status():
    """Получить статус обработки датасета"""
    manager = get_finetune_manager()
    return {"status": manager.get_processing_status()}


@router.get("/dataset/stats")
async def admin_get_dataset_stats():
    """Получить статистику датасета"""
    manager = get_finetune_manager()
    stats = manager.get_dataset_stats()
    return {
        "stats": {
            "total_sessions": stats.total_sessions,
            "total_messages": stats.total_messages,
            "total_tokens": stats.total_tokens,
            "avg_tokens_per_message": stats.avg_tokens_per_message,
            "file_path": stats.file_path,
            "file_size_mb": stats.file_size_mb,
            "modified": stats.modified,
        }
    }


@router.get("/dataset/list")
async def admin_list_datasets():
    """Список доступных датасетов"""
    manager = get_finetune_manager()
    return {"datasets": manager.list_datasets()}


@router.post("/dataset/augment")
async def admin_augment_dataset():
    """Аугментировать датасет"""
    manager = get_finetune_manager()
    return await manager.augment_dataset()


@router.post("/dataset/generate-project")
async def admin_generate_project_dataset(request: GenerateProjectDatasetRequest):
    """Генерировать датасет из проектных источников (ТЗ, FAQ, документация, эскалации, код, GitHub)"""
    manager = get_finetune_manager()
    return await manager.generate_project_dataset(
        include_tz=request.include_tz,
        include_faq=request.include_faq,
        include_docs=request.include_docs,
        include_escalation=request.include_escalation,
        include_code=request.include_code,
        github_repo_url=request.github_repo_url,
        github_branch=request.github_branch,
        output_name=request.output_name,
    )


# ============== Training Config Endpoints ==============


@router.get("/config")
async def admin_get_finetune_config():
    """Получить конфигурацию обучения"""
    manager = get_finetune_manager()
    config = manager.get_config()
    return {
        "config": {
            "base_model": config.base_model,
            "lora_rank": config.lora_rank,
            "lora_alpha": config.lora_alpha,
            "lora_dropout": config.lora_dropout,
            "batch_size": config.batch_size,
            "gradient_accumulation_steps": config.gradient_accumulation_steps,
            "learning_rate": config.learning_rate,
            "num_epochs": config.num_epochs,
            "warmup_ratio": config.warmup_ratio,
            "max_seq_length": config.max_seq_length,
            "output_dir": config.output_dir,
        },
        "presets": {
            name: {
                "lora_rank": p.lora_rank,
                "batch_size": p.batch_size,
                "num_epochs": p.num_epochs,
            }
            for name, p in manager.get_config_presets().items()
        },
    }


@router.post("/config")
async def admin_set_finetune_config(request: FinetuneConfigRequest):
    """Установить конфигурацию обучения"""
    manager = get_finetune_manager()
    config = manager.get_config()

    # Обновляем только переданные параметры
    if request.lora_rank is not None:
        config.lora_rank = request.lora_rank
    if request.lora_alpha is not None:
        config.lora_alpha = request.lora_alpha
    if request.batch_size is not None:
        config.batch_size = request.batch_size
    if request.gradient_accumulation_steps is not None:
        config.gradient_accumulation_steps = request.gradient_accumulation_steps
    if request.learning_rate is not None:
        config.learning_rate = request.learning_rate
    if request.num_epochs is not None:
        config.num_epochs = request.num_epochs
    if request.max_seq_length is not None:
        config.max_seq_length = request.max_seq_length
    if request.output_dir is not None:
        config.output_dir = request.output_dir

    return manager.set_config(config)


# ============== Training Control Endpoints ==============


@router.post("/train/start")
async def admin_start_training():
    """Запустить обучение"""
    manager = get_finetune_manager()
    return await manager.start_training()


@router.post("/train/stop")
async def admin_stop_training():
    """Остановить обучение"""
    manager = get_finetune_manager()
    return await manager.stop_training()


@router.get("/train/status")
async def admin_get_training_status():
    """Получить статус обучения"""
    manager = get_finetune_manager()
    status = manager.get_training_status()
    return {
        "status": {
            "is_running": status.is_running,
            "current_step": status.current_step,
            "total_steps": status.total_steps,
            "current_epoch": status.current_epoch,
            "total_epochs": status.total_epochs,
            "loss": status.loss,
            "learning_rate": status.learning_rate,
            "elapsed_seconds": status.elapsed_seconds,
            "eta_seconds": status.eta_seconds,
            "error": status.error,
        }
    }


@router.get("/train/log")
async def admin_stream_training_log(
    user: User = Depends(require_permission("system", "view")),
):
    """SSE streaming лога обучения"""
    manager = get_finetune_manager()

    async def generate():
        async for data in manager.stream_training_log():
            yield f"data: {data}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ============== Adapter Endpoints ==============


@router.get("/adapters")
async def admin_list_adapters():
    """Получить список LoRA адаптеров"""
    manager = get_finetune_manager()
    adapters = manager.list_adapters()
    return {
        "adapters": [
            {
                "name": a.name,
                "path": a.path,
                "size_mb": a.size_mb,
                "modified": a.modified,
                "active": a.active,
                "config": a.config,
            }
            for a in adapters
        ],
        "active": manager.active_adapter,
    }


@router.post("/adapters/activate")
async def admin_activate_adapter(request: AdapterRequest):
    """Активировать LoRA адаптер"""
    manager = get_finetune_manager()
    return await manager.activate_adapter(request.adapter)


@router.delete("/adapters/{name}")
async def admin_delete_adapter(name: str):
    """Удалить LoRA адаптер"""
    manager = get_finetune_manager()
    return await manager.delete_adapter(name)

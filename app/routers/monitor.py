# app/routers/monitor.py
"""System monitoring router - GPU, CPU, health checks, metrics."""

import asyncio
import json
import logging
import subprocess
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.dependencies import get_container
from service_manager import get_service_manager
from system_monitor import get_system_monitor


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/monitor", tags=["monitor"])


@router.get("/gpu")
async def admin_get_gpu_stats():
    """Получить статистику GPU"""
    import torch

    if not torch.cuda.is_available():
        return {"available": False, "gpus": []}

    gpus = []
    for i in range(torch.cuda.device_count()):
        try:
            name = torch.cuda.get_device_name(i)
            props = torch.cuda.get_device_properties(i)
            total_memory = props.total_memory / (1024**3)
            allocated = torch.cuda.memory_allocated(i) / (1024**3)
            reserved = torch.cuda.memory_reserved(i) / (1024**3)

            # Пытаемся получить утилизацию через nvidia-smi
            utilization = None
            temperature = None
            try:
                result = subprocess.run(
                    [
                        "nvidia-smi",
                        f"--id={i}",
                        "--query-gpu=utilization.gpu,temperature.gpu",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    parts = result.stdout.strip().split(",")
                    if len(parts) >= 2:
                        utilization = int(parts[0].strip())
                        temperature = int(parts[1].strip())
            except Exception:
                pass

            gpus.append(
                {
                    "id": i,
                    "name": name,
                    "total_memory_gb": round(total_memory, 2),
                    "allocated_gb": round(allocated, 2),
                    "reserved_gb": round(reserved, 2),
                    "free_gb": round(total_memory - reserved, 2),
                    "utilization_percent": utilization,
                    "temperature_c": temperature,
                    "compute_capability": f"{props.major}.{props.minor}",
                }
            )
        except Exception as e:
            logger.warning(f"Error getting GPU {i} stats: {e}")

    return {"available": True, "gpus": gpus}


@router.get("/gpu/stream")
async def admin_stream_gpu_stats():
    """SSE streaming статистики GPU"""
    import torch

    async def generate():
        while True:
            if torch.cuda.is_available():
                gpus = []
                for i in range(torch.cuda.device_count()):
                    try:
                        allocated = torch.cuda.memory_allocated(i) / (1024**3)
                        reserved = torch.cuda.memory_reserved(i) / (1024**3)
                        gpus.append(
                            {
                                "id": i,
                                "allocated_gb": round(allocated, 2),
                                "reserved_gb": round(reserved, 2),
                            }
                        )
                    except Exception:
                        pass

                yield f"data: {json.dumps({'gpus': gpus, 'timestamp': datetime.now().isoformat()})}\n\n"
            else:
                yield f"data: {json.dumps({'available': False})}\n\n"

            await asyncio.sleep(5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/health")
async def admin_get_health():
    """Расширенная проверка здоровья всех компонентов"""
    manager = get_service_manager()
    container = get_container()
    health = {"timestamp": datetime.now().isoformat(), "overall": "healthy", "components": {}}

    # Orchestrator
    health["components"]["orchestrator"] = {"status": "healthy", "uptime": "running"}

    # LLM
    llm_service = container.llm_service
    if llm_service:
        try:
            if hasattr(llm_service, "is_available") and llm_service.is_available():
                health["components"]["llm"] = {"status": "healthy", "backend": "vllm"}
            else:
                health["components"]["llm"] = {"status": "healthy", "backend": "gemini"}
        except Exception as e:
            health["components"]["llm"] = {"status": "unhealthy", "error": str(e)}
            health["overall"] = "degraded"
    else:
        health["components"]["llm"] = {"status": "unavailable"}
        health["overall"] = "degraded"

    # TTS
    if container.gulya_voice_service or container.voice_service:
        health["components"]["tts_xtts"] = {"status": "healthy"}
    else:
        health["components"]["tts_xtts"] = {"status": "unavailable"}

    if container.piper_service:
        health["components"]["tts_piper"] = {"status": "healthy"}
    else:
        health["components"]["tts_piper"] = {"status": "unavailable"}

    # vLLM external process
    vllm_status = manager.get_service_status("vllm")
    if vllm_status["is_running"]:
        health["components"]["vllm_process"] = {"status": "healthy", "pid": vllm_status["pid"]}
    else:
        health["components"]["vllm_process"] = {"status": "stopped"}

    return health


@router.get("/metrics")
async def admin_get_metrics():
    """Получить метрики системы"""
    import psutil

    container = get_container()
    metrics = {
        "timestamp": datetime.now().isoformat(),
        "system": {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
            "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        },
        "streaming_tts": (
            container.streaming_tts_manager.get_stats() if container.streaming_tts_manager else None
        ),
    }

    # LLM метрики
    if container.llm_service:
        metrics["llm"] = {
            "history_length": len(getattr(container.llm_service, "conversation_history", [])),
            "faq_count": len(getattr(container.llm_service, "faq", {})),
        }

    return metrics


@router.get("/errors")
async def admin_get_errors():
    """Получить последние ошибки"""
    manager = get_service_manager()
    return {"errors": manager.last_errors, "timestamp": datetime.now().isoformat()}


@router.post("/metrics/reset")
async def admin_reset_metrics():
    """Сбросить метрики"""
    container = get_container()
    # Очищаем кэш TTS
    if container.streaming_tts_manager:
        with container.streaming_tts_manager._cache_lock:
            container.streaming_tts_manager._cache.clear()

    return {"status": "ok", "message": "Metrics reset"}


@router.get("/system")
async def admin_get_system_status():
    """Полная информация о системе: GPU, CPU, RAM, диски, Docker, сеть"""
    monitor = get_system_monitor()
    return monitor.get_full_status()

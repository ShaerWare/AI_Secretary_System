"""GSM телефония - управление SIM7600E-H модулем."""

import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_gsm_service
from auth_manager import User, require_permission
from modules.core.service import config_service
from modules.telephony.service import gsm_service


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/gsm", tags=["gsm"])


# ============== Enums ==============


class ModuleState(str, Enum):
    DISCONNECTED = "disconnected"
    INITIALIZING = "initializing"
    READY = "ready"
    INCOMING_CALL = "incoming_call"
    IN_CALL = "in_call"
    ERROR = "error"


class CallDirection(str, Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class CallState(str, Enum):
    RINGING = "ringing"
    ACTIVE = "active"
    COMPLETED = "completed"
    MISSED = "missed"
    FAILED = "failed"


# ============== Pydantic Models ==============


class GSMStatus(BaseModel):
    """Статус GSM модуля."""

    state: ModuleState = ModuleState.DISCONNECTED
    signal_strength: Optional[int] = None  # 0-31, 99=unknown
    signal_percent: Optional[int] = None
    sim_status: Optional[str] = None  # READY, PIN, PUK, etc
    network_name: Optional[str] = None
    network_registered: bool = False
    phone_number: Optional[str] = None
    at_port: str = "/dev/ttyUSB2"
    audio_port: str = "/dev/ttyUSB4"
    module_info: Optional[str] = None
    last_error: Optional[str] = None
    mock_mode: bool = False


class GSMConfig(BaseModel):
    """Конфигурация GSM модуля."""

    # Порты
    at_port: str = "/dev/ttyUSB2"
    audio_port: str = "/dev/ttyUSB4"
    baud_rate: int = 115200

    # Автоответ
    auto_answer: bool = True
    auto_answer_rings: int = 2

    # Фильтрация номеров
    allowed_numbers: List[str] = []
    blocked_numbers: List[str] = []

    # Сообщения
    greeting_message: str = "Здравствуйте! Чем могу помочь?"
    goodbye_message: str = "До свидания! Хорошего дня!"
    busy_message: str = "Извините, сейчас занято. Оставьте сообщение после сигнала."

    # Таймауты (секунды)
    silence_timeout: int = 5
    max_call_duration: int = 300

    # SMS уведомления
    sms_enabled: bool = True
    sms_notify_number: str = ""
    sms_missed_call_template: str = "Пропущенный звонок от {number} в {time}"
    sms_voicemail_template: str = "Сообщение от {number}: {summary}"

    # LLM
    llm_backend: str = "vllm"
    llm_persona: str = "anna"

    # TTS
    tts_voice: str = "anna"
    tts_preset: str = "natural"


class CallInfo(BaseModel):
    """Информация о звонке."""

    id: str
    direction: CallDirection
    state: CallState
    caller_number: str
    started_at: datetime
    answered_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    transcript_preview: Optional[str] = None
    sms_sent: bool = False


class ActiveCall(BaseModel):
    """Активный звонок."""

    id: str
    direction: CallDirection
    caller_number: str
    started_at: datetime
    duration_seconds: int = 0
    transcript: List[dict] = []


class SMSMessage(BaseModel):
    """SMS сообщение."""

    id: int
    direction: str  # incoming/outgoing
    number: str
    text: str
    sent_at: datetime
    status: str


class SendSMSRequest(BaseModel):
    """Запрос на отправку SMS."""

    number: str
    text: str


class ATCommandRequest(BaseModel):
    """Запрос AT команды (для отладки)."""

    command: str
    timeout: float = 5.0


class ATCommandResponse(BaseModel):
    """Ответ AT команды."""

    command: str
    response: List[str]
    success: bool
    error: Optional[str] = None


class DialRequest(BaseModel):
    """Запрос на исходящий звонок."""

    number: str


# ============== Helpers ==============


def _require_gsm(gsm_svc):
    """Raise 503 if GSM service is not available."""
    if gsm_svc is None:
        raise HTTPException(
            status_code=503,
            detail="GSM сервис не инициализирован. Проверьте подключение модуля.",
        )
    return gsm_svc


# ============== Status Endpoints ==============


@router.get("/status")
async def gsm_status(
    gsm_svc=Depends(get_gsm_service), user: User = Depends(require_permission("gsm", "view"))
) -> GSMStatus:
    """Получить статус GSM модуля."""
    if gsm_svc is None:
        return GSMStatus(
            state=ModuleState.DISCONNECTED,
            last_error="GSM сервис не инициализирован. Модуль не подключен.",
        )

    status = await gsm_svc.get_status()
    return GSMStatus(
        state=ModuleState(status.state),
        signal_strength=status.signal_strength,
        signal_percent=status.signal_percent,
        sim_status=status.sim_status,
        network_name=status.network_name,
        network_registered=status.network_registered,
        phone_number=status.phone_number,
        at_port=gsm_svc.port,
        module_info=status.module_info,
        last_error=status.last_error,
        mock_mode=status.mock_mode,
    )


@router.post("/initialize")
async def initialize_module(
    gsm_svc=Depends(get_gsm_service),
    user: User = Depends(require_permission("gsm", "edit")),
):
    """Инициализировать GSM модуль."""
    gsm = _require_gsm(gsm_svc)

    if gsm.state == "ready":
        return {"status": "ok", "message": "GSM модуль уже инициализирован"}

    ok = await gsm.initialize()
    if ok:
        mode = "mock" if gsm.mock_mode else "hardware"
        return {"status": "ok", "message": f"GSM модуль инициализирован ({mode} mode)"}
    else:
        raise HTTPException(
            status_code=500,
            detail=f"Не удалось инициализировать GSM модуль: {gsm.last_error}",
        )


# ============== Config Endpoints ==============


@router.get("/config")
async def get_gsm_config(user: User = Depends(require_permission("gsm", "view"))) -> GSMConfig:
    """Получить конфигурацию GSM."""
    conf = await config_service.get_config("gsm_config")
    if conf:
        return GSMConfig(**conf)
    return GSMConfig()


@router.put("/config")
async def update_gsm_config(
    config: GSMConfig,
    user: User = Depends(require_permission("gsm", "edit")),
) -> GSMConfig:
    """Обновить конфигурацию GSM."""
    await config_service.set_config("gsm_config", config.model_dump())
    logger.info(f"GSM config updated by {user.username}")
    return config


# ============== Call Endpoints ==============


@router.get("/calls")
async def list_calls(
    limit: int = 50,
    offset: int = 0,
    state: Optional[CallState] = None,
    user: User = Depends(require_permission("gsm", "view")),
) -> dict:
    """Список звонков из БД."""
    state_val = state.value if state else None
    calls = await gsm_service.get_recent_calls(limit=limit, offset=offset, state=state_val)
    total = await gsm_service.count_calls(state=state_val)

    return {
        "calls": calls,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/calls/active")
async def get_active_call(
    gsm_svc=Depends(get_gsm_service), user: User = Depends(require_permission("gsm", "view"))
):
    """Получить активный звонок."""
    if gsm_svc is None:
        return None
    return gsm_svc.get_active_call()


@router.get("/calls/{call_id}")
async def get_call(call_id: str, user: User = Depends(require_permission("gsm", "view"))) -> dict:
    """Детали звонка из БД."""
    calls = await gsm_service.get_recent_calls(limit=200)
    for call in calls:
        if call["id"] == call_id:
            return call
    raise HTTPException(status_code=404, detail="Звонок не найден")


@router.post("/calls/answer")
async def answer_call(
    gsm_svc=Depends(get_gsm_service),
    user: User = Depends(require_permission("gsm", "manage")),
):
    """Ответить на входящий звонок."""
    gsm = _require_gsm(gsm_svc)

    ok = await gsm.answer()
    if ok:
        if gsm.active_call:
            await gsm_service.update_call_state(
                call_id=gsm.active_call.id,
                state="active",
                answered_at=gsm.active_call.answered_at,
            )
        return {"status": "ok", "message": "Звонок принят"}
    else:
        raise HTTPException(status_code=400, detail="Нет входящего звонка для ответа")


@router.post("/calls/hangup")
async def hangup_call(
    gsm_svc=Depends(get_gsm_service),
    user: User = Depends(require_permission("gsm", "manage")),
):
    """Завершить текущий звонок."""
    gsm = _require_gsm(gsm_svc)

    # Capture call info before hangup clears it
    call = gsm.active_call
    ok = await gsm.hangup()
    if ok:
        if call:
            await gsm_service.update_call_state(
                call_id=call.id,
                state="completed",
                ended_at=datetime.utcnow(),
            )
        return {"status": "ok", "message": "Звонок завершён"}
    else:
        raise HTTPException(status_code=400, detail="Нет активного звонка")


@router.post("/calls/dial")
async def dial_number(
    request: DialRequest,
    gsm_svc=Depends(get_gsm_service),
    user: User = Depends(require_permission("gsm", "manage")),
):
    """Позвонить на номер."""
    gsm = _require_gsm(gsm_svc)

    ok, result = await gsm.dial(request.number)
    if ok:
        await gsm_service.create_call(
            direction="outgoing",
            state="ringing",
            caller_number=request.number,
            call_id=result,
        )
        return {"status": "ok", "call_id": result, "message": f"Звонок на {request.number}"}
    else:
        raise HTTPException(status_code=400, detail=result)


# ============== SMS Endpoints ==============


@router.get("/sms")
async def list_sms(
    limit: int = 50, offset: int = 0, user: User = Depends(require_permission("gsm", "view"))
) -> dict:
    """Список SMS из БД."""
    messages = await gsm_service.get_recent_sms(limit=limit, offset=offset)
    total = await gsm_service.count_sms()

    return {
        "messages": messages,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/sms")
async def send_sms(
    request: SendSMSRequest,
    gsm_svc=Depends(get_gsm_service),
    user: User = Depends(require_permission("gsm", "manage")),
):
    """Отправить SMS."""
    gsm = _require_gsm(gsm_svc)

    ok, error = await gsm.send_sms(request.number, request.text)
    if ok:
        await gsm_service.create_sms(
            direction="outgoing",
            number=request.number,
            text=request.text,
            status="sent",
        )
        return {"status": "ok", "message": f"SMS отправлено на {request.number}"}
    else:
        raise HTTPException(status_code=500, detail=error or "Не удалось отправить SMS")


# ============== Debug Endpoints ==============


@router.post("/at")
async def execute_at_command(
    request: ATCommandRequest,
    gsm_svc=Depends(get_gsm_service),
    user: User = Depends(require_permission("gsm", "manage")),
) -> ATCommandResponse:
    """Выполнить AT команду (для отладки)."""
    gsm = _require_gsm(gsm_svc)

    success, lines = await gsm.execute_at(request.command, timeout=request.timeout)
    return ATCommandResponse(
        command=request.command,
        response=lines,
        success=success,
    )


@router.get("/ports")
async def list_serial_ports(user: User = Depends(require_permission("gsm", "view"))) -> dict:
    """Список доступных serial портов."""
    dev_path = Path("/dev")

    usb_ports = [str(p) for p in dev_path.glob("ttyUSB*")]
    acm_ports = [str(p) for p in dev_path.glob("ttyACM*")]

    return {
        "usb_ports": sorted(usb_ports),
        "acm_ports": sorted(acm_ports),
        "total": len(usb_ports) + len(acm_ports),
    }

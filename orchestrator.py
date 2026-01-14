#!/usr/bin/env python3
"""
Главный оркестратор - координирует все сервисы
STT (Whisper) -> LLM (Gemini) -> TTS (XTTS v2)
"""
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
from pathlib import Path
import tempfile
import os
from typing import Optional
from pydantic import BaseModel
import asyncio
from datetime import datetime

# Импорты наших сервисов
from voice_clone_service import VoiceCloneService
from stt_service import STTService
from llm_service import LLMService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Secretary Orchestrator", version="1.0.0")

# CORS для доступа из браузера
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальные сервисы
voice_service: Optional[VoiceCloneService] = None
stt_service: Optional[STTService] = None
llm_service: Optional[LLMService] = None

# Папка для временных файлов
TEMP_DIR = Path("./temp")
TEMP_DIR.mkdir(exist_ok=True)

# Папка для логов звонков
CALLS_LOG_DIR = Path("./calls_log")
CALLS_LOG_DIR.mkdir(exist_ok=True)


class ConversationRequest(BaseModel):
    text: str
    session_id: Optional[str] = None


class TTSRequest(BaseModel):
    text: str
    language: str = "ru"


class OpenAISpeechRequest(BaseModel):
    """OpenAI-compatible TTS request for OpenWebUI integration"""
    model: str = "lidia-voice"
    input: str
    voice: str = "lidia"
    response_format: str = "wav"
    speed: float = 1.0


@app.on_event("startup")
async def startup_event():
    """Инициализация всех сервисов при старте"""
    global voice_service, stt_service, llm_service

    logger.info("🚀 Запуск AI Secretary Orchestrator")

    try:
        # Инициализация сервисов
        logger.info("📦 Загрузка Voice Clone Service...")
        voice_service = VoiceCloneService()

        logger.info("📦 Загрузка STT Service...")
        stt_service = STTService(model_size="base", use_faster_whisper=True)

        logger.info("📦 Загрузка LLM Service...")
        llm_service = LLMService()

        logger.info("✅ Все сервисы загружены успешно")

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации: {e}")
        raise


@app.get("/")
async def root():
    """Проверка работоспособности"""
    return {
        "status": "ok",
        "service": "AI Secretary Orchestrator",
        "endpoints": {
            "health": "/health",
            "process_call": "/process_call (POST)",
            "tts": "/tts (POST)",
            "stt": "/stt (POST)",
            "chat": "/chat (POST)",
        }
    }


@app.get("/health")
async def health_check():
    """Проверка здоровья всех сервисов"""
    services_status = {
        "voice_clone": voice_service is not None,
        "stt": stt_service is not None,
        "llm": llm_service is not None,
    }

    all_ok = all(services_status.values())

    return {
        "status": "healthy" if all_ok else "degraded",
        "services": services_status,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/tts")
async def text_to_speech(request: TTSRequest):
    """
    Синтез речи с клонированным голосом Лидии
    """
    if not voice_service:
        raise HTTPException(status_code=503, detail="Voice service not initialized")

    try:
        # Генерируем уникальное имя файла
        output_file = TEMP_DIR / f"tts_{datetime.now().timestamp()}.wav"

        # Синтезируем
        voice_service.synthesize_to_file(
            text=request.text,
            output_path=str(output_file),
            language=request.language
        )

        # Возвращаем файл
        return FileResponse(
            path=output_file,
            media_type="audio/wav",
            filename="response.wav"
        )

    except Exception as e:
        logger.error(f"❌ TTS Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    """
    Распознавание речи из аудио файла
    """
    if not stt_service:
        raise HTTPException(status_code=503, detail="STT service not initialized")

    try:
        # Сохраняем загруженный файл
        temp_audio = TEMP_DIR / f"stt_{datetime.now().timestamp()}_{audio.filename}"

        with open(temp_audio, "wb") as f:
            content = await audio.read()
            f.write(content)

        # Распознаем
        result = stt_service.transcribe(temp_audio, language="ru")

        # Удаляем временный файл
        temp_audio.unlink()

        return {
            "text": result["text"],
            "language": result["language"],
            "segments_count": len(result.get("segments", []))
        }

    except Exception as e:
        logger.error(f"❌ STT Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat(request: ConversationRequest):
    """
    Получить ответ от LLM (Gemini)
    """
    if not llm_service:
        raise HTTPException(status_code=503, detail="LLM service not initialized")

    try:
        response = llm_service.generate_response(request.text)

        return {
            "response": response,
            "session_id": request.session_id
        }

    except Exception as e:
        logger.error(f"❌ LLM Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/process_call")
async def process_call(audio: UploadFile = File(...)):
    """
    Полный цикл обработки звонка:
    1. STT - распознавание речи
    2. LLM - генерация ответа
    3. TTS - синтез речи

    Возвращает аудио с ответом секретаря
    """
    call_id = f"call_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    logger.info(f"📞 Обработка звонка {call_id}")

    try:
        # 1. Сохраняем входящий аудио
        input_audio = CALLS_LOG_DIR / f"{call_id}_input.wav"
        with open(input_audio, "wb") as f:
            content = await audio.read()
            f.write(content)

        # 2. Распознаем речь (STT)
        logger.info(f"🎧 STT для {call_id}")
        stt_result = stt_service.transcribe(input_audio, language="ru")
        recognized_text = stt_result["text"]
        logger.info(f"📝 Распознано: {recognized_text}")

        # Сохраняем транскрипцию
        with open(CALLS_LOG_DIR / f"{call_id}_transcript.txt", "w") as f:
            f.write(f"USER: {recognized_text}\n")

        # 3. Генерируем ответ (LLM)
        logger.info(f"🤖 LLM для {call_id}")
        llm_response = llm_service.generate_response(recognized_text)
        logger.info(f"💬 Ответ: {llm_response}")

        # Дополняем транскрипцию
        with open(CALLS_LOG_DIR / f"{call_id}_transcript.txt", "a") as f:
            f.write(f"ASSISTANT: {llm_response}\n")

        # 4. Синтезируем ответ (TTS)
        logger.info(f"🎙️  TTS для {call_id}")
        output_audio = CALLS_LOG_DIR / f"{call_id}_output.wav"
        voice_service.synthesize_to_file(
            text=llm_response,
            output_path=str(output_audio),
            language="ru"
        )

        logger.info(f"✅ Звонок {call_id} обработан")

        # 5. Возвращаем аудио ответ
        return FileResponse(
            path=output_audio,
            media_type="audio/wav",
            filename=f"{call_id}_response.wav",
            headers={
                "X-Call-ID": call_id,
                "X-Recognized-Text": recognized_text,
                "X-Response-Text": llm_response
            }
        )

    except Exception as e:
        logger.error(f"❌ Ошибка обработки звонка {call_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reset_conversation")
async def reset_conversation():
    """Сброс истории диалога"""
    if llm_service:
        llm_service.reset_conversation()
        return {"status": "ok", "message": "Conversation history reset"}
    raise HTTPException(status_code=503, detail="LLM service not initialized")


# ============== OpenAI-Compatible Endpoints for OpenWebUI ==============

@app.get("/v1/models")
async def list_models():
    """OpenAI-compatible models list for OpenWebUI TTS integration"""
    return {
        "object": "list",
        "data": [
            {
                "id": "lidia-voice",
                "object": "model",
                "created": 1700000000,
                "owned_by": "ai-secretary",
                "permission": [],
                "root": "lidia-voice",
                "parent": None
            }
        ]
    }


@app.get("/v1/voices")
async def list_voices():
    """List available voices"""
    return {
        "voices": [
            {"voice_id": "lidia", "name": "Лидия", "language": "ru"}
        ]
    }


@app.post("/v1/audio/speech")
async def openai_speech(request: OpenAISpeechRequest):
    """
    OpenAI-compatible TTS endpoint for OpenWebUI integration
    POST /v1/audio/speech
    """
    if not voice_service:
        raise HTTPException(status_code=503, detail="Voice service not initialized")

    try:
        output_file = TEMP_DIR / f"speech_{datetime.now().timestamp()}.wav"

        voice_service.synthesize_to_file(
            text=request.input,
            output_path=str(output_file),
            language="ru"
        )

        return FileResponse(
            path=output_file,
            media_type="audio/wav",
            filename="speech.wav"
        )

    except Exception as e:
        logger.error(f"❌ OpenAI TTS Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    port = int(os.getenv("ORCHESTRATOR_PORT", 8002))
    logger.info(f"🎯 Запуск Orchestrator на порту {port}")
    uvicorn.run(
        "orchestrator:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )

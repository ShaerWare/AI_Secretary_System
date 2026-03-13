"""Legacy and OpenAI-compatible endpoints.

Provides backward-compatible API for telephony integration
and OpenAI-compatible endpoints for OpenWebUI.
"""

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import soundfile as sf
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.dependencies import get_container
from cloud_llm_service import CloudLLMService


logger = logging.getLogger(__name__)

router = APIRouter(tags=["compat"])

TEMP_DIR = Path("./temp")
TEMP_DIR.mkdir(exist_ok=True)

CALLS_LOG_DIR = Path("./calls_log")
CALLS_LOG_DIR.mkdir(exist_ok=True)


# ============== Pydantic Models ==============


class ConversationRequest(BaseModel):
    text: str
    session_id: Optional[str] = None


class TTSRequest(BaseModel):
    text: str
    language: str = "ru"


class OpenAISpeechRequest(BaseModel):
    """OpenAI-compatible TTS request for OpenWebUI integration"""

    model: str = "marina-voice"
    input: str
    voice: str = "marina"
    response_format: str = "wav"
    speed: float = 1.0


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request"""

    model: str = "anna-secretary-qwen"  # Format: {persona}-secretary-{backend}
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


# ============== Helper ==============


def synthesize_with_current_voice(text: str, output_path: str, language: str = "ru"):
    """
    Синтезирует речь с текущим выбранным голосом.
    Учитывает current_voice_config.

    Engines:
    - piper: CPU, быстрый, предобученные голоса (dmitri, irina)
    - openvoice: GPU CC 6.1+, клонирование голоса (marina_openvoice)
    - xtts: GPU CC >= 7.0, лучшее качество клонирования (anna, marina)
    """
    container = get_container()
    voice_config = container.current_voice_config
    engine = voice_config["engine"]
    voice = voice_config["voice"]

    if engine == "piper" and container.piper_service:
        logger.info(f"🎙️ Piper синтез ({voice}): '{text[:40]}...'")
        container.piper_service.synthesize_to_file(text, output_path, voice=voice)
    elif engine == "openvoice" and container.openvoice_service:
        logger.info(f"🎙️ OpenVoice синтез (Марина): '{text[:40]}...'")
        container.openvoice_service.synthesize_to_file(text, output_path, language=language)
    elif engine == "xtts" and voice == "anna" and container.anna_voice_service:
        logger.info(f"🎙️ XTTS синтез (Анна): '{text[:40]}...'")
        container.anna_voice_service.synthesize_to_file(text, output_path, language=language)
    elif engine == "xtts" and voice == "marina" and container.voice_service:
        logger.info(f"🎙️ XTTS синтез (Марина): '{text[:40]}...'")
        container.voice_service.synthesize_to_file(text, output_path, language=language)
    elif container.anna_voice_service:
        # Fallback to Анна if available (default)
        logger.info(f"🎙️ XTTS синтез (Анна fallback): '{text[:40]}...'")
        container.anna_voice_service.synthesize_to_file(text, output_path, language=language)
    elif container.voice_service:
        # Fallback to Марина if available
        logger.info(f"🎙️ XTTS синтез (Марина fallback): '{text[:40]}...'")
        container.voice_service.synthesize_to_file(text, output_path, language=language)
    elif container.openvoice_service:
        # Fallback to OpenVoice if XTTS not available
        logger.info(f"🎙️ OpenVoice синтез (fallback): '{text[:40]}...'")
        container.openvoice_service.synthesize_to_file(text, output_path, language=language)
    elif container.piper_service:
        # Fallback to Piper
        logger.info(f"🎙️ Piper синтез (fallback): '{text[:40]}...'")
        container.piper_service.synthesize_to_file(text, output_path, voice="irina")
    else:
        raise RuntimeError("No TTS service available")


# ============== Legacy Telephony Endpoints ==============


@router.post("/tts")
async def text_to_speech(request: TTSRequest):
    """
    Синтез речи с текущим выбранным голосом
    """
    container = get_container()
    if not container.voice_service and not container.piper_service:
        raise HTTPException(status_code=503, detail="No TTS service initialized")

    try:
        # Генерируем уникальное имя файла
        output_file = TEMP_DIR / f"tts_{datetime.now().timestamp()}.wav"

        # Синтезируем с текущим голосом
        synthesize_with_current_voice(
            text=request.text, output_path=str(output_file), language=request.language
        )

        # Возвращаем файл
        return FileResponse(path=output_file, media_type="audio/wav", filename="response.wav")

    except Exception as e:
        logger.error(f"❌ TTS Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    """
    Распознавание речи из аудио файла
    """
    container = get_container()
    if not container.stt_service:
        raise HTTPException(status_code=503, detail="STT service not initialized")

    try:
        # Сохраняем загруженный файл
        temp_audio = TEMP_DIR / f"stt_{datetime.now().timestamp()}_{audio.filename}"

        with open(temp_audio, "wb") as f:
            content = await audio.read()
            f.write(content)

        # Распознаем
        result = container.stt_service.transcribe(temp_audio, language="ru")

        # Удаляем временный файл
        temp_audio.unlink()

        return {
            "text": result["text"],
            "language": result["language"],
            "segments_count": len(result.get("segments", [])),
        }

    except Exception as e:
        logger.error(f"❌ STT Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat")
async def chat(request: ConversationRequest):
    """
    Получить ответ от LLM
    """
    container = get_container()
    if not container.llm_service:
        raise HTTPException(status_code=503, detail="LLM service not initialized")

    try:
        response = container.llm_service.generate_response(request.text)

        return {"response": response, "session_id": request.session_id}

    except Exception as e:
        logger.error(f"❌ LLM Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process_call")
async def process_call(audio: UploadFile = File(...)):
    """
    Полный цикл обработки звонка:
    1. STT - распознавание речи
    2. LLM - генерация ответа
    3. TTS - синтез речи

    Возвращает аудио с ответом секретаря
    """
    container = get_container()
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
        stt_result = container.stt_service.transcribe(input_audio, language="ru")
        recognized_text = stt_result["text"]
        logger.info(f"📝 Распознано: {recognized_text}")

        # Сохраняем транскрипцию
        with open(CALLS_LOG_DIR / f"{call_id}_transcript.txt", "w") as f:
            f.write(f"USER: {recognized_text}\n")

        # 3. Генерируем ответ (LLM)
        logger.info(f"🤖 LLM для {call_id}")
        llm_response = container.llm_service.generate_response(recognized_text)
        logger.info(f"💬 Ответ: {llm_response}")

        # Дополняем транскрипцию
        with open(CALLS_LOG_DIR / f"{call_id}_transcript.txt", "a") as f:
            f.write(f"ASSISTANT: {llm_response}\n")

        # 4. Синтезируем ответ (TTS)
        logger.info(f"🎙️  TTS для {call_id}")
        output_audio = CALLS_LOG_DIR / f"{call_id}_output.wav"
        container.voice_service.synthesize_to_file(
            text=llm_response, output_path=str(output_audio), language="ru"
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
                "X-Response-Text": llm_response,
            },
        )

    except Exception as e:
        logger.error(f"❌ Ошибка обработки звонка {call_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset_conversation")
async def reset_conversation():
    """Сброс истории диалога"""
    container = get_container()
    if container.llm_service:
        container.llm_service.reset_conversation()
        return {"status": "ok", "message": "Conversation history reset"}
    raise HTTPException(status_code=503, detail="LLM service not initialized")


# ============== OpenAI-Compatible Endpoints for OpenWebUI ==============


@router.get("/v1/models")
@router.get("/v1/models/")
async def list_models():
    """OpenAI-compatible models list for OpenWebUI"""
    container = get_container()
    llm_svc = container.llm_service

    # Определяем backend и суффикс для имени модели
    if llm_svc and hasattr(llm_svc, "api_url"):
        # vLLM backend - проверяем модель
        model_name = getattr(llm_svc, "model_name", "unknown")
        if model_name == "lydia" or "qwen" in model_name.lower():
            backend_suffix = "qwen"
            backend_desc = "Qwen2.5-7B + LoRA"
        elif "llama" in model_name.lower():
            backend_suffix = "llama"
            backend_desc = "Llama-3.1-8B"
        else:
            backend_suffix = "vllm"
            backend_desc = model_name
    elif llm_svc and isinstance(llm_svc, CloudLLMService):
        backend_suffix = "cloud"
        ptype = getattr(llm_svc, "provider_type", "cloud")
        backend_desc = f"{ptype}: {getattr(llm_svc, 'model_name', 'unknown')}"
    else:
        backend_suffix = "cloud"
        backend_desc = "Cloud AI"

    return {
        "object": "list",
        "data": [
            {
                "id": f"anna-secretary-{backend_suffix}",
                "object": "model",
                "created": 1700000000,
                "owned_by": "ai-secretary",
                "permission": [],
                "root": f"anna-secretary-{backend_suffix}",
                "parent": None,
                "description": f"Анна - цифровой секретарь ({backend_desc})",
            },
            {
                "id": f"marina-secretary-{backend_suffix}",
                "object": "model",
                "created": 1700000000,
                "owned_by": "ai-secretary",
                "permission": [],
                "root": f"marina-secretary-{backend_suffix}",
                "parent": None,
                "description": f"Марина - цифровой секретарь ({backend_desc})",
            },
        ],
    }


@router.get("/v1/voices")
async def list_voices():
    """List available voices"""
    container = get_container()
    voices = []
    if container.anna_voice_service:
        voices.append({"voice_id": "anna", "name": "Анна", "language": "ru"})
    if container.voice_service:
        voices.append({"voice_id": "marina", "name": "Марина", "language": "ru"})
    if container.piper_service:
        voices.append({"voice_id": "dmitri", "name": "Дмитрий", "language": "ru"})
        voices.append({"voice_id": "irina", "name": "Ирина", "language": "ru"})
    return {"voices": voices}


@router.post("/v1/audio/speech")
async def openai_speech(request: OpenAISpeechRequest):
    """
    OpenAI-compatible TTS endpoint for OpenWebUI integration
    POST /v1/audio/speech

    Оптимизация: сначала проверяет кэш streaming TTS manager.
    Если аудио уже было предсинтезировано во время streaming LLM - возвращает мгновенно.
    """
    container = get_container()
    if not container.voice_service and not container.piper_service:
        raise HTTPException(status_code=503, detail="No TTS service initialized")

    try:
        output_file = TEMP_DIR / f"speech_{datetime.now().timestamp()}.wav"
        start_time = time.time()

        # Проверяем кэш streaming TTS (только для XTTS)
        cached_audio = None
        if (
            container.current_voice_config["engine"] == "xtts"
            and container.streaming_tts_manager is not None
        ):
            cached_audio = container.streaming_tts_manager.get_cached_audio(request.input)

        if cached_audio is not None:
            # Cache HIT - используем предсинтезированное аудио
            audio_data, sample_rate = cached_audio
            sf.write(str(output_file), audio_data, sample_rate)
            elapsed = time.time() - start_time
            logger.info(f"⚡ TTS из кэша за {elapsed:.3f}s (vs ~5-10s обычный синтез)")
        else:
            # Cache MISS - синтезируем с текущим голосом
            synthesize_with_current_voice(
                text=request.input, output_path=str(output_file), language="ru"
            )
            elapsed = time.time() - start_time
            logger.info(f"🎙️ TTS синтезирован за {elapsed:.2f}s")

        return FileResponse(path=output_file, media_type="audio/wav", filename="speech.wav")

    except Exception as e:
        logger.error(f"❌ OpenAI TTS Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """
    OpenAI-compatible chat completions endpoint for OpenWebUI
    Supports both streaming and non-streaming responses.
    При streaming - запускает фоновый синтез TTS по предложениям.
    """
    container = get_container()
    llm_svc = container.llm_service
    if not llm_svc:
        raise HTTPException(status_code=503, detail="LLM service not initialized")

    logger.info(
        f"💬 Chat completions request: stream={request.stream}, messages={len(request.messages)}"
    )

    # Конвертируем Pydantic модели в dict
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    if request.stream:
        # Streaming response (SSE) с фоновым синтезом TTS
        async def generate_stream():
            created = int(time.time())
            chunk_id = f"chatcmpl-{created}"
            session_id = f"tts-{created}"

            # Начинаем сессию streaming TTS если сервисы доступны
            stm = container.streaming_tts_manager
            vs = container.voice_service
            use_streaming_tts = stm is not None and vs is not None

            if use_streaming_tts:
                stm.start_session(session_id)
                logger.info(f"🎬 Streaming TTS активирован для сессии {session_id}")

            try:
                for text_chunk in llm_svc.generate_response_from_messages(messages, stream=True):
                    # Отправляем chunk клиенту
                    chunk_data = {
                        "id": chunk_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": request.model,
                        "choices": [
                            {"index": 0, "delta": {"content": text_chunk}, "finish_reason": None}
                        ],
                    }
                    yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"

                    # Параллельно добавляем chunk в streaming TTS manager
                    if use_streaming_tts and text_chunk:
                        stm.add_text_chunk(session_id, text_chunk, vs)

                # Final chunk
                final_chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": request.model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
                yield f"data: {json.dumps(final_chunk)}\n\n"
                yield "data: [DONE]\n\n"

                # Завершаем сессию TTS (склеивает и кэширует аудио)
                if use_streaming_tts:
                    # Запускаем в отдельном потоке чтобы не блокировать response
                    threading.Thread(
                        target=stm.finish_session,
                        args=(session_id, vs),
                        daemon=True,
                    ).start()

            except Exception as e:
                logger.error(f"❌ Streaming error: {e}")
                error_chunk = {"error": {"message": str(e), "type": "server_error"}}
                yield f"data: {json.dumps(error_chunk)}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    else:
        # Non-streaming response
        try:
            response_text = llm_svc.generate_response_from_messages(messages, stream=False)

            # Consume generator if it returns one
            if hasattr(response_text, "__iter__") and not isinstance(response_text, str):
                response_text = "".join(response_text)

            return {
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": response_text},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
        except Exception as e:
            logger.error(f"❌ Chat completions error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

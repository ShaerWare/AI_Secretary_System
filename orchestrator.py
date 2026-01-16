#!/usr/bin/env python3
"""
Главный оркестратор - координирует все сервисы
STT (Whisper) -> LLM (Gemini) -> TTS (XTTS v2)
"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
from pathlib import Path
import os
from typing import Optional, List, Dict
from pydantic import BaseModel
from datetime import datetime
import json
import time
import threading
import hashlib
import re
import numpy as np
from collections import OrderedDict
import asyncio
from concurrent.futures import ThreadPoolExecutor
import soundfile as sf

# Импорты наших сервисов
from voice_clone_service import VoiceCloneService
from stt_service import STTService
from llm_service import LLMService
from piper_tts_service import PiperTTSService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============== Streaming TTS Manager ==============
class StreamingTTSManager:
    """
    Менеджер для параллельного синтеза TTS во время streaming LLM.

    Архитектура:
    1. Во время streaming chat/completions - накапливаем текст и при завершении
       предложения запускаем синтез в фоновом потоке
    2. Храним синтезированные сегменты в кэше по хэшу полного текста
    3. При запросе /v1/audio/speech - склеиваем готовые сегменты
    """

    def __init__(self, max_cache_size: int = 50, cache_ttl: int = 300):
        self.max_cache_size = max_cache_size
        self.cache_ttl = cache_ttl  # секунд

        # Кэш: response_hash -> {"segments": [...], "full_audio": np.array, "timestamp": float}
        self._cache: OrderedDict[str, Dict] = OrderedDict()
        self._cache_lock = threading.Lock()

        # Текущие сессии синтеза: session_id -> {"text": str, "segments": [...], "futures": [...]}
        self._active_sessions: Dict[str, Dict] = {}
        self._session_lock = threading.Lock()

        # Thread pool для фонового синтеза
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tts_")

        # Регулярка для разбиения на предложения
        self._sentence_pattern = re.compile(r'([^.!?]*[.!?]+)')

        logger.info("🎙️ StreamingTTSManager инициализирован")

    def _get_text_hash(self, text: str) -> str:
        """Вычисляет хэш текста для кэширования"""
        normalized = text.strip().lower()
        return hashlib.md5(normalized.encode()).hexdigest()[:16]

    def _clean_old_cache(self):
        """Удаляет устаревшие записи из кэша"""
        now = time.time()
        with self._cache_lock:
            keys_to_delete = []
            for key, value in self._cache.items():
                if now - value.get("timestamp", 0) > self.cache_ttl:
                    keys_to_delete.append(key)
            for key in keys_to_delete:
                del self._cache[key]
                logger.debug(f"🗑️ Удалён устаревший кэш: {key}")

            # Ограничиваем размер кэша
            while len(self._cache) > self.max_cache_size:
                self._cache.popitem(last=False)

    def start_session(self, session_id: str) -> None:
        """Начинает новую сессию streaming синтеза"""
        with self._session_lock:
            self._active_sessions[session_id] = {
                "text_buffer": "",
                "full_text": "",
                "segments": [],  # [(text, audio_data, sample_rate), ...]
                "pending_futures": [],
                "start_time": time.time(),
            }
        logger.info(f"🎬 Начата сессия TTS: {session_id}")

    def add_text_chunk(self, session_id: str, chunk: str, voice_service) -> None:
        """
        Добавляет chunk текста и запускает синтез при завершении предложения.
        Вызывается из streaming LLM response.
        """
        with self._session_lock:
            if session_id not in self._active_sessions:
                return

            session = self._active_sessions[session_id]
            session["text_buffer"] += chunk
            session["full_text"] += chunk

            # Проверяем, есть ли завершённые предложения
            buffer = session["text_buffer"]
            sentences = self._sentence_pattern.findall(buffer)

            if sentences:
                # Синтезируем каждое завершённое предложение
                for sentence in sentences:
                    sentence = sentence.strip()
                    if len(sentence) > 3:  # Игнорируем слишком короткие
                        future = self._executor.submit(
                            self._synthesize_segment,
                            sentence,
                            voice_service,
                            session_id
                        )
                        session["pending_futures"].append((sentence, future))
                        logger.info(f"🔄 Запущен синтез: '{sentence[:40]}...'")

                # Удаляем обработанные предложения из буфера
                last_sentence = sentences[-1]
                idx = buffer.rfind(last_sentence) + len(last_sentence)
                session["text_buffer"] = buffer[idx:]

    def _synthesize_segment(self, text: str, voice_service, session_id: str) -> tuple:
        """Синтезирует один сегмент (выполняется в thread pool)"""
        try:
            wav, sr = voice_service.synthesize(
                text=text,
                preset="natural",
                preprocess_text=True,
                split_sentences=False  # Уже разбили
            )
            logger.info(f"✅ Синтезирован сегмент: '{text[:30]}...'")
            return (text, wav, sr)
        except Exception as e:
            logger.error(f"❌ Ошибка синтеза сегмента: {e}")
            return (text, None, None)

    def finish_session(self, session_id: str, voice_service) -> None:
        """
        Завершает сессию: синтезирует оставшийся текст и кэширует результат.
        """
        with self._session_lock:
            if session_id not in self._active_sessions:
                return

            session = self._active_sessions[session_id]

            # Синтезируем остаток буфера если есть
            remaining = session["text_buffer"].strip()
            if remaining and len(remaining) > 3:
                future = self._executor.submit(
                    self._synthesize_segment,
                    remaining,
                    voice_service,
                    session_id
                )
                session["pending_futures"].append((remaining, future))
                logger.info(f"🔄 Запущен синтез остатка: '{remaining[:40]}...'")

            # Ждём завершения всех futures
            for text, future in session["pending_futures"]:
                try:
                    result = future.result(timeout=60)
                    if result[1] is not None:
                        session["segments"].append(result)
                except Exception as e:
                    logger.error(f"❌ Ошибка получения результата синтеза: {e}")

            # Склеиваем сегменты
            full_text = session["full_text"]
            if session["segments"]:
                self._cache_full_audio(full_text, session["segments"])

            elapsed = time.time() - session["start_time"]
            logger.info(f"✅ Сессия {session_id} завершена за {elapsed:.2f}s, "
                       f"сегментов: {len(session['segments'])}")

            # Удаляем сессию
            del self._active_sessions[session_id]

    def _cache_full_audio(self, full_text: str, segments: list) -> None:
        """Склеивает сегменты и кэширует полное аудио"""
        if not segments:
            return

        # Получаем sample rate из первого сегмента
        sample_rate = segments[0][2]

        # Склеиваем аудио с небольшими паузами
        pause_samples = int(0.1 * sample_rate)  # 100ms пауза
        pause = np.zeros(pause_samples, dtype=np.float32)

        audio_parts = []
        for text, wav, sr in segments:
            if wav is not None:
                if isinstance(wav, list):
                    wav = np.array(wav, dtype=np.float32)
                audio_parts.append(wav)
                audio_parts.append(pause)

        if audio_parts:
            full_audio = np.concatenate(audio_parts[:-1])  # Убираем последнюю паузу

            text_hash = self._get_text_hash(full_text)
            with self._cache_lock:
                self._cache[text_hash] = {
                    "full_audio": full_audio,
                    "sample_rate": sample_rate,
                    "full_text": full_text,
                    "timestamp": time.time(),
                    "segments_count": len(segments),
                }
                logger.info(f"💾 Закэшировано аудио: {text_hash} ({len(full_audio)/sample_rate:.2f}s)")

            self._clean_old_cache()

    def get_cached_audio(self, text: str) -> Optional[tuple]:
        """
        Получает закэшированное аудио для текста.
        Returns: (audio_data, sample_rate) или None
        """
        text_hash = self._get_text_hash(text)

        with self._cache_lock:
            if text_hash in self._cache:
                cached = self._cache[text_hash]
                logger.info(f"⚡ Cache HIT: {text_hash}")
                return (cached["full_audio"], cached["sample_rate"])

        logger.info(f"❌ Cache MISS: {text_hash}")
        return None

    def get_stats(self) -> dict:
        """Возвращает статистику менеджера"""
        with self._cache_lock:
            cache_size = len(self._cache)
        with self._session_lock:
            active_sessions = len(self._active_sessions)

        return {
            "cache_size": cache_size,
            "active_sessions": active_sessions,
            "max_cache_size": self.max_cache_size,
        }


# Глобальный менеджер streaming TTS
streaming_tts_manager: Optional[StreamingTTSManager] = None

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
voice_service: Optional[VoiceCloneService] = None  # XTTS (Лидия)
piper_service: Optional[PiperTTSService] = None    # Piper (Dmitri, Irina)
stt_service: Optional[STTService] = None
llm_service: Optional[LLMService] = None

# Конфигурация текущего голоса
# engine: "xtts" (Лидия) или "piper" (Dmitri/Irina)
current_voice_config = {
    "engine": "xtts",
    "voice": "lidia",  # lidia / dmitri / irina
}

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


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request"""
    model: str = "lidia-gemini"
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@app.on_event("startup")
async def startup_event():
    """Инициализация всех сервисов при старте"""
    global voice_service, piper_service, stt_service, llm_service, streaming_tts_manager

    logger.info("🚀 Запуск AI Secretary Orchestrator")

    try:
        # Инициализация XTTS (Лидия)
        logger.info("📦 Загрузка Voice Clone Service (XTTS)...")
        voice_service = VoiceCloneService()

        # Инициализация Piper TTS (Dmitri, Irina)
        logger.info("📦 Загрузка Piper TTS Service...")
        try:
            piper_service = PiperTTSService()
        except Exception as e:
            logger.warning(f"⚠️ Piper TTS недоступен: {e}")
            piper_service = None

        logger.info("📦 Загрузка LLM Service...")
        llm_service = LLMService()

        # Инициализация Streaming TTS Manager
        logger.info("📦 Инициализация Streaming TTS Manager...")
        streaming_tts_manager = StreamingTTSManager(max_cache_size=50, cache_ttl=300)

        # STT отключён временно - для текстового чата не нужен
        # Модель faster-whisper зависает при загрузке
        logger.info("⏭️ STT отключён (для текстового чата не нужен)")
        stt_service = None

        logger.info("✅ Основные сервисы загружены успешно")

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
        "streaming_tts": streaming_tts_manager is not None,
    }

    # Для health check достаточно voice + llm
    core_ok = services_status["voice_clone"] and services_status["llm"]

    result = {
        "status": "healthy" if core_ok else "degraded",
        "services": services_status,
        "timestamp": datetime.now().isoformat()
    }

    # Добавляем статистику streaming TTS если доступен
    if streaming_tts_manager is not None:
        result["streaming_tts_stats"] = streaming_tts_manager.get_stats()

    return result


def synthesize_with_current_voice(text: str, output_path: str, language: str = "ru"):
    """
    Синтезирует речь с текущим выбранным голосом.
    Учитывает current_voice_config.
    """
    engine = current_voice_config["engine"]
    voice = current_voice_config["voice"]

    if engine == "piper" and piper_service:
        logger.info(f"🎙️ Piper синтез ({voice}): '{text[:40]}...'")
        piper_service.synthesize_to_file(text, output_path, voice=voice)
    elif voice_service:
        logger.info(f"🎙️ XTTS синтез (Лидия): '{text[:40]}...'")
        voice_service.synthesize_to_file(text, output_path, language=language)
    else:
        raise RuntimeError("No TTS service available")


@app.post("/tts")
async def text_to_speech(request: TTSRequest):
    """
    Синтез речи с текущим выбранным голосом
    """
    if not voice_service and not piper_service:
        raise HTTPException(status_code=503, detail="No TTS service initialized")

    try:
        # Генерируем уникальное имя файла
        output_file = TEMP_DIR / f"tts_{datetime.now().timestamp()}.wav"

        # Синтезируем с текущим голосом
        synthesize_with_current_voice(
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
@app.get("/v1/models/")
async def list_models():
    """OpenAI-compatible models list for OpenWebUI"""
    return {
        "object": "list",
        "data": [
            {
                "id": "lidia-gemini",
                "object": "model",
                "created": 1700000000,
                "owned_by": "ai-secretary",
                "permission": [],
                "root": "lidia-gemini",
                "parent": None
            },
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

    Оптимизация: сначала проверяет кэш streaming TTS manager.
    Если аудио уже было предсинтезировано во время streaming LLM - возвращает мгновенно.
    """
    if not voice_service and not piper_service:
        raise HTTPException(status_code=503, detail="No TTS service initialized")

    try:
        output_file = TEMP_DIR / f"speech_{datetime.now().timestamp()}.wav"
        start_time = time.time()

        # Проверяем кэш streaming TTS (только для XTTS)
        cached_audio = None
        if current_voice_config["engine"] == "xtts" and streaming_tts_manager is not None:
            cached_audio = streaming_tts_manager.get_cached_audio(request.input)

        if cached_audio is not None:
            # Cache HIT - используем предсинтезированное аудио
            audio_data, sample_rate = cached_audio
            sf.write(str(output_file), audio_data, sample_rate)
            elapsed = time.time() - start_time
            logger.info(f"⚡ TTS из кэша за {elapsed:.3f}s (vs ~5-10s обычный синтез)")
        else:
            # Cache MISS - синтезируем с текущим голосом
            synthesize_with_current_voice(
                text=request.input,
                output_path=str(output_file),
                language="ru"
            )
            elapsed = time.time() - start_time
            logger.info(f"🎙️ TTS синтезирован за {elapsed:.2f}s")

        return FileResponse(
            path=output_file,
            media_type="audio/wav",
            filename="speech.wav"
        )

    except Exception as e:
        logger.error(f"❌ OpenAI TTS Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """
    OpenAI-compatible chat completions endpoint for OpenWebUI
    Supports both streaming and non-streaming responses.
    При streaming - запускает фоновый синтез TTS по предложениям.
    """
    if not llm_service:
        raise HTTPException(status_code=503, detail="LLM service not initialized")

    logger.info(f"💬 Chat completions request: stream={request.stream}, messages={len(request.messages)}")

    # Конвертируем Pydantic модели в dict
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    if request.stream:
        # Streaming response (SSE) с фоновым синтезом TTS
        async def generate_stream():
            created = int(time.time())
            chunk_id = f"chatcmpl-{created}"
            session_id = f"tts-{created}"

            # Начинаем сессию streaming TTS если сервисы доступны
            use_streaming_tts = (
                streaming_tts_manager is not None and
                voice_service is not None
            )

            if use_streaming_tts:
                streaming_tts_manager.start_session(session_id)
                logger.info(f"🎬 Streaming TTS активирован для сессии {session_id}")

            try:
                for text_chunk in llm_service.generate_response_from_messages(messages, stream=True):
                    # Отправляем chunk клиенту
                    chunk_data = {
                        "id": chunk_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": request.model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": text_chunk},
                            "finish_reason": None
                        }]
                    }
                    yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"

                    # Параллельно добавляем chunk в streaming TTS manager
                    if use_streaming_tts and text_chunk:
                        streaming_tts_manager.add_text_chunk(
                            session_id, text_chunk, voice_service
                        )

                # Final chunk
                final_chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": request.model,
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop"
                    }]
                }
                yield f"data: {json.dumps(final_chunk)}\n\n"
                yield "data: [DONE]\n\n"

                # Завершаем сессию TTS (склеивает и кэширует аудио)
                if use_streaming_tts:
                    # Запускаем в отдельном потоке чтобы не блокировать response
                    threading.Thread(
                        target=streaming_tts_manager.finish_session,
                        args=(session_id, voice_service),
                        daemon=True
                    ).start()

            except Exception as e:
                logger.error(f"❌ Streaming error: {e}")
                error_chunk = {
                    "error": {"message": str(e), "type": "server_error"}
                }
                yield f"data: {json.dumps(error_chunk)}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    else:
        # Non-streaming response
        try:
            response_text = llm_service.generate_response_from_messages(messages, stream=False)

            # Consume generator if it returns one
            if hasattr(response_text, '__iter__') and not isinstance(response_text, str):
                response_text = "".join(response_text)

            return {
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": request.model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response_text
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                }
            }
        except Exception as e:
            logger.error(f"❌ Chat completions error: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# ============== Admin Web Interface ==============

@app.get("/admin")
@app.get("/admin/")
async def admin_web_interface():
    """Веб-интерфейс админки"""
    from fastapi.responses import HTMLResponse

    admin_html_path = Path(__file__).parent / "admin_web.html"
    if admin_html_path.exists():
        return HTMLResponse(content=admin_html_path.read_text(encoding='utf-8'))
    else:
        return HTMLResponse(content="""
            <html><body style="background:#1a1a2e;color:#eee;font-family:sans-serif;padding:50px;text-align:center">
            <h1>Admin Web Interface</h1>
            <p>File admin_web.html not found</p>
            <p><a href="/admin/status" style="color:#e94560">API Status</a></p>
            </body></html>
        """)


# ============== Admin API Endpoints ==============

class AdminTTSPresetRequest(BaseModel):
    """Запрос на изменение пресета TTS"""
    preset: str  # warm, calm, energetic, natural, neutral


class AdminLLMPromptRequest(BaseModel):
    """Запрос на изменение системного промпта"""
    prompt: str


class AdminLLMModelRequest(BaseModel):
    """Запрос на изменение модели LLM"""
    model: str  # gemini-2.5-flash, gemini-2.5-pro


class AdminTTSTestRequest(BaseModel):
    """Запрос на тестовый синтез"""
    text: str
    preset: str = "natural"


@app.get("/admin/status")
async def admin_status():
    """Полный статус системы для админки"""
    import torch

    status = {
        "orchestrator": "running",
        "services": {
            "voice_clone": voice_service is not None,
            "llm": llm_service is not None,
            "stt": stt_service is not None,
            "streaming_tts": streaming_tts_manager is not None,
            "piper_tts": piper_service is not None,
        },
        "gpu": None,
        "streaming_tts_stats": None,
        "llm_config": None,
        "tts_config": None,
    }

    # GPU информация
    if torch.cuda.is_available():
        gpu_info = []
        for i in range(torch.cuda.device_count()):
            try:
                name = torch.cuda.get_device_name(i)
                total = torch.cuda.get_device_properties(i).total_memory / (1024**3)
                allocated = torch.cuda.memory_allocated(i) / (1024**3)
                gpu_info.append({
                    "id": i,
                    "name": name,
                    "total_gb": round(total, 2),
                    "used_gb": round(allocated, 2),
                })
            except Exception:
                pass
        status["gpu"] = gpu_info

    # Streaming TTS статистика
    if streaming_tts_manager:
        status["streaming_tts_stats"] = streaming_tts_manager.get_stats()

    # LLM конфигурация
    if llm_service:
        status["llm_config"] = llm_service.get_config()

    # TTS конфигурация
    if voice_service:
        status["tts_config"] = {
            "device": voice_service.device,
            "default_preset": voice_service.default_preset,
            "samples_count": len(voice_service.voice_samples),
            "cache_dir": str(voice_service.cache_dir),
        }

    return status


@app.get("/admin/tts/presets")
async def admin_tts_presets():
    """Список доступных TTS пресетов"""
    from voice_clone_service import INTONATION_PRESETS

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

    current = voice_service.default_preset if voice_service else "natural"

    return {
        "presets": presets,
        "current": current,
    }


@app.post("/admin/tts/preset")
async def admin_set_tts_preset(request: AdminTTSPresetRequest):
    """Установить текущий пресет TTS"""
    from voice_clone_service import INTONATION_PRESETS

    if request.preset not in INTONATION_PRESETS:
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестный пресет: {request.preset}. Доступные: {list(INTONATION_PRESETS.keys())}"
        )

    if voice_service:
        voice_service.default_preset = request.preset
        preset = INTONATION_PRESETS[request.preset]
        return {
            "status": "ok",
            "preset": request.preset,
            "display_name": preset.name,
            "settings": {
                "temperature": preset.temperature,
                "speed": preset.speed,
            }
        }

    raise HTTPException(status_code=503, detail="Voice service not initialized")


@app.post("/admin/tts/test")
async def admin_tts_test(request: AdminTTSTestRequest):
    """Тестовый синтез речи"""
    if not voice_service:
        raise HTTPException(status_code=503, detail="Voice service not initialized")

    try:
        import time as t
        start = t.time()

        output_file = TEMP_DIR / f"admin_test_{datetime.now().timestamp()}.wav"
        voice_service.synthesize_to_file(
            text=request.text,
            output_path=str(output_file),
            preset=request.preset,
            language="ru"
        )

        elapsed = t.time() - start

        # Получаем длительность аудио
        import wave
        with wave.open(str(output_file), 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            duration = frames / float(rate)

        return {
            "status": "ok",
            "file": str(output_file),
            "duration_sec": round(duration, 2),
            "synthesis_time_sec": round(elapsed, 2),
            "rtf": round(elapsed / duration, 2) if duration > 0 else 0,
        }

    except Exception as e:
        logger.error(f"❌ Admin TTS test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/tts/cache")
async def admin_tts_cache():
    """Статистика кэша streaming TTS"""
    if streaming_tts_manager:
        return streaming_tts_manager.get_stats()
    return {"cache_size": 0, "active_sessions": 0}


@app.delete("/admin/tts/cache")
async def admin_clear_tts_cache():
    """Очистить кэш streaming TTS"""
    if streaming_tts_manager:
        with streaming_tts_manager._cache_lock:
            count = len(streaming_tts_manager._cache)
            streaming_tts_manager._cache.clear()
        return {"status": "ok", "cleared_items": count}
    return {"status": "ok", "cleared_items": 0}


@app.get("/admin/llm/prompt")
async def admin_get_llm_prompt():
    """Получить текущий системный промпт LLM"""
    if llm_service:
        return {
            "prompt": llm_service.system_prompt,
            "model": llm_service.model_name,
        }
    raise HTTPException(status_code=503, detail="LLM service not initialized")


@app.post("/admin/llm/prompt")
async def admin_set_llm_prompt(request: AdminLLMPromptRequest):
    """Установить новый системный промпт LLM"""
    if llm_service:
        llm_service.set_system_prompt(request.prompt)
        return {
            "status": "ok",
            "prompt": request.prompt[:100] + "..." if len(request.prompt) > 100 else request.prompt,
        }
    raise HTTPException(status_code=503, detail="LLM service not initialized")


@app.get("/admin/llm/model")
async def admin_get_llm_model():
    """Получить текущую модель LLM"""
    if llm_service:
        return {"model": llm_service.model_name}
    raise HTTPException(status_code=503, detail="LLM service not initialized")


@app.post("/admin/llm/model")
async def admin_set_llm_model(request: AdminLLMModelRequest):
    """Изменить модель LLM"""
    allowed_models = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]

    if request.model not in allowed_models:
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестная модель: {request.model}. Доступные: {allowed_models}"
        )

    if llm_service:
        try:
            llm_service.set_model(request.model)
            return {"status": "ok", "model": request.model}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=503, detail="LLM service not initialized")


@app.delete("/admin/llm/history")
async def admin_clear_llm_history():
    """Очистить историю диалога LLM"""
    if llm_service:
        count = len(llm_service.conversation_history)
        llm_service.reset_conversation()
        return {"status": "ok", "cleared_messages": count}
    raise HTTPException(status_code=503, detail="LLM service not initialized")


@app.get("/admin/llm/history")
async def admin_get_llm_history():
    """Получить историю диалога LLM"""
    if llm_service:
        return {
            "history": llm_service.conversation_history,
            "count": len(llm_service.conversation_history),
        }
    raise HTTPException(status_code=503, detail="LLM service not initialized")


# ============== Voice Selection API ==============

class AdminVoiceRequest(BaseModel):
    voice: str  # lidia / dmitri / irina


@app.get("/admin/voices")
async def admin_get_voices():
    """Получить список всех доступных голосов"""
    voices = []

    # XTTS голос (Лидия)
    if voice_service:
        voices.append({
            "id": "lidia",
            "name": "Лидия",
            "engine": "xtts",
            "description": "Клонированный голос (XTTS v2)",
            "available": True,
            "samples_count": len(voice_service.voice_samples),
        })

    # Piper голоса
    if piper_service:
        piper_voices = piper_service.get_available_voices()
        for voice_id, info in piper_voices.items():
            voices.append({
                "id": voice_id,
                "name": info["name"],
                "engine": "piper",
                "description": info["description"],
                "available": info["available"],
            })

    return {
        "voices": voices,
        "current": current_voice_config,
    }


@app.get("/admin/voice")
async def admin_get_current_voice():
    """Получить текущий выбранный голос"""
    return current_voice_config


@app.post("/admin/voice")
async def admin_set_voice(request: AdminVoiceRequest):
    """Установить активный голос"""
    global current_voice_config

    voice_id = request.voice.lower()

    # Проверяем доступность голоса
    if voice_id == "lidia":
        if not voice_service:
            raise HTTPException(status_code=503, detail="XTTS service not available")
        current_voice_config = {"engine": "xtts", "voice": "lidia"}
        logger.info(f"🎤 Голос изменён на: Лидия (XTTS)")

    elif voice_id in ["dmitri", "irina"]:
        if not piper_service:
            raise HTTPException(status_code=503, detail="Piper TTS service not available")
        piper_voices = piper_service.get_available_voices()
        if voice_id not in piper_voices or not piper_voices[voice_id]["available"]:
            raise HTTPException(status_code=400, detail=f"Voice model not found: {voice_id}")
        current_voice_config = {"engine": "piper", "voice": voice_id}
        logger.info(f"🎤 Голос изменён на: {piper_voices[voice_id]['name']} (Piper)")

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown voice: {voice_id}. Available: lidia, dmitri, irina"
        )

    return {"status": "ok", **current_voice_config}


@app.post("/admin/voice/test")
async def admin_test_voice(request: AdminVoiceRequest):
    """Тестовый синтез выбранным голосом"""
    voice_id = request.voice.lower()
    test_text = "Здравствуйте! Это тестовое сообщение для проверки голоса."

    output_path = TEMP_DIR / f"voice_test_{voice_id}_{int(time.time())}.wav"

    try:
        if voice_id == "lidia":
            if not voice_service:
                raise HTTPException(status_code=503, detail="XTTS not available")
            voice_service.synthesize_to_file(test_text, str(output_path), preset="natural")

        elif voice_id in ["dmitri", "irina"]:
            if not piper_service:
                raise HTTPException(status_code=503, detail="Piper not available")
            piper_service.synthesize_to_file(test_text, str(output_path), voice=voice_id)

        else:
            raise HTTPException(status_code=400, detail=f"Unknown voice: {voice_id}")

        return FileResponse(
            output_path,
            media_type="audio/wav",
            filename=f"test_{voice_id}.wav"
        )

    except Exception as e:
        logger.error(f"❌ Ошибка тестового синтеза: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def get_current_tts_service():
    """Возвращает текущий TTS сервис и параметры на основе конфигурации"""
    engine = current_voice_config["engine"]
    voice = current_voice_config["voice"]

    if engine == "xtts":
        return voice_service, {"preset": "natural"}
    elif engine == "piper":
        return piper_service, {"voice": voice}
    else:
        return voice_service, {"preset": "natural"}


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

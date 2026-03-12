"""
GSM Voice Call Pipeline — connects incoming calls to AI assistant.

Flow: Incoming call -> Auto-answer -> PCM audio capture via /dev/ttyUSB4
      -> STT (Vosk streaming) -> LLM chat API (with RAG + system prompt)
      -> TTS (XTTS/Piper streaming) -> PCM audio playback via /dev/ttyUSB4

SIM7600E-H USB PCM audio:
- AT+CPCMREG=1 enables PCM streaming over /dev/ttyUSB4
- Format: 8kHz 16-bit signed little-endian mono
- Frame: 320 bytes = 20ms of audio

Uses internal chat API for LLM responses (supports RAG, knowledge collections,
system prompts — same as admin panel chat).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Optional

import httpx
import numpy as np


if TYPE_CHECKING:
    from app.services.gsm_service import GSMService

logger = logging.getLogger(__name__)

# SIM7600E-H PCM audio constants
PCM_SAMPLE_RATE = 8000
PCM_SAMPLE_WIDTH = 2  # 16-bit
PCM_FRAME_MS = 20
PCM_FRAME_BYTES = PCM_SAMPLE_RATE * PCM_SAMPLE_WIDTH * PCM_FRAME_MS // 1000  # 320

# Silence detection
# SIM7600E-H PCM over UART sends data in bursts: 1-2 frames with audio, then
# 8-10 empty (zero) frames. Only non-empty frames should be used for silence detection.
SILENCE_THRESHOLD = 300  # RMS below this = silence (non-zero frames only)
ZERO_FRAME_THRESHOLD = 1.0  # RMS below this = empty UART frame (skip entirely)
SILENCE_DURATION_S = 2.0  # Seconds of silence (by wall clock) = end of utterance
MIN_SPEECH_DURATION_S = 0.3  # Minimum speech to consider valid

# Defaults
DEFAULT_GREETING = "Здравствуйте! Вы позвонили виртуальному секретарю. Чем могу помочь?"
DEFAULT_SYSTEM_PROMPT = (
    "Ты — виртуальный секретарь компании. Отвечай кратко и по делу, "
    "максимум 2-3 предложения. Говори на русском языке. "
    "Ты общаешься по телефону, поэтому не используй markdown, ссылки или форматирование."
)

try:
    import serial

    PYSERIAL_AVAILABLE = True
except ImportError:
    PYSERIAL_AVAILABLE = False


class GSMVoiceCallService:
    """Voice call pipeline: PCM audio <-> STT <-> Chat API (RAG+LLM) <-> TTS."""

    def __init__(
        self,
        gsm_service: GSMService,
        stt_service=None,
        tts_service=None,
        piper_service=None,
        audio_port: str = "/dev/ttyUSB4",
        audio_baud: int = 115200,
        auto_answer: bool = True,
        auto_answer_rings: int = 2,
        greeting: str = DEFAULT_GREETING,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        tts_voice: str = "xtts",
        piper_voice: str = "irina",
        rag_mode: str = "all",
        knowledge_collection_ids: Optional[list[int]] = None,
        llm_backend: Optional[str] = None,
        orchestrator_port: int = 8002,
    ):
        self.gsm = gsm_service
        self.stt = stt_service
        self.tts_xtts = tts_service
        self.tts_piper = piper_service
        self.audio_port = audio_port
        self.audio_baud = audio_baud
        self.auto_answer = auto_answer
        self.auto_answer_rings = auto_answer_rings
        self.greeting = greeting
        self.system_prompt = system_prompt
        self.tts_voice = tts_voice  # "xtts", "piper"
        self.piper_voice = piper_voice  # "irina", "dmitri"
        self.rag_mode = rag_mode
        self.llm_backend = llm_backend  # None = system default, "vllm", "cloud:{id}"
        self.knowledge_collection_ids = knowledge_collection_ids or []
        self.orchestrator_port = orchestrator_port
        self.sms_auto_reply = True

        self._audio_serial: Optional[serial.Serial] = None
        self._call_task: Optional[asyncio.Task] = None
        self._ring_count = 0
        self._is_active = False
        self._session_id: Optional[str] = None
        self._jwt_token: Optional[str] = None
        self._sms_sessions: dict[str, str] = {}  # number -> session_id

    async def start(self) -> None:
        """Start voice call + SMS auto-reply — wire into GSM callbacks."""
        self.gsm.on_incoming_call = self._on_incoming_call
        self.gsm.on_call_ended = self._on_call_ended
        self.gsm.on_sms_received = self._on_sms_received
        # Get auth token for internal API
        await self._get_auth_token()
        logger.info(
            f"GSM Voice Call started (auto_answer={self.auto_answer}, "
            f"tts={self.tts_voice}, rag={self.rag_mode}, "
            f"sms_auto_reply={self.sms_auto_reply})"
        )

    async def stop(self) -> None:
        """Stop and cleanup."""
        if self._call_task and not self._call_task.done():
            self._call_task.cancel()
            try:
                await self._call_task
            except asyncio.CancelledError:
                pass
        self._close_audio_port()
        logger.info("GSM Voice Call service stopped")

    # ================================================================
    # Internal API auth
    # ================================================================

    async def _get_auth_token(self) -> None:
        """Get JWT token for internal chat API calls (with DB session)."""
        try:
            from auth_manager import create_session

            result = await create_session(
                username="admin",
                role="admin",
                user_id=1,
                ip="127.0.0.1",
                user_agent="GSMVoiceCallService",
            )
            self._jwt_token = result.access_token
            logger.info("GSM Voice Call: auth token created")
        except Exception as e:
            logger.warning(f"Could not get auth token: {e}")

    def _api_headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._jwt_token:
            h["Authorization"] = f"Bearer {self._jwt_token}"
        return h

    # ================================================================
    # Call lifecycle
    # ================================================================

    def _on_incoming_call(self, call_info) -> None:
        """Callback from GSMService when phone rings."""
        self._ring_count += 1
        logger.info(
            f"Incoming call from {call_info.caller_number} "
            f"(ring {self._ring_count}/{self.auto_answer_rings})"
        )
        if self.auto_answer and self._ring_count >= self.auto_answer_rings:
            if not self._call_task or self._call_task.done():
                self._call_task = asyncio.create_task(self._handle_call(call_info))

    def _on_call_ended(self, call_info) -> None:
        """Callback from GSMService when call ends."""
        logger.info(f"Call ended: {call_info.caller_number} ({call_info.state})")
        self._ring_count = 0
        self._is_active = False
        if self._call_task and not self._call_task.done():
            self._call_task.cancel()
        self._close_audio_port()
        self._session_id = None

    async def _handle_call(self, call_info) -> None:
        """Main call handler — answer, greet, conversation loop."""
        try:
            logger.info(f"Answering call from {call_info.caller_number}...")
            ok = await self.gsm.answer()
            if not ok:
                logger.error("Failed to answer call")
                return

            self._is_active = True
            self._ring_count = 0
            await asyncio.sleep(0.5)

            # Enable PCM audio
            if not await self._enable_pcm_audio():
                logger.error("Failed to enable PCM audio")
                await self.gsm.hangup()
                return

            await asyncio.sleep(0.3)

            # Create chat session via API (with RAG + system prompt)
            await self._create_chat_session(call_info.caller_number)

            # Play greeting
            logger.info("Playing greeting...")
            await self._speak(self.greeting)

            # Conversation loop
            await self._conversation_loop()

        except asyncio.CancelledError:
            logger.info("Call handler cancelled")
        except Exception as e:
            logger.error(f"Call handler error: {e}", exc_info=True)
        finally:
            await self._disable_pcm_audio()
            self._close_audio_port()
            self._is_active = False

    # ================================================================
    # Chat API integration (RAG + LLM + system prompt)
    # ================================================================

    async def _create_chat_session(self, caller_number: str) -> None:
        """Create a chat session for this call via internal API."""
        base = f"http://127.0.0.1:{self.orchestrator_port}"
        try:
            body: dict = {
                "title": f"GSM Call: {caller_number}",
                "system_prompt": self.system_prompt,
                "source": "gsm",
                "source_id": caller_number,
                "rag_mode": self.rag_mode,
            }
            if self.knowledge_collection_ids:
                body["knowledge_collection_ids"] = self.knowledge_collection_ids

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{base}/admin/chat/sessions",
                    json=body,
                    headers=self._api_headers(),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self._session_id = data.get("id") or data.get("session_id")
                    logger.info(f"Chat session created: {self._session_id}")
                else:
                    logger.error(f"Failed to create chat session: {resp.status_code}")
        except Exception as e:
            logger.error(f"Chat session creation error: {e}")

    async def _get_llm_response(self, user_text: str) -> Optional[str]:
        """Send user message to chat API (with RAG) and collect response."""
        if not self._session_id:
            logger.error("No chat session")
            return None

        base = f"http://127.0.0.1:{self.orchestrator_port}"
        try:
            body = {"content": user_text}
            # Override for voice: short responses
            override: dict = {
                "system_prompt": self.system_prompt,
                "llm_params": {"max_tokens": 200},
                "rag_mode": self.rag_mode,
            }
            if self.llm_backend:
                override["llm_backend"] = self.llm_backend
            body["llm_override"] = override
            if self.knowledge_collection_ids:
                body["llm_override"]["knowledge_collection_ids"] = self.knowledge_collection_ids

            full_response = []
            async with (
                httpx.AsyncClient(timeout=60) as client,
                client.stream(
                    "POST",
                    f"{base}/admin/chat/sessions/{self._session_id}/stream",
                    json=body,
                    headers=self._api_headers(),
                ) as resp,
            ):
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line[6:])
                        if data.get("type") == "chunk":
                            full_response.append(data.get("content", ""))
                        elif data.get("type") == "error":
                            logger.error(f"Chat API error: {data}")
                            break
                    except json.JSONDecodeError:
                        continue

            text = "".join(full_response).strip()
            return text if text else None

        except Exception as e:
            logger.error(f"LLM response error: {e}")
            return "Извините, произошла ошибка. Попробуйте ещё раз."

    # ================================================================
    # PCM Audio I/O via /dev/ttyUSB4
    # ================================================================

    async def _enable_pcm_audio(self) -> bool:
        """Enable PCM audio streaming on modem."""
        if not PYSERIAL_AVAILABLE:
            logger.error("pyserial not available")
            return False

        ok, lines = await self.gsm.execute_at("AT+CPCMREG=1")
        if not ok:
            logger.error(f"AT+CPCMREG=1 failed: {lines}")
            return False

        try:
            loop = asyncio.get_event_loop()
            self._audio_serial = await loop.run_in_executor(
                None,
                lambda: serial.Serial(
                    port=self.audio_port,
                    baudrate=self.audio_baud,
                    timeout=0.1,
                    write_timeout=1,
                ),
            )
            logger.info(f"PCM audio enabled on {self.audio_port}")
            return True
        except Exception as e:
            logger.error(f"Failed to open audio port: {e}")
            return False

    async def _disable_pcm_audio(self) -> None:
        try:
            ok, _ = await self.gsm.execute_at("AT+CPCMREG=0")
            if not ok:
                # May fail if call already ended — that's fine
                logger.debug("AT+CPCMREG=0 returned error (call may have ended)")
        except Exception:
            pass

    def _close_audio_port(self) -> None:
        if self._audio_serial and self._audio_serial.is_open:
            try:
                self._audio_serial.close()
            except Exception:
                pass
            self._audio_serial = None

    def _read_audio_frame(self) -> Optional[bytes]:
        """Read one PCM frame (320 bytes = 20ms). Blocking."""
        if not self._audio_serial or not self._audio_serial.is_open:
            return None
        try:
            data = self._audio_serial.read(PCM_FRAME_BYTES)
            return data if len(data) == PCM_FRAME_BYTES else None
        except Exception:
            return None

    def _write_audio_frame(self, data: bytes) -> bool:
        """Write PCM audio data to modem. Blocking."""
        if not self._audio_serial:
            logger.debug("PCM write: _audio_serial is None")
            return False
        if not self._audio_serial.is_open:
            logger.debug("PCM write: port not open")
            return False
        try:
            self._audio_serial.write(data)
            return True
        except Exception as e:
            logger.warning(f"PCM write exception: {e}")
            return False

    # ================================================================
    # Conversation loop
    # ================================================================

    async def _conversation_loop(self) -> None:
        """Listen -> STT -> Chat API (RAG+LLM) -> TTS -> Speak, repeat."""
        while self._is_active:
            user_text = await self._listen()
            if not user_text or not self._is_active:
                continue

            logger.info(f"Caller: {user_text}")

            assistant_text = await self._get_llm_response(user_text)
            if not assistant_text or not self._is_active:
                break

            logger.info(f"Assistant: {assistant_text[:100]}...")
            await self._speak(assistant_text)

    async def _listen(self) -> Optional[str]:
        """Capture audio from modem PCM, run STT, return text.

        SIM7600E-H sends PCM over UART in bursts: a few frames with real audio
        followed by many empty (all-zero) frames. We skip empty frames entirely
        and only use non-empty frames for silence vs speech detection.
        """
        if not self.stt:
            logger.error("STT service not available")
            return None

        loop = asyncio.get_event_loop()
        audio_buffer = bytearray()
        silence_start: Optional[float] = None
        speech_detected = False
        speech_start: Optional[float] = None

        while self._is_active:
            frame = await loop.run_in_executor(None, self._read_audio_frame)
            if frame is None:
                await asyncio.sleep(0.01)
                continue

            samples = np.frombuffer(frame, dtype=np.int16)
            rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
            now = time.time()

            # Skip empty UART frames (SIM7600 burst pattern)
            if rms < ZERO_FRAME_THRESHOLD:
                # Still accumulate zeros in buffer if speech was detected
                # (preserves timing for STT)
                if speech_detected:
                    audio_buffer.extend(frame)
                continue

            # Non-empty frame — evaluate for speech/silence
            if rms > SILENCE_THRESHOLD:
                if not speech_detected:
                    speech_detected = True
                    speech_start = now
                silence_start = None
                audio_buffer.extend(frame)
            elif speech_detected:
                audio_buffer.extend(frame)
                if silence_start is None:
                    silence_start = now
                elif now - silence_start >= SILENCE_DURATION_S:
                    duration = now - (speech_start or now)
                    if duration >= MIN_SPEECH_DURATION_S:
                        break
                    audio_buffer.clear()
                    speech_detected = False
                    silence_start = None

        if not audio_buffer:
            return None

        audio_bytes = bytes(audio_buffer)
        text = await loop.run_in_executor(None, self._run_stt, audio_bytes)
        return text if text and text.strip() else None

    def _run_stt(self, audio_bytes: bytes) -> Optional[str]:
        """Run Vosk STT on PCM audio bytes. Blocking."""
        try:
            chunk_size = PCM_FRAME_BYTES * 5
            texts = []

            def audio_gen():
                offset = 0
                while offset < len(audio_bytes):
                    yield audio_bytes[offset : offset + chunk_size]
                    offset += chunk_size

            recognize = getattr(self.stt, "transcribe_realtime", None) or self.stt.stream_recognize
            for result in recognize(audio_gen()):
                if result.get("type") == "final" and result.get("text"):
                    texts.append(result["text"])

            return " ".join(texts) if texts else None
        except Exception as e:
            logger.error(f"STT error: {e}")
            return None

    # ================================================================
    # TTS -> audio output
    # ================================================================

    async def _speak(self, text: str) -> None:
        """Synthesize text and play through modem PCM port."""
        loop = asyncio.get_event_loop()

        try:
            if self.tts_voice == "xtts" and self.tts_xtts:
                logger.info(f"TTS: using XTTS for '{text[:50]}...'")
                await self._speak_xtts(text, loop)
            elif self.tts_piper:
                logger.info(f"TTS: using Piper ({self.piper_voice}) for '{text[:50]}...'")
                await self._speak_piper(text, loop)
            else:
                logger.warning(
                    "No TTS service available (xtts=%s, piper=%s)", self.tts_xtts, self.tts_piper
                )
        except Exception as e:
            logger.error(f"TTS playback error: {e}", exc_info=True)

    async def _speak_xtts(self, text: str, loop: asyncio.AbstractEventLoop) -> None:
        """Stream XTTS audio to modem."""
        chunk_idx = 0
        for chunk, sr in self.tts_xtts.synthesize_streaming(
            text, target_sample_rate=PCM_SAMPLE_RATE
        ):
            if not self._is_active:
                break
            if chunk_idx == 0:
                logger.info(
                    f"XTTS: first chunk {len(chunk)} samples, sr={sr}, "
                    f"audio_port={'open' if self._audio_serial and self._audio_serial.is_open else 'CLOSED'}"
                )
            chunk_idx += 1
            await self._play_pcm_chunk(chunk, loop)
        logger.info(f"XTTS: sent {chunk_idx} chunks")

    async def _speak_piper(self, text: str, loop: asyncio.AbstractEventLoop) -> None:
        """Synthesize with Piper and play to modem."""
        audio_data, sr = await loop.run_in_executor(
            None, self.tts_piper.synthesize, text, self.piper_voice
        )
        logger.info(f"Piper: synthesized {len(audio_data)} samples at {sr}Hz")
        # Resample to 8kHz if needed
        if sr != PCM_SAMPLE_RATE:
            num_samples = int(len(audio_data) * PCM_SAMPLE_RATE / sr)
            # Use linear interpolation (no scipy dependency)
            indices = np.linspace(0, len(audio_data) - 1, num_samples)
            audio_data = np.interp(indices, np.arange(len(audio_data)), audio_data).astype(
                np.float32
            )
            logger.info(f"Piper: resampled to {num_samples} samples at {PCM_SAMPLE_RATE}Hz")

        await self._play_pcm_chunk(audio_data, loop)

    async def _play_pcm_chunk(self, audio: np.ndarray, loop: asyncio.AbstractEventLoop) -> None:
        """Convert float32 audio to int16 PCM and write to modem."""
        pcm_data = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
        total_frames = len(pcm_data) // PCM_FRAME_BYTES + 1
        frames_written = 0

        offset = 0
        while offset < len(pcm_data) and self._is_active:
            end = offset + PCM_FRAME_BYTES
            frame = pcm_data[offset:end]
            if len(frame) < PCM_FRAME_BYTES:
                frame = frame + b"\x00" * (PCM_FRAME_BYTES - len(frame))

            ok = await loop.run_in_executor(None, self._write_audio_frame, frame)
            if not ok:
                logger.warning(f"PCM write failed at frame {frames_written}/{total_frames}")
                return
            frames_written += 1
            # Pace to real-time
            await asyncio.sleep(PCM_FRAME_MS / 1000.0 * 0.9)
            offset = end

        duration = frames_written * PCM_FRAME_MS / 1000.0
        logger.info(f"PCM: played {frames_written} frames ({duration:.1f}s)")

    # ================================================================
    # SMS auto-reply
    # ================================================================

    def _on_sms_received(self, sms: dict) -> None:
        """Callback from GSM service when SMS arrives."""
        if not self.sms_auto_reply:
            return
        number = sms.get("number", "")
        text = sms.get("text", "")
        if not number or not text.strip():
            return
        logger.info(f"SMS auto-reply triggered for {number}: {text[:50]}...")
        asyncio.ensure_future(self._handle_sms_reply(number, text))

    async def _handle_sms_reply(self, number: str, text: str) -> None:
        """Get LLM response and send SMS back."""
        try:
            # Get or create chat session for this number
            session_id = self._sms_sessions.get(number)
            if not session_id:
                session_id = await self._create_sms_session(number)
                if not session_id:
                    logger.error(f"SMS: failed to create session for {number}")
                    return
                self._sms_sessions[number] = session_id

            # Get LLM response
            response = await self._get_sms_response(session_id, text)
            if not response:
                logger.warning(f"SMS: empty LLM response for {number}")
                return

            # Truncate if too long for SMS (max ~300 chars to be safe with UCS2)
            if len(response) > 300:
                response = response[:297] + "..."

            # Send reply
            logger.info(f"SMS reply to {number}: {response[:50]}...")
            success, err = await self.gsm.send_sms(number, response)
            if success:
                # Save reply to DB
                try:
                    from modules.telephony.service import gsm_service as db_service

                    await db_service.create_sms(
                        direction="outgoing",
                        number=number,
                        text=response,
                        status="sent",
                    )
                except Exception as e:
                    logger.error(f"SMS: DB save error: {e}")
            else:
                logger.error(f"SMS send failed: {err}")
        except Exception as e:
            logger.error(f"SMS auto-reply error: {e}")

    async def _create_sms_session(self, number: str) -> Optional[str]:
        """Create a chat session for SMS conversation."""
        base = f"http://127.0.0.1:{self.orchestrator_port}"
        try:
            sms_prompt = (
                self.system_prompt
                + "\nОбщение идёт через SMS. Отвечай кратко, максимум 2-3 предложения. "
                "Не используй markdown, ссылки или форматирование."
            )
            body: dict = {
                "title": f"GSM SMS: {number}",
                "system_prompt": sms_prompt,
                "source": "gsm_sms",
                "source_id": number,
                "rag_mode": self.rag_mode,
            }
            if self.knowledge_collection_ids:
                body["knowledge_collection_ids"] = self.knowledge_collection_ids

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{base}/admin/chat/sessions",
                    json=body,
                    headers=self._api_headers(),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    sid = data.get("id") or data.get("session_id")
                    logger.info(f"SMS chat session created: {sid}")
                    return sid
                else:
                    logger.error(f"SMS session creation failed: {resp.status_code}")
        except Exception as e:
            logger.error(f"SMS session creation error: {e}")
        return None

    async def _get_sms_response(self, session_id: str, user_text: str) -> Optional[str]:
        """Get LLM response for SMS via chat API."""
        base = f"http://127.0.0.1:{self.orchestrator_port}"
        try:
            override: dict = {
                "system_prompt": self.system_prompt
                + "\nОтвечай кратко — это SMS, максимум 2-3 предложения.",
                "llm_params": {"max_tokens": 150},
                "rag_mode": self.rag_mode,
            }
            if self.llm_backend:
                override["llm_backend"] = self.llm_backend
            if self.knowledge_collection_ids:
                override["knowledge_collection_ids"] = self.knowledge_collection_ids

            body = {"content": user_text, "llm_override": override}

            full_response = []
            async with (
                httpx.AsyncClient(timeout=60) as client,
                client.stream(
                    "POST",
                    f"{base}/admin/chat/sessions/{session_id}/stream",
                    json=body,
                    headers=self._api_headers(),
                ) as resp,
            ):
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line[6:])
                        if data.get("type") == "chunk":
                            full_response.append(data.get("content", ""))
                        elif data.get("type") == "error":
                            logger.error(f"SMS Chat API error: {data}")
                            break
                    except json.JSONDecodeError:
                        continue

            text = "".join(full_response).strip()
            return text if text else None
        except Exception as e:
            logger.error(f"SMS LLM response error: {e}")
            return None

    # ================================================================
    # Status
    # ================================================================

    def get_status(self) -> dict:
        return {
            "active": self._is_active,
            "auto_answer": self.auto_answer,
            "auto_answer_rings": self.auto_answer_rings,
            "tts_voice": self.tts_voice,
            "piper_voice": self.piper_voice,
            "rag_mode": self.rag_mode,
            "sms_auto_reply": self.sms_auto_reply,
            "stt_available": self.stt is not None,
            "tts_xtts_available": self.tts_xtts is not None,
            "tts_piper_available": self.tts_piper is not None,
            "audio_port": self.audio_port,
            "pcm_connected": bool(self._audio_serial and self._audio_serial.is_open),
            "session_id": self._session_id,
        }

    def get_config(self) -> dict:
        return {
            "auto_answer": self.auto_answer,
            "auto_answer_rings": self.auto_answer_rings,
            "greeting": self.greeting,
            "system_prompt": self.system_prompt,
            "tts_voice": self.tts_voice,
            "piper_voice": self.piper_voice,
            "rag_mode": self.rag_mode,
            "knowledge_collection_ids": self.knowledge_collection_ids,
            "llm_backend": self.llm_backend,
            "sms_auto_reply": self.sms_auto_reply,
            "stt_available": self.stt is not None,
            "tts_xtts_available": self.tts_xtts is not None,
            "tts_piper_available": self.tts_piper is not None,
        }

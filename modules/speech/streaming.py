"""
StreamingTTSManager — параллельный синтез TTS во время streaming LLM.

Архитектура:
1. Во время streaming chat/completions — накапливаем текст и при завершении
   предложения запускаем синтез в фоновом потоке
2. Храним синтезированные сегменты в кэше по хэшу полного текста
3. При запросе /v1/audio/speech — склеиваем готовые сегменты
"""

import hashlib
import logging
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional


logger = logging.getLogger(__name__)


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
        self._sentence_pattern = re.compile(r"([^.!?]*[.!?]+)")

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
                            self._synthesize_segment, sentence, voice_service, session_id
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
                split_sentences=False,  # Уже разбили
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
                    self._synthesize_segment, remaining, voice_service, session_id
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
            logger.info(
                f"✅ Сессия {session_id} завершена за {elapsed:.2f}s, "
                f"сегментов: {len(session['segments'])}"
            )

            # Удаляем сессию
            del self._active_sessions[session_id]

    def _cache_full_audio(self, full_text: str, segments: list) -> None:
        """Склеивает сегменты и кэширует полное аудио"""
        if not segments:
            return

        import numpy as np

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
                logger.info(
                    f"💾 Закэшировано аудио: {text_hash} ({len(full_audio) / sample_rate:.2f}s)"
                )

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

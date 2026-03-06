#!/usr/bin/env python3
"""
Сервис распознавания речи на базе Whisper и Vosk

Whisper - высокое качество, batch processing
Vosk - realtime streaming, низкие ресурсы, офлайн
"""

import json
import logging
import tempfile
import wave
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Generator, Optional, Union

import numpy as np


try:
    import torch
except ImportError:
    torch = None  # type: ignore[assignment]


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Base STT Interface
# ============================================================================


class BaseSTTService(ABC):
    """Базовый интерфейс для STT сервисов"""

    @abstractmethod
    def transcribe(self, audio_path: Union[str, Path], language: str = "ru") -> dict:
        """Распознать речь из файла"""
        pass

    @abstractmethod
    def transcribe_audio_data(
        self, audio_data: np.ndarray, sample_rate: int = 16000, language: str = "ru"
    ) -> dict:
        """Распознать речь из numpy array"""
        pass


# ============================================================================
# Vosk STT Service (Realtime, Offline, Low Resource)
# ============================================================================


class VoskSTTService(BaseSTTService):
    """
    STT сервис на базе Vosk

    Преимущества:
    - Realtime streaming распознавание
    - Полностью офлайн
    - Низкие требования к ресурсам (~50-100MB RAM)
    - Хорош для телефонии

    Модели:
    - vosk-model-ru-0.42 (~1.5GB, высокое качество)
    - vosk-model-small-ru-0.22 (~45MB, среднее качество)
    - vosk-model-en-us-0.22 (~1.8GB, английский)
    """

    MODELS_DIR = Path("models/vosk")

    # Известные модели с URLs
    KNOWN_MODELS = {
        "ru": {
            "large": "vosk-model-ru-0.42",
            "small": "vosk-model-small-ru-0.22",
        },
        "en": {
            "large": "vosk-model-en-us-0.22",
            "small": "vosk-model-small-en-us-0.15",
        },
    }

    def __init__(
        self,
        model_path: Optional[Union[str, Path]] = None,
        language: str = "ru",
        model_size: str = "small",
        sample_rate: int = 16000,
    ):
        """
        Инициализация Vosk STT

        Args:
            model_path: Путь к модели (если None, автоопределение)
            language: Язык (ru, en)
            model_size: Размер модели (small, large)
            sample_rate: Частота дискретизации (16000 для телефонии)
        """
        try:
            from vosk import KaldiRecognizer, Model, SetLogLevel

            SetLogLevel(-1)  # Отключить логи Vosk
        except ImportError:
            raise ImportError("Vosk не установлен. Установите: pip install vosk")

        self.sample_rate = sample_rate
        self.language = language

        # Определяем путь к модели
        if model_path:
            self.model_path = Path(model_path)
        else:
            self.model_path = self._find_model(language, model_size)

        if not self.model_path or not self.model_path.exists():
            raise FileNotFoundError(
                f"Модель Vosk не найдена. Скачайте модель в {self.MODELS_DIR}/\n"
                f"Например: vosk-model-small-ru-0.22 с https://alphacephei.com/vosk/models"
            )

        logger.info(f"🎧 Загрузка Vosk модели: {self.model_path}")
        self.model = Model(str(self.model_path))
        self.recognizer = KaldiRecognizer(self.model, sample_rate)
        self.recognizer.SetWords(True)  # Включить timestamps для слов

        logger.info(f"✅ Vosk STT инициализирован ({language}, {sample_rate}Hz)")

    def _find_model(self, language: str, size: str) -> Optional[Path]:
        """Найти модель в директории моделей"""
        self.MODELS_DIR.mkdir(parents=True, exist_ok=True)

        # Ищем известную модель
        if language in self.KNOWN_MODELS and size in self.KNOWN_MODELS[language]:
            model_name = self.KNOWN_MODELS[language][size]
            model_path = self.MODELS_DIR / model_name
            if model_path.exists():
                return model_path

        # Ищем любую модель для языка
        for path in self.MODELS_DIR.iterdir():
            if path.is_dir() and language in path.name.lower():
                return path

        return None

    def transcribe(self, audio_path: Union[str, Path], language: str = "ru") -> dict:
        """
        Распознать речь из аудио файла

        Args:
            audio_path: Путь к WAV файлу (16kHz, mono)
            language: Язык (игнорируется, определяется моделью)

        Returns:
            dict: {"text": str, "words": list, "confidence": float}
        """
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise FileNotFoundError(f"Файл не найден: {audio_path}")

        logger.info(f"🎤 Vosk распознавание: {audio_path}")

        # Сбрасываем recognizer
        self.recognizer.Reset()

        with wave.open(str(audio_path), "rb") as wf:
            if wf.getnchannels() != 1:
                raise ValueError("Требуется mono аудио")
            if wf.getsampwidth() != 2:
                raise ValueError("Требуется 16-bit аудио")
            if wf.getframerate() != self.sample_rate:
                logger.warning(
                    f"Sample rate {wf.getframerate()} != {self.sample_rate}, может снизить качество"
                )

            results = []
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    if result.get("text"):
                        results.append(result)

            # Финальный результат
            final = json.loads(self.recognizer.FinalResult())
            if final.get("text"):
                results.append(final)

        # Объединяем результаты
        full_text = " ".join(r.get("text", "") for r in results).strip()
        all_words = []
        for r in results:
            all_words.extend(r.get("result", []))

        result = {
            "text": full_text,
            "language": self.language,
            "words": all_words,
            "segments": [
                {"text": r.get("text", ""), "words": r.get("result", [])} for r in results
            ],
        }

        logger.info(f"✅ Распознано: '{full_text[:100]}...' ({len(all_words)} слов)")
        return result

    def transcribe_audio_data(
        self, audio_data: np.ndarray, sample_rate: int = 16000, language: str = "ru"
    ) -> dict:
        """Распознать речь из numpy array"""
        import soundfile as sf

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            # Конвертируем в int16 если нужно
            if audio_data.dtype != np.int16:
                audio_data = (audio_data * 32767).astype(np.int16)
            sf.write(tmp.name, audio_data, sample_rate, subtype="PCM_16")
            result = self.transcribe(tmp.name, language)

        Path(tmp.name).unlink()
        return result

    def stream_recognize(
        self,
        audio_chunks: Generator[bytes, None, None],
        on_partial: Optional[Callable[[str], None]] = None,
        on_final: Optional[Callable[[dict], None]] = None,
    ) -> Generator[dict, None, None]:
        """
        Streaming распознавание (для телефонии)

        Args:
            audio_chunks: Генератор чанков аудио (PCM 16-bit)
            on_partial: Callback для частичных результатов
            on_final: Callback для финальных результатов

        Yields:
            dict с результатами распознавания
        """
        self.recognizer.Reset()

        for chunk in audio_chunks:
            if self.recognizer.AcceptWaveform(chunk):
                result = json.loads(self.recognizer.Result())
                if result.get("text"):
                    if on_final:
                        on_final(result)
                    yield {"type": "final", **result}
            else:
                partial = json.loads(self.recognizer.PartialResult())
                if partial.get("partial"):
                    if on_partial:
                        on_partial(partial["partial"])
                    yield {"type": "partial", "text": partial["partial"]}

        # Финальный результат
        final = json.loads(self.recognizer.FinalResult())
        if final.get("text"):
            if on_final:
                on_final(final)
            yield {"type": "final", **final}

    def recognize_microphone(
        self, duration: float = 5.0, on_partial: Optional[Callable[[str], None]] = None
    ) -> dict:
        """
        Распознать речь с микрофона

        Args:
            duration: Длительность записи в секундах
            on_partial: Callback для частичных результатов

        Returns:
            dict с распознанным текстом
        """
        try:
            import sounddevice as sd
        except ImportError:
            raise ImportError("sounddevice не установлен. Установите: pip install sounddevice")

        logger.info(f"🎙️ Запись с микрофона ({duration}s)...")

        self.recognizer.Reset()
        results = []

        def audio_callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"Audio status: {status}")
            # Конвертируем в bytes
            audio_bytes = (indata[:, 0] * 32767).astype(np.int16).tobytes()

            if self.recognizer.AcceptWaveform(audio_bytes):
                result = json.loads(self.recognizer.Result())
                if result.get("text"):
                    results.append(result)
            else:
                partial = json.loads(self.recognizer.PartialResult())
                if partial.get("partial") and on_partial:
                    on_partial(partial["partial"])

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=4000,
            callback=audio_callback,
        ):
            sd.sleep(int(duration * 1000))

        # Финальный результат
        final = json.loads(self.recognizer.FinalResult())
        if final.get("text"):
            results.append(final)

        full_text = " ".join(r.get("text", "") for r in results).strip()

        return {"text": full_text, "language": self.language, "segments": results}


# ============================================================================
# Whisper STT Service (High Quality, Batch Processing)
# ============================================================================


class WhisperSTTService(BaseSTTService):
    """
    STT сервис на базе Whisper

    Преимущества:
    - Высокое качество распознавания
    - Поддержка множества языков
    - GPU ускорение

    Недостатки:
    - Требует GPU для комфортной работы
    - Не подходит для realtime (batch processing)
    """

    def __init__(
        self, model_size: str = "medium", use_faster_whisper: bool = True, device: str = "auto"
    ):
        """
        Инициализация сервиса распознавания речи

        Args:
            model_size: Размер модели (tiny, base, small, medium, large)
            use_faster_whisper: Использовать faster-whisper (быстрее)
            device: Устройство (auto, cuda, cpu)
        """
        self.model_size = model_size
        self.use_faster_whisper = use_faster_whisper

        if device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        logger.info(f"🎧 Инициализация Whisper STT на {self.device}")
        logger.info(f"📊 Модель: {model_size}")

        try:
            if use_faster_whisper:
                from faster_whisper import WhisperModel

                # Faster Whisper - оптимизированная версия
                self.model = WhisperModel(
                    model_size,
                    device=self.device,
                    compute_type="float16" if self.device == "cuda" else "int8",
                )
                logger.info("✅ Faster Whisper загружена")
            else:
                import whisper

                # Оригинальный Whisper
                self.model = whisper.load_model(model_size, device=self.device)
                logger.info("✅ OpenAI Whisper загружена")

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки модели: {e}")
            raise

    def transcribe(self, audio_path: Union[str, Path], language: str = "ru") -> dict:
        """
        Распознает речь из аудио файла

        Args:
            audio_path: Путь к аудио файлу
            language: Язык речи

        Returns:
            dict с полями: text, language, segments
        """
        logger.info(f"🎤 Распознавание: {audio_path}")

        try:
            if self.use_faster_whisper:
                segments, info = self.model.transcribe(
                    str(audio_path),
                    language=language,
                    vad_filter=True,  # Voice Activity Detection
                    vad_parameters=dict(min_silence_duration_ms=500),
                )

                # Собираем текст из сегментов
                text_segments = []
                for segment in segments:
                    text_segments.append(
                        {"start": segment.start, "end": segment.end, "text": segment.text.strip()}
                    )

                full_text = " ".join([s["text"] for s in text_segments])

                result = {"text": full_text, "language": info.language, "segments": text_segments}

            else:
                result_whisper = self.model.transcribe(
                    str(audio_path), language=language, fp16=(self.device == "cuda")
                )

                result = {
                    "text": result_whisper["text"].strip(),
                    "language": result_whisper["language"],
                    "segments": result_whisper.get("segments", []),
                }

            logger.info(f"✅ Распознано: '{result['text'][:100]}...'")
            return result

        except Exception as e:
            logger.error(f"❌ Ошибка распознавания: {e}")
            raise

    def transcribe_audio_data(
        self, audio_data: np.ndarray, sample_rate: int = 16000, language: str = "ru"
    ) -> dict:
        """
        Распознает речь из numpy array

        Args:
            audio_data: Аудио данные
            sample_rate: Частота дискретизации
            language: Язык

        Returns:
            dict с распознанным текстом
        """
        import tempfile

        import soundfile as sf

        # Сохраняем во временный файл
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            sf.write(tmp.name, audio_data, sample_rate)
            result = self.transcribe(tmp.name, language)

        Path(tmp.name).unlink()  # Удаляем временный файл
        return result


# Алиас для обратной совместимости
STTService = WhisperSTTService


# ============================================================================
# Unified STT Manager (автовыбор движка)
# ============================================================================


class UnifiedSTTService:
    """
    Унифицированный STT сервис с автовыбором движка

    Использует Vosk для realtime (телефония) и Whisper для batch (высокое качество)
    """

    def __init__(
        self,
        vosk_model_path: Optional[Union[str, Path]] = None,
        whisper_model_size: str = "base",
        prefer_vosk: bool = True,
        language: str = "ru",
    ):
        """
        Args:
            vosk_model_path: Путь к модели Vosk
            whisper_model_size: Размер модели Whisper
            prefer_vosk: Предпочитать Vosk если доступен
            language: Язык
        """
        self.language = language
        self.vosk_service: Optional[VoskSTTService] = None
        self.whisper_service: Optional[WhisperSTTService] = None
        self.prefer_vosk = prefer_vosk

        # Пробуем инициализировать Vosk
        try:
            self.vosk_service = VoskSTTService(model_path=vosk_model_path, language=language)
            logger.info("✅ Vosk STT доступен")
        except Exception as e:
            logger.warning(f"⚠️ Vosk STT недоступен: {e}")

        # Пробуем инициализировать Whisper (ленивая загрузка)
        self._whisper_model_size = whisper_model_size
        self._whisper_initialized = False

    def _init_whisper(self):
        """Ленивая инициализация Whisper"""
        if not self._whisper_initialized:
            try:
                self.whisper_service = WhisperSTTService(
                    model_size=self._whisper_model_size, use_faster_whisper=True
                )
                logger.info("✅ Whisper STT доступен")
            except Exception as e:
                logger.warning(f"⚠️ Whisper STT недоступен: {e}")
            self._whisper_initialized = True

    def transcribe(
        self, audio_path: Union[str, Path], language: str = "ru", use_whisper: bool = False
    ) -> dict:
        """
        Распознать речь из файла

        Args:
            audio_path: Путь к аудио
            language: Язык
            use_whisper: Принудительно использовать Whisper

        Returns:
            dict с результатом
        """
        if use_whisper or (not self.vosk_service and not self.prefer_vosk):
            self._init_whisper()
            if self.whisper_service:
                return self.whisper_service.transcribe(audio_path, language)

        if self.vosk_service:
            return self.vosk_service.transcribe(audio_path, language)

        raise RuntimeError("Нет доступных STT сервисов")

    def transcribe_realtime(
        self,
        audio_chunks: Generator[bytes, None, None],
        on_partial: Optional[Callable[[str], None]] = None,
    ) -> Generator[dict, None, None]:
        """Realtime распознавание (только Vosk)"""
        if not self.vosk_service:
            raise RuntimeError("Vosk не доступен для realtime распознавания")

        yield from self.vosk_service.stream_recognize(audio_chunks, on_partial=on_partial)

    def get_available_engines(self) -> list:
        """Список доступных движков"""
        engines = []
        if self.vosk_service:
            engines.append("vosk")
        self._init_whisper()
        if self.whisper_service:
            engines.append("whisper")
        return engines


if __name__ == "__main__":
    print("=" * 60)
    print("STT Service Test")
    print("=" * 60)

    # Тест Vosk
    print("\n📍 Тест Vosk STT:")
    try:
        vosk = VoskSTTService(language="ru", model_size="small")
        print(f"   Модель: {vosk.model_path}")
        print("   ✅ Vosk готов к работе")

        # Тест с микрофона (если есть sounddevice)
        try:
            import sounddevice  # noqa: F401 - check if available

            print("\n🎙️ Говорите 3 секунды...")
            result = vosk.recognize_microphone(
                duration=3.0, on_partial=lambda t: print(f"   ... {t}")
            )
            print(f"   📝 Результат: {result['text']}")
        except ImportError:
            print("   ⚠️ sounddevice не установлен, пропуск теста микрофона")

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")

    # Тест Whisper
    print("\n📍 Тест Whisper STT:")
    try:
        whisper_stt = WhisperSTTService(model_size="base", use_faster_whisper=True)
        print("   ✅ Whisper готов к работе")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")

    print("\n" + "=" * 60)

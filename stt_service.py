#!/usr/bin/env python3
"""
Сервис распознавания речи на базе Whisper
"""
import torch
import whisper
from faster_whisper import WhisperModel
import logging
from pathlib import Path
from typing import Optional, Union
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class STTService:
    def __init__(
        self,
        model_size: str = "medium",
        use_faster_whisper: bool = True,
        device: str = "auto"
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

        logger.info(f"🎧 Инициализация STT Service на {self.device}")
        logger.info(f"📊 Модель: {model_size}")

        try:
            if use_faster_whisper:
                # Faster Whisper - оптимизированная версия
                self.model = WhisperModel(
                    model_size,
                    device=self.device,
                    compute_type="float16" if self.device == "cuda" else "int8"
                )
                logger.info("✅ Faster Whisper загружена")
            else:
                # Оригинальный Whisper
                self.model = whisper.load_model(model_size, device=self.device)
                logger.info("✅ OpenAI Whisper загружена")

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки модели: {e}")
            raise

    def transcribe(
        self,
        audio_path: Union[str, Path],
        language: str = "ru"
    ) -> dict:
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
                    vad_parameters=dict(min_silence_duration_ms=500)
                )

                # Собираем текст из сегментов
                text_segments = []
                for segment in segments:
                    text_segments.append({
                        "start": segment.start,
                        "end": segment.end,
                        "text": segment.text.strip()
                    })

                full_text = " ".join([s["text"] for s in text_segments])

                result = {
                    "text": full_text,
                    "language": info.language,
                    "segments": text_segments
                }

            else:
                result_whisper = self.model.transcribe(
                    str(audio_path),
                    language=language,
                    fp16=(self.device == "cuda")
                )

                result = {
                    "text": result_whisper["text"].strip(),
                    "language": result_whisper["language"],
                    "segments": result_whisper.get("segments", [])
                }

            logger.info(f"✅ Распознано: '{result['text'][:100]}...'")
            return result

        except Exception as e:
            logger.error(f"❌ Ошибка распознавания: {e}")
            raise

    def transcribe_audio_data(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
        language: str = "ru"
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


if __name__ == "__main__":
    # Тестирование
    service = STTService(model_size="base", use_faster_whisper=True)

    # Пример использования
    # result = service.transcribe("test_audio.wav")
    # print(f"Распознанный текст: {result['text']}")

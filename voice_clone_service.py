#!/usr/bin/env python3
"""
Сервис клонирования голоса на базе XTTS v2
Использует образцы голоса из папки Лидия для синтеза речи
"""
import os
import torch
from TTS.api import TTS
from pathlib import Path
import soundfile as sf
import numpy as np
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VoiceCloneService:
    def __init__(self, voice_samples_dir: str = "./Лидия", model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2"):
        """
        Инициализация сервиса клонирования голоса

        Args:
            voice_samples_dir: Путь к папке с образцами голоса
            model_name: Название модели TTS
        """
        self.voice_samples_dir = Path(voice_samples_dir)
        self.model_name = model_name
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info(f"🎤 Инициализация Voice Clone Service на {self.device}")
        logger.info(f"📁 Папка с образцами: {self.voice_samples_dir}")

        # Загружаем модель XTTS v2
        try:
            self.tts = TTS(model_name=self.model_name).to(self.device)
            logger.info("✅ XTTS v2 загружена успешно")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки модели: {e}")
            raise

        # Получаем список образцов голоса
        self.voice_samples = self._get_voice_samples()
        if not self.voice_samples:
            logger.warning("⚠️  Не найдены образцы голоса в папке")
        else:
            logger.info(f"📊 Найдено образцов голоса: {len(self.voice_samples)}")

    def _get_voice_samples(self) -> list[Path]:
        """Получает список WAV файлов из папки с образцами"""
        if not self.voice_samples_dir.exists():
            logger.error(f"❌ Папка не найдена: {self.voice_samples_dir}")
            return []

        samples = list(self.voice_samples_dir.glob("*.wav"))
        return samples[:3]  # Используем первые 3 образца для качества

    def synthesize(
        self,
        text: str,
        output_path: Optional[str] = None,
        language: str = "ru"
    ) -> tuple[np.ndarray, int]:
        """
        Синтезирует речь с клонированным голосом

        Args:
            text: Текст для синтеза
            output_path: Путь для сохранения (опционально)
            language: Язык синтеза

        Returns:
            Tuple (audio_data, sample_rate)
        """
        if not self.voice_samples:
            raise ValueError("Нет доступных образцов голоса")

        logger.info(f"🎙️  Синтез: '{text[:50]}...'")

        try:
            # Используем первый образец как референс
            speaker_wav = str(self.voice_samples[0])

            # Генерируем аудио
            wav = self.tts.tts(
                text=text,
                speaker_wav=speaker_wav,
                language=language
            )

            # Конвертируем в numpy array
            if isinstance(wav, list):
                wav = np.array(wav, dtype=np.float32)

            # Сохраняем если указан путь
            if output_path:
                sf.write(output_path, wav, self.tts.synthesizer.output_sample_rate)
                logger.info(f"💾 Сохранено: {output_path}")

            return wav, self.tts.synthesizer.output_sample_rate

        except Exception as e:
            logger.error(f"❌ Ошибка синтеза: {e}")
            raise

    def synthesize_to_file(self, text: str, output_path: str, language: str = "ru"):
        """Синтезирует и сохраняет в файл"""
        self.synthesize(text, output_path, language)
        return output_path


if __name__ == "__main__":
    # Тестирование
    service = VoiceCloneService()

    test_text = "Здравствуйте, это виртуальный секретарь. Чем могу помочь?"
    output = "test_lidia_voice.wav"

    service.synthesize_to_file(test_text, output)
    print(f"✅ Тест завершен. Файл: {output}")

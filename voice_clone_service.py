#!/usr/bin/env python3
"""
Сервис клонирования голоса на базе XTTS v2 (coqui-tts fork 2026)
"""
import torch  # noqa: F401 - используется TTS под капотом
from TTS.api import TTS
from pathlib import Path
import soundfile as sf
import numpy as np
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VoiceCloneService:
    def __init__(
        self,
        voice_samples_dir: str = "./Лидия",
        model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    ):
        self.voice_samples_dir = Path(voice_samples_dir)
        self.model_name = model_name
        # Принудительно CPU, т.к. P104-100 не поддерживается новым PyTorch
        self.device = "cpu"

        logger.info(f"🎤 Инициализация на {self.device}")
        logger.info(f"📁 Образцы: {self.voice_samples_dir}")

        try:
            self.tts = TTS(
                model_name=self.model_name,
                gpu=(self.device == "cuda"),
                progress_bar=True
            )
            logger.info("✅ XTTS v2 загружена")
        except Exception as e:
            logger.error(f"❌ Ошибка модели: {e}")
            raise

        self.voice_samples = self._get_voice_samples()
        if not self.voice_samples:
            logger.warning("⚠️ Образцы голоса не найдены")
        else:
            logger.info(f"📊 Образцов: {len(self.voice_samples)}")

    def _get_voice_samples(self) -> list[Path]:
        if not self.voice_samples_dir.exists():
            logger.error(f"❌ Папка не найдена: {self.voice_samples_dir}")
            return []
        return list(self.voice_samples_dir.glob("*.wav"))[:3]

    def synthesize(
        self,
        text: str,
        output_path: Optional[str] = None,
        language: str = "ru"
    ) -> tuple[np.ndarray, int]:
        if not self.voice_samples:
            raise ValueError("Нет образцов голоса")

        logger.info(f"🎙️ Синтез: '{text[:50]}...'")

        try:
            speaker_wav = str(self.voice_samples[0])

            wav = self.tts.tts(
                text=text,
                speaker_wav=speaker_wav,
                language=language,
                split_sentences=True
            )

            if isinstance(wav, list):
                wav = np.array(wav, dtype=np.float32)

            sample_rate = self.tts.synthesizer.output_sample_rate

            if output_path:
                sf.write(output_path, wav, sample_rate)
                logger.info(f"💾 Сохранено: {output_path}")

            return wav, sample_rate

        except Exception as e:
            logger.error(f"❌ Ошибка синтеза: {e}")
            raise

    def synthesize_to_file(self, text: str, output_path: str, language: str = "ru"):
        self.synthesize(text, output_path, language)
        return output_path


if __name__ == "__main__":
    service = VoiceCloneService()
    test_text = "Привет , Лидочка, это я. Узнаешь мой голос??? По-моему очень похоже..."
    output = "test_lidia_2026.wav"
    service.synthesize_to_file(test_text, output)
    print(f"✅ Готово. Файл: {output}")
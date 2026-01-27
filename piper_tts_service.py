#!/usr/bin/env python3
"""
Сервис TTS на базе Piper (ONNX модели)
Поддерживает модели: dmitri, irina
"""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import soundfile as sf


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PiperTTSService:
    """
    TTS сервис на базе Piper с предобученными ONNX моделями.
    Быстрее XTTS, но без клонирования голоса.
    """

    # Доступные голоса
    VOICES = {
        "dmitri": {
            "model": "ru_RU-dmitri-medium.onnx",
            "name": "Дмитрий",
            "description": "Мужской голос, средний",
        },
        "irina": {
            "model": "ru_RU-irina-medium.onnx",
            "name": "Ирина",
            "description": "Женский голос, средний",
        },
    }

    def __init__(
        self,
        models_dir: str = "./models",
        piper_path: Optional[str] = None,
        default_voice: str = "dmitri",
    ):
        self.models_dir = Path(models_dir)
        self.default_voice = default_voice

        # Ищем piper binary
        self.piper_path = self._find_piper(piper_path)
        if not self.piper_path:
            raise RuntimeError("Piper binary не найден. Укажите путь через piper_path")

        # Проверяем наличие моделей
        self._check_models()

        logger.info("🎤 PiperTTSService инициализирован")
        logger.info(f"   Piper: {self.piper_path}")
        logger.info(f"   Модели: {self.models_dir}")
        logger.info(f"   Голос по умолчанию: {default_voice}")

    def _find_piper(self, piper_path: Optional[str]) -> Optional[str]:
        """Ищет piper binary"""
        if piper_path and Path(piper_path).exists():
            return piper_path

        # Стандартные места
        search_paths = [
            "/home/shaerware/voice-tts/venv/bin/piper",
            "./piper/piper",
            "/usr/local/bin/piper",
            "/usr/bin/piper",
        ]

        # Также проверяем через which
        which_result = shutil.which("piper")
        if which_result:
            search_paths.insert(0, which_result)

        for path in search_paths:
            if Path(path).exists():
                logger.info(f"✅ Найден Piper: {path}")
                return path

        return None

    def _check_models(self):
        """Проверяет наличие ONNX моделей"""
        for voice_id, info in self.VOICES.items():
            model_path = self.models_dir / info["model"]
            if model_path.exists():
                logger.info(f"✅ Модель {voice_id}: {model_path}")
            else:
                logger.warning(f"⚠️ Модель не найдена: {model_path}")

    def get_available_voices(self) -> dict:
        """Возвращает список доступных голосов"""
        available = {}
        for voice_id, info in self.VOICES.items():
            model_path = self.models_dir / info["model"]
            available[voice_id] = {**info, "available": model_path.exists(), "engine": "piper"}
        return available

    def synthesize(
        self, text: str, voice: Optional[str] = None, speed: float = 1.0
    ) -> Tuple[np.ndarray, int]:
        """
        Синтезирует речь из текста.

        Args:
            text: Текст для синтеза
            voice: ID голоса (dmitri, irina)
            speed: Скорость речи (0.5-2.0)

        Returns:
            (wav_array, sample_rate)
        """
        voice = voice or self.default_voice
        if voice not in self.VOICES:
            raise ValueError(f"Неизвестный голос: {voice}. Доступны: {list(self.VOICES.keys())}")

        model_path = self.models_dir / self.VOICES[voice]["model"]
        if not model_path.exists():
            raise FileNotFoundError(f"Модель не найдена: {model_path}")

        logger.info(f"🎙️ Piper синтез: голос={voice}, текст='{text[:50]}...'")

        # Создаём временный файл для вывода
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            output_path = tmp.name

        try:
            # Запускаем piper
            cmd = [
                self.piper_path,
                "--model",
                str(model_path),
                "--output_file",
                output_path,
            ]

            # Добавляем скорость если не 1.0
            if speed != 1.0:
                cmd.extend(["--length_scale", str(1.0 / speed)])

            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = proc.communicate(input=text.encode("utf-8"), timeout=30)

            if proc.returncode != 0:
                logger.error(f"❌ Piper error: {stderr.decode()}")
                raise RuntimeError(f"Piper failed: {stderr.decode()}")

            # Читаем результат
            wav, sr = sf.read(output_path)
            logger.info(f"✅ Синтезировано: {len(wav) / sr:.2f} сек")

            return wav.astype(np.float32), sr

        finally:
            # Удаляем временный файл
            Path(output_path).unlink(missing_ok=True)

    def synthesize_to_file(
        self, text: str, output_path: str, voice: Optional[str] = None, speed: float = 1.0
    ) -> str:
        """Синтезирует и сохраняет в файл"""
        wav, sr = self.synthesize(text, voice, speed)
        sf.write(output_path, wav, sr)
        logger.info(f"💾 Сохранено: {output_path}")
        return output_path


# Тестирование
if __name__ == "__main__":
    try:
        service = PiperTTSService()

        print("\n=== Доступные голоса ===")
        for voice_id, info in service.get_available_voices().items():
            status = "✅" if info["available"] else "❌"
            print(f"  {status} {voice_id}: {info['name']} - {info['description']}")

        print("\n=== Тест синтеза ===")
        for voice in ["dmitri", "irina"]:
            try:
                output = f"test_piper_{voice}.wav"
                service.synthesize_to_file(
                    "Здравствуйте! Это тестовое сообщение голосового синтеза.", output, voice=voice
                )
                print(f"  ✅ {voice}: {output}")
            except Exception as e:
                print(f"  ❌ {voice}: {e}")

    except Exception as e:
        print(f"Ошибка: {e}")

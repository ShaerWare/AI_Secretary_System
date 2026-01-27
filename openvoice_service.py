#!/usr/bin/env python3
"""
OpenVoice v2 TTS Service with Voice Cloning
Запускается на GPU 0 (P104-100, 8GB, CC 6.1)

Совместим с API voice_clone_service.py для интеграции с orchestrator.py
"""

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import numpy as np
import soundfile as sf
import torch
import uvicorn

# FastAPI для HTTP сервиса
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============== Конфигурация ==============
OPENVOICE_PORT = int(os.getenv("OPENVOICE_PORT", "8003"))
VOICE_SAMPLES_DIR = os.getenv("VOICE_SAMPLES_DIR", "./Лидия")
CHECKPOINTS_DIR = os.getenv("OPENVOICE_CHECKPOINTS", "./checkpoints_v2")


def get_gpu_for_openvoice() -> tuple[str, Optional[int]]:
    """
    Определяет GPU для OpenVoice.
    Предпочитает GPU 0 (P104-100) если доступен.
    OpenVoice работает на CC 6.1 (в отличие от XTTS).
    """
    if not torch.cuda.is_available():
        logger.warning("CUDA недоступна, используется CPU")
        return "cpu", None

    # Проверяем GPU 0 (P104-100)
    target_gpu = 0
    if torch.cuda.device_count() > target_gpu:
        name = torch.cuda.get_device_name(target_gpu)
        cap = torch.cuda.get_device_capability(target_gpu)
        mem = torch.cuda.get_device_properties(target_gpu).total_memory / (1024**3)
        logger.info(f"GPU {target_gpu}: {name} (CC {cap[0]}.{cap[1]}, {mem:.1f} GB)")
        return f"cuda:{target_gpu}", target_gpu

    logger.warning("GPU 0 недоступен, используется CPU")
    return "cpu", None


@dataclass
class IntonationPreset:
    """Пресет настроек интонации (совместимость с XTTS API)"""

    name: str
    speed: float  # 0.5-2.0: скорость речи


# Пресеты интонаций (упрощённые для OpenVoice)
INTONATION_PRESETS = {
    "neutral": IntonationPreset(name="Нейтральный", speed=1.0),
    "warm": IntonationPreset(name="Тёплый", speed=0.95),
    "energetic": IntonationPreset(name="Энергичный", speed=1.1),
    "calm": IntonationPreset(name="Спокойный", speed=0.9),
    "natural": IntonationPreset(name="Естественный", speed=0.98),
}


class OpenVoiceService:
    """
    Сервис синтеза речи на базе OpenVoice v2.

    Архитектура OpenVoice:
    1. MeloTTS генерирует базовую речь (любой акцент)
    2. ToneColorConverter клонирует тембр из reference audio

    Особенности:
    - Работает на GPU с CC 6.1 (P104-100)
    - Zero-shot voice cloning
    - Поддержка русского через cross-lingual cloning
    """

    def __init__(
        self,
        voice_samples_dir: str = VOICE_SAMPLES_DIR,
        checkpoints_dir: str = CHECKPOINTS_DIR,
        default_preset: str = "natural",
        force_cpu: bool = False,
    ):
        self.voice_samples_dir = Path(voice_samples_dir)
        self.checkpoints_dir = Path(checkpoints_dir)
        self.default_preset = default_preset

        # Определяем устройство
        if force_cpu:
            self.device = "cpu"
            self.gpu_index = None
        else:
            self.device, self.gpu_index = get_gpu_for_openvoice()

        logger.info("OpenVoice Service инициализация")
        logger.info(f"Устройство: {self.device}")
        logger.info(f"Папка образцов: {self.voice_samples_dir}")
        logger.info(f"Checkpoints: {self.checkpoints_dir}")

        # Импортируем OpenVoice компоненты
        try:
            from melo.api import TTS as MeloTTS
            from openvoice import se_extractor
            from openvoice.api import ToneColorConverter

            self.se_extractor = se_extractor

            # Загружаем ToneColorConverter
            converter_ckpt = self.checkpoints_dir / "converter"
            if not converter_ckpt.exists():
                raise FileNotFoundError(
                    f"Checkpoints не найдены: {converter_ckpt}\n"
                    "Скачайте с https://huggingface.co/myshell-ai/OpenVoiceV2"
                )

            self.tone_converter = ToneColorConverter(
                f"{converter_ckpt}/config.json", device=self.device
            )
            self.tone_converter.load_ckpt(f"{converter_ckpt}/checkpoint.pth")
            logger.info("ToneColorConverter загружен")

            # Загружаем MeloTTS для базового синтеза
            # Используем английский как базу (лучшее качество),
            # затем клонируем тембр
            self.melo_tts = MeloTTS(language="EN", device=self.device)
            self.melo_speaker_ids = self.melo_tts.hps.data.spk2id
            logger.info(f"MeloTTS загружен. Speakers: {list(self.melo_speaker_ids.keys())}")

        except ImportError as e:
            logger.error(f"OpenVoice не установлен: {e}")
            logger.error("Установите: pip install -e OpenVoice/")
            raise
        except Exception as e:
            logger.error(f"Ошибка загрузки моделей: {e}")
            raise

        # Загружаем образцы голоса
        self.voice_samples = self._get_voice_samples()
        if not self.voice_samples:
            logger.warning("Образцы голоса не найдены!")
        else:
            logger.info(f"Найдено образцов: {len(self.voice_samples)}")

        # Извлекаем speaker embedding из reference audio
        self._target_se = None
        self._source_se = None
        self._extract_speaker_embeddings()

        logger.info("OpenVoice Service готов к работе")

    def _get_voice_samples(self) -> list[Path]:
        """Получает образцы голоса из папки"""
        if not self.voice_samples_dir.exists():
            logger.error(f"Папка не найдена: {self.voice_samples_dir}")
            return []

        samples = sorted(self.voice_samples_dir.glob("*.wav"))
        return samples

    def _extract_speaker_embeddings(self):
        """Извлекает speaker embeddings из образцов голоса"""
        if not self.voice_samples:
            return

        # Используем первый образец как reference
        # TODO: можно объединить несколько для лучшего качества
        reference_audio = str(self.voice_samples[0])

        try:
            logger.info(f"Извлечение speaker embedding из: {reference_audio}")
            self._target_se, _ = self.se_extractor.get_se(
                reference_audio, self.tone_converter, vad=True
            )
            logger.info("Speaker embedding извлечён успешно")
        except Exception as e:
            logger.error(f"Ошибка извлечения speaker embedding: {e}")

    def get_preset(self, preset_name: str) -> IntonationPreset:
        """Получает пресет по имени"""
        if preset_name not in INTONATION_PRESETS:
            logger.warning(f"Пресет '{preset_name}' не найден, используется 'natural'")
            preset_name = "natural"
        return INTONATION_PRESETS[preset_name]

    def list_presets(self) -> dict[str, str]:
        """Возвращает список доступных пресетов"""
        return {name: preset.name for name, preset in INTONATION_PRESETS.items()}

    def synthesize(
        self,
        text: str,
        output_path: Optional[str] = None,
        language: str = "ru",
        preset: Optional[str] = None,
        speed: Optional[float] = None,
        **kwargs,  # Для совместимости с XTTS API
    ) -> tuple[np.ndarray, int]:
        """
        Синтезирует речь с клонированием голоса.

        Процесс:
        1. MeloTTS генерирует базовую речь
        2. ToneColorConverter применяет тембр из reference audio

        Args:
            text: Текст для синтеза
            output_path: Путь для сохранения (опционально)
            language: Язык (ru, en и т.д.)
            preset: Имя пресета интонации
            speed: Скорость речи (0.5-2.0)

        Returns:
            tuple[np.ndarray, int]: (wav данные, sample_rate)
        """
        if self._target_se is None:
            raise ValueError("Speaker embedding не загружен. Проверьте образцы голоса.")

        import time

        start_time = time.time()

        # Получаем настройки из пресета
        p = self.get_preset(preset or self.default_preset)
        final_speed = speed if speed is not None else p.speed

        logger.info(f"Синтез: '{text[:50]}...' (speed={final_speed})")

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # Шаг 1: Генерация базовой речи через MeloTTS
                base_audio_path = f"{tmpdir}/base.wav"

                # MeloTTS использует английский speaker для базы
                # (качество лучше, затем тембр клонируется)
                speaker_id = self.melo_speaker_ids.get("EN-Default", 0)

                self.melo_tts.tts_to_file(text, speaker_id, base_audio_path, speed=final_speed)

                # Извлекаем source speaker embedding из сгенерированного аудио
                source_se, _ = self.se_extractor.get_se(
                    base_audio_path, self.tone_converter, vad=False
                )

                # Шаг 2: Конвертация тембра
                output_audio_path = output_path or f"{tmpdir}/output.wav"

                self.tone_converter.convert(
                    audio_src_path=base_audio_path,
                    src_se=source_se,
                    tgt_se=self._target_se,
                    output_path=output_audio_path,
                    message="@OpenVoice",  # watermark
                )

                # Читаем результат
                wav, sample_rate = sf.read(output_audio_path)

                # Конвертируем в float32 numpy array
                if wav.dtype != np.float32:
                    wav = wav.astype(np.float32)

                elapsed = time.time() - start_time
                audio_duration = len(wav) / sample_rate
                rtf = elapsed / audio_duration if audio_duration > 0 else 0

                logger.info(
                    f"Синтез завершён: {elapsed:.2f}s, аудио: {audio_duration:.2f}s, RTF: {rtf:.2f}x"
                )

                # Если указан output_path, файл уже сохранён
                if output_path:
                    logger.info(f"Сохранено: {output_path}")

                return wav, sample_rate

        except Exception as e:
            logger.error(f"Ошибка синтеза: {e}")
            raise

    def synthesize_to_file(
        self, text: str, output_path: str, language: str = "ru", **kwargs
    ) -> str:
        """Синтезирует и сохраняет в файл"""
        self.synthesize(text, output_path, language, **kwargs)
        return output_path

    def synthesize_with_emotion(
        self,
        text: str,
        emotion: Literal["neutral", "warm", "energetic", "calm", "natural"] = "natural",
        output_path: Optional[str] = None,
        language: str = "ru",
    ) -> tuple[np.ndarray, int]:
        """Упрощённый метод синтеза с выбором эмоции"""
        return self.synthesize(
            text=text, output_path=output_path, language=language, preset=emotion
        )


# ============== FastAPI сервер ==============
app = FastAPI(title="OpenVoice TTS Service", version="1.0")

# Глобальный экземпляр сервиса (ленивая инициализация)
_service: Optional[OpenVoiceService] = None


def get_service() -> OpenVoiceService:
    global _service
    if _service is None:
        _service = OpenVoiceService()
    return _service


class SynthesizeRequest(BaseModel):
    text: str
    language: str = "ru"
    preset: str = "natural"
    speed: Optional[float] = None


class VoiceInfo(BaseModel):
    name: str
    engine: str = "openvoice"
    description: str


@app.on_event("startup")
async def startup():
    """Инициализация при запуске"""
    logger.info("Запуск OpenVoice TTS Service...")
    get_service()  # Инициализируем сервис
    logger.info(f"Сервис запущен на порту {OPENVOICE_PORT}")


@app.get("/health")
async def health():
    """Health check"""
    service = get_service()
    return {
        "status": "ok",
        "device": service.device,
        "samples_loaded": len(service.voice_samples),
        "speaker_embedding_ready": service._target_se is not None,
    }


@app.get("/voices")
async def list_voices():
    """Список доступных голосов"""
    service = get_service()
    return {
        "voices": [
            VoiceInfo(
                name="lidia_openvoice",
                engine="openvoice",
                description=f"Клонированный голос Лидии ({len(service.voice_samples)} образцов)",
            )
        ],
        "presets": service.list_presets(),
    }


@app.post("/synthesize")
async def synthesize(request: SynthesizeRequest):
    """
    Синтез речи с клонированием голоса.
    Возвращает WAV аудио.
    """
    service = get_service()

    try:
        wav, sample_rate = service.synthesize(
            text=request.text, language=request.language, preset=request.preset, speed=request.speed
        )

        # Конвертируем в WAV bytes
        import io

        buffer = io.BytesIO()
        sf.write(buffer, wav, sample_rate, format="WAV")
        buffer.seek(0)

        return Response(
            content=buffer.read(),
            media_type="audio/wav",
            headers={"X-Sample-Rate": str(sample_rate), "X-Duration": str(len(wav) / sample_rate)},
        )

    except Exception as e:
        logger.error(f"Ошибка синтеза: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tts")
async def tts_endpoint(request: SynthesizeRequest):
    """Альтернативный endpoint для совместимости"""
    return await synthesize(request)


# ============== CLI запуск ==============
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="OpenVoice TTS Service")
    parser.add_argument("--port", type=int, default=OPENVOICE_PORT, help="Port to listen on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--test", action="store_true", help="Run test synthesis")
    args = parser.parse_args()

    if args.test:
        # Тестовый режим
        print("=" * 70)
        print("OpenVoice TTS Service - Тестирование")
        print("=" * 70)

        service = OpenVoiceService()

        print("\nТестовый синтез...")
        test_text = "Здравствуйте! Это тестовое сообщение от OpenVoice."

        wav, sr = service.synthesize(
            text=test_text, output_path="test_openvoice.wav", preset="natural"
        )

        print("\nСохранено: test_openvoice.wav")
        print(f"Sample rate: {sr}")
        print(f"Duration: {len(wav) / sr:.2f}s")
        print("=" * 70)
    else:
        # Запуск сервера
        uvicorn.run("openvoice_service:app", host=args.host, port=args.port, reload=False)

#!/usr/bin/env python3
"""
TTS Finetune Manager - управление обучением Qwen3-TTS.
Загрузка образцов, транскрибация Whisper, подготовка датасета, обучение.
"""

import json
import logging
import os
import subprocess
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class VoiceSample:
    """Образец голоса"""

    filename: str
    path: str
    duration_sec: float = 0
    transcript: str = ""
    transcript_edited: bool = False
    size_kb: float = 0


@dataclass
class TTSDatasetConfig:
    """Конфигурация датасета TTS"""

    voice_name: str = "custom_voice"
    whisper_model: str = "medium"  # tiny, base, small, medium, large
    language: str = "ru"
    min_duration_sec: float = 1.0
    max_duration_sec: float = 30.0


@dataclass
class TTSTrainingConfig:
    """Конфигурация обучения TTS"""

    base_model: str = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    batch_size: int = 2
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-5
    num_epochs: int = 3
    output_dir: str = "output_custom"


@dataclass
class TTSProcessingStatus:
    """Статус обработки"""

    is_running: bool = False
    stage: str = ""  # "uploading", "transcribing", "preparing", "training"
    current: int = 0
    total: int = 0
    message: str = ""
    error: Optional[str] = None


@dataclass
class TTSTrainingStatus:
    """Статус обучения"""

    is_running: bool = False
    current_step: int = 0
    total_steps: int = 0
    current_epoch: int = 0
    total_epochs: int = 3
    loss: float = 0.0
    elapsed_seconds: float = 0
    eta_seconds: float = 0
    error: Optional[str] = None


class TTSFinetuneManager:
    """Менеджер обучения TTS"""

    def __init__(self, base_dir: str = "/home/shaerware/qwen3-tts"):
        self.base_dir = Path(base_dir)
        self.samples_dir = self.base_dir / "voice_samples"
        self.finetuning_dir = self.base_dir / "finetuning"
        self.venv_python = self.base_dir / "tts_venv" / "bin" / "python"

        # State files
        self.samples_file = self.base_dir / "samples_metadata.json"
        self.config_file = self.base_dir / "tts_config.json"

        # Ensure directories exist
        self.samples_dir.mkdir(parents=True, exist_ok=True)
        self.finetuning_dir.mkdir(parents=True, exist_ok=True)

        # Status
        self._processing_status = TTSProcessingStatus()
        self._training_status = TTSTrainingStatus()
        self._training_process: Optional[subprocess.Popen] = None
        self._training_log: List[str] = []

        # Load config
        self._config = self._load_config()
        self._samples: List[VoiceSample] = self._load_samples()

    def _load_config(self) -> Dict[str, Any]:
        """Загружает конфигурацию"""
        if self.config_file.exists():
            with open(self.config_file) as f:
                return json.load(f)
        return {"dataset": asdict(TTSDatasetConfig()), "training": asdict(TTSTrainingConfig())}

    def _save_config(self):
        """Сохраняет конфигурацию"""
        with open(self.config_file, "w") as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)

    def _load_samples(self) -> List[VoiceSample]:
        """Загружает метаданные образцов"""
        if self.samples_file.exists():
            with open(self.samples_file) as f:
                data = json.load(f)
                return [VoiceSample(**s) for s in data]
        return []

    def _save_samples(self):
        """Сохраняет метаданные образцов"""
        with open(self.samples_file, "w") as f:
            json.dump([asdict(s) for s in self._samples], f, indent=2, ensure_ascii=False)

    # === Public API ===

    def get_config(self) -> Dict[str, Any]:
        """Возвращает конфигурацию"""
        return self._config

    def set_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Обновляет конфигурацию"""
        if "dataset" in config:
            self._config["dataset"].update(config["dataset"])
        if "training" in config:
            self._config["training"].update(config["training"])
        self._save_config()
        return self._config

    def get_samples(self) -> List[Dict[str, Any]]:
        """Возвращает список образцов"""
        return [asdict(s) for s in self._samples]

    def get_sample(self, filename: str) -> Optional[Dict[str, Any]]:
        """Возвращает образец по имени"""
        for s in self._samples:
            if s.filename == filename:
                return asdict(s)
        return None

    def add_sample(self, filename: str, content: bytes) -> VoiceSample:
        """Добавляет образец голоса"""
        # Save file
        filepath = self.samples_dir / filename
        with open(filepath, "wb") as f:
            f.write(content)

        # Get duration
        duration = self._get_audio_duration(filepath)
        size_kb = len(content) / 1024

        # Create sample entry
        sample = VoiceSample(
            filename=filename, path=str(filepath), duration_sec=duration, size_kb=size_kb
        )

        # Update or add
        existing = next((s for s in self._samples if s.filename == filename), None)
        if existing:
            existing.path = sample.path
            existing.duration_sec = sample.duration_sec
            existing.size_kb = sample.size_kb
        else:
            self._samples.append(sample)

        self._save_samples()
        return sample

    def delete_sample(self, filename: str) -> bool:
        """Удаляет образец"""
        sample = next((s for s in self._samples if s.filename == filename), None)
        if not sample:
            return False

        # Delete file
        filepath = Path(sample.path)
        if filepath.exists():
            filepath.unlink()

        # Remove from list
        self._samples = [s for s in self._samples if s.filename != filename]
        self._save_samples()
        return True

    def update_transcript(self, filename: str, transcript: str) -> Optional[VoiceSample]:
        """Обновляет транскрипцию образца"""
        sample = next((s for s in self._samples if s.filename == filename), None)
        if not sample:
            return None

        sample.transcript = transcript
        sample.transcript_edited = True
        self._save_samples()
        return sample

    def get_processing_status(self) -> Dict[str, Any]:
        """Возвращает статус обработки"""
        return asdict(self._processing_status)

    def get_training_status(self) -> Dict[str, Any]:
        """Возвращает статус обучения"""
        return asdict(self._training_status)

    def get_training_log(self) -> List[str]:
        """Возвращает лог обучения"""
        return self._training_log[-500:]  # Last 500 lines

    # === Transcription ===

    def transcribe_samples(self) -> bool:
        """Запускает транскрибацию всех образцов через Whisper"""
        if self._processing_status.is_running:
            return False

        samples_to_transcribe = [s for s in self._samples if not s.transcript_edited]
        if not samples_to_transcribe:
            return False

        def _run():
            try:
                self._processing_status.is_running = True
                self._processing_status.stage = "transcribing"
                self._processing_status.total = len(samples_to_transcribe)
                self._processing_status.current = 0
                self._processing_status.error = None

                # Import whisper
                import whisper

                model_name = self._config["dataset"].get("whisper_model", "medium")
                language = self._config["dataset"].get("language", "ru")

                self._processing_status.message = f"Загрузка модели Whisper {model_name}..."
                model = whisper.load_model(model_name)

                for i, sample in enumerate(samples_to_transcribe):
                    self._processing_status.current = i + 1
                    self._processing_status.message = f"Транскрибация {sample.filename}..."

                    result = model.transcribe(sample.path, language=language, task="transcribe")

                    sample.transcript = result["text"].strip()
                    self._save_samples()

                self._processing_status.message = "Транскрибация завершена"

            except Exception as e:
                logger.error(f"Ошибка транскрибации: {e}")
                self._processing_status.error = str(e)
            finally:
                self._processing_status.is_running = False

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return True

    # === Dataset Preparation ===

    def prepare_dataset(self) -> bool:
        """Подготавливает датасет для обучения (извлекает audio_codes)"""
        if self._processing_status.is_running:
            return False

        samples_with_transcript = [s for s in self._samples if s.transcript]
        if not samples_with_transcript:
            return False

        def _run():
            try:
                self._processing_status.is_running = True
                self._processing_status.stage = "preparing"
                self._processing_status.total = len(samples_with_transcript) + 2
                self._processing_status.current = 0
                self._processing_status.error = None

                voice_name = self._config["dataset"].get("voice_name", "custom_voice")

                # Step 1: Create raw JSONL
                self._processing_status.message = "Создание raw JSONL..."
                self._processing_status.current = 1

                raw_jsonl_path = self.finetuning_dir / f"train_raw_{voice_name}.jsonl"
                with open(raw_jsonl_path, "w") as f:
                    for sample in samples_with_transcript:
                        entry = {
                            "audio": sample.path,
                            "text": sample.transcript,
                            "ref_audio": sample.path,
                        }
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

                # Step 2: Extract audio_codes using prepare_data.py
                self._processing_status.message = "Извлечение audio_codes..."
                self._processing_status.current = 2

                output_jsonl = self.finetuning_dir / f"train_{voice_name}.jsonl"

                cmd = [
                    str(self.venv_python),
                    str(self.finetuning_dir / "prepare_data.py"),
                    "--device",
                    "cuda:1",
                    "--tokenizer_model_path",
                    "Qwen/Qwen3-TTS-Tokenizer-12Hz",
                    "--input_jsonl",
                    str(raw_jsonl_path),
                    "--output_jsonl",
                    str(output_jsonl),
                ]

                result = subprocess.run(
                    cmd, capture_output=True, text=True, cwd=str(self.finetuning_dir)
                )

                if result.returncode != 0:
                    raise Exception(f"prepare_data.py failed: {result.stderr}")

                # Count samples
                with open(output_jsonl) as f:
                    count = sum(1 for _ in f)

                self._processing_status.message = f"Готово! {count} образцов в датасете"
                self._processing_status.current = self._processing_status.total

            except Exception as e:
                logger.error(f"Ошибка подготовки датасета: {e}")
                self._processing_status.error = str(e)
            finally:
                self._processing_status.is_running = False

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return True

    # === Training ===

    def start_training(self) -> bool:
        """Запускает обучение"""
        if self._training_status.is_running or self._processing_status.is_running:
            return False

        voice_name = self._config["dataset"].get("voice_name", "custom_voice")
        train_jsonl = self.finetuning_dir / f"train_{voice_name}.jsonl"

        if not train_jsonl.exists():
            self._training_status.error = "Датасет не найден. Сначала подготовьте датасет."
            return False

        training_config = self._config.get("training", {})

        cmd = [
            str(self.venv_python),
            str(self.finetuning_dir / "sft_12hz.py"),
            "--init_model_path",
            training_config.get("base_model", "Qwen/Qwen3-TTS-12Hz-1.7B-Base"),
            "--output_model_path",
            training_config.get("output_dir", f"output_{voice_name}"),
            "--train_jsonl",
            str(train_jsonl),
            "--batch_size",
            str(training_config.get("batch_size", 2)),
            "--lr",
            str(training_config.get("learning_rate", 2e-5)),
            "--num_epochs",
            str(training_config.get("num_epochs", 3)),
            "--speaker_name",
            voice_name,
        ]

        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = "1"  # Use RTX 3060

        self._training_status = TTSTrainingStatus(
            is_running=True, total_epochs=training_config.get("num_epochs", 3)
        )
        self._training_log = []

        def _run():
            start_time = datetime.now()
            try:
                self._training_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(self.finetuning_dir),
                    env=env,
                    bufsize=1,
                )

                for line in iter(self._training_process.stdout.readline, ""):
                    line = line.strip()
                    if line:
                        self._training_log.append(line)
                        self._parse_training_line(line)

                    elapsed = (datetime.now() - start_time).total_seconds()
                    self._training_status.elapsed_seconds = elapsed

                self._training_process.wait()

                if self._training_process.returncode != 0:
                    self._training_status.error = "Обучение завершилось с ошибкой"

            except Exception as e:
                logger.error(f"Ошибка обучения: {e}")
                self._training_status.error = str(e)
            finally:
                self._training_status.is_running = False
                self._training_process = None

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return True

    def stop_training(self) -> bool:
        """Останавливает обучение"""
        if not self._training_status.is_running or not self._training_process:
            return False

        self._training_process.terminate()
        self._training_status.is_running = False
        return True

    def _parse_training_line(self, line: str):
        """Парсит строку лога обучения"""
        # Example: "Epoch 1 | Step 50 | Loss: 0.1234"
        if "Epoch" in line and "Step" in line and "Loss" in line:
            try:
                parts = line.split("|")
                epoch = int(parts[0].split("Epoch")[1].strip())
                step = int(parts[1].split("Step")[1].strip())
                loss = float(parts[2].split("Loss:")[1].strip())

                self._training_status.current_epoch = epoch
                self._training_status.current_step = step
                self._training_status.loss = loss
            except (ValueError, IndexError):
                pass

    def _get_audio_duration(self, filepath: Path) -> float:
        """Получает длительность аудио в секундах"""
        try:
            import soundfile as sf

            with sf.SoundFile(str(filepath)) as f:
                return len(f) / f.samplerate
        except Exception:
            return 0.0

    def get_trained_models(self) -> List[Dict[str, Any]]:
        """Возвращает список обученных моделей"""
        models = []
        output_dir = self.finetuning_dir

        for d in output_dir.iterdir():
            if d.is_dir() and d.name.startswith("output_"):
                # Check for checkpoints
                checkpoints = list(d.glob("checkpoint-epoch-*"))
                if checkpoints:
                    latest = max(checkpoints, key=lambda p: int(p.name.split("-")[-1]))
                    models.append(
                        {
                            "name": d.name,
                            "path": str(latest),
                            "epochs": len(checkpoints),
                            "modified": datetime.fromtimestamp(latest.stat().st_mtime).isoformat(),
                        }
                    )

        return models


# Global instance
_tts_finetune_manager: Optional[TTSFinetuneManager] = None


def get_tts_finetune_manager() -> TTSFinetuneManager:
    """Возвращает глобальный менеджер TTS fine-tuning"""
    global _tts_finetune_manager
    if _tts_finetune_manager is None:
        _tts_finetune_manager = TTSFinetuneManager()
    return _tts_finetune_manager

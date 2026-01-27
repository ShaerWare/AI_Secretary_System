#!/usr/bin/env python3
"""
Fine-tune Manager - управление дообучением LoRA адаптеров для AI Secretary System.
Поддерживает загрузку датасета, настройку параметров и мониторинг обучения.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TrainingConfig:
    """Конфигурация обучения LoRA"""

    # Model
    base_model: str = "Qwen/Qwen2.5-7B-Instruct"

    # LoRA params
    lora_rank: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05

    # Training params
    batch_size: int = 1
    gradient_accumulation_steps: int = 64
    learning_rate: float = 2e-4
    num_epochs: int = 1
    warmup_ratio: float = 0.03
    weight_decay: float = 0.01
    max_seq_length: int = 768

    # Output
    output_dir: str = "qwen2.5-7b-lydia-lora-new"

    # Advanced
    gradient_checkpointing: bool = True
    fp16: bool = True
    logging_steps: int = 1
    save_steps: int = 100


@dataclass
class AdapterInfo:
    """Информация о LoRA адаптере"""

    name: str
    path: str
    size_mb: float
    modified: str
    active: bool = False
    config: Optional[dict] = None


@dataclass
class TrainingStatus:
    """Статус текущего обучения"""

    is_running: bool = False
    current_step: int = 0
    total_steps: int = 0
    current_epoch: int = 0
    total_epochs: int = 0
    loss: float = 0.0
    learning_rate: float = 0.0
    elapsed_seconds: float = 0.0
    eta_seconds: float = 0.0
    error: Optional[str] = None


@dataclass
class DatasetStats:
    """Статистика датасета"""

    total_sessions: int = 0
    total_messages: int = 0
    total_tokens: int = 0
    avg_tokens_per_message: float = 0.0
    file_path: Optional[str] = None
    file_size_mb: float = 0.0
    modified: Optional[str] = None


@dataclass
class ProcessingStatus:
    """Статус обработки датасета"""

    is_running: bool = False
    stage: str = ""  # "parsing", "transcribing", "building"
    current: int = 0
    total: int = 0
    voice_transcribed: int = 0
    voice_total: int = 0
    error: Optional[str] = None


@dataclass
class DatasetConfig:
    """Конфигурация обработки датасета"""

    owner_name: str = "Артем Юрьевич"
    transcribe_voice: bool = False
    min_dialog_messages: int = 2
    max_message_length: int = 2000
    max_dialog_length: int = 20
    include_groups: bool = False
    output_name: str = "dataset"


class FinetuneManager:
    """
    Менеджер дообучения LoRA адаптеров.

    Функции:
    - Загрузка и обработка датасетов (Telegram export)
    - Настройка параметров обучения
    - Запуск/остановка обучения
    - Мониторинг прогресса (SSE)
    - Управление адаптерами (активация, удаление)
    """

    # Пути по умолчанию (локальная структура в репозитории)
    EXTERNAL_DATA_DIR = Path(os.path.expanduser("~/qwen-finetune"))  # Внешние данные
    VENV_PATH = EXTERNAL_DATA_DIR / "train_venv"  # venv для обучения

    # Скрипты (в finetune/)
    PREPARE_SCRIPT = "prepare_dataset.py"
    TRAIN_SCRIPT = "train.py"
    MERGE_SCRIPT = "merge_lora.py"
    QUANTIZE_SCRIPT = "quantize_awq.py"

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path(__file__).parent

        # Локальные пути (в репозитории)
        self.finetune_dir = self.base_dir / "finetune"
        self.datasets_dir = self.finetune_dir / "datasets"
        self.adapters_dir = self.finetune_dir / "adapters"

        # Внешние данные (для совместимости)
        self.external_data_dir = self.EXTERNAL_DATA_DIR

        # Состояние обучения
        self.training_process: Optional[subprocess.Popen] = None
        self.training_config: Optional[TrainingConfig] = None
        self.training_status = TrainingStatus()
        self.training_log: List[str] = []
        self.training_start_time: Optional[datetime] = None
        self._training_lock = threading.Lock()

        # Состояние обработки датасета
        self.processing_status = ProcessingStatus()
        self.dataset_config = DatasetConfig()
        self._processing_lock = threading.Lock()
        self._stt_service = None  # Lazy load

        # Создаем директории если не существуют
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        self.adapters_dir.mkdir(parents=True, exist_ok=True)

        # Текущий активный адаптер
        self.active_adapter: Optional[str] = None
        self._load_active_adapter()

        logger.info("🎓 FinetuneManager инициализирован")
        logger.info(f"   📁 Finetune dir: {self.finetune_dir}")
        logger.info(f"   📊 Datasets: {self.datasets_dir}")
        logger.info(f"   🔧 Adapters: {self.adapters_dir}")

    def _load_active_adapter(self):
        """Загружает информацию об активном адаптере"""
        active_file = self.adapters_dir / ".active"
        if active_file.exists():
            self.active_adapter = active_file.read_text().strip()

    def _save_active_adapter(self, adapter_name: str):
        """Сохраняет активный адаптер"""
        active_file = self.adapters_dir / ".active"
        active_file.write_text(adapter_name)
        self.active_adapter = adapter_name

    def _run_script(
        self, script_name: str, args: List[str] = None, capture_output: bool = True
    ) -> dict:
        """Запускает Python скрипт в venv finetune"""
        script_path = self.finetune_dir / script_name
        if not script_path.exists():
            return {"status": "error", "message": f"Скрипт не найден: {script_name}"}

        python_path = self.VENV_PATH / "bin" / "python"
        if not python_path.exists():
            # Fallback на системный python
            python_path = "python3"
            logger.warning(f"⚠️ venv не найден: {self.VENV_PATH}, используем системный python")

        cmd = [str(python_path), str(script_path)]
        if args:
            cmd.extend(args)

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.finetune_dir),
                capture_output=capture_output,
                text=True,
                timeout=600,  # 10 минут таймаут
            )

            if result.returncode == 0:
                return {"status": "ok", "stdout": result.stdout, "stderr": result.stderr}
            else:
                return {
                    "status": "error",
                    "message": result.stderr or result.stdout,
                    "returncode": result.returncode,
                }
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Таймаут выполнения скрипта"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ============== Dataset Operations ==============

    async def upload_dataset(self, content: bytes, filename: str) -> dict:
        """
        Сохраняет загруженный датасет (Telegram export JSON).
        """
        try:
            # Определяем путь для сохранения
            if filename.endswith(".json"):
                dest_path = self.datasets_dir / "result.json"
            else:
                dest_path = self.datasets_dir / filename

            dest_path.write_bytes(content)
            file_size = len(content) / (1024 * 1024)

            logger.info(f"📥 Датасет загружен: {dest_path} ({file_size:.2f} MB)")

            return {
                "status": "ok",
                "message": f"Файл сохранён: {dest_path.name}",
                "path": str(dest_path),
                "size_mb": round(file_size, 2),
            }
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки датасета: {e}")
            return {"status": "error", "message": str(e)}

    def _get_stt_service(self):
        """Lazy load STT service for voice transcription"""
        if self._stt_service is None:
            try:
                from stt_service import STTService

                self._stt_service = STTService(
                    model_size="base", use_faster_whisper=True, device="cpu"
                )
                logger.info("✅ STT сервис загружен для расшифровки голосовых")
            except Exception as e:
                logger.warning(f"⚠️ STT недоступен: {e}")
                self._stt_service = False  # Mark as unavailable
        return self._stt_service if self._stt_service else None

    def _extract_text(self, text_field) -> str:
        """Извлекает текст из поля (может быть строкой или списком)"""
        if isinstance(text_field, str):
            return text_field.strip()
        if isinstance(text_field, list):
            parts = []
            for item in text_field:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(item.get("text", ""))
            return "".join(parts).strip()
        return ""

    def _transcribe_voice(self, voice_path: Path, telegram_export_dir: Path) -> Optional[str]:
        """Расшифровывает голосовое сообщение"""
        stt = self._get_stt_service()
        if not stt:
            return None

        # Путь к файлу относительно экспорта Telegram
        full_path = telegram_export_dir / voice_path
        if not full_path.exists():
            # Попробуем найти в datasets_dir
            full_path = self.datasets_dir / voice_path
        if not full_path.exists():
            logger.warning(f"Голосовое не найдено: {voice_path}")
            return None

        try:
            result = stt.transcribe(str(full_path), language="ru")
            return result.get("text", "").strip()
        except Exception as e:
            logger.error(f"Ошибка расшифровки {voice_path}: {e}")
            return None

    def get_dataset_config(self) -> dict:
        """Возвращает текущую конфигурацию обработки"""
        return asdict(self.dataset_config)

    def set_dataset_config(self, **kwargs) -> dict:
        """Устанавливает конфигурацию обработки"""
        for key, value in kwargs.items():
            if hasattr(self.dataset_config, key):
                setattr(self.dataset_config, key, value)
        return {"status": "ok", "config": asdict(self.dataset_config)}

    def get_processing_status(self) -> dict:
        """Возвращает статус обработки датасета"""
        with self._processing_lock:
            return asdict(self.processing_status)

    async def process_dataset(self, config: Optional[dict] = None) -> dict:
        """
        Обрабатывает Telegram export и создает JSONL для обучения.
        Поддерживает расшифровку голосовых сообщений.
        """
        # Применяем конфигурацию если передана
        if config:
            self.set_dataset_config(**config)

        cfg = self.dataset_config

        # Проверяем наличие result.json
        input_file = self.datasets_dir / "result.json"
        if not input_file.exists():
            return {
                "status": "error",
                "message": "Файл result.json не найден. Загрузите Telegram export.",
            }

        with self._processing_lock:
            if self.processing_status.is_running:
                return {"status": "error", "message": "Обработка уже запущена"}
            self.processing_status = ProcessingStatus(is_running=True, stage="parsing")

        try:
            # Загружаем Telegram export
            logger.info(f"📂 Загрузка {input_file}...")
            with open(input_file, encoding="utf-8") as f:
                data = json.load(f)

            chat_list = data.get("chats", {}).get("list", [])
            logger.info(f"📊 Найдено чатов: {len(chat_list)}")

            with self._processing_lock:
                self.processing_status.total = len(chat_list)

            all_dialogs = []
            voice_messages = []  # Для отложенной расшифровки
            stats = {
                "total_chats": len(chat_list),
                "processed_chats": 0,
                "skipped_chats": 0,
                "voice_messages": 0,
            }

            # Определяем директорию с медиафайлами
            telegram_export_dir = input_file.parent

            for idx, chat in enumerate(chat_list):
                with self._processing_lock:
                    self.processing_status.current = idx + 1

                chat_type = chat.get("type", "")

                # Фильтруем по типу чата
                if chat_type == "personal_chat":
                    pass  # Всегда обрабатываем
                elif chat_type in [
                    "private_group",
                    "public_group",
                    "private_supergroup",
                    "public_supergroup",
                ]:
                    if not cfg.include_groups:
                        stats["skipped_chats"] += 1
                        continue
                else:
                    stats["skipped_chats"] += 1
                    continue

                messages = chat.get("messages", [])
                current_dialog = []
                prev_role = None

                for msg in messages:
                    if msg.get("type") != "message":
                        continue

                    sender = msg.get("from", "")
                    text = self._extract_text(msg.get("text", ""))

                    # Обработка голосовых сообщений
                    media_type = msg.get("media_type")
                    if media_type == "voice_message" and cfg.transcribe_voice:
                        voice_file = msg.get("file")
                        if voice_file:
                            stats["voice_messages"] += 1
                            voice_messages.append(
                                {
                                    "file": voice_file,
                                    "sender": sender,
                                    "dialog_idx": len(all_dialogs),
                                    "msg_idx": len(current_dialog),
                                    "export_dir": telegram_export_dir,
                                }
                            )
                            # Placeholder - будет заменен после расшифровки
                            text = f"[VOICE:{voice_file}]"

                    if not text or len(text) < 1:
                        continue

                    if len(text) > cfg.max_message_length:
                        text = text[: cfg.max_message_length] + "..."

                    # Определяем роль
                    role = "assistant" if sender == cfg.owner_name else "user"

                    # Склеиваем последовательные сообщения
                    if role == prev_role and current_dialog:
                        current_dialog[-1]["value"] += "\n" + text
                    else:
                        current_dialog.append({"from": role, "value": text})

                    prev_role = role

                # Разбиваем длинные диалоги
                for i in range(0, len(current_dialog), cfg.max_dialog_length):
                    chunk = current_dialog[i : i + cfg.max_dialog_length]

                    # Диалог должен начинаться с user и заканчиваться assistant
                    while chunk and chunk[0]["from"] == "assistant":
                        chunk = chunk[1:]
                    while chunk and chunk[-1]["from"] == "user":
                        chunk = chunk[:-1]

                    if len(chunk) >= cfg.min_dialog_messages:
                        has_user = any(m["from"] == "user" for m in chunk)
                        has_assistant = any(m["from"] == "assistant" for m in chunk)
                        if has_user and has_assistant:
                            all_dialogs.append({"messages": chunk})

                if current_dialog:
                    stats["processed_chats"] += 1
                else:
                    stats["skipped_chats"] += 1

            # Расшифровка голосовых сообщений
            if voice_messages and cfg.transcribe_voice:
                with self._processing_lock:
                    self.processing_status.stage = "transcribing"
                    self.processing_status.voice_total = len(voice_messages)
                    self.processing_status.voice_transcribed = 0

                logger.info(f"🎤 Расшифровка {len(voice_messages)} голосовых сообщений...")

                for vm in voice_messages:
                    transcribed = self._transcribe_voice(Path(vm["file"]), vm["export_dir"])
                    if transcribed:
                        # Находим и заменяем placeholder
                        # Это упрощённая логика - в реальности нужно отслеживать индексы
                        for dialog in all_dialogs:
                            for msg in dialog["messages"]:
                                placeholder = f"[VOICE:{vm['file']}]"
                                if placeholder in msg["value"]:
                                    msg["value"] = msg["value"].replace(placeholder, transcribed)

                    with self._processing_lock:
                        self.processing_status.voice_transcribed += 1

            # Удаляем нерасшифрованные плейсхолдеры
            for dialog in all_dialogs:
                dialog["messages"] = [
                    m for m in dialog["messages"] if not m["value"].startswith("[VOICE:")
                ]
            # Удаляем пустые диалоги
            all_dialogs = [d for d in all_dialogs if len(d["messages"]) >= cfg.min_dialog_messages]

            # Сохраняем результат
            with self._processing_lock:
                self.processing_status.stage = "building"

            output_file = self.datasets_dir / f"{cfg.output_name}_dataset.jsonl"
            with open(output_file, "w", encoding="utf-8") as f:
                for dialog in all_dialogs:
                    f.write(json.dumps(dialog, ensure_ascii=False) + "\n")

            total_messages = sum(len(d["messages"]) for d in all_dialogs)
            logger.info(
                f"✅ Датасет создан: {len(all_dialogs)} диалогов, {total_messages} сообщений"
            )

            return {
                "status": "ok",
                "message": f"Датасет обработан: {len(all_dialogs)} диалогов",
                "output_file": str(output_file),
                "stats": {
                    **stats,
                    "total_dialogs": len(all_dialogs),
                    "total_messages": total_messages,
                },
            }

        except Exception as e:
            logger.error(f"❌ Ошибка обработки: {e}")
            return {"status": "error", "message": str(e)}

        finally:
            with self._processing_lock:
                self.processing_status.is_running = False
                self.processing_status.stage = ""

    def get_dataset_stats(self, dataset_file: Optional[str] = None) -> DatasetStats:
        """
        Возвращает статистику датасета.
        Если dataset_file не указан, использует последний измененный .jsonl
        """
        stats = DatasetStats()

        # Находим файл датасета
        if dataset_file:
            train_file = Path(dataset_file)
        else:
            # Ищем последний измененный .jsonl файл
            jsonl_files = list(self.datasets_dir.glob("*.jsonl"))
            if not jsonl_files:
                return stats
            train_file = max(jsonl_files, key=lambda f: f.stat().st_mtime)

        if not train_file.exists():
            return stats

        try:
            stat = train_file.stat()
            stats.file_path = str(train_file)
            stats.file_size_mb = round(stat.st_size / (1024 * 1024), 2)
            stats.modified = datetime.fromtimestamp(stat.st_mtime).isoformat()

            # Парсим JSONL
            with open(train_file, encoding="utf-8") as f:
                sessions = [json.loads(line) for line in f if line.strip()]

            stats.total_sessions = len(sessions)

            total_messages = 0
            total_chars = 0

            for session in sessions:
                messages = session.get("conversations", session.get("messages", []))
                total_messages += len(messages)
                for msg in messages:
                    content = msg.get("value", msg.get("content", ""))
                    total_chars += len(content)

            stats.total_messages = total_messages
            # Приблизительная оценка токенов (1 токен ~ 3 символа для русского)
            stats.total_tokens = total_chars // 3
            stats.avg_tokens_per_message = round(stats.total_tokens / max(1, total_messages), 1)

        except Exception as e:
            logger.error(f"❌ Ошибка анализа датасета: {e}")

        return stats

    def list_datasets(self) -> List[dict]:
        """
        Возвращает список доступных датасетов.
        """
        datasets = []

        for f in self.datasets_dir.iterdir():
            if f.suffix == ".jsonl" and f.is_file():
                stat = f.stat()
                datasets.append(
                    {
                        "name": f.name,
                        "path": str(f),
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    }
                )
            elif f.suffix == ".json" and f.name == "result.json":
                stat = f.stat()
                datasets.append(
                    {
                        "name": f.name,
                        "path": str(f),
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "type": "telegram_export",
                    }
                )

        return sorted(datasets, key=lambda x: x["modified"], reverse=True)

    async def augment_dataset(self) -> dict:
        """
        Аугментирует датасет (увеличивает разнообразие).
        Пока не реализовано - возвращает сообщение.
        """
        # TODO: Реализовать аугментацию
        return {
            "status": "ok",
            "message": "Аугментация пока не реализована. Используйте существующие датасеты.",
            "stats": asdict(self.get_dataset_stats()),
        }

    # ============== Training Configuration ==============

    def get_config(self) -> TrainingConfig:
        """Возвращает текущую конфигурацию обучения"""
        if self.training_config:
            return self.training_config

        # Загружаем из файла если есть
        config_file = self.finetune_dir / "training_config.json"
        if config_file.exists():
            try:
                data = json.loads(config_file.read_text())
                self.training_config = TrainingConfig(**data)
            except Exception:
                self.training_config = TrainingConfig()
        else:
            self.training_config = TrainingConfig()

        return self.training_config

    def set_config(self, config: TrainingConfig) -> dict:
        """Устанавливает конфигурацию обучения"""
        self.training_config = config

        # Сохраняем в файл
        config_file = self.finetune_dir / "training_config.json"
        try:
            config_file.write_text(json.dumps(asdict(config), indent=2))
            logger.info(f"⚙️ Конфигурация сохранена: {config_file}")
            return {"status": "ok", "config": asdict(config)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_config_presets(self) -> Dict[str, TrainingConfig]:
        """Возвращает предустановленные конфигурации"""
        return {
            "quick": TrainingConfig(
                lora_rank=4,
                lora_alpha=8,
                batch_size=1,
                gradient_accumulation_steps=32,
                num_epochs=1,
                max_seq_length=512,
                output_dir="adapter-quick",
            ),
            "standard": TrainingConfig(
                lora_rank=8,
                lora_alpha=16,
                batch_size=1,
                gradient_accumulation_steps=64,
                num_epochs=1,
                max_seq_length=768,
                output_dir="adapter-standard",
            ),
            "thorough": TrainingConfig(
                lora_rank=16,
                lora_alpha=32,
                batch_size=1,
                gradient_accumulation_steps=128,
                num_epochs=2,
                max_seq_length=1024,
                output_dir="adapter-thorough",
            ),
        }

    # ============== Training Operations ==============

    async def start_training(self, config: Optional[TrainingConfig] = None) -> dict:
        """
        Запускает обучение в фоновом режиме.
        Использует train.py из finetune/
        """
        if self.training_process and self.training_process.poll() is None:
            return {"status": "error", "message": "Обучение уже запущено"}

        # Используем переданную или текущую конфигурацию
        if config:
            self.training_config = config
        elif not self.training_config:
            self.training_config = TrainingConfig()

        config = self.training_config

        # Проверяем датасет
        jsonl_files = list(self.datasets_dir.glob("*.jsonl"))
        if not jsonl_files:
            return {
                "status": "error",
                "message": "Датасет не найден. Сначала загрузите и обработайте данные.",
            }

        # Используем последний датасет
        _train_file = max(jsonl_files, key=lambda f: f.stat().st_mtime)

        # Создаем директорию для адаптера
        output_dir = self.adapters_dir / config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        # Формируем команду обучения
        python_path = self.VENV_PATH / "bin" / "python"
        if not python_path.exists():
            return {"status": "error", "message": f"venv для обучения не найден: {self.VENV_PATH}"}

        train_script = self.finetune_dir / self.TRAIN_SCRIPT
        if not train_script.exists():
            return {"status": "error", "message": f"Скрипт обучения не найден: {train_script}"}

        # train.py использует хардкодированные параметры, запускаем напрямую
        # В будущем можно добавить поддержку аргументов командной строки
        cmd = [str(python_path), str(train_script)]

        # Устанавливаем переменные окружения для GPU
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = "1"
        env["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"

        try:
            # Очищаем предыдущий лог
            with self._training_lock:
                self.training_log = []
                self.training_status = TrainingStatus(
                    is_running=True, total_epochs=config.num_epochs
                )
                self.training_start_time = datetime.now()

            # Запускаем процесс
            self.training_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(self.finetune_dir),
                env=env,
                text=True,
                bufsize=1,
            )

            # Запускаем поток для чтения вывода
            threading.Thread(target=self._read_training_output, daemon=True).start()

            logger.info(f"🎓 Обучение запущено: {' '.join(cmd[:5])}...")

            return {
                "status": "ok",
                "message": "Обучение запущено",
                "config": asdict(config),
                "pid": self.training_process.pid,
            }

        except Exception as e:
            with self._training_lock:
                self.training_status.is_running = False
                self.training_status.error = str(e)
            logger.error(f"❌ Ошибка запуска обучения: {e}")
            return {"status": "error", "message": str(e)}

    def _read_training_output(self):
        """Читает вывод процесса обучения в фоне"""
        if not self.training_process:
            return

        # Регулярки для парсинга прогресса
        step_pattern = re.compile(r"Step (\d+)/(\d+)")
        loss_pattern = re.compile(r"loss[=:\s]+([0-9.]+)", re.IGNORECASE)
        epoch_pattern = re.compile(r"Epoch (\d+)/(\d+)")
        lr_pattern = re.compile(r"lr[=:\s]+([0-9.e-]+)", re.IGNORECASE)

        for line in iter(self.training_process.stdout.readline, ""):
            if not line:
                break

            line = line.strip()

            with self._training_lock:
                self.training_log.append(line)

                # Ограничиваем размер лога
                if len(self.training_log) > 10000:
                    self.training_log = self.training_log[-5000:]

                # Парсим прогресс
                step_match = step_pattern.search(line)
                if step_match:
                    self.training_status.current_step = int(step_match.group(1))
                    self.training_status.total_steps = int(step_match.group(2))

                loss_match = loss_pattern.search(line)
                if loss_match:
                    self.training_status.loss = float(loss_match.group(1))

                epoch_match = epoch_pattern.search(line)
                if epoch_match:
                    self.training_status.current_epoch = int(epoch_match.group(1))
                    self.training_status.total_epochs = int(epoch_match.group(2))

                lr_match = lr_pattern.search(line)
                if lr_match:
                    self.training_status.learning_rate = float(lr_match.group(1))

                # Вычисляем время
                if self.training_start_time:
                    elapsed = (datetime.now() - self.training_start_time).total_seconds()
                    self.training_status.elapsed_seconds = elapsed

                    # ETA
                    if (
                        self.training_status.current_step > 0
                        and self.training_status.total_steps > 0
                    ):
                        steps_remaining = (
                            self.training_status.total_steps - self.training_status.current_step
                        )
                        time_per_step = elapsed / self.training_status.current_step
                        self.training_status.eta_seconds = steps_remaining * time_per_step

        # Процесс завершился
        with self._training_lock:
            self.training_status.is_running = False
            returncode = self.training_process.wait()
            if returncode != 0:
                self.training_status.error = f"Процесс завершился с кодом {returncode}"
            else:
                logger.info("✅ Обучение завершено успешно")

    async def stop_training(self) -> dict:
        """Останавливает обучение"""
        if not self.training_process or self.training_process.poll() is not None:
            return {"status": "ok", "message": "Обучение не запущено"}

        try:
            self.training_process.terminate()
            try:
                self.training_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.training_process.kill()

            with self._training_lock:
                self.training_status.is_running = False

            logger.info("🛑 Обучение остановлено")
            return {"status": "ok", "message": "Обучение остановлено"}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_training_status(self) -> TrainingStatus:
        """Возвращает текущий статус обучения"""
        with self._training_lock:
            return TrainingStatus(
                is_running=self.training_status.is_running,
                current_step=self.training_status.current_step,
                total_steps=self.training_status.total_steps,
                current_epoch=self.training_status.current_epoch,
                total_epochs=self.training_status.total_epochs,
                loss=self.training_status.loss,
                learning_rate=self.training_status.learning_rate,
                elapsed_seconds=self.training_status.elapsed_seconds,
                eta_seconds=self.training_status.eta_seconds,
                error=self.training_status.error,
            )

    def get_training_log(self, lines: int = 100, offset: int = 0) -> dict:
        """Возвращает лог обучения"""
        with self._training_lock:
            total = len(self.training_log)
            if offset > 0:
                end_idx = max(0, total - offset)
                start_idx = max(0, end_idx - lines)
            else:
                start_idx = max(0, total - lines)
                end_idx = total

            return {
                "lines": self.training_log[start_idx:end_idx],
                "total_lines": total,
                "start_line": start_idx,
                "end_line": end_idx,
            }

    async def stream_training_log(self, interval: float = 0.5) -> AsyncGenerator[str, None]:
        """SSE streaming лога обучения"""
        last_line_idx = 0

        while True:
            with self._training_lock:
                # Отправляем новые строки
                if len(self.training_log) > last_line_idx:
                    new_lines = self.training_log[last_line_idx:]
                    last_line_idx = len(self.training_log)

                    for line in new_lines:
                        yield json.dumps(
                            {"type": "log", "line": line, "timestamp": datetime.now().isoformat()}
                        )

                # Отправляем статус
                yield json.dumps({"type": "status", "status": asdict(self.training_status)})

                is_running = self.training_status.is_running

            if not is_running:
                yield json.dumps({"type": "done"})
                break

            await asyncio.sleep(interval)

    # ============== Adapter Operations ==============

    def list_adapters(self) -> List[AdapterInfo]:
        """Возвращает список доступных LoRA адаптеров"""
        adapters = []

        if not self.adapters_dir.exists():
            return adapters

        for adapter_dir in self.adapters_dir.iterdir():
            if not adapter_dir.is_dir() or adapter_dir.name.startswith("."):
                continue

            # Проверяем наличие файлов адаптера
            adapter_files = list(adapter_dir.glob("adapter_*.safetensors")) + list(
                adapter_dir.glob("adapter_*.bin")
            )
            if not adapter_files:
                # Проверяем подпапку final
                final_dir = adapter_dir / "final"
                if final_dir.exists():
                    adapter_files = list(final_dir.glob("adapter_*.safetensors")) + list(
                        final_dir.glob("adapter_*.bin")
                    )

            if not adapter_files:
                continue

            # Вычисляем размер
            total_size = sum(f.stat().st_size for f in adapter_dir.rglob("*") if f.is_file())
            size_mb = total_size / (1024 * 1024)

            # Дата модификации
            modified = datetime.fromtimestamp(adapter_dir.stat().st_mtime).isoformat()

            # Конфиг если есть
            config = None
            config_file = adapter_dir / "adapter_config.json"
            if not config_file.exists():
                config_file = adapter_dir / "final" / "adapter_config.json"
            if config_file.exists():
                try:
                    config = json.loads(config_file.read_text())
                except Exception:
                    pass

            adapters.append(
                AdapterInfo(
                    name=adapter_dir.name,
                    path=str(adapter_dir),
                    size_mb=round(size_mb, 2),
                    modified=modified,
                    active=(adapter_dir.name == self.active_adapter),
                    config=config,
                )
            )

        return sorted(adapters, key=lambda x: x.modified, reverse=True)

    async def activate_adapter(self, adapter_name: str) -> dict:
        """
        Активирует LoRA адаптер (hot-swap в vLLM).
        """
        adapter_dir = self.adapters_dir / adapter_name
        if not adapter_dir.exists():
            return {"status": "error", "message": f"Адаптер не найден: {adapter_name}"}

        # Проверяем наличие файлов
        final_dir = adapter_dir / "final"
        if final_dir.exists():
            adapter_path = final_dir
        else:
            adapter_path = adapter_dir

        adapter_files = list(adapter_path.glob("adapter_*.safetensors")) + list(
            adapter_path.glob("adapter_*.bin")
        )
        if not adapter_files:
            return {"status": "error", "message": f"Файлы адаптера не найдены в {adapter_path}"}

        # TODO: Реализовать hot-swap через vLLM API
        # Пока просто сохраняем как активный
        self._save_active_adapter(adapter_name)

        logger.info(f"✅ Адаптер активирован: {adapter_name}")

        return {
            "status": "ok",
            "message": f"Адаптер {adapter_name} активирован. Перезапустите vLLM для применения.",
            "adapter": adapter_name,
            "path": str(adapter_path),
            "note": "Требуется перезапуск vLLM для применения нового адаптера",
        }

    async def delete_adapter(self, adapter_name: str) -> dict:
        """Удаляет LoRA адаптер"""
        adapter_dir = self.adapters_dir / adapter_name
        if not adapter_dir.exists():
            return {"status": "error", "message": f"Адаптер не найден: {adapter_name}"}

        if adapter_name == self.active_adapter:
            return {"status": "error", "message": "Нельзя удалить активный адаптер"}

        try:
            shutil.rmtree(adapter_dir)
            logger.info(f"🗑️ Адаптер удалён: {adapter_name}")
            return {"status": "ok", "message": f"Адаптер {adapter_name} удалён"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


# Глобальный экземпляр
_finetune_manager: Optional[FinetuneManager] = None


def get_finetune_manager() -> FinetuneManager:
    """Получает или создает глобальный FinetuneManager"""
    global _finetune_manager
    if _finetune_manager is None:
        _finetune_manager = FinetuneManager()
    return _finetune_manager


if __name__ == "__main__":
    import asyncio

    async def test():
        manager = FinetuneManager()

        print("=== Dataset Stats ===")
        stats = manager.get_dataset_stats()
        print(f"  Sessions: {stats.total_sessions}")
        print(f"  Messages: {stats.total_messages}")
        print(f"  Tokens: {stats.total_tokens}")

        print("\n=== Training Config ===")
        config = manager.get_config()
        print(f"  LoRA rank: {config.lora_rank}")
        print(f"  Batch size: {config.batch_size}")
        print(f"  Learning rate: {config.learning_rate}")

        print("\n=== Adapters ===")
        for adapter in manager.list_adapters():
            active = " (ACTIVE)" if adapter.active else ""
            print(f"  - {adapter.name}: {adapter.size_mb} MB{active}")

    asyncio.run(test())

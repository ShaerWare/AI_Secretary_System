#!/usr/bin/env python3
"""
Fine-tune Manager - управление дообучением LoRA адаптеров для AI Secretary System.
Поддерживает загрузку датасета, настройку параметров и мониторинг обучения.
"""

import ast
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
from typing import AsyncGenerator, Dict, List, Optional, Tuple


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

    # ============== Project Dataset Generation ==============

    async def generate_project_dataset(
        self,
        include_tz: bool = True,
        include_faq: bool = True,
        include_docs: bool = True,
        include_escalation: bool = True,
        include_code: bool = True,
        output_name: str = "project_dataset",
    ) -> dict:
        """
        Генерирует датасет из проектных источников для дообучения модели
        как техподдержки и продавца услуг.

        Источники:
        - docs/tz/tz_tg_bot.md — продажные сценарии, цены, возражения
        - FAQ из БД — типовые вопросы-ответы
        - CLAUDE.md + docs/ — техническая документация
        - Шаблоны эскалации — примеры передачи на старший уровень
        - Python код — endpoints, models, docstrings (NEW)
        - Markdown документация — README, wiki-pages (NEW)
        """
        all_dialogs: List[dict] = []
        sources_stats: Dict[str, int] = {}

        try:
            if include_tz:
                tz_dialogs = self._generate_from_tz()
                all_dialogs.extend(tz_dialogs)
                sources_stats["tz_sales"] = len(tz_dialogs)

            if include_faq:
                faq_dialogs = await self._generate_from_faq()
                all_dialogs.extend(faq_dialogs)
                sources_stats["faq"] = len(faq_dialogs)

            if include_docs:
                docs_dialogs = self._generate_from_docs()
                all_dialogs.extend(docs_dialogs)
                sources_stats["docs"] = len(docs_dialogs)

            if include_escalation:
                escalation_dialogs = self._generate_escalation_examples()
                all_dialogs.extend(escalation_dialogs)
                sources_stats["escalation"] = len(escalation_dialogs)

            if include_code:
                # Парсинг Python кода проекта
                code_dialogs = self._generate_from_python_code()
                all_dialogs.extend(code_dialogs)
                sources_stats["python_code"] = len(code_dialogs)

                # Парсинг Markdown документации
                md_dialogs = self._generate_from_markdown_docs()
                all_dialogs.extend(md_dialogs)
                sources_stats["markdown_docs"] = len(md_dialogs)

            if not all_dialogs:
                return {
                    "status": "error",
                    "message": "Не удалось сгенерировать ни одного диалога. Проверьте источники.",
                }

            # Сохраняем
            output_file = self.datasets_dir / f"{output_name}.jsonl"
            with open(output_file, "w", encoding="utf-8") as f:
                for dialog in all_dialogs:
                    f.write(json.dumps(dialog, ensure_ascii=False) + "\n")

            total_messages = sum(len(d["messages"]) for d in all_dialogs)

            logger.info(
                f"✅ Проектный датасет создан: {len(all_dialogs)} диалогов, "
                f"{total_messages} сообщений → {output_file}"
            )

            return {
                "status": "ok",
                "message": f"Датасет сгенерирован: {len(all_dialogs)} диалогов",
                "output_file": str(output_file),
                "stats": {
                    "total_dialogs": len(all_dialogs),
                    "total_messages": total_messages,
                    "sources": sources_stats,
                },
            }

        except Exception as e:
            logger.error(f"❌ Ошибка генерации проектного датасета: {e}")
            return {"status": "error", "message": str(e)}

    def _make_dialog(self, pairs: List[tuple]) -> dict:
        """Создаёт диалог из списка пар (user, assistant)."""
        messages = []
        for user_msg, assistant_msg in pairs:
            messages.append({"from": "user", "value": user_msg})
            messages.append({"from": "assistant", "value": assistant_msg})
        return {"messages": messages}

    def _generate_from_tz(self) -> List[dict]:
        """Генерирует диалоги из ТЗ продажного бота (docs/tz/tz_tg_bot.md)."""
        dialogs = []
        tz_file = self.base_dir / "docs" / "tz" / "tz_tg_bot.md"
        if not tz_file.exists():
            logger.warning(f"⚠️ ТЗ не найдено: {tz_file}")
            return dialogs

        # --- Продуктовые вопросы ---
        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Что такое AI Secretary?",
                        "AI Secretary — это голосовой AI-ассистент на вашем собственном сервере. "
                        "Он говорит вашим голосом благодаря клонированию, работает без интернета, "
                        "без абонентской платы. Все данные остаются у вас.",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Какие у вас есть тарифы?",
                        "Есть три варианта:\n\n"
                        "1. Бесплатно — скачиваете с GitHub и ставите сами\n"
                        "2. Установка «под ключ» — 5,000₽ разово. Я подключаюсь к вашему серверу "
                        "и всё настраиваю за 30 минут\n"
                        "3. Кастомное решение — от 50,000₽. Интеграция с CRM, телефонией, "
                        "обучение на ваших данных\n\n"
                        "Какой вариант вам ближе?",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Сколько стоит установка?",
                        "Установка «под ключ» стоит 5,000₽ — это разовый платёж. "
                        "Я подключаюсь к вашему серверу по SSH, устанавливаю систему, "
                        "оптимизирую под ваш GPU и проверяю работоспособность. "
                        "Весь процесс занимает около 30 минут. "
                        "Гарантия: если не заработает — верну деньги.",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Зачем мне это, если есть ChatGPT?",
                        "Отличный вопрос! Ключевые отличия:\n\n"
                        "• Приватность — ваши данные не уходят на чужие серверы (GDPR, 152-ФЗ)\n"
                        "• Нет абонентки — один раз настроил и работает бесплатно\n"
                        "• Ваш голос — AI говорит вашим клонированным голосом\n"
                        "• Работает офлайн — не зависит от интернета\n"
                        "• Полная кастомизация — обучаете на своих данных\n\n"
                        "Типичный SaaS-бот стоит 15,000₽/мес. За 3 года это 540,000₽. "
                        "AI Secretary окупается за 10 дней.",
                    ),
                ]
            )
        )

        # --- Требования к железу ---
        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Какой GPU нужен для работы?",
                        "Зависит от нужного качества:\n\n"
                        "• GTX 1660 (6 ГБ) — Qwen-3B, базовое качество ⭐⭐\n"
                        "• RTX 3060 (12 ГБ) — Qwen-7B, хорошее качество ⭐⭐⭐\n"
                        "• RTX 3090 (24 ГБ) — Qwen-14B, отличное качество ⭐⭐⭐⭐\n"
                        "• RTX 4090 (24 ГБ) — Qwen-32B, максимальное качество ⭐⭐⭐⭐⭐\n\n"
                        "Нет GPU? Есть CPU-режим с облачным LLM (Gemini API) — бесплатно.",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "У меня нет GPU, могу ли я использовать систему?",
                        "Да! Есть три варианта:\n\n"
                        "1. CPU + облачный LLM (бесплатно)\n"
                        "   Голос: Piper TTS (быстрый, на CPU)\n"
                        "   Мозги: Gemini API (бесплатный тир)\n"
                        "   Качество: хорошее ⭐⭐⭐\n\n"
                        "2. Аренда VPS с GPU — от 3,000₽/мес за RTX 3060\n\n"
                        "3. Свой мини-сервер — RTX 3060 б/у ~25,000₽, "
                        "окупается за 8 месяцев по сравнению с VPS\n\n"
                        "Какой вариант вам ближе?",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Какие минимальные системные требования?",
                        "Минимум:\n"
                        "• ОС: Ubuntu 20.04+ или Debian 11+\n"
                        "• RAM: 8 ГБ (16 ГБ рекомендуется)\n"
                        "• Диск: 20 ГБ свободного места\n"
                        "• Docker установлен\n\n"
                        "Для GPU-режима дополнительно:\n"
                        "• NVIDIA GPU с CUDA Compute Capability ≥ 7.0\n"
                        "• NVIDIA Driver ≥ 525\n"
                        "• nvidia-container-toolkit\n\n"
                        "Для CPU-режима GPU не нужен — будет использоваться "
                        "облачный LLM и лёгкий TTS.",
                    ),
                ]
            )
        )

        # --- Установка ---
        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Как установить AI Secretary?",
                        "Установка очень простая — 5 минут:\n\n"
                        "```\n"
                        "git clone https://github.com/ShaerWare/AI_Secretary_System\n"
                        "cd AI_Secretary_System\n"
                        "cp .env.example .env\n"
                        "docker compose up -d\n"
                        "```\n\n"
                        "Админка: http://localhost:8002/admin\n"
                        "Логин: admin / admin\n\n"
                        "Если застрянете — пишите, помогу! "
                        "Или могу установить за вас за 5,000₽.",
                    ),
                ]
            )
        )

        # --- Возможности ---
        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Какие возможности есть у системы?",
                        "AI Secretary умеет:\n\n"
                        "🗣️ Голос:\n"
                        "• Клонирование голоса (XTTS v2) — говорит вашим голосом\n"
                        "• Предобученные голоса (Piper) — быстрый CPU-режим\n\n"
                        "🧠 Интеллект:\n"
                        "• Локальный LLM (vLLM + Qwen/Llama/DeepSeek)\n"
                        "• Облачные LLM (Gemini, OpenAI, Claude, DeepSeek)\n"
                        "• FAQ-система для мгновенных ответов\n\n"
                        "📱 Каналы:\n"
                        "• Telegram-бот (мульти-инстансы)\n"
                        "• Виджет для сайта\n"
                        "• GSM-телефония (SIM7600E-H)\n"
                        "• OpenAI-совместимый API\n\n"
                        "⚙️ Админка: 14 вкладок, PWA, темы, i18n (ru/en)",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Можно ли интегрировать с CRM?",
                        "Да, в рамках кастомного решения. Поддерживаем:\n\n"
                        "• Bitrix24\n"
                        "• amoCRM\n"
                        "• 1С\n"
                        "• Телефония (SIP/GSM)\n"
                        "• Любая система через API\n\n"
                        "Стоимость интеграции зависит от сложности — от 20,000₽ за одну систему. "
                        "Расскажите о вашей задаче, и я подготовлю расчёт.",
                    ),
                ]
            )
        )

        # --- Возражения ---
        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Дорого, есть что-нибудь попроще?",
                        "Конечно! Есть несколько вариантов:\n\n"
                        "1. MVP-версия (быстрый старт) — 50,000₽\n"
                        "   Базовая система без интеграций, вы сами связываете с CRM\n\n"
                        "2. Поэтапное внедрение\n"
                        "   Сначала базовая система, потом добавляем интеграции. "
                        "Платите по частям\n\n"
                        "3. Self-hosted с консультацией — 15,000₽\n"
                        "   Ставите сами с GitHub, я консультирую по настройке\n\n"
                        "Какой вариант интереснее?",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "А это безопасно? Где хранятся данные?",
                        "Это одно из главных преимуществ AI Secretary — "
                        "все данные хранятся только на вашем сервере.\n\n"
                        "• Локальная модель — запросы не уходят в интернет\n"
                        "• SQLite база данных — на вашем диске\n"
                        "• Нет телеметрии и трекинга\n"
                        "• Полное соответствие 152-ФЗ и GDPR\n\n"
                        "Вы единственный, кто имеет доступ к данным.",
                    ),
                ]
            )
        )

        # --- Кейсы и social proof ---
        dialogs.append(
            self._make_dialog(
                [
                    (
                        "У вас есть примеры внедрения?",
                        "Да, вот несколько кейсов:\n\n"
                        "🏢 Автосалон — снизили нагрузку на менеджеров на 70%. "
                        "Бот отвечает на типовые вопросы о наличии, ценах, комплектациях\n\n"
                        "🏥 Клиника — автозапись 24/7, +40% записей на приём. "
                        "Бот записывает пациентов, напоминает о визитах\n\n"
                        "🛒 E-commerce — бот-консультант, +25% конверсии. "
                        "Помогает выбрать товар, отвечает на вопросы\n\n"
                        "Хотите обсудить ваш конкретный случай?",
                    ),
                ]
            )
        )

        # --- Мультиходовые диалоги ---
        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Привет! Хочу поставить AI-секретаря для бизнеса",
                        "Отлично! Давайте подберём лучший вариант. "
                        "Ответьте на пару вопросов:\n\n"
                        "Как вы относитесь к технической стороне?\n"
                        "1. Люблю сам разбираться в настройках\n"
                        "2. Предпочитаю готовое решение\n"
                        "3. У меня бизнес-задача, нужна интеграция",
                    ),
                    (
                        "2, мне нужно готовое",
                        "Понял! Тогда вариант «Установка под ключ» за 5,000₽ — то, что нужно.\n\n"
                        "Есть ли у вас сервер для установки?\n"
                        "1. Да, есть сервер с GPU\n"
                        "2. Есть сервер, но без GPU\n"
                        "3. Нет сервера\n"
                        "4. Не знаю / нужна консультация",
                    ),
                    (
                        "Есть VPS на Ubuntu, но без GPU",
                        "Отлично! Вот что получится на CPU:\n\n"
                        "🧠 LLM: облачный Gemini API (бесплатный тир)\n"
                        "🗣️ TTS: Piper (быстрый, работает на CPU)\n"
                        "📊 Качество: хорошее ⭐⭐⭐\n"
                        "⚡ Скорость: ~1-2 сек на ответ\n\n"
                        "Это работает без GPU и без абонентской платы. "
                        "Хотите, чтобы я установил? 5,000₽ разово.",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Здравствуйте, мне нужен голосовой бот для телефонии",
                        "Здравствуйте! AI Secretary поддерживает GSM-телефонию "
                        "через модуль SIM7600E-H.\n\n"
                        "Бот может:\n"
                        "• Отвечать на входящие звонки\n"
                        "• Совершать исходящие\n"
                        "• Отправлять SMS\n"
                        "• Работать с вашим голосом\n\n"
                        "Расскажите подробнее — "
                        "какой объём звонков в день и какие задачи нужно решить?",
                    ),
                    (
                        "Около 100 звонков в день, запись на приём в клинику",
                        "Отличная задача! Для 100 звонков/день достаточно одного модуля.\n\n"
                        "Предварительный расчёт:\n"
                        "• Базовая система: 50,000₽\n"
                        "• GSM-модуль SIM7600E-H: ~5,000₽\n"
                        "• Настройка сценариев записи: 20,000₽\n"
                        "• Итого: 75,000-85,000₽\n\n"
                        "Срок: 2-3 недели. Хотите обсудить детали?",
                    ),
                ]
            )
        )

        # --- Технические вопросы ---
        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Какие модели LLM поддерживаются?",
                        "Локальные (через vLLM):\n"
                        "• Qwen 2.5 (3B, 7B, 14B, 32B) — рекомендуем\n"
                        "• Llama 3 (8B, 70B)\n"
                        "• DeepSeek (7B, 67B)\n"
                        "• Mistral, Phi, Gemma, Yi\n\n"
                        "Облачные:\n"
                        "• Google Gemini (бесплатный тир)\n"
                        "• OpenAI (GPT-4o)\n"
                        "• Anthropic (Claude)\n"
                        "• DeepSeek API\n"
                        "• OpenRouter (200+ моделей)\n\n"
                        "Переключение между моделями — одним кликом в админке.",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Как работает клонирование голоса?",
                        "Используем XTTS v2 — одну из лучших open-source моделей.\n\n"
                        "Процесс:\n"
                        "1. Загружаете 3-5 минут записи вашего голоса (WAV)\n"
                        "2. Система обрабатывает и создаёт голосовой профиль\n"
                        "3. AI говорит вашим голосом в реальном времени\n\n"
                        "Требования:\n"
                        "• GPU с 5+ ГБ VRAM (RTX 3060+)\n"
                        "• Чистая запись без фонового шума\n\n"
                        "Для CPU есть предобученные голоса (Piper) — "
                        "мужской и женский, без клонирования.",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Есть ли API для интеграции?",
                        "Да, есть OpenAI-совместимый API:\n\n"
                        "• POST /v1/chat/completions — чат со стримингом\n"
                        "• POST /v1/audio/speech — генерация речи\n"
                        "• GET /v1/models — список моделей\n\n"
                        "Можно подключить к OpenWebUI или любому "
                        "OpenAI-совместимому клиенту.\n\n"
                        "Также есть ~130 admin API endpoint'ов для полного "
                        "управления системой. Документация в админке.",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Как обновлять систему?",
                        "Обновление через Docker — одной командой:\n\n"
                        "```\n"
                        "git pull\n"
                        "docker compose build --no-cache orchestrator\n"
                        "docker compose up -d\n"
                        "```\n\n"
                        "Данные (БД, голоса, настройки) сохраняются в папке data/. "
                        "Обновление затрагивает только код.",
                    ),
                ]
            )
        )

        # --- Follow-up / удержание ---
        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Я подумаю",
                        "Конечно, не тороплю! Вот что может помочь определиться:\n\n"
                        "📊 Калькулятор экономии: типичный SaaS-бот стоит 15,000₽/мес, "
                        "за 3 года это 540,000₽. AI Secretary — 5,000₽ один раз.\n\n"
                        "🎬 Демо: могу показать админку в действии\n\n"
                        "⭐ GitHub: можете посмотреть код и отзывы\n\n"
                        "Напишите, когда будете готовы — помогу!",
                    ),
                ]
            )
        )

        logger.info(f"📝 Из ТЗ сгенерировано {len(dialogs)} диалогов")
        return dialogs

    async def _generate_from_faq(self) -> List[dict]:
        """Генерирует диалоги из FAQ записей в БД."""
        dialogs = []

        try:
            from db.integration import async_faq_manager

            faq_entries = await async_faq_manager.get_all()

            for question, answer in faq_entries.items():
                if question and answer:
                    dialogs.append(
                        self._make_dialog(
                            [
                                (question, answer),
                            ]
                        )
                    )

            logger.info(f"📝 Из FAQ сгенерировано {len(dialogs)} диалогов")

        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить FAQ: {e}")

        return dialogs

    def _generate_from_docs(self) -> List[dict]:
        """Генерирует технические Q&A из документации проекта."""
        dialogs = []

        # --- Из CLAUDE.md ---
        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Как запустить систему в Docker?",
                        "Самый простой способ:\n\n"
                        "```\n"
                        "cp .env.docker.example .env\n"
                        "docker compose up -d\n"
                        "```\n\n"
                        "Для CPU-режима (без GPU):\n"
                        "```\n"
                        "docker compose -f docker-compose.yml "
                        "-f docker-compose.cpu.yml up -d\n"
                        "```\n\n"
                        "Логи: `docker compose logs -f orchestrator`\n"
                        "Админка: http://localhost:8002/admin (admin/admin)",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Как проверить что система работает?",
                        "Проверка здоровья:\n"
                        "```\ncurl http://localhost:8002/health\n```\n\n"
                        'Если вернулось {"status": "ok"} — система работает.\n\n'
                        "Также можно зайти в админку: http://localhost:8002/admin\n"
                        "Логин по умолчанию: admin / admin",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Как переключить LLM-бэкенд?",
                        "В админке → вкладка LLM → выберите бэкенд:\n\n"
                        "• vllm — локальная модель (нужен GPU)\n"
                        "• gemini — Google Gemini API\n"
                        "• cloud:{id} — любой облачный провайдер из списка\n\n"
                        "Или через переменную окружения:\n"
                        "```\nLLM_BACKEND=vllm  # или gemini, cloud:openrouter-1\n```\n\n"
                        "Переключение без перезагрузки — моментально.",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Как добавить облачного LLM-провайдера?",
                        "В админке → LLM → Cloud Providers → Добавить:\n\n"
                        "1. Выберите тип (Gemini, OpenAI, Claude, DeepSeek, OpenRouter, Kimi)\n"
                        "2. Введите API-ключ\n"
                        "3. Выберите модель\n"
                        "4. Нажмите Тест → Сохранить\n\n"
                        "Для OpenRouter есть бесплатные модели. "
                        "Для Gemini можно настроить VLESS-прокси.",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Как настроить Telegram-бота?",
                        "В админке → Telegram → Добавить инстанс:\n\n"
                        "1. Создайте бота у @BotFather → получите токен\n"
                        "2. В админке: Добавить → вставьте токен\n"
                        "3. Настройте: приветствие, кнопки, LLM-бэкенд\n"
                        "4. Нажмите Старт\n\n"
                        "Бот автоматически запускается после перезагрузки системы. "
                        "Можно создавать несколько ботов одновременно.",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Как подключить виджет чата на сайт?",
                        "В админке → Виджет → Добавить инстанс:\n\n"
                        "1. Укажите имя и настройки\n"
                        "2. Скопируйте сгенерированный скрипт\n"
                        "3. Вставьте его на ваш сайт перед </body>\n\n"
                        "Виджет автоматически подключается к вашей системе. "
                        "Можно создать несколько виджетов для разных сайтов.",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Какая база данных используется?",
                        "SQLite + опциональный Redis.\n\n"
                        "• SQLite: основное хранилище (data/secretary.db)\n"
                        "  Таблицы: чаты, FAQ, пресеты TTS, провайдеры LLM, "
                        "боты, виджеты, аудит\n\n"
                        "• Redis: кэширование (опционально)\n"
                        "  Если Redis недоступен — система работает без него\n\n"
                        "Бэкапы: cp data/secretary.db data/backup/",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Как обучить модель на своих данных?",
                        "В админке → Обучение (Fine-tune):\n\n"
                        "1. Загрузите Telegram-экспорт (result.json) или "
                        "сгенерируйте датасет из проекта\n"
                        "2. Настройте параметры (LoRA rank, epochs)\n"
                        "3. Нажмите Start — обучение идёт на вашем GPU\n"
                        "4. После завершения — активируйте адаптер\n\n"
                        "Требуется GPU (RTX 3060+) и train_venv. "
                        "Обучение на ~2000 диалогов занимает 1-2 часа.",
                    ),
                ]
            )
        )

        logger.info(f"📝 Из документации сгенерировано {len(dialogs)} диалогов")
        return dialogs

    def _generate_escalation_examples(self) -> List[dict]:
        """Генерирует примеры эскалации на старший уровень поддержки."""
        dialogs = []

        # Сложная техническая проблема
        dialogs.append(
            self._make_dialog(
                [
                    (
                        "У меня сложная интеграция с CRM через webhook, данные не приходят",
                        "Это нестандартный случай, подключаю старшего специалиста. "
                        "Он свяжется с вами в течение 15 минут.\n\n"
                        "Пока можете описать подробнее:\n"
                        "• Какая CRM (Bitrix, amoCRM, другая)?\n"
                        "• Какие данные должны приходить?\n"
                        "• Есть ли логи ошибок?\n\n"
                        "Это поможет решить вопрос быстрее.",
                    ),
                ]
            )
        )

        # Непонятная ошибка
        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Docker контейнер падает с ошибкой CUDA out of memory",
                        "Похоже, не хватает видеопамяти. Пара быстрых советов:\n\n"
                        "• Проверьте, не запущено ли что-то ещё на GPU: `nvidia-smi`\n"
                        "• Попробуйте модель поменьше в .env\n\n"
                        "Если не поможет — подключу специалиста. "
                        "Скажите, какая у вас видеокарта и сколько VRAM?",
                    ),
                ]
            )
        )

        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Не работает распознавание речи, Vosk выдаёт пустые результаты",
                        "Проверьте несколько вещей:\n\n"
                        "1. Модель Vosk скачана: `ls models/vosk/`\n"
                        "2. Формат аудио: WAV, 16kHz, mono\n"
                        "3. Микрофон работает: запишите тестовое аудио\n\n"
                        "Если проблема остаётся — это нестандартный случай. "
                        "Подключу старшего специалиста для диагностики. "
                        "Пришлите, пожалуйста, лог ошибки.",
                    ),
                ]
            )
        )

        # Запрос не по теме
        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Можете помочь написать код на Python?",
                        "Я специализируюсь на AI Secretary — голосовом AI-ассистенте. "
                        "К сожалению, помочь с общими задачами программирования не смогу.\n\n"
                        "Но если ваш вопрос связан с интеграцией или настройкой "
                        "AI Secretary — с радостью помогу!\n\n"
                        "Чем ещё могу быть полезен?",
                    ),
                ]
            )
        )

        # Жалоба на качество
        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Модель отвечает ерунду, качество ответов ужасное",
                        "Понимаю ваше разочарование. Давайте разберёмся:\n\n"
                        "1. Какая модель используется? (посмотрите в админке → LLM)\n"
                        "2. Есть ли обученный LoRA-адаптер?\n"
                        "3. Заполнен ли FAQ для типовых вопросов?\n\n"
                        "Обычно качество значительно улучшается после:\n"
                        "• Добавления FAQ (мгновенные точные ответы)\n"
                        "• Дообучения модели на ваших данных\n"
                        "• Переключения на более мощную модель\n\n"
                        "Если хотите — подключу специалиста для настройки. "
                        "Или расскажите подробнее, и я подскажу что улучшить.",
                    ),
                ]
            )
        )

        # Запрос на большой кастомный проект
        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Нам нужно развернуть систему на 10 серверах с балансировкой",
                        "Это enterprise-задача, требует индивидуального подхода.\n\n"
                        "Передаю ваш запрос нашему архитектору. "
                        "Он свяжется с вами для обсуждения:\n\n"
                        "• Архитектуры развёртывания\n"
                        "• Балансировки нагрузки\n"
                        "• Отказоустойчивости\n"
                        "• Стоимости и сроков\n\n"
                        "Оставьте, пожалуйста, контакт для связи "
                        "(email или телефон).",
                    ),
                ]
            )
        )

        # Не знает ответ
        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Работает ли система на ARM-процессорах? Хочу запустить на Raspberry Pi",
                        "Интересный вопрос! На данный момент система тестировалась "
                        "только на x86_64 (Intel/AMD). Поддержка ARM официально не заявлена.\n\n"
                        "Уточню у разработчиков и вернусь с ответом. "
                        "Если хотите — оставьте контакт, напишу как появится информация.\n\n"
                        "Как вариант, можно использовать CPU-режим с облачным LLM — "
                        "он менее требователен к железу.",
                    ),
                ]
            )
        )

        # Благодарность
        dialogs.append(
            self._make_dialog(
                [
                    (
                        "Спасибо, всё заработало! Классный проект",
                        "Рад, что всё получилось! 🎉\n\n"
                        "Если проект полезен — буду признателен за звезду на GitHub ⭐\n"
                        "github.com/ShaerWare/AI_Secretary_System\n\n"
                        "А если возникнут вопросы в будущем — пишите, помогу!\n\n"
                        "Хорошего дня!",
                    ),
                ]
            )
        )

        logger.info(f"📝 Эскалаций сгенерировано {len(dialogs)} диалогов")
        return dialogs

    # ============== Code & Documentation Parsing ==============

    def _generate_from_python_code(self) -> List[dict]:
        """
        Генерирует Q&A пары из Python кода проекта.

        Источники:
        - app/routers/*.py — FastAPI endpoints с docstrings
        - db/models.py — ORM модели с описаниями
        - vllm_llm_service.py — SECRETARY_PERSONAS, PREDEFINED_MODELS
        - cloud_llm_service.py — PROVIDER_TYPES
        """
        dialogs = []

        # 1. Парсим роутеры (API endpoints)
        routers_dir = self.base_dir / "app" / "routers"
        if routers_dir.exists():
            for router_file in routers_dir.glob("*.py"):
                if router_file.name.startswith("__"):
                    continue
                try:
                    dialogs.extend(self._parse_router_file(router_file))
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка парсинга {router_file}: {e}")

        # 2. Парсим ORM модели
        models_file = self.base_dir / "db" / "models.py"
        if models_file.exists():
            try:
                dialogs.extend(self._parse_orm_models(models_file))
            except Exception as e:
                logger.warning(f"⚠️ Ошибка парсинга models.py: {e}")

        # 3. Парсим конфигурационные словари
        for service_file in [
            "vllm_llm_service.py",
            "cloud_llm_service.py",
            "llm_service.py",
        ]:
            filepath = self.base_dir / service_file
            if filepath.exists():
                try:
                    dialogs.extend(self._parse_config_dicts(filepath))
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка парсинга {service_file}: {e}")

        # 4. Парсим orchestrator.py (Pydantic models)
        orchestrator_file = self.base_dir / "orchestrator.py"
        if orchestrator_file.exists():
            try:
                dialogs.extend(self._parse_pydantic_models(orchestrator_file))
            except Exception as e:
                logger.warning(f"⚠️ Ошибка парсинга orchestrator.py: {e}")

        logger.info(f"📝 Из Python кода сгенерировано {len(dialogs)} диалогов")
        return dialogs

    def _parse_router_file(self, filepath: Path) -> List[dict]:
        """Парсит FastAPI роутер и извлекает endpoint описания."""
        dialogs = []
        content = filepath.read_text(encoding="utf-8")
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Ищем декораторы @router.get/post/put/delete
                for decorator in node.decorator_list:
                    method, path = self._extract_route_info(decorator)
                    if method and path:
                        docstring = ast.get_docstring(node)
                        func_name = node.name

                        # Генерируем Q&A пару
                        if docstring:
                            q = f"Что делает endpoint {method.upper()} {path}?"
                            a = f"Endpoint {method.upper()} {path} ({func_name}):\n{docstring}"
                            dialogs.append(self._make_dialog([(q, a)]))

                        # Дополнительная пара про использование
                        if docstring and len(docstring) > 20:
                            q2 = f"Как использовать API {path}?"
                            a2 = f"Вызовите {method.upper()} {path}.\n\n{docstring}"
                            dialogs.append(self._make_dialog([(q2, a2)]))

        return dialogs

    def _extract_route_info(self, decorator: ast.expr) -> Tuple[Optional[str], Optional[str]]:
        """Извлекает HTTP метод и путь из декоратора роутера."""
        try:
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Attribute):
                    method = decorator.func.attr  # get, post, put, delete
                    if method in ("get", "post", "put", "delete", "patch"):
                        # Извлекаем путь из первого аргумента
                        if decorator.args:
                            if isinstance(decorator.args[0], ast.Constant):
                                path = decorator.args[0].value
                                return method, path
        except Exception:
            pass
        return None, None

    def _parse_orm_models(self, filepath: Path) -> List[dict]:
        """Парсит ORM модели (SQLAlchemy) и извлекает описания таблиц."""
        dialogs = []
        content = filepath.read_text(encoding="utf-8")
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Проверяем что это SQLAlchemy модель (наследуется от Base)
                is_model = any(
                    (isinstance(base, ast.Name) and base.id == "Base")
                    or (isinstance(base, ast.Attribute) and base.attr == "Base")
                    for base in node.bases
                )

                if is_model:
                    class_name = node.name
                    docstring = ast.get_docstring(node)

                    # Собираем поля модели
                    fields = []
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            for target in item.targets:
                                if isinstance(target, ast.Name):
                                    fields.append(target.id)
                        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                            fields.append(item.target.id)

                    if fields:
                        # Фильтруем служебные поля
                        visible_fields = [
                            f for f in fields if not f.startswith("_") and f != "__tablename__"
                        ]

                        q = f"Какие поля есть в таблице {class_name}?"
                        a = f"Таблица {class_name} содержит поля:\n• " + "\n• ".join(
                            visible_fields[:15]
                        )
                        if docstring:
                            a += f"\n\nОписание: {docstring}"
                        dialogs.append(self._make_dialog([(q, a)]))

        return dialogs

    def _parse_config_dicts(self, filepath: Path) -> List[dict]:
        """Парсит конфигурационные словари из сервисных файлов."""
        dialogs = []
        content = filepath.read_text(encoding="utf-8")

        # Ищем известные конфигурационные словари
        config_patterns = [
            (
                r"SECRETARY_PERSONAS\s*=\s*\{([^}]+)\}",
                "Какие персоны секретаря доступны?",
                "Доступные персоны секретаря:\n",
            ),
            (
                r"PROVIDER_TYPES\s*=\s*\{([^}]+)\}",
                "Какие типы облачных LLM провайдеров поддерживаются?",
                "Поддерживаемые облачные провайдеры:\n",
            ),
            (
                r"PREDEFINED_MODELS\s*=\s*\{([^}]+)\}",
                "Какие предустановленные модели доступны для vLLM?",
                "Предустановленные модели:\n",
            ),
        ]

        for pattern, question, answer_prefix in config_patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                # Извлекаем ключи из словаря
                dict_content = match.group(1)
                keys = re.findall(r'"([^"]+)":', dict_content)
                if not keys:
                    keys = re.findall(r"'([^']+)':", dict_content)

                if keys:
                    answer = answer_prefix + "• " + "\n• ".join(keys[:10])
                    dialogs.append(self._make_dialog([(question, answer)]))

        # Парсим docstrings функций
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    docstring = ast.get_docstring(node)
                    if docstring and len(docstring) > 50:
                        func_name = node.name
                        if not func_name.startswith("_"):
                            q = f"Что делает функция {func_name}?"
                            a = f"Функция {func_name}:\n{docstring[:500]}"
                            dialogs.append(self._make_dialog([(q, a)]))
        except Exception:
            pass

        return dialogs

    def _parse_pydantic_models(self, filepath: Path) -> List[dict]:
        """Парсит Pydantic модели (Request/Response) из файла."""
        dialogs = []
        content = filepath.read_text(encoding="utf-8")
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Проверяем что это Pydantic модель (наследуется от BaseModel)
                is_pydantic = any(
                    (isinstance(base, ast.Name) and base.id == "BaseModel")
                    or (isinstance(base, ast.Attribute) and base.attr == "BaseModel")
                    for base in node.bases
                )

                if is_pydantic:
                    class_name = node.name
                    docstring = ast.get_docstring(node)

                    # Собираем поля с типами
                    fields = []
                    for item in node.body:
                        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                            field_name = item.target.id
                            # Пытаемся получить тип
                            type_str = ast.unparse(item.annotation) if item.annotation else "Any"
                            fields.append(f"{field_name}: {type_str}")

                    if fields and ("Request" in class_name or "Response" in class_name):
                        q = f"Какие параметры принимает {class_name}?"
                        a = f"Модель {class_name}:\n• " + "\n• ".join(fields[:10])
                        if docstring:
                            a = f"{docstring}\n\nПоля:\n• " + "\n• ".join(fields[:10])
                        dialogs.append(self._make_dialog([(q, a)]))

        return dialogs

    def _generate_from_markdown_docs(self) -> List[dict]:
        """
        Генерирует Q&A пары из Markdown документации проекта.

        Источники:
        - README.md, CLAUDE.md, QUICKSTART.md
        - wiki-pages/*.md
        - examples.md, CHEATSHEET.md
        """
        dialogs = []

        # Список основных документов
        main_docs = [
            "README.md",
            "QUICKSTART.md",
            "CHEATSHEET.md",
            "examples.md",
        ]

        for doc_name in main_docs:
            doc_path = self.base_dir / doc_name
            if doc_path.exists():
                try:
                    dialogs.extend(self._parse_markdown_file(doc_path))
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка парсинга {doc_name}: {e}")

        # Парсим wiki-pages
        wiki_dir = self.base_dir / "wiki-pages"
        if wiki_dir.exists():
            for wiki_file in wiki_dir.glob("*.md"):
                try:
                    dialogs.extend(self._parse_markdown_file(wiki_file))
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка парсинга {wiki_file.name}: {e}")

        logger.info(f"📝 Из Markdown документации сгенерировано {len(dialogs)} диалогов")
        return dialogs

    def _parse_markdown_file(self, filepath: Path) -> List[dict]:
        """Парсит Markdown файл и генерирует Q&A пары."""
        dialogs = []
        content = filepath.read_text(encoding="utf-8")
        filename = filepath.stem

        # 1. Парсим секции (## заголовки)
        sections = self._split_md_by_headers(content)
        for header, body in sections:
            if len(body.strip()) > 50:  # Минимальная длина контента
                dialogs.extend(self._generate_qa_from_section(header, body, filename))

        # 2. Парсим code blocks
        code_blocks = self._extract_code_blocks(content)
        for lang, code in code_blocks:
            if len(code.strip()) > 20:
                dialogs.extend(self._generate_qa_from_code(lang, code, filename))

        # 3. Парсим таблицы
        tables = self._extract_md_tables(content)
        for table_header, table_content in tables:
            dialogs.extend(self._generate_qa_from_table(table_header, table_content))

        return dialogs

    def _split_md_by_headers(self, content: str) -> List[Tuple[str, str]]:
        """Разбивает Markdown по заголовкам ## и ###."""
        sections = []
        # Паттерн для заголовков уровня 2 и 3
        pattern = r"^(#{2,3})\s+(.+?)$"

        lines = content.split("\n")
        current_header = ""
        current_body = []

        for line in lines:
            match = re.match(pattern, line)
            if match:
                # Сохраняем предыдущую секцию
                if current_header and current_body:
                    sections.append((current_header, "\n".join(current_body)))
                current_header = match.group(2).strip()
                current_body = []
            else:
                current_body.append(line)

        # Последняя секция
        if current_header and current_body:
            sections.append((current_header, "\n".join(current_body)))

        return sections

    def _generate_qa_from_section(self, header: str, body: str, filename: str) -> List[dict]:
        """Генерирует Q&A пары из секции документа."""
        dialogs = []

        # Очищаем body от лишних пробелов
        body = body.strip()
        if len(body) < 30:
            return dialogs

        # Ограничиваем длину ответа
        if len(body) > 1500:
            body = body[:1500] + "..."

        # Определяем тип вопроса по заголовку
        header_lower = header.lower()

        if any(kw in header_lower for kw in ["install", "setup", "установк", "настройк", "запуск"]):
            q = f"Как настроить/установить {header}?"
        elif any(kw in header_lower for kw in ["api", "endpoint", "route"]):
            q = f"Как использовать API {header}?"
        elif any(
            kw in header_lower for kw in ["troubleshoot", "problem", "error", "ошибк", "проблем"]
        ):
            q = f"Как решить проблему с {header}?"
        elif any(kw in header_lower for kw in ["feature", "возможност", "функци"]):
            q = f"Какие возможности есть у {header}?"
        elif any(kw in header_lower for kw in ["require", "требован", "prerequisite"]):
            q = f"Какие требования для {header}?"
        else:
            q = f"Что такое {header}?"

        dialogs.append(self._make_dialog([(q, body)]))
        return dialogs

    def _extract_code_blocks(self, content: str) -> List[Tuple[str, str]]:
        """Извлекает code blocks из Markdown."""
        blocks = []
        pattern = r"```(\w*)\n(.*?)```"
        matches = re.findall(pattern, content, re.DOTALL)
        for lang, code in matches:
            if lang in ("bash", "python", "sh", "shell", ""):
                blocks.append((lang or "bash", code.strip()))
        return blocks[:20]  # Ограничиваем количество

    def _generate_qa_from_code(self, lang: str, code: str, filename: str) -> List[dict]:
        """Генерирует Q&A из code block."""
        dialogs = []

        # Только для коротких примеров команд
        if len(code) > 500 or len(code) < 10:
            return dialogs

        # Определяем тип команды
        if lang in ("bash", "sh", "shell", ""):
            # Извлекаем первую команду
            first_line = code.split("\n")[0].strip()
            if first_line.startswith("#"):
                return dialogs

            if "docker" in first_line:
                q = "Как запустить систему через Docker?"
            elif "curl" in first_line:
                q = "Как вызвать API через curl?"
            elif "git" in first_line:
                q = "Как работать с репозиторием?"
            elif "pip" in first_line or "npm" in first_line:
                q = "Как установить зависимости?"
            elif "pytest" in first_line:
                q = "Как запустить тесты?"
            else:
                q = f"Пример команды из {filename}"

            a = f"```{lang}\n{code}\n```"
            dialogs.append(self._make_dialog([(q, a)]))

        return dialogs

    def _extract_md_tables(self, content: str) -> List[Tuple[str, str]]:
        """Извлекает таблицы из Markdown."""
        tables = []
        # Простой паттерн для таблиц
        pattern = r"(\|.+\|)\n(\|[-:| ]+\|)\n((?:\|.+\|\n?)+)"
        matches = re.findall(pattern, content)

        for header_row, sep_row, body_rows in matches:
            # Извлекаем заголовки колонок
            headers = [h.strip() for h in header_row.split("|") if h.strip()]
            if headers:
                table_content = header_row + "\n" + sep_row + "\n" + body_rows
                tables.append((", ".join(headers[:3]), table_content))

        return tables[:10]

    def _generate_qa_from_table(self, table_header: str, table_content: str) -> List[dict]:
        """Генерирует Q&A из таблицы."""
        dialogs = []

        if len(table_content) > 1000:
            return dialogs

        q = f"Какие параметры/опции доступны ({table_header})?"
        a = table_content
        dialogs.append(self._make_dialog([(q, a)]))

        return dialogs

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

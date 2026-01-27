#!/usr/bin/env python3
"""
Model Manager - управление локальными моделями.
Поиск, загрузка, удаление моделей с HuggingFace и локального хранилища.
"""

import logging
import re
import shutil
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Информация о модели"""

    name: str
    path: str
    size_gb: float
    type: str  # "llm", "tts", "stt", "embedding", "unknown"
    format: str  # "safetensors", "bin", "gguf", "onnx", etc.
    source: str  # "huggingface", "local", "ollama"
    modified: str
    is_cached: bool = False  # В кэше HuggingFace
    repo_id: Optional[str] = None  # HuggingFace repo ID


@dataclass
class DownloadProgress:
    """Прогресс загрузки"""

    is_active: bool = False
    repo_id: str = ""
    filename: str = ""
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed_mbps: float = 0
    eta_seconds: int = 0
    error: Optional[str] = None
    completed: bool = False


@dataclass
class ScanProgress:
    """Прогресс сканирования"""

    is_active: bool = False
    current_path: str = ""
    files_scanned: int = 0
    models_found: int = 0
    error: Optional[str] = None


class ModelManager:
    """Менеджер моделей"""

    # Известные расширения моделей
    MODEL_EXTENSIONS = {
        ".safetensors": "safetensors",
        ".bin": "bin",
        ".gguf": "gguf",
        ".ggml": "ggml",
        ".onnx": "onnx",
        ".pt": "pytorch",
        ".pth": "pytorch",
    }

    # Паттерны для определения типа модели
    TYPE_PATTERNS = {
        "llm": [
            "llama",
            "qwen",
            "mistral",
            "phi",
            "gemma",
            "gpt",
            "falcon",
            "mpt",
            "opt",
            "bloom",
            "codellama",
            "deepseek",
            "yi-",
        ],
        "tts": [
            "tts",
            "xtts",
            "bark",
            "tortoise",
            "coqui",
            "piper",
            "vits",
            "tacotron",
            "fastspeech",
            "qwen3-tts",
            "openvoice",
        ],
        "stt": ["whisper", "vosk", "wav2vec", "hubert", "conformer", "speech"],
        "embedding": ["embed", "bge", "e5-", "sentence", "instructor", "nomic"],
    }

    # Директории для поиска
    SEARCH_PATHS = [
        Path.home() / ".cache" / "huggingface" / "hub",
        Path.home() / ".cache" / "torch" / "hub",
        Path.home() / ".ollama" / "models",
        Path.home() / "models",
        Path("/opt/models"),
        Path("/var/lib/models"),
    ]

    def __init__(self, project_dir: Optional[str] = None):
        self.project_dir = Path(project_dir) if project_dir else Path(__file__).parent
        self.cache_dir = Path.home() / ".cache" / "huggingface" / "hub"

        # State
        self._download_progress = DownloadProgress()
        self._scan_progress = ScanProgress()
        self._models_cache: List[ModelInfo] = []
        self._download_thread: Optional[threading.Thread] = None
        self._scan_thread: Optional[threading.Thread] = None
        self._cancel_download = False
        self._cancel_scan = False

    def get_download_progress(self) -> Dict[str, Any]:
        """Возвращает прогресс загрузки"""
        return asdict(self._download_progress)

    def get_scan_progress(self) -> Dict[str, Any]:
        """Возвращает прогресс сканирования"""
        return asdict(self._scan_progress)

    def get_cached_models(self) -> List[Dict[str, Any]]:
        """Возвращает кэшированный список моделей"""
        return [asdict(m) for m in self._models_cache]

    def _detect_model_type(self, name: str, path: str) -> str:
        """Определяет тип модели по имени и пути"""
        name_lower = name.lower()
        path_lower = path.lower()
        combined = f"{name_lower} {path_lower}"

        for model_type, patterns in self.TYPE_PATTERNS.items():
            for pattern in patterns:
                if pattern in combined:
                    return model_type
        return "unknown"

    def _extract_repo_id(self, path: str) -> Optional[str]:
        """Извлекает repo_id из пути кэша HuggingFace"""
        # Паттерн: models--owner--name
        match = re.search(r"models--([^/\\]+)--([^/\\]+)", path)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
        return None

    def _get_dir_size(self, path: Path) -> float:
        """Получает размер директории в GB"""
        total = 0
        try:
            for f in path.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
        except (PermissionError, OSError):
            pass
        return total / (1024**3)

    def _scan_huggingface_cache(self) -> List[ModelInfo]:
        """Сканирует кэш HuggingFace"""
        models = []
        if not self.cache_dir.exists():
            return models

        for model_dir in self.cache_dir.iterdir():
            if not model_dir.is_dir() or not model_dir.name.startswith("models--"):
                continue

            try:
                self._scan_progress.current_path = str(model_dir)

                repo_id = self._extract_repo_id(str(model_dir))
                name = repo_id.split("/")[-1] if repo_id else model_dir.name

                # Найти snapshot директорию
                snapshots_dir = model_dir / "snapshots"
                if snapshots_dir.exists():
                    # Берём последний snapshot
                    snapshots = sorted(
                        snapshots_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True
                    )
                    if snapshots:
                        snapshot = snapshots[0]
                        size_gb = self._get_dir_size(snapshot)

                        # Определяем формат по файлам
                        formats = set()
                        for f in snapshot.rglob("*"):
                            if f.suffix in self.MODEL_EXTENSIONS:
                                formats.add(self.MODEL_EXTENSIONS[f.suffix])

                        model_format = ", ".join(formats) if formats else "unknown"

                        models.append(
                            ModelInfo(
                                name=name,
                                path=str(model_dir),
                                size_gb=round(size_gb, 2),
                                type=self._detect_model_type(name, str(model_dir)),
                                format=model_format,
                                source="huggingface",
                                modified=datetime.fromtimestamp(
                                    model_dir.stat().st_mtime
                                ).isoformat(),
                                is_cached=True,
                                repo_id=repo_id,
                            )
                        )
                        self._scan_progress.models_found += 1

            except (PermissionError, OSError) as e:
                logger.warning(f"Cannot scan {model_dir}: {e}")

            self._scan_progress.files_scanned += 1
            if self._cancel_scan:
                break

        return models

    def _scan_directory(self, path: Path, source: str = "local") -> List[ModelInfo]:
        """Сканирует директорию на наличие моделей"""
        models = []
        if not path.exists():
            return models

        try:
            for item in path.rglob("*"):
                if self._cancel_scan:
                    break

                self._scan_progress.files_scanned += 1
                self._scan_progress.current_path = str(item)[:100]

                if item.is_file() and item.suffix in self.MODEL_EXTENSIONS:
                    try:
                        size_gb = item.stat().st_size / (1024**3)
                        if size_gb < 0.01:  # Пропускаем очень маленькие файлы
                            continue

                        models.append(
                            ModelInfo(
                                name=item.stem,
                                path=str(item),
                                size_gb=round(size_gb, 2),
                                type=self._detect_model_type(item.stem, str(item)),
                                format=self.MODEL_EXTENSIONS[item.suffix],
                                source=source,
                                modified=datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
                                is_cached=False,
                            )
                        )
                        self._scan_progress.models_found += 1
                    except (PermissionError, OSError):
                        pass

        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot scan {path}: {e}")

        return models

    def scan_all_models(self, include_system: bool = False) -> bool:
        """Запускает полное сканирование моделей"""
        if self._scan_progress.is_active:
            return False

        def _scan():
            try:
                self._scan_progress = ScanProgress(is_active=True)
                self._models_cache = []
                self._cancel_scan = False

                # 1. Сканируем кэш HuggingFace
                logger.info("Scanning HuggingFace cache...")
                self._models_cache.extend(self._scan_huggingface_cache())

                if self._cancel_scan:
                    return

                # 2. Сканируем известные директории
                for search_path in self.SEARCH_PATHS:
                    if self._cancel_scan:
                        break
                    if search_path.exists() and str(search_path) != str(self.cache_dir):
                        logger.info(f"Scanning {search_path}...")
                        source = "ollama" if ".ollama" in str(search_path) else "local"
                        self._models_cache.extend(self._scan_directory(search_path, source))

                # 3. Сканируем директорию проекта
                if self._cancel_scan:
                    return
                logger.info(f"Scanning project dir {self.project_dir}...")
                self._models_cache.extend(
                    self._scan_directory(self.project_dir / "models", "project")
                )
                self._models_cache.extend(
                    self._scan_directory(self.project_dir / "finetune", "project")
                )

                # 4. Опционально сканируем home директорию
                if include_system and not self._cancel_scan:
                    logger.info("Scanning home directory...")
                    home = Path.home()
                    for subdir in ["Downloads", "Documents", "Desktop"]:
                        if self._cancel_scan:
                            break
                        subpath = home / subdir
                        if subpath.exists():
                            self._models_cache.extend(self._scan_directory(subpath, "local"))

                # Удаляем дубликаты по пути
                seen_paths = set()
                unique_models = []
                for model in self._models_cache:
                    if model.path not in seen_paths:
                        seen_paths.add(model.path)
                        unique_models.append(model)
                self._models_cache = unique_models

                logger.info(f"Scan complete: {len(self._models_cache)} models found")

            except Exception as e:
                logger.error(f"Scan error: {e}")
                self._scan_progress.error = str(e)
            finally:
                self._scan_progress.is_active = False

        self._scan_thread = threading.Thread(target=_scan, daemon=True)
        self._scan_thread.start()
        return True

    def cancel_scan(self) -> bool:
        """Отменяет сканирование"""
        if self._scan_progress.is_active:
            self._cancel_scan = True
            return True
        return False

    def download_model(self, repo_id: str, revision: str = "main") -> bool:
        """Загружает модель с HuggingFace"""
        if self._download_progress.is_active:
            return False

        def _download():
            try:
                self._download_progress = DownloadProgress(
                    is_active=True, repo_id=repo_id, filename="Initializing..."
                )
                self._cancel_download = False

                # Используем huggingface-cli для загрузки с прогрессом
                from huggingface_hub import snapshot_download

                # Кастомный callback для прогресса
                def progress_callback(progress):
                    if hasattr(progress, "n") and hasattr(progress, "total"):
                        self._download_progress.downloaded_bytes = progress.n
                        self._download_progress.total_bytes = progress.total or 0
                        if hasattr(progress, "rate") and progress.rate:
                            self._download_progress.speed_mbps = progress.rate / (1024 * 1024)
                        if hasattr(progress, "desc"):
                            self._download_progress.filename = progress.desc or repo_id

                logger.info(f"Downloading {repo_id}...")

                # Загружаем весь репозиторий
                local_dir = snapshot_download(
                    repo_id, revision=revision, resume_download=True, local_dir_use_symlinks=False
                )

                self._download_progress.completed = True
                self._download_progress.filename = f"Completed: {local_dir}"
                logger.info(f"Download complete: {local_dir}")

                # Обновляем кэш моделей
                self.scan_all_models()

            except Exception as e:
                logger.error(f"Download error: {e}")
                self._download_progress.error = str(e)
            finally:
                self._download_progress.is_active = False

        self._download_thread = threading.Thread(target=_download, daemon=True)
        self._download_thread.start()
        return True

    def cancel_download(self) -> bool:
        """Отменяет загрузку"""
        if self._download_progress.is_active:
            self._cancel_download = True
            # К сожалению, huggingface_hub не поддерживает отмену напрямую
            return True
        return False

    def delete_model(self, path: str) -> Dict[str, Any]:
        """Удаляет модель"""
        try:
            target = Path(path)

            if not target.exists():
                return {"status": "error", "message": "Path not found"}

            # Проверяем, что это безопасный путь
            safe_prefixes = [
                str(self.cache_dir),
                str(Path.home() / ".ollama"),
                str(self.project_dir / "models"),
                str(self.project_dir / "finetune"),
            ]

            is_safe = any(str(target).startswith(prefix) for prefix in safe_prefixes)
            if not is_safe:
                return {
                    "status": "error",
                    "message": "Cannot delete models outside safe directories",
                }

            if target.is_dir():
                size = self._get_dir_size(target)
                shutil.rmtree(target)
            else:
                size = target.stat().st_size / (1024**3)
                target.unlink()

            # Обновляем кэш
            self._models_cache = [m for m in self._models_cache if m.path != path]

            return {"status": "ok", "message": f"Deleted {path}", "freed_gb": round(size, 2)}

        except Exception as e:
            logger.error(f"Delete error: {e}")
            return {"status": "error", "message": str(e)}

    def search_huggingface(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Поиск моделей на HuggingFace"""
        try:
            from huggingface_hub import HfApi

            api = HfApi()

            models = api.list_models(search=query, limit=limit, sort="downloads", direction=-1)

            results = []
            for model in models:
                results.append(
                    {
                        "repo_id": model.id,
                        "author": model.author,
                        "downloads": model.downloads,
                        "likes": model.likes,
                        "tags": model.tags[:5] if model.tags else [],
                        "pipeline_tag": model.pipeline_tag,
                        "last_modified": model.last_modified.isoformat()
                        if model.last_modified
                        else None,
                    }
                )

            return results

        except Exception as e:
            logger.error(f"HuggingFace search error: {e}")
            return []

    def get_model_details(self, repo_id: str) -> Optional[Dict[str, Any]]:
        """Получает детали модели с HuggingFace"""
        try:
            from huggingface_hub import model_info

            info = model_info(repo_id)

            # Считаем размер
            total_size = 0
            model_files = []
            for sibling in info.siblings or []:
                if sibling.rfilename:
                    ext = Path(sibling.rfilename).suffix
                    if ext in self.MODEL_EXTENSIONS or sibling.rfilename.endswith(".json"):
                        size = sibling.size or 0
                        total_size += size
                        model_files.append(
                            {"name": sibling.rfilename, "size_mb": round(size / (1024 * 1024), 2)}
                        )

            return {
                "repo_id": repo_id,
                "author": info.author,
                "downloads": info.downloads,
                "likes": info.likes,
                "tags": info.tags,
                "pipeline_tag": info.pipeline_tag,
                "library_name": info.library_name,
                "total_size_gb": round(total_size / (1024**3), 2),
                "files": model_files[:20],  # Первые 20 файлов
                "card_data": info.card_data.__dict__ if info.card_data else None,
            }

        except Exception as e:
            logger.error(f"Model details error: {e}")
            return None


# Global instance
_model_manager: Optional[ModelManager] = None


def get_model_manager() -> ModelManager:
    """Возвращает глобальный менеджер моделей"""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager

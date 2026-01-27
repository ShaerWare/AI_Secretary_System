#!/usr/bin/env python3
"""
Service Manager - управление процессами и сервисами AI Secretary System.
Поддерживает запуск/остановку vLLM и других внешних сервисов.
"""

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional

import psutil


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ServiceConfig:
    """Конфигурация сервиса"""

    name: str
    display_name: str
    start_script: Optional[str] = None
    port: Optional[int] = None
    health_endpoint: Optional[str] = None
    log_file: Optional[str] = None
    venv_path: Optional[str] = None
    internal: bool = False  # True = управляется orchestrator, False = внешний процесс
    gpu_required: bool = False
    cpu_only: bool = False
    pid_file: Optional[str] = None


# Конфигурация всех сервисов системы
SERVICE_CONFIGS: Dict[str, ServiceConfig] = {
    "vllm": ServiceConfig(
        name="vllm",
        display_name="vLLM Server",
        start_script="start_qwen.sh",
        port=11434,
        health_endpoint="/health",
        log_file="logs/vllm.log",
        venv_path=os.path.expanduser("~/vllm_env/venv"),
        internal=False,
        gpu_required=True,
        pid_file="logs/vllm.pid",
    ),
    "xtts_gulya": ServiceConfig(
        name="xtts_gulya",
        display_name="XTTS Gulya",
        internal=True,
        gpu_required=True,
    ),
    "xtts_lidia": ServiceConfig(
        name="xtts_lidia",
        display_name="XTTS Lidia",
        internal=True,
        gpu_required=True,
    ),
    "piper": ServiceConfig(
        name="piper",
        display_name="Piper TTS",
        internal=True,
        cpu_only=True,
    ),
    "openvoice": ServiceConfig(
        name="openvoice",
        display_name="OpenVoice TTS",
        internal=True,
        gpu_required=True,
    ),
    "orchestrator": ServiceConfig(
        name="orchestrator",
        display_name="Orchestrator",
        port=8002,
        health_endpoint="/health",
        log_file="logs/orchestrator.log",
        internal=True,
    ),
}


class ServiceManager:
    """
    Менеджер сервисов для запуска/остановки/мониторинга.

    Особенности:
    - Внешние сервисы (vLLM) запускаются через start_script
    - Внутренние сервисы (XTTS, Piper) управляются orchestrator
    - Поддерживает чтение логов и streaming
    - Отслеживает PID и память процессов
    """

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path(__file__).parent
        self.logs_dir = self.base_dir / "logs"
        self.logs_dir.mkdir(exist_ok=True)

        # Запущенные процессы (только внешние, управляемые этим классом)
        self.processes: Dict[str, subprocess.Popen] = {}

        # Последние ошибки
        self.last_errors: Dict[str, str] = {}

        # Время запуска сервисов
        self.start_times: Dict[str, datetime] = {}

        logger.info(f"🔧 ServiceManager инициализирован: {self.base_dir}")

    def _get_config(self, service_name: str) -> ServiceConfig:
        """Получает конфигурацию сервиса"""
        if service_name not in SERVICE_CONFIGS:
            raise ValueError(f"Неизвестный сервис: {service_name}")
        return SERVICE_CONFIGS[service_name]

    def _find_process_by_port(self, port: int) -> Optional[psutil.Process]:
        """Находит процесс, слушающий указанный порт"""
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr.port == port and conn.status == "LISTEN":
                try:
                    return psutil.Process(conn.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        return None

    def _find_process_by_pid_file(self, pid_file: str) -> Optional[psutil.Process]:
        """Находит процесс по PID файлу"""
        pid_path = self.base_dir / pid_file
        if pid_path.exists():
            try:
                pid = int(pid_path.read_text().strip())
                proc = psutil.Process(pid)
                if proc.is_running():
                    return proc
            except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return None

    def _is_service_running(self, service_name: str) -> tuple[bool, Optional[int], Optional[float]]:
        """
        Проверяет, запущен ли сервис.
        Returns: (is_running, pid, memory_mb)
        """
        config = self._get_config(service_name)

        # Проверяем внутренний процесс
        if service_name in self.processes:
            proc = self.processes[service_name]
            if proc.poll() is None:  # Still running
                try:
                    ps_proc = psutil.Process(proc.pid)
                    memory_mb = ps_proc.memory_info().rss / (1024 * 1024)
                    return True, proc.pid, memory_mb
                except psutil.NoSuchProcess:
                    pass
            # Процесс завершился
            del self.processes[service_name]

        # Проверяем по PID файлу
        if config.pid_file:
            proc = self._find_process_by_pid_file(config.pid_file)
            if proc:
                memory_mb = proc.memory_info().rss / (1024 * 1024)
                return True, proc.pid, memory_mb

        # Проверяем по порту
        if config.port:
            proc = self._find_process_by_port(config.port)
            if proc:
                memory_mb = proc.memory_info().rss / (1024 * 1024)
                return True, proc.pid, memory_mb

        return False, None, None

    async def _check_health(self, service_name: str) -> bool:
        """Проверяет health endpoint сервиса"""
        config = self._get_config(service_name)

        if not config.port or not config.health_endpoint:
            return True  # Нет health check = считаем OK если процесс работает

        import httpx

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                url = f"http://localhost:{config.port}{config.health_endpoint}"
                response = await client.get(url)
                return response.status_code == 200
        except Exception:
            return False

    async def start_service(self, service_name: str) -> dict:
        """
        Запускает сервис.
        Returns: {"status": "ok/error", "message": str, "pid": int}
        """
        config = self._get_config(service_name)

        if config.internal:
            return {
                "status": "error",
                "message": f"Сервис {config.display_name} управляется orchestrator, перезапустите orchestrator",
            }

        # Проверяем, не запущен ли уже
        is_running, pid, _ = self._is_service_running(service_name)
        if is_running:
            return {"status": "ok", "message": f"{config.display_name} уже запущен", "pid": pid}

        if not config.start_script:
            return {"status": "error", "message": f"Нет скрипта запуска для {config.display_name}"}

        script_path = self.base_dir / config.start_script
        if not script_path.exists():
            return {"status": "error", "message": f"Скрипт не найден: {script_path}"}

        try:
            # Запускаем процесс
            log_file = (
                self.logs_dir / f"{service_name}.log"
                if not config.log_file
                else self.base_dir / config.log_file
            )

            with open(log_file, "a") as log:
                log.write(f"\n{'=' * 60}\n")
                log.write(f"Starting {config.display_name} at {datetime.now().isoformat()}\n")
                log.write(f"{'=' * 60}\n")

            env = os.environ.copy()

            # Активируем venv если указан
            if config.venv_path:
                venv_bin = Path(config.venv_path) / "bin"
                env["PATH"] = f"{venv_bin}:{env['PATH']}"
                env["VIRTUAL_ENV"] = config.venv_path

            proc = subprocess.Popen(
                ["bash", str(script_path)],
                stdout=open(log_file, "a"),
                stderr=subprocess.STDOUT,
                cwd=str(self.base_dir),
                env=env,
                start_new_session=True,  # Отсоединяем от родительского процесса
            )

            self.processes[service_name] = proc
            self.start_times[service_name] = datetime.now()

            # Ждем немного и проверяем, что процесс не упал
            await asyncio.sleep(2)

            if proc.poll() is not None:
                # Процесс завершился
                return {
                    "status": "error",
                    "message": f"{config.display_name} завершился сразу после запуска. Проверьте логи.",
                }

            # Сохраняем PID
            if config.pid_file:
                pid_path = self.base_dir / config.pid_file
                pid_path.write_text(str(proc.pid))

            logger.info(f"✅ {config.display_name} запущен (PID: {proc.pid})")

            return {"status": "ok", "message": f"{config.display_name} запущен", "pid": proc.pid}

        except Exception as e:
            error_msg = str(e)
            self.last_errors[service_name] = error_msg
            logger.error(f"❌ Ошибка запуска {config.display_name}: {error_msg}")
            return {"status": "error", "message": f"Ошибка запуска: {error_msg}"}

    async def stop_service(self, service_name: str) -> dict:
        """Останавливает сервис"""
        config = self._get_config(service_name)

        if config.internal:
            return {
                "status": "error",
                "message": f"Сервис {config.display_name} управляется orchestrator",
            }

        is_running, pid, _ = self._is_service_running(service_name)
        if not is_running:
            return {"status": "ok", "message": f"{config.display_name} уже остановлен"}

        try:
            # Пытаемся остановить gracefully через SIGTERM
            if service_name in self.processes:
                proc = self.processes[service_name]
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                del self.processes[service_name]
            else:
                # Процесс не наш - ищем по PID/порту
                proc = None
                if config.pid_file:
                    proc = self._find_process_by_pid_file(config.pid_file)
                if not proc and config.port:
                    proc = self._find_process_by_port(config.port)

                if proc:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except psutil.TimeoutExpired:
                        proc.kill()

            # Удаляем PID файл
            if config.pid_file:
                pid_path = self.base_dir / config.pid_file
                if pid_path.exists():
                    pid_path.unlink()

            # Убираем из времени запуска
            self.start_times.pop(service_name, None)

            logger.info(f"🛑 {config.display_name} остановлен")

            return {"status": "ok", "message": f"{config.display_name} остановлен"}

        except Exception as e:
            error_msg = str(e)
            self.last_errors[service_name] = error_msg
            logger.error(f"❌ Ошибка остановки {config.display_name}: {error_msg}")
            return {"status": "error", "message": f"Ошибка остановки: {error_msg}"}

    async def restart_service(self, service_name: str) -> dict:
        """Перезапускает сервис"""
        self._get_config(service_name)  # Validate service exists

        stop_result = await self.stop_service(service_name)
        if stop_result["status"] == "error" and "управляется orchestrator" not in stop_result.get(
            "message", ""
        ):
            return stop_result

        # Даем время на освобождение порта
        await asyncio.sleep(2)

        return await self.start_service(service_name)

    def get_service_status(self, service_name: str) -> dict:
        """Получает статус сервиса"""
        config = self._get_config(service_name)
        is_running, pid, memory_mb = self._is_service_running(service_name)

        status = {
            "name": service_name,
            "display_name": config.display_name,
            "is_running": is_running,
            "pid": pid,
            "memory_mb": round(memory_mb, 2) if memory_mb else None,
            "port": config.port,
            "internal": config.internal,
            "gpu_required": config.gpu_required,
            "cpu_only": config.cpu_only,
            "log_file": config.log_file,
            "last_error": self.last_errors.get(service_name),
        }

        # Добавляем uptime
        if service_name in self.start_times and is_running:
            uptime = datetime.now() - self.start_times[service_name]
            status["uptime_seconds"] = uptime.total_seconds()

        return status

    def get_all_status(self) -> dict:
        """Получает статус всех сервисов"""
        services = {}
        for name in SERVICE_CONFIGS:
            services[name] = self.get_service_status(name)
        return {"services": services, "timestamp": datetime.now().isoformat()}

    def read_log(
        self, service_name: str, lines: int = 100, offset: int = 0, search: Optional[str] = None
    ) -> dict:
        """
        Читает логи сервиса.

        Args:
            service_name: Имя сервиса или имя лог-файла
            lines: Количество строк
            offset: Пропустить N строк с конца
            search: Фильтр по подстроке

        Returns:
            {"lines": [...], "total_lines": int, "file": str}
        """
        # Определяем путь к логу
        if service_name in SERVICE_CONFIGS:
            config = SERVICE_CONFIGS[service_name]
            if config.log_file:
                log_path = self.base_dir / config.log_file
            else:
                log_path = self.logs_dir / f"{service_name}.log"
        else:
            # Возможно это имя файла
            log_path = self.logs_dir / service_name
            if not log_path.exists():
                log_path = self.base_dir / service_name

        if not log_path.exists():
            return {
                "lines": [],
                "total_lines": 0,
                "file": str(log_path),
                "error": "Лог файл не найден",
            }

        try:
            with open(log_path, encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()

            # Фильтруем по поиску если указан
            if search:
                all_lines = [line for line in all_lines if search.lower() in line.lower()]

            total = len(all_lines)

            # Применяем offset и limit
            if offset > 0:
                end_idx = max(0, total - offset)
                start_idx = max(0, end_idx - lines)
            else:
                start_idx = max(0, total - lines)
                end_idx = total

            result_lines = all_lines[start_idx:end_idx]

            return {
                "lines": [line.rstrip("\n") for line in result_lines],
                "total_lines": total,
                "file": str(log_path),
                "start_line": start_idx + 1,
                "end_line": end_idx,
            }

        except Exception as e:
            return {"lines": [], "total_lines": 0, "file": str(log_path), "error": str(e)}

    async def stream_log(
        self, service_name: str, interval: float = 1.0
    ) -> AsyncGenerator[str, None]:
        """
        Async generator для SSE streaming логов.
        Возвращает новые строки по мере их появления.
        """
        # Определяем путь к логу
        if service_name in SERVICE_CONFIGS:
            config = SERVICE_CONFIGS[service_name]
            if config.log_file:
                log_path = self.base_dir / config.log_file
            else:
                log_path = self.logs_dir / f"{service_name}.log"
        else:
            log_path = self.logs_dir / service_name

        if not log_path.exists():
            yield json.dumps({"error": "Лог файл не найден", "file": str(log_path)})
            return

        # Начинаем с конца файла
        last_position = log_path.stat().st_size

        while True:
            try:
                current_size = log_path.stat().st_size

                if current_size > last_position:
                    # Есть новые данные
                    with open(log_path, encoding="utf-8", errors="replace") as f:
                        f.seek(last_position)
                        new_content = f.read()
                        last_position = f.tell()

                    # Отправляем новые строки
                    for line in new_content.splitlines():
                        if line.strip():
                            yield json.dumps(
                                {"line": line, "timestamp": datetime.now().isoformat()}
                            )

                elif current_size < last_position:
                    # Файл был перезаписан (rotate)
                    last_position = 0

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                yield json.dumps({"error": str(e)})
                await asyncio.sleep(interval)

    def get_available_logs(self) -> List[dict]:
        """Возвращает список доступных лог-файлов"""
        logs = []

        # Логи из конфигураций сервисов
        for name, config in SERVICE_CONFIGS.items():
            if config.log_file:
                log_path = self.base_dir / config.log_file
                if log_path.exists():
                    stat = log_path.stat()
                    logs.append(
                        {
                            "name": name,
                            "file": config.log_file,
                            "display_name": config.display_name,
                            "size_kb": round(stat.st_size / 1024, 2),
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        }
                    )

        # Дополнительные логи в папке logs
        for log_file in self.logs_dir.glob("*.log"):
            if not any(
                log_file.name == Path(c.log_file).name
                for c in SERVICE_CONFIGS.values()
                if c.log_file
            ):
                stat = log_file.stat()
                logs.append(
                    {
                        "name": log_file.stem,
                        "file": str(log_file.relative_to(self.base_dir)),
                        "display_name": log_file.stem,
                        "size_kb": round(stat.st_size / 1024, 2),
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    }
                )

        return sorted(logs, key=lambda x: x["modified"], reverse=True)


# Глобальный экземпляр для использования в orchestrator
_service_manager: Optional[ServiceManager] = None


def get_service_manager() -> ServiceManager:
    """Получает или создает глобальный ServiceManager"""
    global _service_manager
    if _service_manager is None:
        _service_manager = ServiceManager()
    return _service_manager


if __name__ == "__main__":
    import asyncio

    async def test():
        manager = ServiceManager()

        print("=== Service Status ===")
        status = manager.get_all_status()
        for name, info in status["services"].items():
            running = "✅" if info["is_running"] else "❌"
            print(
                f"{running} {info['display_name']}: PID={info['pid']}, Memory={info['memory_mb']}MB"
            )

        print("\n=== Available Logs ===")
        for log in manager.get_available_logs():
            print(f"  - {log['display_name']}: {log['file']} ({log['size_kb']}KB)")

        print("\n=== Recent vLLM Logs ===")
        logs = manager.read_log("vllm", lines=10)
        for line in logs["lines"]:
            print(f"  {line}")

    asyncio.run(test())

#!/usr/bin/env python3
"""
System Monitor - полный мониторинг аппаратного обеспечения.
GPU, CPU, RAM, диски, Docker контейнеры, сеть.
"""

import json
import logging
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class GpuInfo:
    """Информация о GPU"""

    index: int
    name: str
    driver_version: str = ""
    memory_total_mb: int = 0
    memory_used_mb: int = 0
    memory_free_mb: int = 0
    utilization_percent: int = 0
    temperature_c: int = 0
    power_draw_w: float = 0
    power_limit_w: float = 0
    fan_speed_percent: int = 0
    compute_capability: str = ""
    pcie_gen: int = 0
    pcie_width: int = 0


@dataclass
class CpuInfo:
    """Информация о CPU"""

    model: str = ""
    cores_physical: int = 0
    cores_logical: int = 0
    frequency_mhz: float = 0
    frequency_max_mhz: float = 0
    usage_percent: float = 0
    usage_per_core: List[float] = None
    temperature_c: float = 0
    load_avg_1m: float = 0
    load_avg_5m: float = 0
    load_avg_15m: float = 0


@dataclass
class MemoryInfo:
    """Информация о памяти"""

    total_gb: float = 0
    used_gb: float = 0
    free_gb: float = 0
    available_gb: float = 0
    percent_used: float = 0
    swap_total_gb: float = 0
    swap_used_gb: float = 0
    swap_percent: float = 0


@dataclass
class DiskInfo:
    """Информация о диске"""

    device: str = ""
    mountpoint: str = ""
    fstype: str = ""
    total_gb: float = 0
    used_gb: float = 0
    free_gb: float = 0
    percent_used: float = 0


@dataclass
class DockerContainer:
    """Информация о Docker контейнере"""

    id: str = ""
    name: str = ""
    image: str = ""
    status: str = ""
    state: str = ""  # running, exited, paused
    ports: str = ""
    cpu_percent: float = 0
    memory_mb: float = 0
    memory_limit_mb: float = 0
    memory_percent: float = 0
    created: str = ""
    uptime: str = ""


@dataclass
class NetworkInfo:
    """Информация о сети"""

    interface: str = ""
    ip_address: str = ""
    mac_address: str = ""
    bytes_sent_mb: float = 0
    bytes_recv_mb: float = 0
    packets_sent: int = 0
    packets_recv: int = 0
    is_up: bool = True


@dataclass
class ProcessInfo:
    """Информация о процессе"""

    pid: int = 0
    name: str = ""
    cpu_percent: float = 0
    memory_percent: float = 0
    memory_mb: float = 0
    status: str = ""
    cmdline: str = ""


class SystemMonitor:
    """Класс для мониторинга системы"""

    def __init__(self):
        self._psutil_available = False
        self._torch_available = False
        self._docker_available = False

        try:
            import psutil

            self._psutil = psutil
            self._psutil_available = True
        except ImportError:
            logger.warning("psutil не установлен")

        try:
            import torch

            self._torch = torch
            self._torch_available = torch.cuda.is_available()
        except ImportError:
            logger.warning("torch не установлен")

        # Проверяем Docker
        try:
            result = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
            self._docker_available = result.returncode == 0
        except Exception:
            self._docker_available = False

    def get_gpu_info(self) -> List[GpuInfo]:
        """Получает информацию о всех GPU через nvidia-smi"""
        gpus = []

        try:
            # Используем nvidia-smi для полной информации
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,driver_version,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw,power.limit,fan.speed,pcie.link.gen.current,pcie.link.width.current",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 13:
                        try:
                            gpu = GpuInfo(
                                index=int(parts[0]),
                                name=parts[1],
                                driver_version=parts[2],
                                memory_total_mb=int(float(parts[3])),
                                memory_used_mb=int(float(parts[4])),
                                memory_free_mb=int(float(parts[5])),
                                utilization_percent=int(float(parts[6]))
                                if parts[6] != "[Not Supported]"
                                else 0,
                                temperature_c=int(float(parts[7]))
                                if parts[7] != "[Not Supported]"
                                else 0,
                                power_draw_w=float(parts[8])
                                if parts[8] != "[Not Supported]"
                                else 0,
                                power_limit_w=float(parts[9])
                                if parts[9] != "[Not Supported]"
                                else 0,
                                fan_speed_percent=int(float(parts[10]))
                                if parts[10] != "[Not Supported]"
                                else 0,
                                pcie_gen=int(parts[11]) if parts[11] != "[Not Supported]" else 0,
                                pcie_width=int(parts[12]) if parts[12] != "[Not Supported]" else 0,
                            )

                            # Добавляем compute capability через torch
                            if (
                                self._torch_available
                                and gpu.index < self._torch.cuda.device_count()
                            ):
                                props = self._torch.cuda.get_device_properties(gpu.index)
                                gpu.compute_capability = f"{props.major}.{props.minor}"

                            gpus.append(gpu)
                        except (ValueError, IndexError) as e:
                            logger.warning(f"Ошибка парсинга GPU info: {e}")

        except FileNotFoundError:
            logger.warning("nvidia-smi не найден")
        except subprocess.TimeoutExpired:
            logger.warning("nvidia-smi timeout")
        except Exception as e:
            logger.error(f"Ошибка получения GPU info: {e}")

        # Fallback на torch если nvidia-smi не сработал
        if not gpus and self._torch_available:
            for i in range(self._torch.cuda.device_count()):
                props = self._torch.cuda.get_device_properties(i)
                total = props.total_memory // (1024 * 1024)
                allocated = self._torch.cuda.memory_allocated(i) // (1024 * 1024)
                gpus.append(
                    GpuInfo(
                        index=i,
                        name=props.name,
                        memory_total_mb=total,
                        memory_used_mb=allocated,
                        memory_free_mb=total - allocated,
                        compute_capability=f"{props.major}.{props.minor}",
                    )
                )

        return gpus

    def get_cpu_info(self) -> CpuInfo:
        """Получает информацию о CPU"""
        info = CpuInfo()

        if not self._psutil_available:
            return info

        try:
            # Модель CPU
            try:
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if "model name" in line:
                            info.model = line.split(":")[1].strip()
                            break
            except Exception:
                info.model = "Unknown"

            # Ядра
            info.cores_physical = self._psutil.cpu_count(logical=False) or 0
            info.cores_logical = self._psutil.cpu_count(logical=True) or 0

            # Частота
            freq = self._psutil.cpu_freq()
            if freq:
                info.frequency_mhz = round(freq.current, 0)
                info.frequency_max_mhz = round(freq.max, 0) if freq.max else info.frequency_mhz

            # Использование
            info.usage_percent = self._psutil.cpu_percent(interval=0.1)
            info.usage_per_core = self._psutil.cpu_percent(interval=0.1, percpu=True)

            # Load average
            load = os.getloadavg()
            info.load_avg_1m = round(load[0], 2)
            info.load_avg_5m = round(load[1], 2)
            info.load_avg_15m = round(load[2], 2)

            # Температура CPU
            try:
                temps = self._psutil.sensors_temperatures()
                if "coretemp" in temps:
                    info.temperature_c = max(t.current for t in temps["coretemp"])
                elif "k10temp" in temps:  # AMD
                    info.temperature_c = max(t.current for t in temps["k10temp"])
                elif temps:
                    # Берём первый доступный сенсор
                    first_sensor = list(temps.values())[0]
                    if first_sensor:
                        info.temperature_c = first_sensor[0].current
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Ошибка получения CPU info: {e}")

        return info

    def get_memory_info(self) -> MemoryInfo:
        """Получает информацию о памяти"""
        info = MemoryInfo()

        if not self._psutil_available:
            return info

        try:
            mem = self._psutil.virtual_memory()
            info.total_gb = round(mem.total / (1024**3), 2)
            info.used_gb = round(mem.used / (1024**3), 2)
            info.free_gb = round(mem.free / (1024**3), 2)
            info.available_gb = round(mem.available / (1024**3), 2)
            info.percent_used = mem.percent

            swap = self._psutil.swap_memory()
            info.swap_total_gb = round(swap.total / (1024**3), 2)
            info.swap_used_gb = round(swap.used / (1024**3), 2)
            info.swap_percent = swap.percent

        except Exception as e:
            logger.error(f"Ошибка получения memory info: {e}")

        return info

    def get_disk_info(self) -> List[DiskInfo]:
        """Получает информацию о дисках"""
        disks = []

        if not self._psutil_available:
            return disks

        try:
            for partition in self._psutil.disk_partitions():
                # Пропускаем виртуальные ФС
                if partition.fstype in ["squashfs", "tmpfs", "devtmpfs"]:
                    continue
                if "/snap/" in partition.mountpoint:
                    continue

                try:
                    usage = self._psutil.disk_usage(partition.mountpoint)
                    disks.append(
                        DiskInfo(
                            device=partition.device,
                            mountpoint=partition.mountpoint,
                            fstype=partition.fstype,
                            total_gb=round(usage.total / (1024**3), 2),
                            used_gb=round(usage.used / (1024**3), 2),
                            free_gb=round(usage.free / (1024**3), 2),
                            percent_used=usage.percent,
                        )
                    )
                except PermissionError:
                    pass

        except Exception as e:
            logger.error(f"Ошибка получения disk info: {e}")

        return disks

    def get_docker_containers(self) -> List[DockerContainer]:
        """Получает информацию о Docker контейнерах"""
        containers = []

        if not self._docker_available:
            return containers

        try:
            # Получаем список контейнеров
            result = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        container = DockerContainer(
                            id=data.get("ID", "")[:12],
                            name=data.get("Names", ""),
                            image=data.get("Image", ""),
                            status=data.get("Status", ""),
                            state=data.get("State", ""),
                            ports=data.get("Ports", ""),
                            created=data.get("CreatedAt", ""),
                        )
                        containers.append(container)
                    except json.JSONDecodeError:
                        pass

            # Получаем статистику для запущенных контейнеров
            result = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                stats_map = {}
                for line in result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        name = data.get("Name", "")
                        stats_map[name] = {
                            "cpu": self._parse_percent(data.get("CPUPerc", "0%")),
                            "mem_usage": data.get("MemUsage", ""),
                            "mem_perc": self._parse_percent(data.get("MemPerc", "0%")),
                        }
                    except json.JSONDecodeError:
                        pass

                # Обновляем контейнеры статистикой
                for c in containers:
                    if c.name in stats_map:
                        stats = stats_map[c.name]
                        c.cpu_percent = stats["cpu"]
                        c.memory_percent = stats["mem_perc"]
                        # Парсим использование памяти
                        mem_usage = stats["mem_usage"]
                        if "/" in mem_usage:
                            used, limit = mem_usage.split("/")
                            c.memory_mb = self._parse_memory(used.strip())
                            c.memory_limit_mb = self._parse_memory(limit.strip())

        except subprocess.TimeoutExpired:
            logger.warning("docker stats timeout")
        except Exception as e:
            logger.error(f"Ошибка получения docker info: {e}")

        return containers

    def get_network_info(self) -> List[NetworkInfo]:
        """Получает информацию о сетевых интерфейсах"""
        networks = []

        if not self._psutil_available:
            return networks

        try:
            # Получаем адреса
            addrs = self._psutil.net_if_addrs()
            stats = self._psutil.net_if_stats()
            io = self._psutil.net_io_counters(pernic=True)

            for iface, addr_list in addrs.items():
                # Пропускаем loopback и виртуальные
                if iface.startswith(("lo", "docker", "br-", "veth")):
                    continue

                info = NetworkInfo(interface=iface)

                for addr in addr_list:
                    if addr.family.name == "AF_INET":
                        info.ip_address = addr.address
                    elif addr.family.name == "AF_PACKET":
                        info.mac_address = addr.address

                if iface in stats:
                    info.is_up = stats[iface].isup

                if iface in io:
                    info.bytes_sent_mb = round(io[iface].bytes_sent / (1024**2), 2)
                    info.bytes_recv_mb = round(io[iface].bytes_recv / (1024**2), 2)
                    info.packets_sent = io[iface].packets_sent
                    info.packets_recv = io[iface].packets_recv

                if info.ip_address:  # Только интерфейсы с IP
                    networks.append(info)

        except Exception as e:
            logger.error(f"Ошибка получения network info: {e}")

        return networks

    def get_top_processes(self, limit: int = 10) -> List[ProcessInfo]:
        """Получает топ процессов по использованию ресурсов"""
        processes = []

        if not self._psutil_available:
            return processes

        try:
            procs = []
            for proc in self._psutil.process_iter(
                ["pid", "name", "cpu_percent", "memory_percent", "memory_info", "status", "cmdline"]
            ):
                try:
                    pinfo = proc.info
                    if pinfo["cpu_percent"] or pinfo["memory_percent"]:
                        procs.append(pinfo)
                except (self._psutil.NoSuchProcess, self._psutil.AccessDenied):
                    pass

            # Сортируем по CPU + Memory
            procs.sort(
                key=lambda x: (x["cpu_percent"] or 0) + (x["memory_percent"] or 0), reverse=True
            )

            for p in procs[:limit]:
                mem_mb = p["memory_info"].rss / (1024**2) if p["memory_info"] else 0
                cmdline = " ".join(p["cmdline"][:5]) if p["cmdline"] else p["name"]
                processes.append(
                    ProcessInfo(
                        pid=p["pid"],
                        name=p["name"],
                        cpu_percent=round(p["cpu_percent"] or 0, 1),
                        memory_percent=round(p["memory_percent"] or 0, 1),
                        memory_mb=round(mem_mb, 1),
                        status=p["status"],
                        cmdline=cmdline[:100],
                    )
                )

        except Exception as e:
            logger.error(f"Ошибка получения process info: {e}")

        return processes

    def get_system_info(self) -> Dict[str, Any]:
        """Получает общую информацию о системе"""
        info = {
            "hostname": "",
            "os": "",
            "kernel": "",
            "uptime": "",
            "boot_time": "",
        }

        try:
            import platform

            info["hostname"] = platform.node()
            info["os"] = f"{platform.system()} {platform.release()}"
            info["kernel"] = platform.release()

            if self._psutil_available:
                boot = self._psutil.boot_time()
                info["boot_time"] = datetime.fromtimestamp(boot).isoformat()
                uptime_sec = (datetime.now() - datetime.fromtimestamp(boot)).total_seconds()
                days = int(uptime_sec // 86400)
                hours = int((uptime_sec % 86400) // 3600)
                minutes = int((uptime_sec % 3600) // 60)
                info["uptime"] = f"{days}d {hours}h {minutes}m"

        except Exception as e:
            logger.error(f"Ошибка получения system info: {e}")

        return info

    def get_full_status(self) -> Dict[str, Any]:
        """Получает полную информацию о системе"""
        return {
            "system": self.get_system_info(),
            "gpus": [asdict(g) for g in self.get_gpu_info()],
            "cpu": asdict(self.get_cpu_info()),
            "memory": asdict(self.get_memory_info()),
            "disks": [asdict(d) for d in self.get_disk_info()],
            "docker": [asdict(c) for c in self.get_docker_containers()],
            "network": [asdict(n) for n in self.get_network_info()],
            "processes": [asdict(p) for p in self.get_top_processes()],
            "timestamp": datetime.now().isoformat(),
        }

    def _parse_percent(self, s: str) -> float:
        """Парсит процент из строки типа '12.5%'"""
        try:
            return float(s.rstrip("%"))
        except (ValueError, AttributeError):
            return 0.0

    def _parse_memory(self, s: str) -> float:
        """Парсит память из строки типа '1.5GiB' или '512MiB'"""
        try:
            s = s.upper()
            if "GIB" in s or "GB" in s:
                return float(s.replace("GIB", "").replace("GB", "").strip()) * 1024
            elif "MIB" in s or "MB" in s:
                return float(s.replace("MIB", "").replace("MB", "").strip())
            elif "KIB" in s or "KB" in s:
                return float(s.replace("KIB", "").replace("KB", "").strip()) / 1024
            return float(s)
        except (ValueError, AttributeError):
            return 0.0


# Глобальный экземпляр
_system_monitor: Optional[SystemMonitor] = None


def get_system_monitor() -> SystemMonitor:
    """Получает глобальный SystemMonitor"""
    global _system_monitor
    if _system_monitor is None:
        _system_monitor = SystemMonitor()
    return _system_monitor


if __name__ == "__main__":
    monitor = SystemMonitor()
    status = monitor.get_full_status()
    print(json.dumps(status, indent=2, default=str))

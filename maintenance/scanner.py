import getpass
import hashlib
import json
import os
import platform
import subprocess
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from maintenance.models import (
    DashboardSnapshot,
    FileCandidate,
    ProcessCandidate,
    ResourceSummary,
)

try:
    import psutil
except ImportError:
    psutil = None

try:
    import pynvml
except ImportError:
    pynvml = None


class SystemScanner:
    """Read system state and discover reviewable cleanup candidates."""

    BYTES_IN_GIB: int = 1024**3
    LARGE_FILE_BYTES: int = 100 * 1024**2
    DUPLICATE_MIN_BYTES: int = 1024**2
    HASH_CHUNK_BYTES: int = 1024**2
    PROCESS_MIN_BYTES: int = 10 * 1024**2

    PROTECTED_PROCESS_NAMES: set[str] = {
        "csrss.exe",
        "controlcenter",
        "dwm.exe",
        "dock",
        "explorer.exe",
        "finder",
        "init",
        "kernel_task",
        "kthreadd",
        "launchd",
        "lsass.exe",
        "loginwindow",
        "registry",
        "services.exe",
        "smss.exe",
        "system",
        "systemd",
        "systemuiserver",
        "terminal",
        "wininit.exe",
        "winlogon.exe",
        "windowserver",
    }

    def __init__(self, downloads_path: Path | None = None) -> None:
        self.downloads_path = downloads_path or self._default_downloads_path()

    @staticmethod
    def _require_psutil() -> None:
        if psutil is None:
            raise RuntimeError(
                "psutil is not installed. Run: python -m pip install psutil"
            )

    @classmethod
    def format_bytes(cls, number_of_bytes: int | float) -> str:
        value = float(number_of_bytes)
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if abs(value) < 1024 or unit == "TiB":
                return f"{value:.2f} {unit}"
            value /= 1024
        return f"{value:.2f} TiB"

    def scan_dashboard(self) -> DashboardSnapshot:
        self._require_psutil()

        cpu_percent = psutil.cpu_percent(interval=0.2)
        frequency = psutil.cpu_freq()
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage(str(Path.home()))
        network = psutil.net_io_counters()
        battery = psutil.sensors_battery()
        gpu_details = self.gpu_details()

        cpu_frequency = f"{frequency.current:.0f} MHz" if frequency else "Unavailable"
        battery_value = (
            f"{battery.percent:.0f}%" if battery is not None else "Unavailable"
        )
        battery_subtitle = "No battery information"
        battery_percent: float | None = None
        battery_details = ("Battery information is unavailable.",)

        if battery is not None:
            battery_percent = battery.percent
            battery_subtitle = "Charging" if battery.power_plugged else "Not charging"
            battery_details = (
                f"Charge: {battery.percent:.1f}%",
                f"Power: {battery_subtitle}",
            )

        resources = (
            ResourceSummary(
                key="cpu",
                title="CPU",
                value=f"{cpu_percent:.1f}%",
                subtitle="Current processor usage",
                percent=cpu_percent,
                details=(
                    f"Physical cores: {psutil.cpu_count(logical=False) or 'Unknown'}",
                    f"Logical cores: {psutil.cpu_count(logical=True) or 'Unknown'}",
                    f"Current frequency: {cpu_frequency}",
                ),
                actionable=True,
            ),
            ResourceSummary(
                key="memory",
                title="Memory",
                value=f"{memory.percent:.1f}%",
                subtitle=f"{self.format_bytes(memory.available)} available",
                percent=memory.percent,
                details=(
                    f"RAM total: {self.format_bytes(memory.total)}",
                    f"RAM used: {self.format_bytes(memory.used)}",
                    f"RAM available: {self.format_bytes(memory.available)}",
                    f"Swap used: {self.format_bytes(swap.used)} of "
                    f"{self.format_bytes(swap.total)} ({swap.percent:.1f}%)",
                ),
                actionable=True,
            ),
            ResourceSummary(
                key="storage",
                title="Storage",
                value=f"{disk.percent:.1f}%",
                subtitle=f"{self.format_bytes(disk.free)} free",
                percent=disk.percent,
                details=(
                    f"Main disk: {Path.home()}",
                    f"Total: {self.format_bytes(disk.total)}",
                    f"Used: {self.format_bytes(disk.used)}",
                    f"Free: {self.format_bytes(disk.free)}",
                    f"Downloads: {self.downloads_path}",
                    f"Trash size: {self.format_bytes(self.trash_size())}",
                ),
                actionable=True,
            ),
            ResourceSummary(
                key="gpu",
                title="GPU",
                value=gpu_details[0],
                subtitle="Graphics hardware",
                percent=None,
                details=gpu_details,
            ),
            ResourceSummary(
                key="network",
                title="Network",
                value=self.format_bytes(network.bytes_sent + network.bytes_recv),
                subtitle="Transferred since startup",
                percent=None,
                details=(
                    f"Data sent: {self.format_bytes(network.bytes_sent)}",
                    f"Data received: {self.format_bytes(network.bytes_recv)}",
                ),
            ),
            ResourceSummary(
                key="battery",
                title="Battery",
                value=battery_value,
                subtitle=battery_subtitle,
                percent=battery_percent,
                details=battery_details,
            ),
        )

        system_label = (
            f"{platform.system()} {platform.release()} • {platform.machine()}"
        )
        return DashboardSnapshot(
            system_label=system_label,
            scanned_at=datetime.now(),
            resources=resources,
        )

    def scan_processes(self) -> list[ProcessCandidate]:
        self._require_psutil()
        current_user = getpass.getuser()
        protected_pids = self._protected_pids()
        processes = list(psutil.process_iter())

        for process in processes:
            try:
                process.cpu_percent(None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        time.sleep(0.25)
        candidates: list[ProcessCandidate] = []

        for process in processes:
            try:
                info = process.as_dict(attrs=["pid", "name", "username", "memory_info"])
                cpu_percent = process.cpu_percent(None)
                memory_bytes = info["memory_info"].rss
                memory_percent = process.memory_percent()
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                continue

            if memory_bytes < self.PROCESS_MIN_BYTES and cpu_percent < 1:
                continue

            name = info["name"] or f"Process {info['pid']}"
            username = info["username"] or "Unknown"
            protected_name = name.casefold() in self.PROTECTED_PROCESS_NAMES
            action_allowed = (
                self._same_user(username, current_user)
                and info["pid"] not in protected_pids
                and not protected_name
            )
            activity = "Low activity" if cpu_percent < 1 else "Active"

            candidates.append(
                ProcessCandidate(
                    pid=info["pid"],
                    name=name,
                    memory_bytes=memory_bytes,
                    memory_percent=memory_percent,
                    cpu_percent=cpu_percent,
                    activity=activity,
                    username=username,
                    action_allowed=action_allowed,
                )
            )

        return candidates

    def scan_downloads(self) -> list[FileCandidate]:
        root = self.downloads_path.expanduser()
        if not root.exists():
            return []

        file_stats = self._download_file_stats(root)
        reasons = self._download_reasons(file_stats)

        candidates = [
            self._download_candidate(path, file_stats[path], path_reasons)
            for path, path_reasons in reasons.items()
        ]
        return sorted(candidates, key=lambda item: item.size_bytes, reverse=True)

    def _download_file_stats(
        self,
        root: Path,
    ) -> dict[Path, os.stat_result]:
        file_stats: dict[Path, os.stat_result] = {}

        try:
            for path in root.rglob("*"):
                if not self._is_download_file(path, root):
                    continue

                try:
                    file_stats[path] = path.stat()
                except (OSError, ValueError):
                    continue
        except OSError:
            return file_stats

        return file_stats

    @staticmethod
    def _is_download_file(path: Path, root: Path) -> bool:
        if path.is_symlink() or not path.is_file():
            return False

        try:
            relative_parts = path.relative_to(root).parts
        except ValueError:
            return False

        return not any(part.startswith(".") for part in relative_parts)

    def _download_reasons(
        self,
        file_stats: dict[Path, os.stat_result],
    ) -> dict[Path, list[str]]:
        reasons: dict[Path, list[str]] = defaultdict(list)
        self._mark_large_downloads(file_stats, reasons)
        self._mark_duplicate_downloads(file_stats, reasons)
        return reasons

    def _mark_large_downloads(
        self,
        file_stats: dict[Path, os.stat_result],
        reasons: dict[Path, list[str]],
    ) -> None:
        for path, stat in file_stats.items():
            if stat.st_size >= self.LARGE_FILE_BYTES:
                reasons[path].append("Large file")

    def _mark_duplicate_downloads(
        self,
        file_stats: dict[Path, os.stat_result],
        reasons: dict[Path, list[str]],
    ) -> None:
        files_by_size: dict[int, list[Path]] = defaultdict(list)
        for path, stat in file_stats.items():
            if stat.st_size >= self.DUPLICATE_MIN_BYTES:
                files_by_size[stat.st_size].append(path)

        for same_size_paths in files_by_size.values():
            if len(same_size_paths) < 2:
                continue

            files_by_hash: dict[str, list[Path]] = defaultdict(list)
            for path in same_size_paths:
                try:
                    files_by_hash[self._file_hash(path)].append(path)
                except OSError:
                    continue

            for digest, duplicate_paths in files_by_hash.items():
                if len(duplicate_paths) < 2:
                    continue

                ordered_paths = sorted(
                    duplicate_paths,
                    key=lambda item: str(item).casefold(),
                )
                for duplicate_path in ordered_paths[1:]:
                    reasons[duplicate_path].append(f"Duplicate file ({digest[:8]})")

    @staticmethod
    def _download_candidate(
        path: Path,
        stat: os.stat_result,
        reasons: list[str],
    ) -> FileCandidate:
        return FileCandidate(
            path=path,
            size_bytes=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            reason=", ".join(reasons),
        )

    def trash_size(self) -> int:
        total = 0
        for trash in self._trash_paths():
            if not trash.exists():
                continue
            for path in trash.rglob("*"):
                try:
                    if path.is_file() and not path.is_symlink():
                        total += path.stat().st_size
                except OSError:
                    continue
        return total

    def _protected_pids(self) -> set[int]:
        protected = {0, 1, os.getpid()}
        if psutil is None:
            return protected

        try:
            process = psutil.Process(os.getpid())
            protected.update(parent.pid for parent in process.parents())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return protected

    @classmethod
    def _file_hash(cls, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            while chunk := file.read(cls.HASH_CHUNK_BYTES):
                digest.update(chunk)
        return digest.hexdigest()

    def gpu_details(self) -> tuple[str, ...]:
        """Return platform-appropriate GPU details."""
        if platform.system() == "Darwin":
            return self._mac_gpu_details()

        nvidia_details = self._nvidia_gpu_details()
        if nvidia_details:
            return nvidia_details

        if platform.system() == "Windows":
            return self._windows_gpu_details()
        if platform.system() == "Linux":
            return self._linux_gpu_details()
        return ("GPU information unavailable",)

    def _nvidia_gpu_details(self) -> tuple[str, ...] | None:
        if pynvml is None:
            return None

        try:
            pynvml.nvmlInit()
            lines: list[str] = []
            for index in range(pynvml.nvmlDeviceGetCount()):
                handle = pynvml.nvmlDeviceGetHandleByIndex(index)
                name = pynvml.nvmlDeviceGetName(handle)
                memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                usage = pynvml.nvmlDeviceGetUtilizationRates(handle)
                if isinstance(name, bytes):
                    name = name.decode(errors="replace")
                lines.extend(
                    [
                        str(name),
                        f"GPU usage: {usage.gpu}%",
                        f"Memory: {self.format_bytes(memory.used)} used of "
                        f"{self.format_bytes(memory.total)}",
                    ]
                )
            return tuple(lines) or None
        except Exception:
            return None
        finally:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass

    @staticmethod
    def _mac_gpu_details() -> tuple[str, ...]:
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            displays = json.loads(result.stdout).get("SPDisplaysDataType", [])
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
            return (f"GPU information unavailable: {error}",)

        lines: list[str] = []
        for display in displays:
            name = display.get("sppci_model") or display.get("_name") or "Apple GPU"
            lines.append(str(name))
            if memory := display.get("spdisplays_vram"):
                lines.append(f"Memory: {memory}")
            if metal := display.get("spdisplays_metal"):
                lines.append(f"Metal: {metal}")
        return tuple(lines) or ("GPU information unavailable",)

    @classmethod
    def _windows_gpu_details(cls) -> tuple[str, ...]:
        command = (
            "Get-CimInstance Win32_VideoController | "
            "Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Json"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            controllers = json.loads(result.stdout or "[]")
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
            return (f"GPU information unavailable: {error}",)

        if isinstance(controllers, dict):
            controllers = [controllers]

        lines: list[str] = []
        for controller in controllers:
            name = controller.get("Name") or "Windows GPU"
            lines.append(str(name))
            adapter_ram = controller.get("AdapterRAM")
            if isinstance(adapter_ram, int) and adapter_ram > 0:
                lines.append(f"Memory: {cls.format_bytes(adapter_ram)}")
            if driver := controller.get("DriverVersion"):
                lines.append(f"Driver: {driver}")
        return tuple(lines) or ("GPU information unavailable",)

    @staticmethod
    def _linux_gpu_details() -> tuple[str, ...]:
        try:
            result = subprocess.run(
                ["lspci"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return (f"GPU information unavailable: {error}",)

        gpu_lines = [
            line.split(": ", 1)[-1]
            for line in result.stdout.splitlines()
            if "VGA compatible controller" in line
            or "3D controller" in line
            or "Display controller" in line
        ]
        return tuple(gpu_lines) or ("GPU information unavailable",)

    @staticmethod
    def _default_downloads_path() -> Path:
        if platform.system() == "Windows":
            home = Path(os.environ.get("USERPROFILE", Path.home()))
            one_drive = os.environ.get("OneDrive")
            one_drive_downloads = Path(one_drive) / "Downloads" if one_drive else None
            if one_drive_downloads and one_drive_downloads.exists():
                return one_drive_downloads
            return home / "Downloads"
        return Path.home() / "Downloads"

    @staticmethod
    def _trash_paths() -> tuple[Path, ...]:
        system = platform.system()
        if system == "Darwin":
            return (Path.home() / ".Trash",)
        if system == "Linux":
            return (Path.home() / ".local" / "share" / "Trash" / "files",)
        return ()

    @staticmethod
    def _same_user(username: str, current_user: str) -> bool:
        def normalise(value: str) -> str:
            return value.replace("/", "\\").rsplit("\\", 1)[-1].casefold()

        return normalise(username) == normalise(current_user)

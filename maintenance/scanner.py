import ctypes
import getpass
import hashlib
import json
import os
import platform
import subprocess
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from maintenance.models import (
    DashboardSnapshot,
    FileCandidate,
    ProcessCandidate,
    ResourceSummary,
)
from maintenance.components import (
    DownloadScanner as ComponentDownloadScanner,
)

try:
    import psutil
except ImportError:
    psutil = None

try:
    import pynvml
except ImportError:
    pynvml = None


class ScanCancelled(Exception):
    """Raised when a cancellable Downloads scan is stopped by the user."""


class _WindowsGuid(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_ulong),
        ("data2", ctypes.c_ushort),
        ("data3", ctypes.c_ushort),
        ("data4", ctypes.c_ubyte * 8),
    ]


class _RecycleBinInfo(ctypes.Structure):
    _fields_ = [
        ("cb_size", ctypes.c_ulong),
        ("size", ctypes.c_longlong),
        ("item_count", ctypes.c_longlong),
    ]


_WINDOWS_DOWNLOADS_GUID = _WindowsGuid(
    0x374DE290,
    0x123F,
    0x4565,
    (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B),
)

ProgressCallback = Callable[[str], None]
HashFingerprint = tuple[int, int, int, int, int]


class SystemScanner:
    """Read system state and discover reviewable cleanup candidates."""

    BYTES_IN_GIB: int = 1024**3
    LARGE_FILE_BYTES: int = 100 * 1024**2
    DUPLICATE_MIN_BYTES: int = 1024**2
    HASH_CHUNK_BYTES: int = 1024**2
    HASH_CACHE_MAX_ENTRIES: int = 1024
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
        self._download_scanner = ComponentDownloadScanner(self.downloads_path)
        self._hash_cache: OrderedDict[Path, tuple[HashFingerprint, bytes, str]] = (
            self._download_scanner._hash_cache
        )
        self._hash_cache_lock = self._download_scanner._hash_cache_lock
        self._downloads_scan_lock = self._download_scanner._downloads_scan_lock
        self._static_gpu_details: tuple[str, ...] | None = None
        self._static_gpu_lock = threading.Lock()

    def _sync_download_scanner(self) -> ComponentDownloadScanner:
        scanner = self._download_scanner
        scanner.downloads_path = self.downloads_path
        scanner.LARGE_FILE_BYTES = self.LARGE_FILE_BYTES
        scanner.DUPLICATE_MIN_BYTES = self.DUPLICATE_MIN_BYTES
        scanner.HASH_CHUNK_BYTES = self.HASH_CHUNK_BYTES
        scanner.HASH_CACHE_MAX_ENTRIES = self.HASH_CACHE_MAX_ENTRIES
        scanner._check_cancelled = self._check_cancelled
        scanner._file_hash = self._download_file_hash
        scanner._file_content_marker = self._download_file_content_marker
        return scanner

    def _download_file_hash(
        self,
        path: Path,
        cancel_event: threading.Event | None = None,
    ) -> str:
        try:
            return self._file_hash(path, cancel_event=cancel_event)
        except TypeError as error:
            if "unexpected keyword argument" not in str(error):
                raise
            if cancel_event is not None:
                self._check_cancelled(cancel_event)
            return self._file_hash(path)

    def _download_file_content_marker(
        self,
        path: Path,
        cancel_event: threading.Event | None = None,
    ) -> bytes:
        try:
            return self._file_content_marker(path, cancel_event=cancel_event)
        except TypeError as error:
            if "unexpected keyword argument" not in str(error):
                raise
            if cancel_event is not None:
                self._check_cancelled(cancel_event)
            return self._file_content_marker(path)

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

    def scan_dashboard(
        self,
        cancel_event: threading.Event | None = None,
    ) -> DashboardSnapshot:
        self._require_psutil()
        self._check_cancelled(cancel_event)

        cpu_percent = psutil.cpu_percent(interval=0.2)
        self._check_cancelled(cancel_event)
        frequency = psutil.cpu_freq()
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage(str(Path.home()))
        network = psutil.net_io_counters()
        battery = psutil.sensors_battery()
        gpu_details = self.gpu_details()
        self._check_cancelled(cancel_event)
        trash_bytes = self.trash_size()
        self._check_cancelled(cancel_event)

        cpu_frequency = f"{frequency.current:.0f} MHz" if frequency else "Unavailable"
        battery_value = (
            f"{battery.percent:.0f}%" if battery is not None else "Unavailable"
        )
        battery_subtitle = "No battery information"
        battery_percent: float | None = None
        battery_details: tuple[str, ...] = ("Battery information is unavailable.",)

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
                    f"Trash size: {self.format_bytes(trash_bytes)}",
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
        self._check_cancelled(cancel_event)
        return DashboardSnapshot(
            system_label=system_label,
            scanned_at=datetime.now(),
            resources=resources,
        )

    def scan_processes(
        self,
        cancel_event: threading.Event | None = None,
    ) -> list[ProcessCandidate]:
        self._check_cancelled(cancel_event)
        self._require_psutil()
        current_user = getpass.getuser()
        protected_pids = self._protected_pids()
        processes = list(self._process_iter(attrs=["pid", "create_time"]))
        process_creation_times: dict[int, float] = {}
        for process in processes:
            self._check_cancelled(cancel_event)
            try:
                create_time = process.info.get("create_time")
                if isinstance(create_time, (int, float)):
                    process_creation_times[process.pid] = float(create_time)
            except (AttributeError, KeyError, TypeError):
                continue

        for process in processes:
            self._check_cancelled(cancel_event)
            try:
                process.cpu_percent(None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if cancel_event is not None:
            if cancel_event.wait(0.25):
                raise ScanCancelled("Process scan cancelled")
        else:
            time.sleep(0.25)

        candidates: list[ProcessCandidate] = []

        for process in processes:
            self._check_cancelled(cancel_event)
            try:
                info = process.as_dict(
                    attrs=[
                        "pid",
                        "name",
                        "username",
                        "memory_info",
                        "memory_percent",
                        "create_time",
                    ]
                )
                cpu_percent = process.cpu_percent(None)
                memory_info = info["memory_info"]
                memory_bytes = memory_info.rss
                memory_percent = info["memory_percent"]
                expected_create_time = process_creation_times.get(info["pid"])
                current_create_time = info.get("create_time")
                if expected_create_time is None or not isinstance(
                    current_create_time,
                    (int, float),
                ):
                    continue
                if float(current_create_time) != expected_create_time:
                    continue
                self._check_cancelled(cancel_event)
            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied,
                AttributeError,
                KeyError,
                TypeError,
            ):
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

    @staticmethod
    def _process_iter(*, attrs: list[str]) -> Any:
        try:
            return psutil.process_iter(attrs=attrs)
        except TypeError:
            return psutil.process_iter()

    def scan_downloads(
        self,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> list[FileCandidate]:
        return self._sync_download_scanner().scan_downloads(
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

    def _scan_downloads(
        self,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> list[FileCandidate]:
        return self._sync_download_scanner()._scan_downloads(
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

    def _download_file_stats(
        self,
        root: Path,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[Path, os.stat_result]:
        return self._sync_download_scanner()._download_file_stats(
            root,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

    @staticmethod
    def _is_download_file(path: Path, root: Path) -> bool:
        return ComponentDownloadScanner._is_download_file(path, root)

    def _download_reasons(
        self,
        file_stats: dict[Path, os.stat_result],
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[Path, list[str]]:
        return self._sync_download_scanner()._download_reasons(
            file_stats,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

    def _mark_large_downloads(
        self,
        file_stats: dict[Path, os.stat_result],
        reasons: dict[Path, list[str]],
        cancel_event: threading.Event | None = None,
    ) -> None:
        self._sync_download_scanner()._mark_large_downloads(
            file_stats,
            reasons,
            cancel_event=cancel_event,
        )

    def _mark_duplicate_downloads(
        self,
        file_stats: dict[Path, os.stat_result],
        reasons: dict[Path, list[str]],
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self._sync_download_scanner()._mark_duplicate_downloads(
            file_stats,
            reasons,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

    @staticmethod
    def _download_candidate(
        path: Path,
        stat: os.stat_result,
        reasons: list[str],
    ) -> FileCandidate:
        return ComponentDownloadScanner._download_candidate(path, stat, reasons)

    def trash_size(self) -> int:
        if platform.system() == "Windows":
            return self._windows_trash_size()

        total = 0
        for trash in self._trash_paths():
            if not trash.exists():
                continue
            total += self._directory_file_size(trash)
        return total

    @staticmethod
    def _directory_file_size(root: Path) -> int:
        total = 0
        pending_directories = [root]

        while pending_directories:
            directory = pending_directories.pop()
            try:
                entries = os.scandir(directory)
            except OSError:
                continue

            try:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            pending_directories.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
            except OSError:
                pass
            finally:
                entries.close()

        return total

    @staticmethod
    def _windows_trash_size() -> int:
        try:
            shell32 = ctypes.windll.shell32
            query_recycle_bin = shell32.SHQueryRecycleBinW
        except (AttributeError, OSError, ctypes.ArgumentError):
            return 0

        info = _RecycleBinInfo()
        info.cb_size = ctypes.sizeof(info)
        try:
            query_recycle_bin.argtypes = [
                ctypes.c_wchar_p,
                ctypes.POINTER(_RecycleBinInfo),
            ]
            query_recycle_bin.restype = ctypes.c_long
            result = query_recycle_bin(None, ctypes.byref(info))
        except (OSError, TypeError, AttributeError, ctypes.ArgumentError):
            return 0

        if result != 0 or info.size < 0:
            return 0
        return int(info.size)

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
    def _file_hash(
        cls,
        path: Path,
        cancel_event: threading.Event | None = None,
    ) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            while chunk := file.read(cls.HASH_CHUNK_BYTES):
                cls._check_cancelled(cancel_event)
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _check_cancelled(cancel_event: threading.Event | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise ScanCancelled("Downloads scan cancelled")

    @staticmethod
    def _hash_fingerprint(stat: os.stat_result) -> HashFingerprint:
        return (
            stat.st_size,
            stat.st_mtime_ns,
            getattr(stat, "st_ctime_ns", 0),
            getattr(stat, "st_dev", 0),
            getattr(stat, "st_ino", 0),
        )

    def _file_content_marker(
        self,
        path: Path,
        cancel_event: threading.Event | None = None,
    ) -> bytes:
        """Validate the complete file content before reusing a digest."""
        self._check_cancelled(cancel_event)
        marker = hashlib.blake2b(digest_size=16)
        with path.open("rb") as file:
            while chunk := file.read(self.HASH_CHUNK_BYTES):
                self._check_cancelled(cancel_event)
                marker.update(chunk)
        self._check_cancelled(cancel_event)
        return marker.digest()

    def _prune_hash_cache(
        self,
        file_stats: dict[Path, os.stat_result],
        cancel_event: threading.Event | None = None,
    ) -> None:
        self._sync_download_scanner()._prune_hash_cache(
            file_stats,
            cancel_event=cancel_event,
        )

    def _cached_file_hash(
        self,
        path: Path,
        stat: os.stat_result,
        cancel_event: threading.Event | None = None,
    ) -> str:
        return self._sync_download_scanner()._cached_file_hash(
            path,
            stat,
            cancel_event=cancel_event,
        )

    def gpu_details(self) -> tuple[str, ...]:
        """Return platform-appropriate GPU details."""
        system = platform.system()
        if system == "Darwin":
            return self._cached_static_gpu_details(self._mac_gpu_details)

        nvidia_details = self._nvidia_gpu_details()
        if nvidia_details:
            return nvidia_details

        if system == "Windows":
            return self._cached_static_gpu_details(self._windows_gpu_details)
        if system == "Linux":
            return self._cached_static_gpu_details(self._linux_gpu_details)
        return ("GPU information unavailable",)

    def _cached_static_gpu_details(
        self,
        loader: Callable[[], tuple[str, ...]],
    ) -> tuple[str, ...]:
        with self._static_gpu_lock:
            if self._static_gpu_details is not None:
                return self._static_gpu_details

            details = loader()
            if details and not details[0].startswith("GPU information unavailable"):
                self._static_gpu_details = details
            return details

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
            known_folder = SystemScanner._windows_downloads_path()
            if known_folder is not None and SystemScanner._is_directory(known_folder):
                return known_folder

            home = Path(os.environ.get("USERPROFILE", Path.home()))
            one_drive = os.environ.get("OneDrive")
            one_drive_downloads = Path(one_drive) / "Downloads" if one_drive else None
            if one_drive_downloads and SystemScanner._is_directory(one_drive_downloads):
                return one_drive_downloads
            return SystemScanner._safe_downloads_fallback(home)
        return SystemScanner._safe_downloads_fallback(Path.home())

    @staticmethod
    def _is_directory(path: Path) -> bool:
        try:
            return path.is_dir()
        except (OSError, ValueError):
            return False

    @staticmethod
    def _safe_downloads_fallback(home: Path) -> Path:
        candidate = home / "Downloads"
        if SystemScanner._path_exists(candidate) and not SystemScanner._is_directory(
            candidate
        ):
            sentinel = home / "Downloads.__unavailable__"
            suffix = 0
            while SystemScanner._path_exists(sentinel):
                suffix += 1
                sentinel = home / f"Downloads.__unavailable__.{suffix}"
            return sentinel
        return candidate

    @staticmethod
    def _path_exists(path: Path) -> bool:
        try:
            return path.exists()
        except (OSError, ValueError):
            return True

    @staticmethod
    def _windows_downloads_path() -> Path | None:
        try:
            shell32 = ctypes.windll.shell32
            ole32 = ctypes.windll.ole32
            get_known_folder_path = shell32.SHGetKnownFolderPath
            co_initialize = ole32.CoInitializeEx
            co_uninitialize = ole32.CoUninitialize
            free_memory = ole32.CoTaskMemFree
        except (AttributeError, OSError, ctypes.ArgumentError):
            return None

        path_pointer = ctypes.c_wchar_p()
        initialization_result: int | None = None
        try:
            co_initialize.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            co_initialize.restype = ctypes.c_long
            initialization_result = co_initialize(None, 0x2)
            if initialization_result not in (0, 1):
                return None
            co_uninitialize.argtypes = []
            co_uninitialize.restype = None
            free_memory.argtypes = [ctypes.c_void_p]
            free_memory.restype = None
            get_known_folder_path.argtypes = [
                ctypes.POINTER(_WindowsGuid),
                ctypes.c_uint32,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_wchar_p),
            ]
            get_known_folder_path.restype = ctypes.c_long
            result = get_known_folder_path(
                ctypes.byref(_WINDOWS_DOWNLOADS_GUID),
                0,
                None,
                ctypes.byref(path_pointer),
            )
            if result != 0 or not path_pointer.value:
                return None
            return Path(path_pointer.value)
        except (OSError, TypeError, AttributeError, ctypes.ArgumentError):
            return None
        finally:
            pointer_address = ctypes.cast(path_pointer, ctypes.c_void_p).value
            if pointer_address:
                try:
                    free_memory(ctypes.c_void_p(pointer_address))
                except (OSError, TypeError, AttributeError, ctypes.ArgumentError):
                    pass
            if initialization_result in (0, 1):
                try:
                    co_uninitialize()
                except (OSError, TypeError, AttributeError, ctypes.ArgumentError):
                    pass

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

"""Shared maintenance components used by the scanner, dialogs, and window.

These helpers are extracted seams kept in one place so wiring stays small.
Current source references:
- `ProcessSafetyPolicy` for future wiring in `maintenance/scanner.py` and
  `maintenance/actions.py`.
- `DownloadsPathResolver` in `maintenance/scanner.py`.
- `DownloadScanner` in `maintenance/scanner.py`.
- `GpuDetector` in `maintenance/scanner.py`.
- `BackgroundTaskRunner` in `maintenance/dialogs.py`.
- `ResourceFeatureCatalog` for future wiring in `window.py`, `algo.py`, and
  `maintenance/scanner.py`.
- `ScanCoordinator` in `window.py`.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import platform
import threading
import tkinter as tk
from collections import OrderedDict, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import messagebox
from typing import Any

from maintenance.models import FileCandidate

# =============================================================================
# Shared types and Windows interop support
# Implementation: maintenance/components.py
# Shared by: maintenance/scanner.py, maintenance/dialogs.py
# Tests: tests/test_components.py, tests/test_maintenance.py
# =============================================================================

ProgressCallback = Callable[[str], None]
ProgressTask = Callable[[ProgressCallback, threading.Event], Any]
HashFingerprint = tuple[int, int, int, int, int]


class ScanCancelled(Exception):
    """Raised when a cancellable Downloads scan is stopped by the caller."""


class _WindowsGuid(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_ulong),
        ("data2", ctypes.c_ushort),
        ("data3", ctypes.c_ushort),
        ("data4", ctypes.c_ubyte * 8),
    ]


_WINDOWS_DOWNLOADS_GUID = _WindowsGuid(
    0x374DE290,
    0x123F,
    0x4565,
    (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B),
)


# =============================================================================
# Process safety decisions
# Domain owners: maintenance/scanner.py, maintenance/actions.py
# Implementation: maintenance/components.py
# Tests: tests/test_components.py, tests/test_maintenance.py
# =============================================================================


class ProcessSafetyPolicy:
    """Answer whether a process may be managed without performing the action.

    The policy keeps the scanner and process-action protection rules together,
    but it never terminates or otherwise changes a process. Missing or
    inaccessible process information is treated as protected.
    """

    PROTECTED_NAMES: frozenset[str] = frozenset(
        {
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
    )

    def __init__(
        self,
        *,
        current_pid_loader: Callable[[], int] = os.getpid,
        process_loader: Callable[[int], Any] | None = None,
        protected_names: Iterable[str] | None = None,
    ) -> None:
        self._current_pid_loader = current_pid_loader
        self._process_loader = process_loader or self._default_process_loader
        names = self.PROTECTED_NAMES if protected_names is None else protected_names
        self._protected_names = frozenset(
            name.casefold() for name in names if isinstance(name, str) and name
        )

    def protected_pids(self) -> set[int]:
        """Return PID 0, PID 1, this process, and its known parent chain."""

        protected, _complete = self._protected_pid_snapshot()
        return protected

    def same_user(self, username: str, current_user: str) -> bool:
        """Compare local usernames while ignoring Windows domain prefixes."""

        normalized_username = self._normalize_username(username)
        normalized_current_user = self._normalize_username(current_user)
        return (
            bool(normalized_username) and normalized_username == normalized_current_user
        )

    def can_manage(
        self,
        *,
        pid: int,
        name: str,
        username: str,
        current_user: str,
    ) -> bool:
        """Return whether a process with the supplied facts may be managed."""

        protected_pids, complete = self._protected_pid_snapshot()
        if not complete:
            return False
        return self._can_manage_with_pids(
            pid=pid,
            name=name,
            username=username,
            current_user=current_user,
            protected_pids=protected_pids,
        )

    def can_manage_process(self, *, pid: int, current_user: str) -> bool:
        """Load one process and apply the policy, failing closed on lookup errors."""

        protected_pids, complete = self._protected_pid_snapshot()
        if not complete or not isinstance(pid, int) or pid in protected_pids:
            return False

        try:
            process = self._process_loader(pid)
            name = process.name()
            username = process.username()
        except Exception:  # noqa: BLE001 - fail closed on any loader failure.
            # A disappearing or inaccessible process cannot be safely offered.
            return False

        return self._can_manage_with_pids(
            pid=pid,
            name=name,
            username=username,
            current_user=current_user,
            protected_pids=protected_pids,
        )

    def _protected_pid_snapshot(self) -> tuple[set[int], bool]:
        protected = {0, 1}
        try:
            current_pid = self._current_pid_loader()
            if not isinstance(current_pid, int) or current_pid < 0:
                return protected, False
            protected.add(current_pid)

            process = self._process_loader(current_pid)
            for parent in process.parents():
                parent_pid = getattr(parent, "pid", None)
                if not isinstance(parent_pid, int) or parent_pid < 0:
                    return protected, False
                protected.add(parent_pid)
        except Exception:  # noqa: BLE001 - fail closed on any ancestry failure.
            # Keep the base protected PIDs visible, but do not permit management
            # when the current process ancestry cannot be established.
            return protected, False
        return protected, True

    def _can_manage_with_pids(
        self,
        *,
        pid: int,
        name: str,
        username: str,
        current_user: str,
        protected_pids: set[int],
    ) -> bool:
        if not isinstance(pid, int) or pid < 0 or pid in protected_pids:
            return False
        if not isinstance(name, str) or not name:
            return False
        if name.casefold() in self._protected_names:
            return False
        return self.same_user(username, current_user)

    @staticmethod
    def _normalize_username(value: str) -> str:
        if not isinstance(value, str):
            return ""
        return value.replace("/", "\\").rsplit("\\", 1)[-1].casefold()

    @staticmethod
    def _default_process_loader(pid: int) -> Any:
        try:
            import psutil
        except ImportError as error:
            raise RuntimeError(
                "psutil is not installed. Run: python -m pip install psutil"
            ) from error
        return psutil.Process(pid)


# =============================================================================
# Downloads path resolution
# Domain owner: maintenance/scanner.py
# Implementation: maintenance/components.py
# Tests: tests/test_components.py, tests/test_maintenance.py
# =============================================================================


class DownloadsPathResolver:
    """Resolve the Downloads root.

    Extracted from the Downloads-root resolution code in `maintenance/scanner.py`.
    """

    def __init__(
        self,
        *,
        system: Callable[[], str] = platform.system,
        home: Callable[[], Path] = Path.home,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._system = system
        self._home = home
        self._environment = environment or os.environ

    def select(self, downloads_path: Path | None = None) -> Path:
        """Return the explicit Downloads path or the platform default."""

        if downloads_path is not None:
            return downloads_path
        return self._default_downloads_path()

    def _default_downloads_path(self) -> Path:
        if self._system() == "Windows":
            known_folder = self._windows_downloads_path()
            if known_folder is not None and self._is_directory(known_folder):
                return known_folder

            home = Path(self._environment.get("USERPROFILE", self._home()))
            one_drive = self._environment.get("OneDrive")
            one_drive_downloads = Path(one_drive) / "Downloads" if one_drive else None
            if one_drive_downloads and self._is_directory(one_drive_downloads):
                return one_drive_downloads
            return self._safe_downloads_fallback(home)
        return self._safe_downloads_fallback(Path(self._home()))

    @staticmethod
    def _is_directory(path: Path) -> bool:
        try:
            return path.is_dir()
        except (OSError, ValueError):
            return False

    @staticmethod
    def _path_exists(path: Path) -> bool:
        try:
            return path.exists()
        except (OSError, ValueError):
            return True

    @classmethod
    def _safe_downloads_fallback(cls, home: Path) -> Path:
        candidate = home / "Downloads"
        if cls._path_exists(candidate) and not cls._is_directory(candidate):
            sentinel = home / "Downloads.__unavailable__"
            suffix = 0
            while cls._path_exists(sentinel):
                suffix += 1
                sentinel = home / f"Downloads.__unavailable__.{suffix}"
            return sentinel
        return candidate

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


# =============================================================================
# Downloads discovery, duplicate detection, and hash caching
# Domain owner: maintenance/scanner.py
# Implementation: maintenance/components.py
# Facade and compatibility hooks: maintenance/scanner.py
# Tests: tests/test_components.py, tests/test_maintenance.py
# =============================================================================


class DownloadScanner:
    """Scan Downloads for large files and verified duplicates.

    Extracted from `maintenance/scanner.py:352-585, 703-790`.
    """

    LARGE_FILE_BYTES: int = 100 * 1024**2
    DUPLICATE_MIN_BYTES: int = 1024**2
    HASH_CHUNK_BYTES: int = 1024**2
    HASH_CACHE_MAX_ENTRIES: int = 1024

    def __init__(
        self,
        downloads_path: Path | None = None,
        *,
        resolver: DownloadsPathResolver | None = None,
    ) -> None:
        self._resolver = resolver or DownloadsPathResolver()
        self.downloads_path = self._resolver.select(downloads_path)
        self._hash_cache: OrderedDict[Path, tuple[HashFingerprint, bytes, str]] = (
            OrderedDict()
        )
        self._hash_cache_lock = threading.Lock()
        self._downloads_scan_lock = threading.Lock()

    def scan_downloads(
        self,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> list[FileCandidate]:
        while not self._downloads_scan_lock.acquire(timeout=0.1):
            self._check_cancelled(cancel_event)
        try:
            return self._scan_downloads(
                progress_callback=progress_callback,
                cancel_event=cancel_event,
            )
        finally:
            self._downloads_scan_lock.release()

    def _scan_downloads(
        self,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> list[FileCandidate]:
        self._check_cancelled(cancel_event)
        root = self.downloads_path.expanduser()
        if not root.exists():
            self._prune_hash_cache({}, cancel_event=cancel_event)
            return []

        if progress_callback is None and cancel_event is None:
            file_stats = self._download_file_stats(root)
        else:
            try:
                file_stats = self._download_file_stats(
                    root,
                    progress_callback=progress_callback,
                    cancel_event=cancel_event,
                )
            except TypeError as error:
                if "unexpected keyword argument" not in str(error):
                    raise
                self._check_cancelled(cancel_event)
                file_stats = self._download_file_stats(root)
        self._prune_hash_cache(file_stats, cancel_event=cancel_event)
        if progress_callback is None and cancel_event is None:
            reasons = self._download_reasons(file_stats)
        else:
            try:
                reasons = self._download_reasons(
                    file_stats,
                    progress_callback=progress_callback,
                    cancel_event=cancel_event,
                )
            except TypeError as error:
                if "unexpected keyword argument" not in str(error):
                    raise
                self._check_cancelled(cancel_event)
                reasons = self._download_reasons(file_stats)

        candidates: list[FileCandidate] = []
        for path, path_reasons in reasons.items():
            self._check_cancelled(cancel_event)
            candidates.append(
                self._download_candidate(path, file_stats[path], path_reasons)
            )
        self._check_cancelled(cancel_event)
        if progress_callback is not None:
            progress_callback(f"Scan complete: {len(candidates)} candidate(s)")
        return sorted(
            candidates,
            key=lambda item: (
                -item.size_bytes,
                str(item.path).casefold(),
                str(item.path),
            ),
        )

    def _download_file_stats(
        self,
        root: Path,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[Path, os.stat_result]:
        file_stats: dict[Path, os.stat_result] = {}
        pending_directories = [root]
        last_reported_file_count = 0

        while pending_directories:
            self._check_cancelled(cancel_event)
            directory = pending_directories.pop()
            try:
                entries = os.scandir(directory)
            except OSError:
                continue

            try:
                for entry in entries:
                    self._check_cancelled(cancel_event)
                    path = Path(entry.path)
                    try:
                        if entry.name.startswith("."):
                            continue

                        if entry.is_dir(follow_symlinks=False):
                            pending_directories.append(path)
                            continue

                        if not entry.is_file(follow_symlinks=False):
                            continue

                        file_stats[path] = path.stat()
                    except (OSError, ValueError):
                        continue
            except OSError:
                pass
            finally:
                entries.close()

            if progress_callback is not None and (
                len(file_stats) == 1
                or len(file_stats) - last_reported_file_count >= 100
            ):
                progress_callback(f"Found {len(file_stats)} file(s) in Downloads")
                last_reported_file_count = len(file_stats)

        if (
            progress_callback is not None
            and len(file_stats) != last_reported_file_count
        ):
            progress_callback(f"Found {len(file_stats)} file(s) in Downloads")

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
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[Path, list[str]]:
        reasons: dict[Path, list[str]] = defaultdict(list)
        self._mark_large_downloads(
            file_stats,
            reasons,
            cancel_event=cancel_event,
        )
        self._mark_duplicate_downloads(
            file_stats,
            reasons,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )
        return reasons

    def _mark_large_downloads(
        self,
        file_stats: dict[Path, os.stat_result],
        reasons: dict[Path, list[str]],
        cancel_event: threading.Event | None = None,
    ) -> None:
        for path, stat in file_stats.items():
            self._check_cancelled(cancel_event)
            if stat.st_size >= self.LARGE_FILE_BYTES:
                reasons[path].append("Large file")

    def _mark_duplicate_downloads(
        self,
        file_stats: dict[Path, os.stat_result],
        reasons: dict[Path, list[str]],
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        files_by_size: dict[int, list[Path]] = defaultdict(list)
        for path, stat in file_stats.items():
            self._check_cancelled(cancel_event)
            if stat.st_size >= self.DUPLICATE_MIN_BYTES:
                files_by_size[stat.st_size].append(path)

        hash_total = sum(
            len(same_size_paths)
            for same_size_paths in files_by_size.values()
            if len(same_size_paths) >= 2
        )
        hashed_count = 0

        for same_size_paths in files_by_size.values():
            self._check_cancelled(cancel_event)
            if len(same_size_paths) < 2:
                continue

            files_by_hash: dict[str, list[Path]] = defaultdict(list)
            for path in same_size_paths:
                self._check_cancelled(cancel_event)
                try:
                    files_by_hash[
                        self._cached_file_hash(
                            path,
                            file_stats[path],
                            cancel_event=cancel_event,
                        )
                    ].append(path)
                except OSError:
                    continue
                finally:
                    hashed_count += 1
                    if progress_callback is not None and (
                        hashed_count == 1
                        or hashed_count == hash_total
                        or hashed_count % 16 == 0
                    ):
                        progress_callback(
                            f"Checking duplicates: {hashed_count}/{hash_total}"
                        )

            for digest, duplicate_paths in files_by_hash.items():
                if len(duplicate_paths) < 2:
                    continue

                ordered_paths = sorted(
                    duplicate_paths,
                    key=lambda item: (str(item).casefold(), str(item)),
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

    @staticmethod
    def _file_hash(
        path: Path,
        cancel_event: threading.Event | None = None,
    ) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            while chunk := file.read(DownloadScanner.HASH_CHUNK_BYTES):
                DownloadScanner._check_cancelled(cancel_event)
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
        current_fingerprints: dict[Path, HashFingerprint] = {}
        for path, stat in file_stats.items():
            self._check_cancelled(cancel_event)
            current_fingerprints[path] = self._hash_fingerprint(stat)
        with self._hash_cache_lock:
            retained_items = [
                (
                    path,
                    cached,
                )
                for path, cached in self._hash_cache.items()
                if path in current_fingerprints
                and cached[0] == current_fingerprints[path]
            ]
            self._hash_cache.clear()
            self._hash_cache.update(retained_items)
            while len(self._hash_cache) > self.HASH_CACHE_MAX_ENTRIES:
                self._hash_cache.popitem(last=False)

    def _cached_file_hash(
        self,
        path: Path,
        stat: os.stat_result,
        cancel_event: threading.Event | None = None,
    ) -> str:
        for _attempt in range(2):
            self._check_cancelled(cancel_event)
            fingerprint = self._hash_fingerprint(stat)
            marker = self._file_content_marker(path, cancel_event)
            with self._hash_cache_lock:
                cached = self._hash_cache.get(path)

            if cached is not None and cached[0] == fingerprint and cached[1] == marker:
                current_stat = path.stat()
                current_marker = self._file_content_marker(path, cancel_event)
                if (
                    self._hash_fingerprint(current_stat) == fingerprint
                    and current_marker == marker
                ):
                    with self._hash_cache_lock:
                        self._hash_cache.move_to_end(path)
                    return cached[2]
                stat = current_stat
                continue

            if cancel_event is None:
                digest = self._file_hash(path)
            else:
                try:
                    digest = self._file_hash(path, cancel_event)
                except TypeError as error:
                    if "positional argument" not in str(error):
                        raise
                    digest = self._file_hash(path)
                    self._check_cancelled(cancel_event)
            current_stat = path.stat()
            current_marker = self._file_content_marker(path, cancel_event)
            if (
                self._hash_fingerprint(current_stat) == fingerprint
                and current_marker == marker
            ):
                with self._hash_cache_lock:
                    self._hash_cache[path] = (fingerprint, current_marker, digest)
                    self._hash_cache.move_to_end(path)
                    while len(self._hash_cache) > self.HASH_CACHE_MAX_ENTRIES:
                        self._hash_cache.popitem(last=False)
                return digest
            stat = current_stat

        raise OSError(f"File changed while hashing: {path}")


# =============================================================================
# GPU platform selection
# Domain owner: maintenance/scanner.py
# Implementation: maintenance/components.py
# Consumer and compatibility hooks: maintenance/scanner.py
# Tests: tests/test_components.py, tests/test_maintenance.py
# =============================================================================


class GpuDetector:
    """Select the correct GPU detail loader for the active platform.

    Extracted from the platform-dispatch path in
    `maintenance/scanner.py:792-837` and now used by `SystemScanner.gpu_details()`.
    """

    def __init__(
        self,
        *,
        system: Callable[[], str],
        nvidia_loader: Callable[[], tuple[str, ...] | None],
        mac_loader: Callable[[], tuple[str, ...]],
        windows_loader: Callable[[], tuple[str, ...]],
        linux_loader: Callable[[], tuple[str, ...]],
    ) -> None:
        self._system = system
        self._nvidia_loader = nvidia_loader
        self._mac_loader = mac_loader
        self._windows_loader = windows_loader
        self._linux_loader = linux_loader

    def detect(self) -> tuple[str, ...]:
        """Return the first applicable GPU detail set for this platform."""

        system = self._system()
        if system == "Darwin":
            # macOS keeps its native path first so the future wiring stays cheap.
            return self._mac_loader()

        nvidia_details = self._nvidia_loader()
        if nvidia_details:
            return nvidia_details

        if system == "Windows":
            return self._windows_loader()
        if system == "Linux":
            return self._linux_loader()
        return ("GPU information unavailable",)


# =============================================================================
# Background Tk task delivery
# Domain owner: maintenance/dialogs.py
# Implementation: maintenance/components.py
# Entry point: maintenance/dialogs.py
# Tests: tests/test_components.py, tests/test_storage_dialog.py
# =============================================================================


class BackgroundTaskRunner:
    """Run work off the Tkinter thread and safely deliver the result.

    Extracted from `maintenance/dialogs.py:21-74, 527-726`.
    """

    @staticmethod
    def run_in_thread(
        widget: tk.Misc,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[str], None] | None = None,
        *,
        progress_task: ProgressTask | None = None,
        cancel_event: threading.Event | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        operation_cancel_event = cancel_event or threading.Event()

        def deliver(callback: Callable, value: Any) -> None:
            try:
                if widget.winfo_exists():
                    callback(value)
            except (RuntimeError, tk.TclError):
                pass

        def report_progress(message: str) -> None:
            if on_progress is None:
                return
            try:
                widget.after(0, deliver, on_progress, message)
            except (RuntimeError, tk.TclError):
                pass

        def worker() -> None:
            try:
                if progress_task is None:
                    result = task()
                else:
                    result = progress_task(report_progress, operation_cancel_event)
            except Exception as error:
                callback = on_error or (
                    lambda message: messagebox.showerror(
                        "Operation Error",
                        message,
                        parent=widget,
                    )
                )
                try:
                    widget.after(0, deliver, callback, str(error))
                except (RuntimeError, tk.TclError):
                    pass
            else:
                try:
                    widget.after(0, deliver, on_success, result)
                except (RuntimeError, tk.TclError):
                    pass

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def run(
        widget: tk.Misc,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[str], None] | None = None,
        *,
        progress_task: ProgressTask | None = None,
        cancel_event: threading.Event | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        BackgroundTaskRunner.run_in_thread(
            widget,
            task,
            on_success,
            on_error,
            progress_task=progress_task,
            cancel_event=cancel_event,
            on_progress=on_progress,
        )


# =============================================================================
# Resource feature metadata
# Domain owners: window.py, algo.py, maintenance/scanner.py
# Implementation: maintenance/components.py
# Consumers to wire later: window.py, algo.py, maintenance/scanner.py
# Tests: tests/test_components.py, tests/test_maintenance.py
# =============================================================================


@dataclass(frozen=True, slots=True)
class ResourceFeature:
    """Immutable metadata for one dashboard resource category.

    ``loader_name`` names an existing analyzer detail method for future
    wiring. The catalog describes metadata only; it never imports or calls
    scanners, handlers, widgets, or destructive actions.
    """

    key: str
    title: str
    order: int
    action_kind: str
    loader_name: str
    platforms: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if (
            not self.key
            or not self.title
            or not self.action_kind
            or not self.loader_name
        ):
            raise ValueError("Resource feature metadata fields cannot be empty")
        if self.order < 0:
            raise ValueError("Resource feature order cannot be negative")

        if self.platforms is not None:
            platforms = tuple(self.platforms)
            if not platforms or any(not platform for platform in platforms):
                raise ValueError("Resource feature platforms cannot be empty")
            object.__setattr__(self, "platforms", platforms)

    def is_available_on(self, platform_name: str) -> bool:
        """Return whether this feature is declared for a platform."""

        if self.platforms is None:
            return True
        normalized_platform = platform_name.casefold()
        return any(
            platform.casefold() == normalized_platform for platform in self.platforms
        )


class ResourceFeatureCatalog:
    """Own isolated, deterministic metadata for dashboard resource features.

    The default entries mirror the current dashboard. Registering a feature
    extends one catalog instance only, so future feature experiments cannot
    mutate another window or a process-wide registry by accident.
    """

    DEFAULT_FEATURES: tuple[ResourceFeature, ...] = (
        ResourceFeature("cpu", "CPU", 0, "process", "cpu_info"),
        ResourceFeature("memory", "Memory", 1, "process", "memory_info"),
        ResourceFeature("storage", "Storage", 2, "storage", "storage_info"),
        ResourceFeature("gpu", "GPU", 3, "informational", "gpu_info"),
        ResourceFeature("network", "Network", 4, "informational", "network_info"),
        ResourceFeature("battery", "Battery", 5, "informational", "battery_info"),
    )

    def __init__(
        self,
        features: Iterable[ResourceFeature] | None = None,
    ) -> None:
        self._features: dict[str, ResourceFeature] = {}
        for feature in self.DEFAULT_FEATURES if features is None else features:
            self.register(feature)

    def all(self) -> tuple[ResourceFeature, ...]:
        """Return features in deterministic display order."""

        return tuple(
            sorted(
                self._features.values(),
                key=lambda feature: (feature.order, feature.key),
            )
        )

    def get(self, key: str) -> ResourceFeature:
        """Return one feature or raise a clear error for an unknown key."""

        try:
            return self._features[key]
        except KeyError as error:
            raise KeyError(f"Unknown resource feature: {key}") from error

    def register(self, feature: ResourceFeature) -> None:
        """Register one immutable feature, rejecting duplicate keys."""

        if not isinstance(feature, ResourceFeature):
            raise TypeError("feature must be a ResourceFeature")
        if feature.key in self._features:
            raise ValueError(f"Resource feature already registered: {feature.key}")
        self._features[feature.key] = feature

    def available_on(self, platform_name: str) -> tuple[ResourceFeature, ...]:
        """Return the ordered features declared for one platform."""

        return tuple(
            feature for feature in self.all() if feature.is_available_on(platform_name)
        )


# =============================================================================
# Dashboard scan coordination
# Domain owner: window.py
# Implementation: maintenance/components.py
# Consumer: window.py
# Tests: tests/test_components.py, tests/test_window.py
# =============================================================================


@dataclass
class ScanCoordinator:
    """Track live scan state for `window.AppWindow`.

    Extracted from the live-scan coordination flow in `window.py:394-451`.

    It keeps the in-flight flag, generation counter, and queued rerun request
    together so the UI can wait for the current loading cycle to finish before
    scheduling the next one.
    """

    active: bool = False
    generation: int = 0
    rerun_requested: bool = False

    def begin(self) -> tuple[int, bool]:
        """Start a scan or mark that one should run again after completion."""

        if self.active:
            self.rerun_requested = True
            return self.generation, False

        self.active = True
        self.generation += 1
        return self.generation, True

    def finish(self, generation: int) -> tuple[bool, bool]:
        """Finish the active generation and report whether a rerun is queued."""

        if generation != self.generation:
            return False, False

        return True, self._reset_state_and_return_rerun()

    def cancel(self) -> None:
        """Clear the active state without scheduling another scan."""

        self._reset_state()

    def _reset_state(self) -> None:
        self.active = False
        self.rerun_requested = False

    def _reset_state_and_return_rerun(self) -> bool:
        rerun_requested = self.rerun_requested
        self._reset_state()
        return rerun_requested

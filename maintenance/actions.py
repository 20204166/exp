from collections.abc import Callable, Iterable
import getpass
import os
from typing import Any
from pathlib import Path

from maintenance.models import FileActionResult, ProcessActionResult
from maintenance.scanner import SystemScanner

try:
    import psutil
except ImportError:
    psutil = None

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None


class ProcessManager:
    """Quit selected user processes with explicit safety checks."""

    PROTECTED_NAMES = {
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

    @staticmethod
    def _require_psutil() -> Any:
        if psutil is None:
            raise RuntimeError(
                "psutil is not installed. Run: python -m pip install psutil"
            )
        return psutil

    def request_quit(self, pids: list[int]) -> ProcessActionResult:
        return self._run_process_action(pids, lambda process: process.terminate())

    def force_quit(self, pids: list[int]) -> ProcessActionResult:
        return self._run_process_action(
            pids,
            lambda process: process.kill(),
            alive_message="did not stop.",
        )

    def _run_process_action(
        self,
        pids: list[int],
        action: Callable[[Any], None],
        alive_message: str | None = None,
    ) -> ProcessActionResult:
        psutil_module = self._require_psutil()
        processes, errors = self._allowed_processes(pids, psutil_module)
        if not processes:
            return self._build_process_action_result(pids, (), (), errors)

        process_errors = (
            psutil_module.NoSuchProcess,
            psutil_module.AccessDenied,
        )
        for process in processes:
            try:
                action(process)
            except process_errors as error:
                errors.append(f"PID {process.pid}: {error}")

        gone, alive = psutil_module.wait_procs(processes, timeout=3)
        if alive_message is not None:
            errors.extend(f"PID {process.pid} {alive_message}" for process in alive)
        return self._build_process_action_result(pids, gone, alive, errors)

    @staticmethod
    def _build_process_action_result(
        pids: list[int],
        gone: Iterable[Any],
        alive: Iterable[Any],
        errors: list[str],
    ) -> ProcessActionResult:
        return ProcessActionResult(
            requested=len(pids),
            stopped=tuple(process.pid for process in gone),
            force_required=tuple(process.pid for process in alive),
            errors=tuple(errors),
        )

    def _allowed_processes(
        self,
        pids: list[int],
        psutil_module: Any,
    ) -> tuple[list[Any], list[str]]:
        current_user = getpass.getuser()
        protected_pids = self._protected_pids(psutil_module)
        process_factory = psutil_module.Process
        same_user = self._same_user
        protected_names = self.PROTECTED_NAMES
        processes: list[Any] = []
        errors: list[str] = []

        for pid in dict.fromkeys(pids):
            if pid in protected_pids:
                errors.append(f"PID {pid} is protected.")
                continue

            try:
                process = process_factory(pid)
                name = process.name()
                username = process.username()
            except (psutil_module.NoSuchProcess, psutil_module.AccessDenied) as error:
                errors.append(f"PID {pid}: {error}")
                continue

            if (
                not same_user(username, current_user)
                or name.casefold() in protected_names
            ):
                errors.append(f"{name} (PID {pid}) is protected.")
                continue
            processes.append(process)

        return processes, errors

    @staticmethod
    def _protected_pids(psutil_module: Any) -> set[int]:
        protected = {0, 1, os.getpid()}
        try:
            process = psutil_module.Process(os.getpid())
            protected.update(parent.pid for parent in process.parents())
        except (psutil_module.NoSuchProcess, psutil_module.AccessDenied):
            pass
        return protected

    @staticmethod
    def _same_user(username: str, current_user: str) -> bool:
        def normalise(value: str) -> str:
            return value.replace("/", "\\").rsplit("\\", 1)[-1].casefold()

        return normalise(username) == normalise(current_user)


class FileManager:
    """Move selected files to Trash after validating their location."""

    def __init__(self, allowed_root: Path | None = None) -> None:
        self.allowed_root = (
            allowed_root or SystemScanner._default_downloads_path()
        ).resolve()

    @staticmethod
    def _require_send2trash() -> Any:
        if send2trash is None:
            raise RuntimeError(
                "send2trash is not installed. Run: python -m pip install send2trash"
            )
        return send2trash

    def move_to_trash(self, paths: list[Path]) -> FileActionResult:
        send2trash_fn = self._require_send2trash()
        allowed_root = self.allowed_root
        moved: list[Path] = []
        errors: list[str] = []

        for original_path in dict.fromkeys(paths):
            path = original_path.expanduser()

            if path.is_symlink():
                errors.append(f"{path}: symbolic links are not allowed.")
                continue

            try:
                resolved_path = path.resolve(strict=True)
            except (OSError, RuntimeError) as error:
                errors.append(f"{path}: {error}")
                continue

            if (
                not allowed_root.is_dir()
                or not resolved_path.is_relative_to(allowed_root)
                or not resolved_path.is_file()
            ):
                errors.append(f"{path}: not an allowed Downloads file.")
                continue

            try:
                send2trash_fn(str(resolved_path))
            except OSError as error:
                errors.append(f"{path}: {error}")
            else:
                moved.append(resolved_path)

        return FileActionResult(
            requested=len(paths),
            moved=tuple(moved),
            errors=tuple(errors),
        )

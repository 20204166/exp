import getpass
import os
from pathlib import Path

from maintenance.models import FileActionResult, ProcessActionResult

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
    def _require_psutil() -> None:
        if psutil is None:
            raise RuntimeError(
                "psutil is not installed. Run: python -m pip install psutil"
            )

    def request_quit(self, pids: list[int]) -> ProcessActionResult:
        self._require_psutil()
        processes, errors = self._allowed_processes(pids)

        for process in processes:
            try:
                process.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied) as error:
                errors.append(f"PID {process.pid}: {error}")

        gone, alive = psutil.wait_procs(processes, timeout=3)
        return ProcessActionResult(
            requested=len(pids),
            stopped=tuple(process.pid for process in gone),
            force_required=tuple(process.pid for process in alive),
            errors=tuple(errors),
        )

    def force_quit(self, pids: list[int]) -> ProcessActionResult:
        self._require_psutil()
        processes, errors = self._allowed_processes(pids)

        for process in processes:
            try:
                process.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied) as error:
                errors.append(f"PID {process.pid}: {error}")

        gone, alive = psutil.wait_procs(processes, timeout=3)
        errors.extend(f"PID {process.pid} did not stop." for process in alive)
        return ProcessActionResult(
            requested=len(pids),
            stopped=tuple(process.pid for process in gone),
            force_required=tuple(process.pid for process in alive),
            errors=tuple(errors),
        )

    def _allowed_processes(self, pids: list[int]) -> tuple[list, list[str]]:
        current_user = getpass.getuser()
        protected_pids = self._protected_pids()
        processes = []
        errors: list[str] = []

        for pid in dict.fromkeys(pids):
            if pid in protected_pids:
                errors.append(f"PID {pid} is protected.")
                continue

            try:
                process = psutil.Process(pid)
                name = process.name()
                username = process.username()
            except (psutil.NoSuchProcess, psutil.AccessDenied) as error:
                errors.append(f"PID {pid}: {error}")
                continue

            if (
                not self._same_user(username, current_user)
                or name.casefold() in self.PROTECTED_NAMES
            ):
                errors.append(f"{name} (PID {pid}) is protected.")
                continue
            processes.append(process)

        return processes, errors

    @staticmethod
    def _protected_pids() -> set[int]:
        protected = {0, 1, os.getpid()}
        try:
            process = psutil.Process(os.getpid())
            protected.update(parent.pid for parent in process.parents())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
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
        self.allowed_root = (allowed_root or Path.home() / "Downloads").resolve()

    @staticmethod
    def _require_send2trash() -> None:
        if send2trash is None:
            raise RuntimeError(
                "send2trash is not installed. "
                "Run: python -m pip install send2trash"
            )

    def move_to_trash(self, paths: list[Path]) -> FileActionResult:
        self._require_send2trash()
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
                not resolved_path.is_relative_to(self.allowed_root)
                or not resolved_path.is_file()
            ):
                errors.append(f"{path}: not an allowed Downloads file.")
                continue

            try:
                send2trash(str(resolved_path))
            except OSError as error:
                errors.append(f"{path}: {error}")
            else:
                moved.append(resolved_path)

        return FileActionResult(
            requested=len(paths),
            moved=tuple(moved),
            errors=tuple(errors),
        )
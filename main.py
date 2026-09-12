import logging
import os
import platform
from logging.handlers import RotatingFileHandler
from pathlib import Path

from window import AppWindow

LOG_DIR_NAME = "system-analyzer"
LOG_FILE_NAME = "system-analyzer.log"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def default_log_path(
    *,
    environment: dict[str, str] | None = None,
    home: Path | None = None,
    platform_name: str | None = None,
) -> Path:
    """Return the standard per-user log path for the active platform."""

    env = os.environ if environment is None else environment
    home_dir = Path.home() if home is None else home
    system = platform.system() if platform_name is None else platform_name

    if system == "Windows":
        base = env.get("LOCALAPPDATA") or env.get("APPDATA")
        return (
            (Path(base) if base else home_dir / "AppData" / "Local")
            / LOG_DIR_NAME
            / LOG_FILE_NAME
        )
    if system == "Darwin":
        return home_dir / "Library" / "Logs" / LOG_DIR_NAME / LOG_FILE_NAME
    base = env.get("XDG_STATE_HOME")
    return (
        (Path(base) if base else home_dir / ".local" / "state")
        / LOG_DIR_NAME
        / LOG_FILE_NAME
    )


def setup_logging() -> Path | None:
    """Configure per-user file logging and return the log path (or None).

    The log lives under the XDG state directory (``~/.local/state`` by
    default) and is size-bounded so a disk-full situation cannot grow logs
    without limit. If the state directory is unavailable, logging falls back
    to stderr instead of failing the app.
    """

    path = default_log_path()
    log_dir = path.parent
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
    except OSError:
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
        return None

    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return path


def main() -> None:
    setup_logging()
    app = AppWindow()
    app.run()


if __name__ == "__main__":
    main()

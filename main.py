import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from window import AppWindow

LOG_DIR_NAME = "system-analyzer"
LOG_FILE_NAME = "system-analyzer.log"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging() -> Path | None:
    """Configure per-user file logging and return the log path (or None).

    The log lives under the XDG state directory (``~/.local/state`` by
    default) and is size-bounded so a disk-full situation cannot grow logs
    without limit. If the state directory is unavailable, logging falls back
    to stderr instead of failing the app.
    """

    base = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
    log_dir = base / LOG_DIR_NAME
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / LOG_FILE_NAME
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

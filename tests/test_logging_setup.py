from tests.support.scanner import make_scanner

"""Focused tests for per-user logging setup and error-path diagnostics."""

import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class LoggingSetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._root_logger = logging.getLogger()
        self._original_handlers = list(self._root_logger.handlers)
        self._original_level = self._root_logger.level
        self._original_propagate = self._root_logger.propagate

    def tearDown(self) -> None:
        root = self._root_logger
        for handler in list(root.handlers):
            if handler not in self._original_handlers:
                handler.close()
                root.removeHandler(handler)
        root.setLevel(self._original_level)
        root.propagate = self._original_propagate

    def test_setup_logging_creates_per_user_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"XDG_STATE_HOME": directory}, clear=False):
                path = main.setup_logging()

            self.assertIsNotNone(path)
            self.assertTrue(Path(path or "").exists())

    def test_log_path_uses_platform_state_conventions(self) -> None:
        home = Path("/home/alice")
        self.assertEqual(
            main.default_log_path(
                environment={"XDG_STATE_HOME": "/tmp/state"},
                home=home,
                platform_name="Linux",
            ),
            Path("/tmp/state/system-analyzer/system-analyzer.log"),
        )
        self.assertEqual(
            main.default_log_path(
                environment={"LOCALAPPDATA": r"C:\Users\Alice\AppData\Local"},
                home=home,
                platform_name="Windows",
            ),
            Path(r"C:\Users\Alice\AppData\Local/system-analyzer/system-analyzer.log"),
        )
        self.assertEqual(
            main.default_log_path(environment={}, home=home, platform_name="Darwin"),
            home / "Library" / "Logs" / "system-analyzer" / main.LOG_FILE_NAME,
        )

    def test_setup_logging_falls_back_when_state_dir_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / "state"
            blocker.write_text("not a directory")

            with patch.dict(os.environ, {"XDG_STATE_HOME": str(blocker)}, clear=False):
                result = main.setup_logging()

            self.assertIsNone(result)


class ScannerErrorLoggingTests(unittest.TestCase):
    def test_psutil_value_logs_failed_sensor_read(self) -> None:
        scanner = make_scanner()

        def broken() -> object:
            raise PermissionError("sensor denied")

        with self.assertLogs("maintenance.scanner", level="WARNING") as log:
            result = scanner._psutil_value(broken)

        self.assertIsNone(result)
        self.assertIn("sensor denied", "\n".join(log.output))


class EntryPointArgParsingTests(unittest.TestCase):
    """Regression for Windows finding #1: CLI flags must not launch the GUI.

    Previously every flag (--help, --version, or any unknown flag) silently
    launched the full GUI window and hung forever.  argparse must intercept
    argv before any GUI or logging setup is reached.
    """

    def test_help_flag_exits_zero_without_launching_gui(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            main._build_arg_parser().parse_args(["--help"])
        self.assertEqual(cm.exception.code, 0)

    def test_version_flag_exits_zero_and_prints_version(self) -> None:
        import io

        buf = io.StringIO()
        with (
            self.assertRaises(SystemExit) as cm,
            patch("sys.stdout", buf),
        ):
            main._build_arg_parser().parse_args(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("system-analyzer", buf.getvalue())

    def test_unknown_flag_exits_nonzero_without_launching_gui(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            main._build_arg_parser().parse_args(["--totally-bogus-flag-xyz"])
        self.assertNotEqual(cm.exception.code, 0)

    def test_no_flags_returns_namespace_without_exiting(self) -> None:
        # parse_args([]) must return normally — no SystemExit, no GUI.
        ns = main._build_arg_parser().parse_args([])
        self.assertIsNotNone(ns)


if __name__ == "__main__":
    unittest.main()

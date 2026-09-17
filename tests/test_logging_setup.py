from tests.support.scanner import make_scanner

"""Focused tests for per-user logging setup and error-path diagnostics."""

import io
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import main
from maintenance._version import __version__


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

    Parser-isolation layer: tests _build_arg_parser() directly.
    """

    def test_help_flag_exits_zero(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            main._build_arg_parser().parse_args(["--help"])
        self.assertEqual(cm.exception.code, 0)

    def test_version_flag_exits_zero_and_emits_canonical_version(self) -> None:
        buf = io.StringIO()
        with (
            self.assertRaises(SystemExit) as cm,
            patch("sys.stdout", buf),
        ):
            main._build_arg_parser().parse_args(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("system-analyzer", buf.getvalue())
        self.assertIn(__version__, buf.getvalue())

    def test_unknown_flag_exits_nonzero(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            main._build_arg_parser().parse_args(["--totally-bogus-flag-xyz"])
        self.assertNotEqual(cm.exception.code, 0)

    def test_no_flags_returns_namespace_without_exiting(self) -> None:
        ns = main._build_arg_parser().parse_args([])
        self.assertIsNotNone(ns)


class EntryPointEndToEndTests(unittest.TestCase):
    """End-to-end tests invoking main.main() with mocked GUI bootstrap.

    These prove that argparse fires BEFORE AppWindow is constructed, so
    --help / --version / unknown options can never start the GUI, the listener,
    or discovery — regardless of future refactoring inside main().
    """

    def _run_main(self, argv: list[str]) -> None:
        with patch("sys.argv", ["system-analyzer"] + argv):
            main.main()

    def test_help_exits_zero_and_never_constructs_app_window(self) -> None:
        with (
            patch("main.AppWindow") as mock_app,
            patch("main.setup_logging", return_value=None),
            self.assertRaises(SystemExit) as cm,
        ):
            self._run_main(["--help"])
        self.assertEqual(cm.exception.code, 0)
        mock_app.assert_not_called()

    def test_version_exits_zero_and_never_constructs_app_window(self) -> None:
        buf = io.StringIO()
        with (
            patch("main.AppWindow") as mock_app,
            patch("main.setup_logging", return_value=None),
            patch("sys.stdout", buf),
            self.assertRaises(SystemExit) as cm,
        ):
            self._run_main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn(__version__, buf.getvalue())
        mock_app.assert_not_called()

    def test_unknown_option_exits_nonzero_and_never_constructs_app_window(
        self,
    ) -> None:
        with (
            patch("main.AppWindow") as mock_app,
            patch("main.setup_logging", return_value=None),
            self.assertRaises(SystemExit) as cm,
        ):
            self._run_main(["--totally-bogus-flag-xyz"])
        self.assertNotEqual(cm.exception.code, 0)
        mock_app.assert_not_called()

    def test_no_args_constructs_app_window_exactly_once_and_calls_run(self) -> None:
        mock_lock = MagicMock()
        mock_instance = MagicMock()
        with (
            patch("main.instance_lock.acquire", return_value=mock_lock),
            patch("main.AppWindow", return_value=mock_instance) as mock_app,
            patch("main.setup_logging", return_value=None),
        ):
            self._run_main([])
        mock_app.assert_called_once_with()
        mock_instance.run.assert_called_once_with()
        mock_lock.release.assert_called_once_with()

    def test_second_launch_exits_nonzero_and_never_constructs_app_window(self) -> None:
        with (
            patch("main.instance_lock.acquire", return_value=None),
            patch("main.AppWindow") as mock_app,
            patch("main.setup_logging", return_value=None),
            self.assertRaises(SystemExit) as cm,
        ):
            self._run_main([])
        self.assertEqual(cm.exception.code, 1)
        mock_app.assert_not_called()

    def test_help_exits_before_lock_is_attempted(self) -> None:
        with (
            patch("main.instance_lock.acquire") as mock_acquire,
            patch("main.AppWindow") as mock_app,
            patch("main.setup_logging", return_value=None),
            self.assertRaises(SystemExit) as cm,
        ):
            self._run_main(["--help"])
        self.assertEqual(cm.exception.code, 0)
        mock_acquire.assert_not_called()
        mock_app.assert_not_called()

    def test_version_exits_before_lock_is_attempted(self) -> None:
        buf = io.StringIO()
        with (
            patch("main.instance_lock.acquire") as mock_acquire,
            patch("main.AppWindow") as mock_app,
            patch("main.setup_logging", return_value=None),
            patch("sys.stdout", buf),
            self.assertRaises(SystemExit) as cm,
        ):
            self._run_main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn(__version__, buf.getvalue())
        mock_acquire.assert_not_called()
        mock_app.assert_not_called()

    def test_lock_released_after_app_run_completes(self) -> None:
        mock_lock = MagicMock()
        mock_instance = MagicMock()
        call_order: list[str] = []
        mock_instance.run.side_effect = lambda: call_order.append("run")
        mock_lock.release.side_effect = lambda: call_order.append("release")
        with (
            patch("main.instance_lock.acquire", return_value=mock_lock),
            patch("main.AppWindow", return_value=mock_instance),
            patch("main.setup_logging", return_value=None),
        ):
            self._run_main([])
        self.assertEqual(call_order, ["run", "release"])


if __name__ == "__main__":
    unittest.main()

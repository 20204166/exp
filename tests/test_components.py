import os
import tempfile
import threading
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from maintenance.components import (
    BackgroundTaskRunner,
    DownloadScanner,
    DownloadsPathResolver,
    GpuDetector,
    ScanCoordinator,
    ScanCancelled,
)


class FailingAfterWidget:
    def winfo_exists(self) -> bool:
        return True

    def after(self, _delay: int, _callback: object, *_args: object) -> None:
        raise RuntimeError("event loop is stopping")


class ImmediateAfterWidget:
    def winfo_exists(self) -> bool:
        return True

    def after(self, _delay: int, callback: Callable[..., Any], *args: object) -> None:
        callback(*args)


class DownloadsPathResolverTests(unittest.TestCase):
    def test_select_returns_explicit_path(self) -> None:
        resolver = DownloadsPathResolver(
            system=lambda: "Linux",
            home=lambda: Path("/ignored"),
        )
        custom = Path("custom-downloads")

        self.assertEqual(resolver.select(custom), custom)

    def test_windows_onedrive_downloads_fallback_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            profile = base / "Profile"
            one_drive = base / "OneDrive"
            downloads = one_drive / "Downloads"
            downloads.mkdir(parents=True)

            resolver = DownloadsPathResolver(
                system=lambda: "Windows",
                home=lambda: profile,
                environment={
                    "USERPROFILE": str(profile),
                    "OneDrive": str(one_drive),
                },
            )

            with patch.object(
                DownloadsPathResolver,
                "_windows_downloads_path",
                return_value=None,
            ):
                self.assertEqual(resolver.select(), downloads)

    def test_path_exists_is_fail_safe_when_exists_raises(self) -> None:
        with patch.object(Path, "exists", side_effect=OSError("boom")):
            self.assertTrue(DownloadsPathResolver._path_exists(Path("broken")))


class DownloadScannerTests(unittest.TestCase):
    def test_scan_finds_large_files_and_only_extra_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            downloads = Path(directory)
            hidden_dir = downloads / ".hidden"
            hidden_file = hidden_dir / "secret.bin"
            first = downloads / "a-copy.bin"
            second = downloads / "b-copy.bin"
            large = downloads / "large.bin"

            hidden_dir.mkdir()
            first.write_bytes(b"same contents")
            second.write_bytes(b"same contents")
            hidden_file.write_bytes(b"hidden contents")
            large.write_bytes(b"large file contents")

            scanner = DownloadScanner(downloads)
            scanner.DUPLICATE_MIN_BYTES = 1
            scanner.LARGE_FILE_BYTES = 15

            candidates = scanner.scan_downloads()
            by_path = {candidate.path: candidate for candidate in candidates}

            self.assertNotIn(first, by_path)
            self.assertIn(second, by_path)
            self.assertIn("Duplicate file", by_path[second].reason)
            self.assertIn(large, by_path)
            self.assertIn("Large file", by_path[large].reason)
            self.assertNotIn(hidden_file, by_path)

    def test_scan_reuses_hash_cache_and_invalidates_on_mtime_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            downloads = Path(directory)
            first = downloads / "a-copy.bin"
            second = downloads / "b-copy.bin"
            first.write_bytes(b"same contents")
            second.write_bytes(b"same contents")

            scanner = DownloadScanner(downloads)
            scanner.DUPLICATE_MIN_BYTES = 1
            real_hash = DownloadScanner._file_hash

            with patch.object(
                DownloadScanner,
                "_file_hash",
                wraps=real_hash,
            ) as hash_mock:
                self.assertEqual(len(scanner.scan_downloads()), 1)
                self.assertEqual(len(scanner.scan_downloads()), 1)
                self.assertEqual(hash_mock.call_count, 2)

                updated_mtime = first.stat().st_mtime_ns + 2_000_000
                os.utime(first, ns=(updated_mtime, updated_mtime))
                self.assertEqual(len(scanner.scan_downloads()), 1)

            self.assertEqual(hash_mock.call_count, 3)

    def test_scan_reports_progress_and_honours_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            downloads = Path(directory)
            first = downloads / "one.bin"
            second = downloads / "two.bin"
            first.write_bytes(b"same contents")
            second.write_bytes(b"same contents")

            scanner = DownloadScanner(downloads)
            scanner.DUPLICATE_MIN_BYTES = 1
            messages: list[str] = []

            scanner.scan_downloads(progress_callback=messages.append)

            self.assertTrue(any(message.startswith("Found ") for message in messages))
            self.assertTrue(
                any("Checking duplicates" in message for message in messages)
            )

            cancel_event = threading.Event()
            cancel_event.set()
            with self.assertRaises(ScanCancelled):
                scanner.scan_downloads(cancel_event=cancel_event)


class BackgroundTaskRunnerTests(unittest.TestCase):
    def test_run_in_thread_delivers_progress_and_success(self) -> None:
        widget: Any = ImmediateAfterWidget()
        runner = BackgroundTaskRunner()
        progress_messages: list[str] = []
        completed = threading.Event()
        success = Mock(side_effect=lambda _value: completed.set())

        def progress_task(report, _cancel_event):
            report("working")
            return "done"

        runner.run_in_thread(
            widget,
            lambda: "unused",
            success,
            progress_task=progress_task,
            on_progress=progress_messages.append,
        )

        self.assertTrue(completed.wait(1))
        success.assert_called_once_with("done")
        self.assertEqual(progress_messages, ["working"])

    def test_run_ignores_runtime_error_during_widget_teardown(self) -> None:
        widget: Any = FailingAfterWidget()
        runner = BackgroundTaskRunner()
        task_finished = threading.Event()
        success = Mock()

        def task() -> None:
            task_finished.set()

        runner.run(widget, task, success)

        self.assertTrue(task_finished.wait(1))
        success.assert_not_called()


class GpuDetectorTests(unittest.TestCase):
    def test_gpu_detector_prefers_platform_specific_loader(self) -> None:
        calls: list[str] = []

        def nvidia_loader() -> tuple[str, ...] | None:
            calls.append("nvidia")
            return None

        def mac_loader() -> tuple[str, ...]:
            calls.append("mac")
            return ("mac",)

        def windows_loader() -> tuple[str, ...]:
            calls.append("windows")
            return ("windows",)

        def linux_loader() -> tuple[str, ...]:
            calls.append("linux")
            return ("linux",)

        detector = GpuDetector(
            system=lambda: "Linux",
            nvidia_loader=nvidia_loader,
            mac_loader=mac_loader,
            windows_loader=windows_loader,
            linux_loader=linux_loader,
        )

        self.assertEqual(detector.detect(), ("linux",))
        self.assertEqual(calls, ["nvidia", "linux"])


class ScanCoordinatorTests(unittest.TestCase):
    def test_scan_coordinator_defers_rerun_until_completion(self) -> None:
        coordinator = ScanCoordinator()

        generation, started = coordinator.begin()
        self.assertTrue(started)
        self.assertEqual(generation, 1)

        repeated_generation, repeated_started = coordinator.begin()
        self.assertFalse(repeated_started)
        self.assertEqual(repeated_generation, 1)

        finished, rerun_requested = coordinator.finish(generation)
        self.assertTrue(finished)
        self.assertTrue(rerun_requested)

        next_generation, next_started = coordinator.begin()
        self.assertTrue(next_started)
        self.assertEqual(next_generation, 2)

    def test_scan_coordinator_cancel_clears_pending_scan_state(self) -> None:
        coordinator = ScanCoordinator()

        generation, started = coordinator.begin()
        self.assertTrue(started)
        self.assertEqual(generation, 1)

        coordinator.begin()
        coordinator.cancel()

        self.assertFalse(coordinator.active)
        self.assertFalse(coordinator.rerun_requested)
        self.assertEqual(coordinator.generation, 1)

        next_generation, next_started = coordinator.begin()
        self.assertTrue(next_started)
        self.assertEqual(next_generation, 2)


if __name__ == "__main__":
    unittest.main()

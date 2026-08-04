import getpass
import importlib.util
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import maintenance.scanner as scanner_module
from maintenance.actions import FileManager, ProcessManager
from maintenance.models import DashboardSnapshot, ResourceSummary
from maintenance.scanner import ScanCancelled, SystemScanner


class ScannerTests(unittest.TestCase):
    def test_download_scan_finds_large_files_and_only_extra_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            downloads = Path(directory)
            first = downloads / "a-copy.bin"
            second = downloads / "b-copy.bin"
            large = downloads / "large.bin"
            first.write_bytes(b"same contents")
            second.write_bytes(b"same contents")
            large.write_bytes(b"large file contents")

            scanner = SystemScanner(downloads)
            scanner.DUPLICATE_MIN_BYTES = 1
            scanner.LARGE_FILE_BYTES = 15
            candidates = scanner.scan_downloads()

            by_path = {candidate.path: candidate for candidate in candidates}
            self.assertNotIn(first, by_path)
            self.assertIn(second, by_path)
            self.assertIn("Duplicate file", by_path[second].reason)
            self.assertIn(large, by_path)
            self.assertIn("Large file", by_path[large].reason)

    def test_download_scan_ignores_hidden_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            downloads = Path(directory)
            visible = downloads / "visible.bin"
            hidden_dir = downloads / ".hidden"
            hidden_file = hidden_dir / "secret.bin"

            hidden_dir.mkdir()
            visible.write_bytes(b"visible contents")
            hidden_file.write_bytes(b"hidden contents")

            scanner = SystemScanner(downloads)
            scanner.DUPLICATE_MIN_BYTES = 1
            scanner.LARGE_FILE_BYTES = 1
            candidates = scanner.scan_downloads()

            by_path = {candidate.path for candidate in candidates}
            self.assertIn(visible, by_path)
            self.assertNotIn(hidden_file, by_path)

    def test_download_scan_keeps_equal_size_candidates_in_stable_path_order(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            downloads = Path(directory)
            first_directory = downloads / "a"
            second_directory = downloads / "b"
            first_directory.mkdir()
            second_directory.mkdir()
            first = first_directory / "file.bin"
            second = second_directory / "file.bin"
            first.write_bytes(b"same size")
            second.write_bytes(b"same size")

            scanner = SystemScanner(downloads)
            scanner.LARGE_FILE_BYTES = 1
            scanner.DUPLICATE_MIN_BYTES = 100

            candidates = scanner.scan_downloads()

            self.assertEqual(
                [candidate.path for candidate in candidates], [first, second]
            )

    def test_download_scan_keeps_iterator_errors_fail_soft(self) -> None:
        class BrokenEntries:
            def __iter__(self) -> "BrokenEntries":
                return self

            def __next__(self) -> object:
                raise OSError("directory changed during scan")

            def close(self) -> None:
                pass

        with tempfile.TemporaryDirectory() as directory:
            scanner = SystemScanner(Path(directory))
            with patch(
                "maintenance.scanner.os.scandir",
                return_value=BrokenEntries(),
            ):
                self.assertEqual(scanner._download_file_stats(Path(directory)), {})

    def test_duplicate_hash_cache_reuses_hashes_and_invalidates_on_mtime_change(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            downloads = Path(directory)
            first = downloads / "a-copy.bin"
            second = downloads / "b-copy.bin"
            first.write_bytes(b"same contents")
            second.write_bytes(b"same contents")

            scanner = SystemScanner(downloads)
            scanner.DUPLICATE_MIN_BYTES = 1
            real_hash = SystemScanner._file_hash

            with patch.object(
                SystemScanner, "_file_hash", wraps=real_hash
            ) as hash_mock:
                self.assertEqual(len(scanner.scan_downloads()), 1)
                self.assertEqual(len(scanner.scan_downloads()), 1)
                self.assertEqual(hash_mock.call_count, 2)

                updated_mtime = first.stat().st_mtime_ns + 2_000_000
                os.utime(first, ns=(updated_mtime, updated_mtime))
                self.assertEqual(len(scanner.scan_downloads()), 1)

            self.assertEqual(hash_mock.call_count, 3)

    def test_duplicate_hash_cache_rechecks_same_timestamp_content_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            downloads = Path(directory)
            first = downloads / "a-copy.bin"
            second = downloads / "b-copy.bin"
            first.write_bytes(b"same contents")
            second.write_bytes(b"same contents")

            scanner = SystemScanner(downloads)
            scanner.DUPLICATE_MIN_BYTES = 1
            scanner.scan_downloads()
            original_mtime = first.stat().st_mtime_ns

            first.write_bytes(b"other content")
            os.utime(first, ns=(original_mtime, original_mtime))

            self.assertEqual(scanner.scan_downloads(), [])

    def test_duplicate_hash_cache_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            downloads = Path(directory)
            for index in range(4):
                (downloads / f"copy-{index}.bin").write_bytes(b"same contents")

            scanner = SystemScanner(downloads)
            scanner.DUPLICATE_MIN_BYTES = 1
            scanner.HASH_CACHE_MAX_ENTRIES = 2

            scanner.scan_downloads()

            self.assertLessEqual(len(scanner._hash_cache), 2)

    def test_download_scan_reports_progress_and_honours_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            downloads = Path(directory)
            (downloads / "one.bin").write_bytes(b"same contents")
            (downloads / "two.bin").write_bytes(b"same contents")
            scanner = SystemScanner(downloads)
            scanner.DUPLICATE_MIN_BYTES = 1
            messages: list[str] = []

            scanner.scan_downloads(progress_callback=messages.append)

            self.assertTrue(
                any("Checking duplicates" in message for message in messages)
            )

            cancel_event = threading.Event()
            cancel_event.set()
            with self.assertRaises(ScanCancelled):
                scanner.scan_downloads(cancel_event=cancel_event)

    def test_cancellable_scan_keeps_one_argument_hash_hooks_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            downloads = Path(directory)
            (downloads / "one.bin").write_bytes(b"same contents")
            (downloads / "two.bin").write_bytes(b"same contents")
            scanner = SystemScanner(downloads)
            scanner.DUPLICATE_MIN_BYTES = 1
            original_hash = SystemScanner._file_hash
            scanner._file_hash = lambda path: original_hash(path)

            self.assertEqual(
                len(scanner.scan_downloads(cancel_event=threading.Event())),
                1,
            )

    def test_process_scan_honours_cancellation_before_enumeration(self) -> None:
        cancel_event = threading.Event()
        cancel_event.set()

        with self.assertRaises(ScanCancelled):
            SystemScanner(Path("Downloads")).scan_processes(cancel_event=cancel_event)

    def test_snapshot_get_returns_resource_and_rejects_unknown_key(self) -> None:
        resource = ResourceSummary(
            key="cpu",
            title="CPU",
            value="10%",
            subtitle="Current usage",
            percent=10,
            details=("Two cores",),
        )
        snapshot = DashboardSnapshot(
            system_label="Test System",
            scanned_at=SimpleNamespace(),
            resources=(resource,),
        )

        self.assertEqual(snapshot.get("cpu"), resource)
        with self.assertRaises(KeyError):
            snapshot.get("missing")

    def test_windows_usernames_are_compared_without_the_domain(self) -> None:
        self.assertTrue(SystemScanner._same_user("WORKGROUP\\Iryna", "iryna"))

    def test_mac_windows_and_linux_gpu_fallbacks_are_parsed(self) -> None:
        mac_result = SimpleNamespace(
            stdout=json.dumps(
                {
                    "SPDisplaysDataType": [
                        {"sppci_model": "Intel Iris", "spdisplays_vram": "1 GB"}
                    ]
                }
            )
        )
        windows_result = SimpleNamespace(
            stdout=json.dumps(
                {
                    "Name": "AMD Radeon",
                    "AdapterRAM": 2 * 1024**3,
                    "DriverVersion": "1.2.3",
                }
            )
        )
        linux_result = SimpleNamespace(
            stdout="00:02.0 VGA compatible controller: Intel Corporation UHD\n"
        )

        with patch("maintenance.scanner.subprocess.run", return_value=mac_result):
            self.assertIn("Intel Iris", SystemScanner._mac_gpu_details())
        with patch("maintenance.scanner.subprocess.run", return_value=windows_result):
            self.assertIn("AMD Radeon", SystemScanner._windows_gpu_details())
        with patch("maintenance.scanner.subprocess.run", return_value=linux_result):
            self.assertIn(
                "Intel Corporation UHD",
                SystemScanner._linux_gpu_details(),
            )

    def test_gpu_fallback_details_are_cached_per_scanner(self) -> None:
        scanner = SystemScanner(Path("Downloads"))
        with (
            patch("maintenance.scanner.platform.system", return_value="Windows"),
            patch.object(scanner, "_nvidia_gpu_details", return_value=None),
            patch.object(
                scanner,
                "_windows_gpu_details",
                return_value=("AMD Radeon",),
            ) as loader,
        ):
            self.assertEqual(scanner.gpu_details(), ("AMD Radeon",))
            self.assertEqual(scanner.gpu_details(), ("AMD Radeon",))

        loader.assert_called_once_with()

    def test_gpu_fallback_errors_are_retried_for_recovery(self) -> None:
        scanner = SystemScanner(Path("Downloads"))
        with (
            patch("maintenance.scanner.platform.system", return_value="Darwin"),
            patch.object(scanner, "_mac_gpu_details") as loader,
        ):
            loader.side_effect = [
                ("GPU information unavailable: first failure",),
                ("Intel Iris",),
            ]

            self.assertIn("unavailable", scanner.gpu_details()[0])
            self.assertEqual(scanner.gpu_details(), ("Intel Iris",))

        self.assertEqual(loader.call_count, 2)

    def test_windows_known_folder_is_used_before_environment_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            known_folder = Path(directory)
            with (
                patch("maintenance.scanner.platform.system", return_value="Windows"),
                patch.object(
                    SystemScanner,
                    "_windows_downloads_path",
                    return_value=known_folder,
                ),
            ):
                self.assertEqual(
                    SystemScanner._default_downloads_path(),
                    known_folder,
                )

    def test_missing_windows_known_folder_uses_existing_onedrive_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            one_drive = Path(directory)
            downloads = one_drive / "Downloads"
            downloads.mkdir()
            malformed_known_folder = one_drive / "KnownFolderFile"
            malformed_known_folder.write_text("not a directory")
            with (
                patch("maintenance.scanner.platform.system", return_value="Windows"),
                patch.object(
                    SystemScanner,
                    "_windows_downloads_path",
                    return_value=malformed_known_folder,
                ),
                patch.dict(
                    os.environ,
                    {
                        "USERPROFILE": str(one_drive / "Profile"),
                        "OneDrive": str(one_drive),
                    },
                    clear=False,
                ),
            ):
                self.assertEqual(SystemScanner._default_downloads_path(), downloads)

    def test_file_home_downloads_falls_back_to_unavailable_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "Downloads").write_text("not a directory")
            with (
                patch("maintenance.scanner.platform.system", return_value="Windows"),
                patch.object(
                    SystemScanner, "_windows_downloads_path", return_value=None
                ),
                patch.dict(
                    os.environ,
                    {"USERPROFILE": str(home), "OneDrive": str(home / "Missing")},
                    clear=False,
                ),
            ):
                result = SystemScanner._default_downloads_path()

            self.assertEqual(result.name, "Downloads.__unavailable__")
            self.assertFalse(result.is_file())

    def test_windows_recycle_bin_size_uses_shell_query(self) -> None:
        class FakeQuery:
            restype: object = None

            def __call__(self, _root: object, info_pointer: Any) -> int:
                info_pointer._obj.size = 1234
                return 0

        fake_windll: Any = type(
            "FakeWindll",
            (),
            {"shell32": type("FakeShell", (), {"SHQueryRecycleBinW": FakeQuery()})()},
        )()

        with (
            patch("maintenance.scanner.platform.system", return_value="Windows"),
            patch.object(scanner_module.ctypes, "windll", fake_windll),
        ):
            self.assertEqual(SystemScanner().trash_size(), 1234)
            self.assertIsNotNone(fake_windll.shell32.SHQueryRecycleBinW.argtypes)


class FileManagerTests(unittest.TestCase):
    def test_file_root_cannot_be_used_as_trash_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root_file = Path(directory) / "Downloads"
            root_file.write_text("not a directory")
            moved: list[str] = []
            manager = FileManager(root_file)

            with patch("maintenance.actions.send2trash", moved.append):
                result = manager.move_to_trash([root_file])

            self.assertEqual(result.moved, ())
            self.assertEqual(moved, [])

    def test_only_files_inside_allowed_root_can_move_to_trash(self) -> None:
        with tempfile.TemporaryDirectory() as allowed_directory:
            with tempfile.TemporaryDirectory() as outside_directory:
                allowed = Path(allowed_directory)
                inside = allowed / "inside.txt"
                outside = Path(outside_directory) / "outside.txt"
                inside.write_text("inside")
                outside.write_text("outside")
                moved: list[str] = []

                manager = FileManager(allowed)
                with patch("maintenance.actions.send2trash", moved.append):
                    result = manager.move_to_trash([inside, outside])

                self.assertEqual(result.moved, (inside.resolve(),))
                self.assertEqual(moved, [str(inside.resolve())])
                self.assertEqual(len(result.errors), 1)


class FakeProcess:
    def __init__(self, pid: int, name: str, username: str) -> None:
        self.pid = pid
        self._name = name
        self._username = username
        self.terminated = False
        self.killed = False

    def name(self) -> str:
        return self._name

    def username(self) -> str:
        return self._username

    def parents(self) -> list:
        return []

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


class FakePsutil:
    class NoSuchProcess(Exception):
        pass

    class AccessDenied(Exception):
        pass

    def __init__(self, processes: dict[int, FakeProcess]) -> None:
        self.processes = processes
        self.wait_procs_calls = 0

    def Process(self, pid: int) -> FakeProcess:
        return self.processes[pid]

    def wait_procs(
        self, processes: list[FakeProcess], timeout: int
    ) -> tuple[list, list]:
        del timeout
        self.wait_procs_calls += 1
        return processes, []


class ProcessManagerTests(unittest.TestCase):
    def test_current_process_is_protected_and_user_process_can_quit(self) -> None:
        current = FakeProcess(os.getpid(), "python", getpass.getuser())
        allowed = FakeProcess(50001, "Example App", getpass.getuser())
        fake_psutil = FakePsutil({os.getpid(): current, 50001: allowed})

        with patch("maintenance.actions.psutil", fake_psutil):
            result = ProcessManager().request_quit([os.getpid(), 50001])

        self.assertFalse(current.terminated)
        self.assertTrue(allowed.terminated)
        self.assertEqual(result.stopped, (50001,))
        self.assertTrue(any("protected" in error for error in result.errors))

    def test_empty_quit_request_returns_without_waiting(self) -> None:
        current = FakeProcess(os.getpid(), "python", getpass.getuser())
        fake_psutil = FakePsutil({os.getpid(): current})

        with patch("maintenance.actions.psutil", fake_psutil):
            result = ProcessManager().request_quit([])

        self.assertEqual(result.requested, 0)
        self.assertEqual(result.stopped, ())
        self.assertEqual(result.force_required, ())
        self.assertEqual(result.errors, ())
        self.assertEqual(fake_psutil.wait_procs_calls, 0)


class SourceIntegrationTests(unittest.TestCase):
    def test_attached_analyzer_exposes_dashboard_methods(self) -> None:
        path = Path(__file__).parents[1] / "algo.py"
        spec = importlib.util.spec_from_file_location("attached_algo", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        analyzer = module.Analyzer()
        self.assertTrue(callable(analyzer.dashboard_snapshot))
        self.assertTrue(callable(analyzer.process_candidates))
        self.assertTrue(callable(analyzer.storage_candidates))


if __name__ == "__main__":
    unittest.main()

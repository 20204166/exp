import getpass
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from maintenance.actions import FileManager, ProcessManager
from maintenance.models import DashboardSnapshot, ResourceSummary
from maintenance.scanner import SystemScanner


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


class FileManagerTests(unittest.TestCase):
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

    def Process(self, pid: int) -> FakeProcess:
        return self.processes[pid]

    @staticmethod
    def wait_procs(processes: list[FakeProcess], timeout: int) -> tuple[list, list]:
        del timeout
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
import os
import tempfile
import threading
import unittest
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from maintenance.components import (
    BackgroundTaskRunner,
    DownloadScanner,
    DownloadsPathResolver,
    GpuDetector,
    ProcessSafetyPolicy,
    ResourceFeature,
    ResourceFeatureCatalog,
    ScanCancelled,
    ScanCoordinator,
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


class PolicyProcess:
    def __init__(
        self,
        pid: int,
        name: str = "Example App",
        username: str = "alice",
        parents: list["PolicyProcess"] | None = None,
    ) -> None:
        self.pid = pid
        self._name = name
        self._username = username
        self._parents = parents or []

    def name(self) -> str:
        return self._name

    def username(self) -> str:
        return self._username

    def parents(self) -> list["PolicyProcess"]:
        return self._parents


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


class ProcessSafetyPolicyTests(unittest.TestCase):
    CURRENT_PID = 100

    def setUp(self) -> None:
        self.current = PolicyProcess(
            self.CURRENT_PID,
            parents=[PolicyProcess(90), PolicyProcess(80)],
        )
        self.processes = {self.CURRENT_PID: self.current}
        self.policy = ProcessSafetyPolicy(
            current_pid_loader=lambda: self.CURRENT_PID,
            process_loader=self.processes.__getitem__,
        )

    def test_same_local_user_is_allowed(self) -> None:
        self.assertTrue(self.policy.same_user("alice", "ALICE"))

    def test_different_user_is_rejected(self) -> None:
        self.assertFalse(self.policy.same_user("alice", "bob"))

    def test_windows_domain_prefix_is_ignored(self) -> None:
        self.assertTrue(self.policy.same_user(r"WORKGROUP\Alice", "alice"))
        self.assertTrue(self.policy.same_user("WORKGROUP/Alice", "ALICE"))

    def test_protected_name_is_case_insensitive(self) -> None:
        self.assertFalse(
            self.policy.can_manage(
                pid=200,
                name="EXPLORER.EXE",
                username="alice",
                current_user="alice",
            )
        )

    def test_base_current_and_parent_pids_are_protected(self) -> None:
        protected = self.policy.protected_pids()

        self.assertTrue({0, 1, 80, 90, self.CURRENT_PID} <= protected)
        for pid in (0, 1, 80, 90, self.CURRENT_PID):
            self.assertFalse(
                self.policy.can_manage(
                    pid=pid,
                    name="Example App",
                    username="alice",
                    current_user="alice",
                )
            )

    def test_normal_same_user_application_is_allowed(self) -> None:
        self.assertTrue(
            self.policy.can_manage(
                pid=200,
                name="Example App",
                username="alice",
                current_user="alice",
            )
        )

    def test_missing_process_is_protected(self) -> None:
        self.assertFalse(self.policy.can_manage_process(pid=201, current_user="alice"))

    def test_access_denied_process_information_is_protected(self) -> None:
        def loader(pid: int) -> PolicyProcess:
            if pid == self.CURRENT_PID:
                return self.current
            raise PermissionError("access denied")

        policy = ProcessSafetyPolicy(
            current_pid_loader=lambda: self.CURRENT_PID,
            process_loader=loader,
        )

        self.assertFalse(policy.can_manage_process(pid=202, current_user="alice"))

    def test_access_denied_current_process_ancestry_fails_closed(self) -> None:
        def loader(_pid: int) -> PolicyProcess:
            raise PermissionError("access denied")

        policy = ProcessSafetyPolicy(
            current_pid_loader=lambda: self.CURRENT_PID,
            process_loader=loader,
        )

        self.assertEqual(policy.protected_pids(), {0, 1, self.CURRENT_PID})
        self.assertFalse(
            policy.can_manage(
                pid=200,
                name="Example App",
                username="alice",
                current_user="alice",
            )
        )

    def test_can_manage_process_uses_loaded_name_and_user(self) -> None:
        self.processes[200] = PolicyProcess(
            200,
            name="Example App",
            username=r"WORKGROUP\Alice",
        )

        self.assertTrue(self.policy.can_manage_process(pid=200, current_user="alice"))


class ResourceFeatureCatalogTests(unittest.TestCase):
    EXPECTED_KEYS = ("cpu", "memory", "storage", "gpu", "network", "battery")

    def test_default_catalog_preserves_current_six_resources_and_order(self) -> None:
        catalog = ResourceFeatureCatalog()

        self.assertEqual(
            tuple(feature.key for feature in catalog.all()),
            self.EXPECTED_KEYS,
        )
        self.assertEqual(
            tuple(feature.title for feature in catalog.all()),
            ("CPU", "Memory", "Storage", "GPU", "Network", "Battery"),
        )
        self.assertEqual(
            tuple(feature.loader_name for feature in catalog.all()),
            (
                "cpu_info",
                "memory_info",
                "storage_info",
                "gpu_info",
                "network_info",
                "battery_info",
            ),
        )

    def test_action_categories_match_current_resource_handlers(self) -> None:
        catalog = ResourceFeatureCatalog()

        self.assertEqual(catalog.get("cpu").action_kind, "process")
        self.assertEqual(catalog.get("memory").action_kind, "process")
        self.assertEqual(catalog.get("storage").action_kind, "storage")
        self.assertEqual(catalog.get("gpu").action_kind, "informational")
        self.assertEqual(catalog.get("network").action_kind, "informational")
        self.assertEqual(catalog.get("battery").action_kind, "informational")

    def test_lookup_and_unknown_key_behavior_are_explicit(self) -> None:
        catalog = ResourceFeatureCatalog()

        self.assertEqual(catalog.get("gpu").title, "GPU")
        with self.assertRaisesRegex(KeyError, "Unknown resource feature"):
            catalog.get("missing")

    def test_register_rejects_duplicate_keys(self) -> None:
        catalog = ResourceFeatureCatalog()

        with self.assertRaisesRegex(ValueError, "already registered"):
            catalog.register(ResourceFeature("cpu", "Other CPU", 9, "info", "other"))

    def test_ordering_is_deterministic_for_custom_features(self) -> None:
        catalog = ResourceFeatureCatalog(
            (
                ResourceFeature("later", "Later", 4, "info", "later_info"),
                ResourceFeature("same-b", "Same B", 2, "info", "b_info"),
                ResourceFeature("first", "First", 1, "info", "first_info"),
                ResourceFeature("same-a", "Same A", 2, "info", "a_info"),
            )
        )

        self.assertEqual(
            tuple(feature.key for feature in catalog.all()),
            ("first", "same-a", "same-b", "later"),
        )

    def test_platform_availability_is_metadata_not_ui_logic(self) -> None:
        feature = ResourceFeature(
            "windows-only",
            "Windows Only",
            6,
            "informational",
            "windows_info",
            platforms=("Windows", "Darwin"),
        )
        catalog = ResourceFeatureCatalog(features=(feature,))

        self.assertTrue(feature.is_available_on("windows"))
        self.assertTrue(feature.is_available_on("DARWIN"))
        self.assertFalse(feature.is_available_on("Linux"))
        self.assertEqual(catalog.available_on("linux"), ())

    def test_separate_catalog_instances_are_isolated(self) -> None:
        first = ResourceFeatureCatalog()
        second = ResourceFeatureCatalog()
        extra = ResourceFeature("extra", "Extra", 6, "informational", "extra_info")

        first.register(extra)

        self.assertEqual(first.get("extra"), extra)
        with self.assertRaises(KeyError):
            second.get("extra")

    def test_feature_definitions_are_immutable_and_all_returns_tuple(self) -> None:
        feature = ResourceFeature("test", "Test", 0, "informational", "test_info")
        catalog = ResourceFeatureCatalog(features=(feature,))

        with self.assertRaises(FrozenInstanceError):
            feature.title = "Changed"  # type: ignore[misc]
        self.assertIsInstance(catalog.all(), tuple)


class ProcessSafetyPolicyParityTests(unittest.TestCase):
    CURRENT = 5555

    def _policy(self) -> ProcessSafetyPolicy:
        def loader(pid: int) -> PolicyProcess:
            if pid == self.CURRENT:
                return PolicyProcess(self.CURRENT)
            raise KeyError(pid)

        return ProcessSafetyPolicy(
            current_pid_loader=lambda: self.CURRENT,
            process_loader=loader,
        )

    def test_same_user_matches_existing_implementations(self) -> None:
        from maintenance.actions import ProcessManager
        from maintenance.scanner import SystemScanner

        policy = ProcessSafetyPolicy(
            current_pid_loader=lambda: 0,
            process_loader=lambda pid: PolicyProcess(pid),
        )
        pairs = (
            ("alice", "ALICE"),
            (r"WORKGROUP\Iryna", "iryna"),
            ("WORKGROUP/Alice", "alice"),
            ("alice", "bob"),
            ("", "alice"),
        )
        for username, current_user in pairs:
            expected = SystemScanner._same_user(username, current_user)
            self.assertEqual(policy.same_user(username, current_user), expected)
            self.assertEqual(
                ProcessManager._same_user(username, current_user), expected
            )

    def test_protected_names_cover_both_existing_collections(self) -> None:
        from maintenance.actions import ProcessManager
        from maintenance.scanner import SystemScanner

        expected = set(SystemScanner.PROTECTED_PROCESS_NAMES)
        self.assertEqual(set(ProcessSafetyPolicy.PROTECTED_NAMES), expected)
        self.assertEqual(set(ProcessManager.PROTECTED_NAMES), expected)

    def test_base_protected_pids_match_existing_defaults(self) -> None:
        from maintenance.scanner import SystemScanner

        base = {0, 1, os.getpid()}
        self.assertLessEqual(base, ProcessSafetyPolicy().protected_pids())
        self.assertLessEqual(base, SystemScanner(Path("Downloads"))._protected_pids())

    def test_decision_parity_with_scanner_and_manager_for_established_cases(
        self,
    ) -> None:
        from maintenance.actions import ProcessManager
        from maintenance.scanner import SystemScanner

        policy = self._policy()
        base = {0, 1, self.CURRENT}
        cases: tuple[tuple[int, str, str, str], ...] = (
            (self.CURRENT, "Example App", "alice", "alice"),
            (0, "Example App", "alice", "alice"),
            (1, "Example App", "alice", "alice"),
            (9999, "EXPLORER.EXE", "alice", "alice"),
            (9999, "Example App", "bob", "alice"),
            (9999, "Example App", r"WORKGROUP\Alice", "alice"),
            (9999, "Example App", "alice", "ALICE"),
            (9999, "Example App", "alice", "alice"),
        )

        def existing_decision(
            same_user: object,
            protected_names: set[str],
            pid: int,
            name: str,
            username: str,
            current_user: str,
        ) -> bool:
            return bool(
                same_user(username, current_user)
                and pid not in base
                and name.casefold() not in protected_names
            )

        for pid, name, username, current_user in cases:
            policy_decision = policy.can_manage(
                pid=pid,
                name=name,
                username=username,
                current_user=current_user,
            )
            scanner_decision = existing_decision(
                SystemScanner._same_user,
                set(SystemScanner.PROTECTED_PROCESS_NAMES),
                pid,
                name,
                username,
                current_user,
            )
            manager_decision = existing_decision(
                ProcessManager._same_user,
                set(ProcessManager.PROTECTED_NAMES),
                pid,
                name,
                username,
                current_user,
            )
            self.assertEqual(policy_decision, scanner_decision)
            self.assertEqual(policy_decision, manager_decision)


class ResourceFeatureCatalogParityTests(unittest.TestCase):
    def test_default_keys_match_window_dashboard_resource_cards(self) -> None:
        from window import AppWindow

        self.assertEqual(
            tuple(feature.key for feature in ResourceFeatureCatalog().all()),
            tuple(key for key, _ in AppWindow.RESOURCE_CARDS),
        )


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

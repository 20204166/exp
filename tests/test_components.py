import hashlib
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
    ClockCoordinator,
    DownloadScanner,
    DownloadsPathResolver,
    GpuDetector,
    JobProfile,
    PressureSnapshot,
    ProcessSafetyPolicy,
    ResourceFeature,
    ResourceFeatureCatalog,
    ResourceGovernor,
    ScanCancelled,
    ScanCoordinator,
    check_cancelled,
    gpu_unavailable_message,
    normalize_username,
    protected_process_pids,
    require_psutil,
    usernames_match,
    windows_windll,
)
from maintenance.components.coordinator import (
    AppCoordinator,
    ComponentRefreshScheduler,
    RefreshIntervals,
)
from maintenance.components.scan_support import (
    call_cancellable,
    call_legacy_compatible,
    detail_line_suffix,
    file_content_marker,
    file_sha256,
    stat_fingerprint,
)
from tests.support.scheduling import DeferredRunner


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
            self.assertIn("Verified duplicate", by_path[second].reason)
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

    def test_title_for_returns_title_for_registered_key(self) -> None:
        catalog = ResourceFeatureCatalog()

        self.assertEqual(catalog.title_for("gpu"), "GPU")
        self.assertEqual(catalog.title_for("battery"), "Battery")

    def test_title_for_returns_none_for_unknown_key(self) -> None:
        catalog = ResourceFeatureCatalog()

        self.assertIsNone(catalog.title_for("missing"))

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
            ("", ""),
        )
        for username, current_user in pairs:
            expected = SystemScanner._same_user(username, current_user)
            self.assertEqual(policy.same_user(username, current_user), expected)
            self.assertEqual(
                ProcessManager._same_user(username, current_user), expected
            )

    def test_both_empty_usernames_are_denied_by_every_implementation(self) -> None:
        from maintenance.actions import ProcessManager
        from maintenance.scanner import SystemScanner

        self.assertFalse(SystemScanner._same_user("", ""))
        self.assertFalse(ProcessManager._same_user("", ""))
        self.assertFalse(ProcessSafetyPolicy().same_user("", ""))

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
            same_user: Callable[[str, str], bool],
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
    def test_default_catalog_keys_and_titles_match_literals(self) -> None:
        features = ResourceFeatureCatalog().all()
        self.assertEqual(
            tuple(feature.key for feature in features),
            ("cpu", "memory", "storage", "gpu", "network", "battery"),
        )
        self.assertEqual(
            tuple(feature.title for feature in features),
            ("CPU", "Memory", "Storage", "GPU", "Network", "Battery"),
        )

    def test_default_orders_are_unique_ascending_from_zero(self) -> None:
        self.assertEqual(
            tuple(feature.order for feature in ResourceFeatureCatalog().all()),
            tuple(range(6)),
        )

    def test_action_kind_is_one_of_expected_kinds(self) -> None:
        for feature in ResourceFeatureCatalog().all():
            with self.subTest(key=feature.key):
                self.assertIn(
                    feature.action_kind, {"process", "storage", "informational"}
                )

    def test_action_kind_matches_unavailable_summary_actionable(self) -> None:
        from maintenance.models import unavailable_summary

        for feature in ResourceFeatureCatalog().all():
            with self.subTest(key=feature.key):
                self.assertEqual(
                    feature.action_kind != "informational",
                    unavailable_summary(feature.key, feature.title).actionable,
                )

    def test_loader_names_exist_on_analyzer(self) -> None:
        import algo

        for feature in ResourceFeatureCatalog().all():
            with self.subTest(key=feature.key):
                self.assertTrue(callable(getattr(algo.Analyzer, feature.loader_name)))

    def test_component_titles_match_catalog(self) -> None:
        from maintenance.scanner import SystemScanner

        self.assertEqual(
            SystemScanner.COMPONENT_TITLES,
            {feature.key: feature.title for feature in ResourceFeatureCatalog().all()},
        )

    def test_default_keys_match_scan_component_keys(self) -> None:
        from maintenance.scanner import SystemScanner

        self.assertEqual(
            tuple(feature.key for feature in ResourceFeatureCatalog().all()),
            SystemScanner.COMPONENT_KEYS,
        )

    def test_refresh_interval_keys_match_catalog_keys(self) -> None:
        intervals = RefreshIntervals().as_dict()

        self.assertEqual(
            set(intervals),
            {feature.key for feature in ResourceFeatureCatalog().all()},
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

    def test_scan_coordinator_cancel_invalidates_pending_generation(self) -> None:
        coordinator = ScanCoordinator()

        generation, started = coordinator.begin()
        self.assertTrue(started)
        self.assertEqual(generation, 1)

        coordinator.begin()
        coordinator.cancel()

        self.assertFalse(coordinator.active)
        self.assertFalse(coordinator.rerun_requested)
        self.assertEqual(coordinator.generation, 2)
        self.assertEqual(coordinator.finish(generation), (False, False))


class ComponentRefreshSchedulerTests(unittest.TestCase):
    def test_begin_claims_due_component_and_blocks_overlap(self) -> None:
        scheduler = ComponentRefreshScheduler({"cpu": 1000})

        self.assertTrue(scheduler.begin("cpu", 0.0))
        self.assertTrue(scheduler.in_flight("cpu"))
        self.assertFalse(scheduler.begin("cpu", 0.5))
        self.assertFalse(scheduler.begin("cpu", 2.0))

        scheduler.finish("cpu")
        self.assertFalse(scheduler.in_flight("cpu"))

    def test_begin_blocks_until_interval_elapses(self) -> None:
        scheduler = ComponentRefreshScheduler({"cpu": 1000})

        self.assertTrue(scheduler.begin("cpu", 0.0))
        scheduler.finish("cpu")
        self.assertFalse(scheduler.begin("cpu", 0.5))
        self.assertTrue(scheduler.begin("cpu", 1.0))

    def test_due_keys_exclude_in_flight_and_future(self) -> None:
        scheduler = ComponentRefreshScheduler({"cpu": 1000, "memory": 5000})

        self.assertEqual(set(scheduler.due_keys(0.0)), {"cpu", "memory"})
        scheduler.begin("cpu", 0.0)
        self.assertEqual(scheduler.due_keys(0.0), ("memory",))
        scheduler.finish("cpu")
        self.assertEqual(scheduler.due_keys(0.5), ("memory",))
        self.assertEqual(scheduler.due_keys(1.0), ("cpu", "memory"))

    def test_mark_all_refreshed_delays_every_component(self) -> None:
        scheduler = ComponentRefreshScheduler({"cpu": 1000, "memory": 5000})

        scheduler.mark_all_refreshed(0.0)

        self.assertEqual(scheduler.due_keys(0.9), ())
        self.assertEqual(scheduler.due_keys(1.0), ("cpu",))
        self.assertEqual(scheduler.due_keys(5.0), ("cpu", "memory"))

    def test_refresh_intervals_defaults_match_design(self) -> None:
        intervals = RefreshIntervals().as_dict()

        self.assertEqual(intervals["cpu"], 1000)
        self.assertEqual(intervals["network"], 1000)
        self.assertEqual(intervals["memory"], 5000)
        self.assertEqual(intervals["gpu"], 3000)
        self.assertEqual(intervals["storage"], 30000)
        self.assertEqual(intervals["battery"], 30000)
        self.assertLess(intervals["cpu"], intervals["memory"])
        self.assertLess(intervals["memory"], intervals["storage"])

    def test_set_interval_updates_only_named_component_deadline(self) -> None:
        scheduler = ComponentRefreshScheduler({"cpu": 1000, "memory": 5000})
        scheduler.mark_all_refreshed(0.0)

        scheduler.set_interval("cpu", 5000, 100.0)

        self.assertEqual(scheduler.intervals["cpu"], 5000)
        self.assertEqual(scheduler.intervals["memory"], 5000)
        self.assertEqual(scheduler.due_keys(100.9), ("memory",))
        self.assertEqual(scheduler.due_keys(101.0), ("memory",))
        self.assertEqual(scheduler.due_keys(105.0), ("cpu", "memory"))

    def test_set_interval_preserves_in_flight_and_rejects_bad_values(self) -> None:
        scheduler = ComponentRefreshScheduler({"cpu": 1000})
        self.assertTrue(scheduler.begin("cpu", 0.0))

        scheduler.set_interval("cpu", 5000, 0.0)

        self.assertTrue(scheduler.in_flight("cpu"))
        scheduler.finish("cpu")
        with self.assertRaises(ValueError):
            scheduler.set_interval("nope", 1000, 0.0)
        with self.assertRaises(TypeError):
            scheduler.set_interval("cpu", True, 0.0)
        with self.assertRaises(ValueError):
            scheduler.set_interval("cpu", 0, 0.0)

    def test_cancel_clears_in_flight_and_retry_state(self) -> None:
        scheduler = ComponentRefreshScheduler({"cpu": 1000})
        self.assertTrue(scheduler.begin("cpu", 0.0))
        scheduler.request_refresh("cpu")
        scheduler.defer("cpu", 10.0)

        scheduler.cancel("cpu")

        self.assertFalse(scheduler.in_flight("cpu"))
        self.assertNotIn("cpu", scheduler._in_flight)
        self.assertNotIn("cpu", scheduler._refresh_requested)
        self.assertNotIn("cpu", scheduler._deferred_until)

    def test_pause_prevents_due_and_new_claims_but_not_running(self) -> None:
        scheduler = ComponentRefreshScheduler({"cpu": 1000})
        self.assertTrue(scheduler.begin("cpu", 0.0))

        scheduler.pause("cpu")

        self.assertTrue(scheduler.is_paused("cpu"))
        self.assertTrue(scheduler.in_flight("cpu"))
        self.assertEqual(scheduler.due_keys(5.0), ())
        self.assertFalse(scheduler.begin("cpu", 5.0))

        scheduler.finish("cpu")
        self.assertEqual(scheduler.due_keys(5.0), ())

    def test_resume_restores_eligibility_without_duplicating_worker(self) -> None:
        scheduler = ComponentRefreshScheduler({"cpu": 1000})
        self.assertTrue(scheduler.begin("cpu", 0.0))
        scheduler.pause("cpu")
        scheduler.resume("cpu")

        self.assertFalse(scheduler.is_paused("cpu"))
        self.assertTrue(scheduler.in_flight("cpu"))
        self.assertEqual(scheduler.due_keys(0.0), ())
        scheduler.finish("cpu")
        self.assertEqual(scheduler.due_keys(1.0), ("cpu",))

    def test_request_refresh_coalesces_and_is_consumed_on_claim(self) -> None:
        scheduler = ComponentRefreshScheduler({"cpu": 1000, "memory": 5000})
        scheduler.mark_all_refreshed(100.0)

        scheduler.request_refresh("memory")
        scheduler.request_refresh("memory")

        self.assertEqual(scheduler.due_keys(100.0), ("memory",))
        self.assertTrue(scheduler.begin("memory", 100.0))
        self.assertEqual(scheduler.due_keys(100.0), ())

    def test_request_refresh_during_flight_waits_until_finish(self) -> None:
        scheduler = ComponentRefreshScheduler({"cpu": 1000})
        self.assertTrue(scheduler.begin("cpu", 0.0))

        scheduler.request_refresh("cpu")
        scheduler.finish("cpu")

        self.assertEqual(scheduler.due_keys(0.0), ("cpu",))
        self.assertTrue(scheduler.begin("cpu", 0.5))
        self.assertFalse(scheduler.begin("cpu", 0.5))
        self.assertEqual(scheduler.due_keys(0.5), ())

    def test_request_refresh_while_paused_deferred_until_resume(self) -> None:
        scheduler = ComponentRefreshScheduler({"cpu": 1000})
        scheduler.pause("cpu")

        scheduler.request_refresh("cpu")
        scheduler.resume("cpu")

        self.assertEqual(scheduler.due_keys(0.0), ("cpu",))

    def test_mark_all_refreshed_clears_pending_requests(self) -> None:
        scheduler = ComponentRefreshScheduler({"cpu": 1000})
        scheduler.request_refresh("cpu")

        scheduler.mark_all_refreshed(0.0)

        self.assertEqual(scheduler.due_keys(0.0), ())
        self.assertEqual(scheduler.due_keys(1.0), ("cpu",))

    def test_request_refresh_rejects_unknown_key(self) -> None:
        scheduler = ComponentRefreshScheduler({"cpu": 1000})
        with self.assertRaises(ValueError):
            scheduler.request_refresh("nope")


class ClockCoordinatorTests(unittest.TestCase):
    def test_begin_keeps_absolute_deadlines_after_long_run(self) -> None:
        clock = ClockCoordinator({"cpu": 1.0})

        self.assertEqual(clock.due_keys(0.0), ("cpu",))
        self.assertTrue(clock.begin("cpu", 0.0))
        clock.finish("cpu")

        self.assertEqual(clock.due_keys(0.5), ())
        self.assertEqual(clock.due_keys(1.0), ("cpu",))

        self.assertTrue(clock.begin("cpu", 3.2))
        clock.finish("cpu")

        self.assertEqual(clock.next_deadline(3.2), 4.0)
        self.assertEqual(clock.due_keys(3.2), ())

    def test_refresh_requests_and_deferrals_are_coalesced(self) -> None:
        clock = ClockCoordinator({"cpu": 1.0})
        clock.mark_all_refreshed(10.0)

        clock.request_refresh("cpu")
        self.assertEqual(clock.due_keys(10.0), ("cpu",))
        self.assertTrue(clock.begin("cpu", 10.0))
        clock.finish("cpu")

        clock.defer("cpu", 12.0)
        self.assertEqual(clock.due_keys(11.0), ())
        self.assertEqual(clock.next_deadline(11.0), 12.0)
        self.assertEqual(clock.due_keys(12.0), ("cpu",))


class ResourceGovernorTests(unittest.TestCase):
    def test_pressure_sampling_runs_off_the_caller_thread(self) -> None:
        sampler_started = threading.Event()
        sampler_release = threading.Event()
        ran_on_main_thread: list[bool] = []

        def sampler() -> PressureSnapshot:
            ran_on_main_thread.append(
                threading.current_thread() is threading.main_thread()
            )
            sampler_started.set()
            sampler_release.wait(1)
            return PressureSnapshot(
                sampled_at=1.0,
                memory_percent=40.0,
                available=True,
            )

        governor = ResourceGovernor(
            clock=lambda: 0.0,
            pressure_sampler=sampler,
            pressure_sample_seconds=0.0,
        )

        decision = governor.admit(JobProfile(key="component:cpu", kind="periodic"))

        self.assertTrue(decision.admitted)
        self.assertTrue(sampler_started.wait(1))
        self.assertEqual(ran_on_main_thread, [False])
        sampler_release.set()

    def test_refresh_pressure_recovers_after_partial_missing_metrics(self) -> None:
        samples = iter(
            [
                PressureSnapshot(
                    sampled_at=1.0,
                    memory_percent=96.0,
                    swap_percent=15.0,
                    rss_bytes=10,
                    cpu_percent=90.0,
                    available=True,
                ),
                PressureSnapshot(
                    sampled_at=2.0,
                    memory_percent=None,
                    swap_percent=None,
                    rss_bytes=None,
                    cpu_percent=None,
                    available=False,
                    sample_error="unavailable",
                ),
                PressureSnapshot(
                    sampled_at=3.0,
                    memory_percent=40.0,
                    swap_percent=0.0,
                    rss_bytes=1,
                    cpu_percent=5.0,
                    available=True,
                ),
            ]
        )
        governor = ResourceGovernor(
            clock=lambda: 0.0,
            pressure_sampler=lambda: next(samples),
            pressure_sample_seconds=0.0,
            memory_enter_percent=90.0,
            memory_leave_percent=80.0,
            swap_enter_percent=10.0,
            swap_leave_percent=5.0,
            rss_enter_fraction=0.75,
            rss_leave_fraction=0.65,
        )

        first = governor.refresh_pressure(1.0)
        second = governor.refresh_pressure(2.0)
        third = governor.refresh_pressure(3.0)

        self.assertTrue(first.degraded)
        self.assertTrue(second.degraded)
        self.assertFalse(third.degraded)
        self.assertEqual(first.available, True)
        self.assertEqual(second.available, False)
        self.assertEqual(third.available, True)

    def test_background_capacity_reserves_space_for_manual_work(self) -> None:
        governor = ResourceGovernor(max_active=2, max_periodic=1, manual_reserve=1)

        first = governor.admit(JobProfile(key="component:cpu", kind="periodic"), 0.0)
        second = governor.admit(
            JobProfile(key="component:memory", kind="periodic"), 0.0
        )
        manual = governor.admit(JobProfile(key="dashboard", kind="manual"), 0.0)

        self.assertTrue(first.admitted)
        self.assertFalse(second.admitted)
        self.assertTrue(manual.admitted)

        governor.release("component:cpu")
        governor.release("dashboard")

    def test_pressure_degrades_periodic_work_without_blocking_manual_work(self) -> None:
        governor = ResourceGovernor(max_active=2, max_periodic=2, manual_reserve=1)
        governor._pressure_degraded = True
        governor._pressure = PressureSnapshot(
            sampled_at=0.0,
            degraded=True,
            available=True,
        )

        periodic = governor.admit(JobProfile(key="component:cpu", kind="periodic"), 0.0)
        manual = governor.admit(JobProfile(key="dashboard", kind="manual"), 0.0)

        self.assertFalse(periodic.admitted)
        self.assertTrue(manual.admitted)


class SharedScanHelperTests(unittest.TestCase):
    def test_check_cancelled_is_quiet_without_event_or_unset_event(self) -> None:
        check_cancelled(None)
        check_cancelled(threading.Event())

    def test_check_cancelled_raises_with_default_and_custom_message(self) -> None:
        cancel_event = threading.Event()
        cancel_event.set()

        with self.assertRaisesRegex(ScanCancelled, "Downloads scan cancelled"):
            check_cancelled(cancel_event)
        with self.assertRaisesRegex(ScanCancelled, "Process scan cancelled"):
            check_cancelled(cancel_event, "Process scan cancelled")

    def test_require_psutil_raises_consistent_message_for_missing_module(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "python -m pip install psutil"):
            require_psutil(None)

    def test_require_psutil_returns_the_supplied_module(self) -> None:
        fake = object()
        self.assertIs(require_psutil(fake), fake)

    def test_username_matching_ignores_domain_and_non_strings(self) -> None:
        self.assertTrue(usernames_match("WORKGROUP\\Iryna", "iryna"))
        self.assertTrue(usernames_match("Iryna", "IRYNA"))
        self.assertFalse(usernames_match("alice", "bob"))
        self.assertFalse(usernames_match(None, "bob"))
        self.assertFalse(usernames_match("alice", None))
        self.assertEqual(normalize_username(r"DOMAIN\Alice"), "alice")
        self.assertEqual(normalize_username(""), "")

    def test_windows_windll_returns_none_on_this_platform(self) -> None:
        self.assertIsNone(windows_windll())

    def test_windows_windll_uses_ctypes_getattr_when_available(self) -> None:
        fake_windll = object()
        with patch(
            "maintenance.components.scan_support.ctypes.windll",
            fake_windll,
            create=True,
        ):
            self.assertIs(windows_windll(), fake_windll)

    def test_gpu_unavailable_message_is_concise_and_logs_detail(self) -> None:
        with self.assertLogs("maintenance.components.gpu", level="WARNING") as log:
            self.assertEqual(
                gpu_unavailable_message(ValueError("boom")),
                "GPU information unavailable",
            )
            self.assertEqual(
                gpu_unavailable_message("query timed out"),
                "GPU information unavailable",
            )

        self.assertIn("boom", "\n".join(log.output))
        self.assertIn("query timed out", "\n".join(log.output))

    def test_protected_process_pids_without_psutil_is_base_set(self) -> None:
        self.assertEqual(protected_process_pids(None), {0, 1, os.getpid()})

    def test_protected_process_pids_collects_parent_chain(self) -> None:
        class ParentChainProcess:
            def __init__(self, pids: list[int]) -> None:
                self._pids = pids

            def parents(self) -> list[PolicyProcess]:
                return [PolicyProcess(pid) for pid in self._pids]

        class ParentChainPsutil:
            NoSuchProcess = type("NoSuchProcess", (Exception,), {})
            AccessDenied = type("AccessDenied", (Exception,), {})

            @staticmethod
            def Process(pid: int) -> ParentChainProcess:
                del pid
                return ParentChainProcess([4242, 4243])

        self.assertEqual(
            protected_process_pids(ParentChainPsutil),
            {0, 1, os.getpid(), 4242, 4243},
        )

    def test_protected_process_pids_tolerates_lookup_errors(self) -> None:
        class FailingPsutil:
            NoSuchProcess = type("NoSuchProcess", (Exception,), {})
            AccessDenied = type("AccessDenied", (Exception,), {})

            @staticmethod
            def Process(pid: int) -> Any:
                del pid
                raise FailingPsutil.NoSuchProcess("gone")

        self.assertEqual(protected_process_pids(FailingPsutil), {0, 1, os.getpid()})

    def test_file_sha256_matches_stdlib_and_honours_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.bin"
            path.write_bytes(b"chunked content")

            self.assertEqual(
                file_sha256(path, chunk_bytes=2),
                hashlib.sha256(b"chunked content").hexdigest(),
            )

            cancel_event = threading.Event()
            cancel_event.set()
            with self.assertRaises(ScanCancelled):
                file_sha256(path, chunk_bytes=2, cancel_event=cancel_event)

    def test_file_content_marker_matches_blake2b(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.bin"
            path.write_bytes(b"content")

            self.assertEqual(
                file_content_marker(path, chunk_bytes=2),
                hashlib.blake2b(b"content", digest_size=16).digest(),
            )

    def test_stat_fingerprint_returns_identity_tuple(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.bin"
            path.write_bytes(b"content")
            stat = path.stat()

            self.assertEqual(
                stat_fingerprint(stat),
                (
                    stat.st_size,
                    stat.st_mtime_ns,
                    getattr(stat, "st_ctime_ns", 0),
                    getattr(stat, "st_dev", 0),
                    getattr(stat, "st_ino", 0),
                ),
            )

    def test_call_legacy_compatible_returns_primary_on_success(self) -> None:
        self.assertEqual(
            call_legacy_compatible(lambda: "ok", lambda: "legacy"),
            "ok",
        )

    def test_call_legacy_compatible_falls_back_for_legacy_signature(self) -> None:
        calls: list[str] = []

        def primary() -> str:
            raise TypeError("got an unexpected keyword argument 'cancel_event'")

        def fallback() -> str:
            calls.append("fallback")
            return "legacy"

        def before() -> None:
            calls.append("before")

        def after() -> None:
            calls.append("after")

        result = call_legacy_compatible(
            primary,
            fallback,
            before_fallback=before,
            after_fallback=after,
        )

        self.assertEqual(result, "legacy")
        self.assertEqual(calls, ["before", "fallback", "after"])

    def test_call_legacy_compatible_rereaises_unrelated_type_errors(self) -> None:
        def primary() -> str:
            raise TypeError("something else broke")

        with self.assertRaisesRegex(TypeError, "something else broke"):
            call_legacy_compatible(primary, lambda: "legacy")

    def test_call_legacy_compatible_rereaises_non_type_errors(self) -> None:
        def primary() -> str:
            raise RuntimeError("boom")

        with self.assertRaisesRegex(RuntimeError, "boom"):
            call_legacy_compatible(primary, lambda: "legacy")

    def test_call_cancellable_returns_primary_on_success(self) -> None:
        calls: list[str] = []

        def primary() -> str:
            calls.append("primary")
            return "ok"

        def fallback() -> str:
            calls.append("fallback")
            return "legacy"

        result = call_cancellable(primary, fallback, threading.Event())

        self.assertEqual(result, "ok")
        self.assertEqual(calls, ["primary"])

    def test_call_cancellable_falls_back_without_cancellation(self) -> None:
        calls: list[str] = []

        def primary() -> str:
            raise TypeError("unexpected keyword argument 'cancel_event'")

        def fallback() -> str:
            calls.append("fallback")
            return "legacy"

        result = call_cancellable(primary, fallback, threading.Event())

        self.assertEqual(result, "legacy")
        self.assertEqual(calls, ["fallback"])

    def test_call_cancellable_raises_when_cancelled_before_fallback(self) -> None:
        fallback_calls: list[str] = []

        def primary() -> str:
            raise TypeError("unexpected keyword argument 'cancel_event'")

        def fallback() -> str:
            fallback_calls.append("fallback")
            return "legacy"

        cancel_event = threading.Event()
        cancel_event.set()

        with self.assertRaises(ScanCancelled):
            call_cancellable(primary, fallback, cancel_event)

        self.assertEqual(fallback_calls, [])

    def test_call_cancellable_without_event_is_quiet(self) -> None:
        def primary() -> str:
            raise TypeError("unexpected keyword argument 'cancel_event'")

        result = call_cancellable(primary, lambda: "legacy", None)

        self.assertEqual(result, "legacy")

    def test_detail_line_suffix_returns_suffix_after_prefix(self) -> None:
        self.assertEqual(
            detail_line_suffix(("CPU: 45°C", "NVMe: 38°C"), "CPU: "),
            "45°C",
        )

    def test_detail_line_suffix_returns_first_matching_line(self) -> None:
        self.assertEqual(
            detail_line_suffix(
                ("Temperature: 51°C", "Temperature: 60°C"),
                "Temperature: ",
            ),
            "51°C",
        )

    def test_detail_line_suffix_is_prefix_strict(self) -> None:
        self.assertIsNone(detail_line_suffix(("Temperatures: 45°C",), "Temperature: "))
        self.assertIsNone(detail_line_suffix(("Temperature: 45°C",), "Temp: "))

    def test_detail_line_suffix_missing_and_empty(self) -> None:
        self.assertIsNone(detail_line_suffix(("Other: 45°C",), "CPU: "))
        self.assertIsNone(detail_line_suffix((), "CPU: "))

    def test_detail_line_suffix_empty_suffix_is_kept(self) -> None:
        self.assertEqual(detail_line_suffix(("CPU: ",), "CPU: "), "")


class AppCoordinatorTests(unittest.TestCase):
    def test_begin_claims_and_coalesces_duplicate_triggers(self) -> None:
        coordinator = AppCoordinator()

        generation, started = coordinator.begin("storage")
        self.assertTrue(started)
        self.assertEqual(generation, 1)
        repeated_generation, repeated_started = coordinator.begin("storage")
        self.assertFalse(repeated_started)
        self.assertEqual(repeated_generation, 1)

        finished, rerun_requested = coordinator.finish(
            "storage",
            generation,
            ["candidate"],
        )
        self.assertTrue(finished)
        self.assertTrue(rerun_requested)
        self.assertEqual(coordinator.last_result("storage"), ["candidate"])

        next_generation, next_started = coordinator.begin("storage")
        self.assertTrue(next_started)
        self.assertEqual(next_generation, 2)

    def test_finish_drops_late_generation_and_does_not_overwrite_cache(self) -> None:
        coordinator = AppCoordinator()
        generation, _started = coordinator.begin("storage")
        coordinator.finish("storage", generation, ["first"])

        stale_generation, _started = coordinator.begin("storage")
        coordinator.finish("storage", stale_generation, None)

        self.assertEqual(coordinator.last_result("storage"), ["first"])
        finished, _rerun = coordinator.finish("storage", generation, ["late"])
        self.assertFalse(finished)

    def test_cancel_clears_state_and_notifies_waiters(self) -> None:
        coordinator = AppCoordinator()
        received: list[tuple[str, object | None]] = []
        generation, started = coordinator.begin("storage")
        self.assertTrue(started)
        coordinator.subscribe(
            "storage", lambda key, result: received.append((key, result))
        )

        coordinator.cancel("storage")

        # The in-flight hold prevents overlap until the worker's completion
        # is delivered; the waiters were woken immediately.
        self.assertTrue(coordinator.in_flight("storage"))
        self.assertEqual(received, [("storage", None)])

        finished, _rerun = coordinator.finish("storage", generation, ["late"])
        self.assertFalse(finished)
        self.assertFalse(coordinator.in_flight("storage"))
        self.assertIsNone(coordinator.last_result("storage"))

    def test_subscribers_receive_shared_result_once(self) -> None:
        coordinator = AppCoordinator()
        received: list[object | None] = []
        generation, _started = coordinator.begin("storage")
        coordinator.subscribe("storage", lambda _key, result: received.append(result))
        coordinator.subscribe("storage", lambda _key, result: received.append(result))

        coordinator.finish("storage", generation, ["result"])

        self.assertEqual(received, [["result"], ["result"]])
        self.assertEqual(coordinator.last_result("storage"), ["result"])

    def test_unsubscribe_removes_closed_dialog_callback(self) -> None:
        coordinator = AppCoordinator()
        received: list[object | None] = []
        callback = lambda _key, result: received.append(result)
        generation, _started = coordinator.begin("storage")
        coordinator.subscribe("storage", callback)
        coordinator.unsubscribe("storage", callback)

        coordinator.finish("storage", generation, ["result"])

        self.assertEqual(received, [])

    def test_store_and_retrieve_instant_cache(self) -> None:
        coordinator = AppCoordinator()

        coordinator.store("dashboard", {"snapshot": 1})

        self.assertEqual(coordinator.last_result("dashboard"), {"snapshot": 1})
        self.assertIsNone(coordinator.last_result("never"))

    def test_finish_while_cancelled_is_dropped(self) -> None:
        coordinator = AppCoordinator()
        generation, _started = coordinator.begin("storage")
        coordinator.cancel("storage")

        finished, _rerun = coordinator.finish("storage", generation, ["late"])

        self.assertFalse(finished)
        self.assertIsNone(coordinator.last_result("storage"))

    def test_independent_keys_do_not_interfere(self) -> None:
        coordinator = AppCoordinator()

        storage_generation, storage_started = coordinator.begin("storage")
        process_generation, process_started = coordinator.begin("process")

        self.assertTrue(storage_started)
        self.assertTrue(process_started)
        coordinator.finish("storage", storage_generation, ["s"])
        self.assertEqual(coordinator.last_result("storage"), ["s"])
        self.assertIsNone(coordinator.last_result("process"))
        self.assertTrue(coordinator.in_flight("process"))
        coordinator.finish("process", process_generation, ["p"])
        self.assertEqual(coordinator.last_result("process"), ["p"])


class AppCoordinatorRunTests(unittest.TestCase):
    def _make(self) -> tuple[AppCoordinator, DeferredRunner]:
        runner = DeferredRunner()
        coordinator = AppCoordinator(runner=runner, deliver=lambda callback: callback())
        return coordinator, runner

    def test_run_coalesces_duplicate_triggers_into_one_rerun(self) -> None:
        coordinator, runner = self._make()
        results: list[object] = []

        generation = coordinator.run(
            "storage",
            lambda _event, _progress: ["first"],
            on_result=lambda _key, result: results.append(result),
        )
        self.assertIsNotNone(generation)
        second = coordinator.run(
            "storage",
            lambda _event, _progress: ["second"],
            on_result=lambda _key, result: results.append(result),
        )
        self.assertIsNone(second)
        self.assertEqual(len(runner.workers), 1)

        runner.run_next()
        self.assertEqual(len(runner.workers), 1, "coalesced trigger must replay")
        runner.run_next()
        self.assertEqual(results, [["first"], ["first"]])
        self.assertEqual(coordinator.last_result("storage"), ["first"])

    def test_run_delivers_progress_and_result_through_delivery(self) -> None:
        coordinator, runner = self._make()
        progress: list[str] = []
        complete: list[str] = []

        def task(_event: object, emit: Callable[[str], None]) -> str:
            emit("halfway")
            return "done"

        coordinator.run(
            "storage",
            task,
            on_progress=lambda _key, message: progress.append(message),
            on_result=lambda _key, result: complete.append(result),
        )
        runner.run_next()

        self.assertEqual(progress, ["halfway"])
        self.assertEqual(complete, ["done"])

    def test_run_error_does_not_overwrite_cached_result(self) -> None:
        coordinator, runner = self._make()
        coordinator.store("storage", ["good"])

        def boom(_event: object, _progress: object) -> None:
            raise ValueError("boom")

        coordinator.run("storage", boom, on_error=lambda _key, _message: None)
        runner.run_next()

        self.assertEqual(coordinator.last_result("storage"), ["good"])

    def test_cancel_notifies_owner_and_holds_in_flight_until_completion(self) -> None:
        coordinator, runner = self._make()
        errors: list[str] = []

        coordinator.run(
            "storage",
            lambda _event, _progress: ["x"],
            on_error=lambda _key, message: errors.append(message),
        )
        cancel_event = coordinator.state("storage").cancel_event
        self.assertIsNotNone(cancel_event)

        coordinator.cancel("storage", cancellation_message="cancelled")

        self.assertTrue(cancel_event.is_set())  # type: ignore[union-attr]
        self.assertEqual(errors, ["cancelled"])
        self.assertTrue(coordinator.in_flight("storage"))

        runner.run_next()
        self.assertFalse(coordinator.in_flight("storage"))
        self.assertIsNone(coordinator.last_result("storage"))

    def test_trigger_after_cancel_replays_once_the_worker_quits(self) -> None:
        coordinator, runner = self._make()
        results: list[int] = []

        coordinator.run(
            "storage",
            lambda _event, _progress: 1,
            on_result=lambda _key, result: results.append(result),
        )
        coordinator.cancel("storage")
        coordinator.run(
            "storage",
            lambda _event, _progress: 2,
            on_result=lambda _key, result: results.append(result),
        )
        self.assertEqual(len(runner.workers), 1, "no second worker may overlap")

        runner.run_next()
        self.assertEqual(len(runner.workers), 1, "replay started after release")
        runner.run_next()
        self.assertEqual(coordinator.last_result("storage"), 1)
        self.assertEqual(results, [1])

    def test_run_notifies_waiting_subscribers(self) -> None:
        coordinator, runner = self._make()
        received: list[object] = []

        coordinator.run("storage", lambda _event, _progress: ["shared"])
        coordinator.subscribe("storage", lambda _key, result: received.append(result))
        runner.run_next()

        self.assertEqual(received, [["shared"]])

    def test_uncaught_ui_callback_never_breaks_delivery(self) -> None:
        coordinator, runner = self._make()
        completed: list[object] = []

        def crashing(_key: str, _result: object) -> None:
            raise RuntimeError("widget gone")

        coordinator.run("storage", lambda _event, _progress: ["ok"], on_result=crashing)
        coordinator.subscribe("storage", lambda _key, result: completed.append(result))
        runner.run_next()

        self.assertEqual(completed, [["ok"]])


if __name__ == "__main__":
    unittest.main()

import threading
import tkinter as tk
import unittest
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import ANY, Mock, patch

from maintenance.components.coordinator import AppCoordinator
from maintenance.dialogs import (
    StorageDialog,
    _dispatch_coordinated_shared_result,
    _register_coordinated_waiter,
    _start_coordinated_dialog_scan,
    run_in_thread,
    show_action_result,
)
from maintenance.models import FileCandidate
from tests.support.scheduling import DeferredRunner


class FakeTree:
    def __init__(self, selected: tuple[str, ...] = ()) -> None:
        self.selected = selected
        self.width = 755
        self.widths: dict[str, int] = {}
        self.rows: list[Any] = []

    def selection(self) -> tuple[str, ...]:
        return self.selected

    def winfo_width(self) -> int:
        return self.width

    def column(self, name: str, **options: int) -> None:
        self.widths[name] = options["width"]

    def delete(self, *items: object) -> None:
        self.rows.clear()

    def get_children(self) -> tuple[()]:
        return ()

    def insert(self, *args: object, **kwargs: object) -> None:
        self.rows.append(args)


class FakeControl:
    def __init__(self) -> None:
        self.state: str | None = None
        self.text: str | None = None

    def config(self, **options: object) -> None:
        state = options.get("state")
        text = options.get("text")
        self.state = state if isinstance(state, str) else None
        self.text = text if isinstance(text, str) else None


class FailingAfterWidget:
    def winfo_exists(self) -> bool:
        return True

    def after(self, _delay: int, _callback: object, *_args: object) -> None:
        raise RuntimeError("event loop is stopping")


class _FakeCoordinatedDialog:
    def __init__(
        self,
        coordinator: AppCoordinator,
        *,
        operation_key: str = "storage",
    ) -> None:
        self.coordinator = coordinator
        self._operation_key = operation_key
        self._scan_active = False
        self._waiting_for_shared = False
        self.status_label = Mock()
        self.owner_results: list[Any] = []
        self.shared_results: list[Any] = []
        self.retries: list[bool] = []
        self.owner_started = 0

    def record_owner(self, result: Any) -> None:
        self.owner_results.append(result)

    def record_shared(self, _key: str, result: Any | None) -> None:
        self._waiting_for_shared = False
        self.shared_results.append(result)

    def retry(self) -> None:
        self.retries.append(True)

    def started(self) -> None:
        self.owner_started += 1


class FakeManager:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def move_to_trash(self, paths: list[Path]) -> None:
        self.paths = paths


class StorageDialogTests(unittest.TestCase):
    def test_worker_delivery_ignores_runtime_error_during_tk_teardown(self) -> None:
        task_finished = threading.Event()
        success = Mock()

        def task() -> None:
            task_finished.set()

        widget: Any = FailingAfterWidget()
        run_in_thread(widget, task, success)

        self.assertTrue(task_finished.wait(1))
        success.assert_not_called()

    def test_run_in_thread_delegates_to_background_task_runner(self) -> None:
        widget: Any = object()
        success = Mock()

        with patch("maintenance.dialogs.BackgroundTaskRunner.run") as runner:
            run_in_thread(widget, lambda: "done", success)

        runner.assert_called_once_with(
            widget,
            ANY,
            success,
            None,
            progress_task=None,
            cancel_event=None,
            on_progress=None,
        )

    def test_show_action_result_appends_first_errors(self) -> None:
        widget: Any = object()

        with patch("maintenance.dialogs.messagebox.showinfo") as showinfo:
            show_action_result(widget, "Cleanup", "Done.", ("error one", "error two"))

        showinfo.assert_called_once_with(
            "Cleanup",
            "Done.\n\nerror one\nerror two",
            parent=widget,
        )

    def test_show_action_result_without_errors_is_clean(self) -> None:
        widget: Any = object()

        with patch("maintenance.dialogs.messagebox.showinfo") as showinfo:
            show_action_result(widget, "Cleanup", "Done.", ())

        showinfo.assert_called_once_with("Cleanup", "Done.", parent=widget)

    def test_resize_columns_gives_remaining_width_to_file_path(self) -> None:
        dialog: Any = object.__new__(StorageDialog)
        dialog.tree = FakeTree()

        dialog._resize_columns()
        self.assertEqual(
            dialog.tree.widths,
            {"path": 410, "reason": 140, "size": 85, "modified": 120},
        )

        dialog.tree.width = 915
        dialog._resize_columns()
        self.assertEqual(dialog.tree.widths["path"], 570)

    def test_move_selected_passes_all_selected_files_to_manager(self) -> None:
        first = Path("first.zip")
        second = Path("second.zip")
        candidates = {
            "0": FileCandidate(
                first,
                10,
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                "Large file",
            ),
            "1": FileCandidate(
                second,
                20,
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                "Verified duplicate",
            ),
        }
        manager = FakeManager()
        dialog: Any = object.__new__(StorageDialog)
        dialog.tree = FakeTree(("0", "1"))
        dialog.candidates = candidates
        dialog.manager = manager
        dialog.scan_button = FakeControl()
        dialog.trash_button = FakeControl()
        dialog.status_label = FakeControl()

        def run_task(
            _widget: object,
            task: Callable[[], object],
            *_callbacks: object,
        ) -> None:
            task()

        with (
            patch("maintenance.dialogs.messagebox.askyesno", return_value=True),
            patch("maintenance.dialogs.run_in_thread", side_effect=run_task),
        ):
            dialog.move_selected()

        self.assertEqual(manager.paths, [first, second])

    def test_show_candidates_empty_state_is_intentional(self) -> None:
        dialog: Any = object.__new__(StorageDialog)
        dialog.tree = FakeTree()
        dialog.candidates = {}
        dialog.status_label = FakeControl()
        dialog.scan_button = FakeControl()
        dialog.trash_button = FakeControl()

        dialog._show_candidates([])

        self.assertEqual(dialog.status_label.text, "No cleanup candidates found.")
        self.assertEqual(dialog.scan_button.state, tk.NORMAL)
        self.assertEqual(dialog.trash_button.state, tk.DISABLED)

    def test_show_candidates_non_empty_state_is_unchanged(self) -> None:
        candidate = FileCandidate(
            Path("first.zip"),
            10,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            "Large file",
        )
        dialog: Any = object.__new__(StorageDialog)
        dialog.tree = FakeTree()
        dialog.candidates = {}
        dialog.status_label = FakeControl()
        dialog.scan_button = FakeControl()
        dialog.trash_button = FakeControl()

        dialog._show_candidates([candidate])

        self.assertEqual(
            dialog.status_label.text,
            "1 candidate(s) • up to 10.00 B reviewable",
        )
        self.assertEqual(dialog.scan_button.state, tk.NORMAL)
        self.assertEqual(dialog.trash_button.state, tk.NORMAL)


class StorageDialogCoordinatorTests(unittest.TestCase):
    def _dialog(self) -> Any:
        dialog: Any = object.__new__(StorageDialog)
        dialog.coordinator = AppCoordinator()
        dialog.analyzer = Mock()
        dialog._waiting_for_shared = False
        dialog._scan_active = False
        dialog._on_close = dialog._default_close
        dialog.status_label = FakeControl()
        dialog.scan_button = FakeControl()
        dialog.trash_button = FakeControl()
        dialog._show_candidates = Mock()
        dialog._set_scan_idle = Mock()
        return dialog

    def test_node_qualified_operation_key_is_used(self) -> None:
        dialog = self._dialog()
        dialog.coordinator = AppCoordinator(deliver=lambda cb: None)
        dialog._operation_key = "node:dev:storage"
        dialog._read_only = False

        dialog.scan()

        self.assertTrue(dialog.coordinator.in_flight("node:dev:storage"))

    def test_default_operation_key_is_local_storage(self) -> None:
        dialog: Any = object.__new__(StorageDialog)
        self.assertEqual(dialog._operation_key, "storage")
        self.assertFalse(dialog._read_only)

    def test_read_only_dialog_keeps_trash_disabled(self) -> None:
        candidate = FileCandidate(
            Path("first.zip"),
            10,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            "Large file",
        )
        dialog: Any = object.__new__(StorageDialog)
        dialog.tree = FakeTree()
        dialog.candidates = {}
        dialog.status_label = FakeControl()
        dialog.scan_button = FakeControl()
        dialog.trash_button = FakeControl()
        dialog._read_only = True

        dialog._show_candidates([candidate])

        self.assertEqual(dialog.trash_button.state, tk.DISABLED)
        self.assertEqual(dialog.scan_button.state, tk.NORMAL)

    def test_second_instance_waits_instead_of_duplicate_scan(self) -> None:
        owner = self._dialog()
        waiter = self._dialog()
        owner.coordinator = waiter.coordinator = AppCoordinator()

        _generation, started = owner.coordinator.begin("storage")
        self.assertTrue(started)

        waiter.scan()

        self.assertTrue(waiter._waiting_for_shared)
        self.assertFalse(waiter._scan_active)
        self.assertEqual(
            waiter.status_label.text,
            "Waiting for the active Downloads scan...",
        )
        self.assertTrue(owner.coordinator.in_flight("storage"))
        owner.coordinator.cancel("storage")

    def test_waiter_renders_shared_result_when_owner_finishes(self) -> None:
        operations = AppCoordinator()
        owner = self._dialog()
        waiter = self._dialog()
        owner.coordinator = waiter.coordinator = operations

        generation, _started = operations.begin("storage")
        waiter.scan()
        self.assertTrue(waiter._waiting_for_shared)

        operations.finish("storage", generation, ["shared"])

        waiter._show_candidates.assert_called_once_with(["shared"])
        self.assertFalse(waiter._waiting_for_shared)

    def test_waiter_retries_when_shared_scan_is_cancelled(self) -> None:
        runner = DeferredRunner()
        coordinator = AppCoordinator(runner=runner, deliver=lambda callback: callback())
        dialog = self._dialog()
        dialog.coordinator = coordinator

        generation = coordinator.run("storage", lambda _event, _progress: ["shared"])
        self.assertIsNotNone(generation)
        dialog._wait_for_shared_scan()
        self.assertTrue(dialog._waiting_for_shared)

        coordinator.cancel("storage")
        self.assertTrue(coordinator.in_flight("storage"))

        runner.run_next()  # the cancelled worker releases the lease + replays
        runner.run_next()  # the replay delivers the result to the waiter

        self.assertFalse(dialog._waiting_for_shared)
        dialog._show_candidates.assert_called_once_with(["shared"])
        self.assertFalse(coordinator.in_flight("storage"))

    def test_cached_result_is_rendered_on_reopen(self) -> None:
        dialog = self._dialog()
        dialog.coordinator.store("storage", ["cached"])
        dialog._show_candidates.reset_mock()

        cached = dialog.coordinator.last_result("storage")

        self.assertEqual(cached, ["cached"])

    def test_cancelling_owner_releases_coordinator(self) -> None:
        runner = DeferredRunner()
        dialog = self._dialog()
        dialog.coordinator = AppCoordinator(
            runner=runner, deliver=lambda callback: callback()
        )
        dialog._scan_active = True
        dialog.destroy = Mock()
        dialog.coordinator.run("storage", lambda _event, _progress: ["x"])
        self.assertTrue(dialog.coordinator.in_flight("storage"))

        dialog._close()

        self.assertTrue(dialog.coordinator.in_flight("storage"))
        runner.run_next()
        self.assertFalse(dialog.coordinator.in_flight("storage"))
        dialog.destroy.assert_called_once_with()

    def test_owner_error_clears_active_state(self) -> None:
        runner = DeferredRunner()
        dialog: Any = object.__new__(StorageDialog)
        dialog.coordinator = AppCoordinator(
            runner=runner, deliver=lambda callback: callback()
        )
        dialog.analyzer = Mock()
        dialog.analyzer.storage_candidates.side_effect = RuntimeError("boom")
        dialog._waiting_for_shared = False
        dialog._scan_active = False
        dialog.status_label = FakeControl()
        dialog.scan_button = FakeControl()
        dialog.trash_button = FakeControl()
        dialog._show_candidates = Mock()
        dialog._show_error = Mock()

        dialog.scan()

        self.assertTrue(dialog._scan_active)
        self.assertTrue(dialog.coordinator.in_flight("storage"))

        runner.run_next()

        self.assertFalse(dialog._scan_active)
        self.assertFalse(dialog.coordinator.in_flight("storage"))
        dialog._show_error.assert_called_once_with("boom")


class CoordinatedDialogScanLifecycleTests(unittest.TestCase):
    def _start(self, dialog: Any, coordinator: AppCoordinator) -> bool:
        return _start_coordinated_dialog_scan(
            dialog,
            task_factory=lambda _event, _progress: ["ok"],
            active_attr="_scan_active",
            on_result=dialog.record_owner,
            on_error=lambda message: None,
            on_progress=None,
            waiting_text="Waiting...",
            subscribe_callback=dialog.record_shared,
            on_owner_started=dialog.started,
        )

    def test_owner_start_sets_active_and_runs_once_without_subscribing(self) -> None:
        runner = DeferredRunner()
        coordinator = AppCoordinator(runner=runner, deliver=lambda callback: callback())
        dialog = _FakeCoordinatedDialog(coordinator)

        started = self._start(dialog, coordinator)

        self.assertTrue(started)
        self.assertTrue(dialog._scan_active)
        self.assertFalse(dialog._waiting_for_shared)
        self.assertEqual(dialog.owner_started, 1)
        self.assertEqual(len(runner.workers), 1)

        runner.run_next()

        self.assertEqual(dialog.owner_results, [["ok"]])
        self.assertEqual(dialog.shared_results, [])
        self.assertFalse(coordinator.in_flight("storage"))

    def test_coalesced_trigger_subscribes_once_as_waiter(self) -> None:
        runner = DeferredRunner()
        coordinator = AppCoordinator(runner=runner, deliver=lambda callback: callback())
        generation = coordinator.run("storage", lambda _event, _progress: ["owner"])
        self.assertIsNotNone(generation)

        waiter = _FakeCoordinatedDialog(coordinator)
        started = self._start(waiter, coordinator)

        self.assertFalse(started)
        self.assertTrue(waiter._waiting_for_shared)
        self.assertFalse(waiter._scan_active)

        runner.run_next()

        self.assertEqual(waiter.shared_results, [["owner"]])
        self.assertFalse(waiter._waiting_for_shared)

    def test_repeated_wait_does_not_double_subscribe(self) -> None:
        runner = DeferredRunner()
        coordinator = AppCoordinator(runner=runner, deliver=lambda callback: callback())
        coordinator.run("storage", lambda _event, _progress: ["owner"])
        waiter = _FakeCoordinatedDialog(coordinator)
        self._start(waiter, coordinator)
        _register_coordinated_waiter(
            waiter,
            waiting_text="Waiting...",
            subscribe_callback=waiter.record_shared,
        )

        runner.run_next()

        self.assertEqual(waiter.shared_results, [["owner"]])

    def test_existing_active_run_is_a_noop(self) -> None:
        runner = DeferredRunner()
        coordinator = AppCoordinator(runner=runner, deliver=lambda callback: callback())
        dialog = _FakeCoordinatedDialog(coordinator)
        dialog._scan_active = True

        started = self._start(dialog, coordinator)

        self.assertFalse(started)
        self.assertEqual(len(runner.workers), 0)
        self.assertFalse(coordinator.in_flight("storage"))

    def test_shared_result_present_is_dispatched(self) -> None:
        dialog = _FakeCoordinatedDialog(AppCoordinator())
        dialog._waiting_for_shared = True

        _dispatch_coordinated_shared_result(
            dialog,
            result=["shared"],
            retry=dialog.retry,
            on_shared_result=dialog.record_owner,
        )

        self.assertFalse(dialog._waiting_for_shared)
        self.assertEqual(dialog.owner_results, [["shared"]])
        self.assertEqual(dialog.retries, [])

    def test_shared_result_none_retries(self) -> None:
        dialog = _FakeCoordinatedDialog(AppCoordinator())
        dialog._waiting_for_shared = True

        _dispatch_coordinated_shared_result(
            dialog,
            result=None,
            retry=dialog.retry,
            on_shared_result=dialog.record_owner,
        )

        self.assertFalse(dialog._waiting_for_shared)
        self.assertEqual(dialog.retries, [True])
        self.assertEqual(dialog.owner_results, [])

    def test_process_and_storage_keys_stay_isolated_on_one_coordinator(self) -> None:
        runner = DeferredRunner()
        coordinator = AppCoordinator(runner=runner, deliver=lambda callback: callback())
        coordinator.run("process", lambda _event, _progress: ["process-result"])
        storage = _FakeCoordinatedDialog(coordinator, operation_key="storage")

        started = self._start(storage, coordinator)

        self.assertTrue(started)
        self.assertFalse(storage._waiting_for_shared)
        self.assertTrue(coordinator.in_flight("process"))
        self.assertTrue(coordinator.in_flight("storage"))


if __name__ == "__main__":
    unittest.main()

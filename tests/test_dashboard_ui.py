"""Focused direct regression tests for the dashboard UI contracts."""

import threading
import tkinter as tk
import unittest
from queue import Queue
from typing import Any
from unittest.mock import Mock, patch

from maintenance.components import ResourceFeatureCatalog, ScanCoordinator
from maintenance.components.coordinator import (
    AppCoordinator,
    ComponentRefreshScheduler,
)
from maintenance.dialogs import ResourceCard, action_label_text, metric_label_pairs
from maintenance.models import (
    CapabilityState,
    DashboardSnapshot,
    ResourceSummary,
    unavailable_summary,
)
from maintenance.ui.action_coordinator import ButtonCoordinator
from tests.support.models import make_snapshot, make_summary
from tests.support.scheduling import TimerMaster
from window import AppWindow


class FakeControl:
    def __init__(self) -> None:
        self.options: dict[str, object] = {}

    def config(self, **options: object) -> None:
        self.options.update(options)


def make_window() -> Any:
    window: Any = object.__new__(AppWindow)
    window.master = TimerMaster()
    window._is_closing = False
    window._pending_after_ids = set()
    window._background_poll_id = None
    window._background_tasks = 0
    window._scan_coordinator = ScanCoordinator()
    window._analysis_cancel_event = None
    window._scan_timeout_id = None
    window._resolved_scan_generation = 0
    window._background_queue = Queue()
    window._component_scheduler = ComponentRefreshScheduler()
    window._feature_catalog = ResourceFeatureCatalog()
    window._component_poll_id = None
    window._component_queue = Queue()
    window._coordinator = AppCoordinator()
    window._timed_out_generation = None
    window._lease_grace_id = None
    window.analyze_button = FakeControl()
    window.cancel_button = FakeControl()
    window.status_label = FakeControl()
    window.refreshed_label = FakeControl()
    window.scan_time_label = FakeControl()
    window.progress_bar = Mock()
    window.health_label = FakeControl()
    window._set_busy = Mock()
    window.cards = {}
    return window


def summary(
    key: str,
    title: str,
    value: str = "10%",
    *,
    failed: bool = False,
    actionable: bool = False,
    percent: float | None = 5.0,
    details: tuple[str, ...] = ("Detail: value",),
    capability: CapabilityState = CapabilityState.UNKNOWN,
) -> ResourceSummary:
    return make_summary(
        key,
        title,
        value=value,
        subtitle="subtitle",
        percent=percent,
        details=details,
        actionable=actionable,
        failed=failed,
        capability=capability,
    )


def snapshot(*resources: ResourceSummary) -> DashboardSnapshot:
    return make_snapshot(*resources)


class ResourceCardContractTests(unittest.TestCase):
    def test_usage_bar_rules_match_resource_semantics(self) -> None:
        self.assertTrue(ResourceCard.should_show_usage_bar(summary("cpu", "CPU")))
        self.assertTrue(ResourceCard.should_show_usage_bar(summary("memory", "Memory")))
        self.assertTrue(
            ResourceCard.should_show_usage_bar(summary("storage", "Storage"))
        )
        self.assertTrue(
            ResourceCard.should_show_usage_bar(summary("battery", "Battery"))
        )
        self.assertFalse(
            ResourceCard.should_show_usage_bar(
                summary("battery", "Battery", percent=None, details=(), failed=True)
            )
        )
        self.assertFalse(ResourceCard.should_show_usage_bar(summary("gpu", "GPU")))
        self.assertFalse(
            ResourceCard.should_show_usage_bar(summary("network", "Network"))
        )

    def test_action_label_text_matches_actionable_flag(self) -> None:
        self.assertEqual(action_label_text(True), "Review and clean  →")
        self.assertEqual(action_label_text(False), "View details  →")

    def test_metric_label_pairs_filters_headline_and_splits_labels(self) -> None:
        self.assertEqual(
            metric_label_pairs(
                ("Physical RAM: 16.00 GiB", "16.00 GiB", "Available: 8.00 GiB"),
                "16.00 GiB",
            ),
            (("Physical RAM", "16.00 GiB"), ("Available", "8.00 GiB")),
        )

    def test_metric_label_pairs_keeps_unprefixed_lines(self) -> None:
        self.assertEqual(
            metric_label_pairs(("AMD Vega GPU", "Temperature: 56°C"), "headline"),
            (("", "AMD Vega GPU"), ("Temperature", "56°C")),
        )

    def test_update_summary_sets_labels_and_action_text(self) -> None:
        card: Any = object.__new__(ResourceCard)
        card.value_label = FakeControl()
        card.subtitle_label = FakeControl()
        card.progress = FakeControl()
        card.details_label = FakeControl()
        card.metric_rows = []
        card.metrics_frame = Mock()
        card.colors = {"card": "#fff", "secondary": "#666", "text": "#000"}
        with (
            patch("maintenance.dialogs.tk.Frame"),
            patch("maintenance.dialogs.tk.Label") as label_factory,
        ):
            card.update_summary(
                summary("cpu", "CPU", "45%", actionable=True, details=("Load: 45%",))
            )

        self.assertEqual(card.value_label.options["text"], "45%")
        self.assertEqual(card.details_label.options["text"], "Review and clean  →")
        self.assertEqual(card.progress.options["value"], 5.0)
        label_factory.assert_called()

    def test_update_summary_exposes_capability_status_in_secondary_text(self) -> None:
        for state, expected in (
            (CapabilityState.UNSUPPORTED, "Unsupported"),
            (
                CapabilityState.TEMPORARILY_UNAVAILABLE,
                "Temporarily unavailable",
            ),
            (CapabilityState.PERMISSION_LIMITED, "Permission required"),
        ):
            card: Any = object.__new__(ResourceCard)
            card.value_label = FakeControl()
            card.subtitle_label = FakeControl()
            card.progress = None
            card.details_label = FakeControl()
            card.metric_rows = []
            card.metrics_frame = Mock()
            card.colors = {"card": "#fff", "secondary": "#666", "text": "#000"}
            with patch("maintenance.dialogs.tk.Frame"), patch(
                "maintenance.dialogs.tk.Label"
            ):
                card.update_summary(
                    summary("gpu", "GPU", percent=None, capability=state)
                )
            self.assertIn(expected, card.subtitle_label.options["text"])

    def test_update_summary_shrinks_metric_rows(self) -> None:
        card: Any = object.__new__(ResourceCard)
        card.value_label = FakeControl()
        card.subtitle_label = FakeControl()
        card.progress = FakeControl()
        card.details_label = FakeControl()
        card.metric_rows = []
        card.metrics_frame = Mock()
        card.colors = {"card": "#fff", "secondary": "#666", "text": "#000"}
        with (
            patch("maintenance.dialogs.tk.Frame"),
            patch("maintenance.dialogs.tk.Label"),
        ):
            card.update_summary(summary("cpu", "CPU", details=("A: 1", "B: 2", "C: 3")))
            self.assertEqual(len(card.metric_rows), 3)
            card.update_summary(summary("cpu", "CPU", details=("A: 1",)))
            self.assertEqual(len(card.metric_rows), 1)

    def test_reset_summary_restores_unscanned_card_state(self) -> None:
        card: Any = object.__new__(ResourceCard)
        card.value_label = FakeControl()
        card.subtitle_label = FakeControl()
        card.progress = FakeControl()
        card.details_label = FakeControl()
        row = Mock()
        card.metric_rows = [(row, Mock(), Mock())]

        card.reset_summary()

        self.assertEqual(card.value_label.options["text"], "—")
        self.assertEqual(
            card.subtitle_label.options["text"], "No data yet"
        )
        self.assertEqual(card.progress.options["value"], 0)
        self.assertEqual(card.details_label.options["text"], "View details  →")
        row.destroy.assert_called_once()
        self.assertEqual(card.metric_rows, [])

    def test_open_uses_coordinator_action_id_when_present(self) -> None:
        coordinator = ButtonCoordinator()
        open_card: Any = object.__new__(ResourceCard)
        open_card._button_coordinator = coordinator
        open_card._action_id = "dashboard:resource:cpu"
        open_card.on_open = Mock()
        open_card.key = "cpu"
        coordinator.register("dashboard:resource:cpu", lambda: open_card.on_open("cpu"))

        open_card._open()

        open_card.on_open.assert_called_once_with("cpu")

    def test_unavailable_summary_keeps_review_label_for_actionable_keys(self) -> None:
        self.assertEqual(
            action_label_text(unavailable_summary("cpu", "CPU").actionable),
            "Review and clean  →",
        )
        self.assertEqual(
            action_label_text(unavailable_summary("gpu", "GPU").actionable),
            "View details  →",
        )


class DashboardWindowTests(unittest.TestCase):
    def test_open_resource_during_background_refresh_constructs_dialog(self) -> None:
        window = make_window()
        window._background_tasks = 2
        window.snapshot = snapshot(
            summary("cpu", "CPU"),
            summary("storage", "Storage"),
            summary("gpu", "GPU"),
        )
        window.analyzer = Mock()
        window.process_manager = Mock()
        window.file_manager = Mock()

        with (
            patch("window.ProcessDialog") as process_dialog,
            patch("window.StorageDialog") as storage_dialog,
            patch("window.InfoDialog") as info_dialog,
        ):
            window.open_resource("cpu")
            window.open_resource("storage")
            window.open_resource("gpu")

        self.assertEqual(process_dialog.call_count, 1)
        self.assertEqual(storage_dialog.call_count, 1)
        self.assertEqual(info_dialog.call_count, 1)

    def test_component_result_started_before_full_snapshot_is_dropped(self) -> None:
        window = make_window()
        window._full_snapshot_applied_at = 100.0
        window.snapshot = snapshot(summary("cpu", "CPU", "25%"))
        window.cards = {"cpu": Mock()}
        window._queue_component_result("cpu", 50.0, summary("cpu", "CPU", "90%"))

        window.cards["cpu"].update_summary.assert_not_called()
        self.assertEqual(window.snapshot.get("cpu").value, "25%")
        self.assertFalse(window._component_scheduler.in_flight("cpu"))

    def test_component_result_started_after_full_snapshot_is_applied(self) -> None:
        window = make_window()
        window._full_snapshot_applied_at = 50.0
        window.snapshot = snapshot(summary("cpu", "CPU", "25%"))
        window.cards = {"cpu": Mock()}
        window._queue_component_result("cpu", 100.0, summary("cpu", "CPU", "90%"))

        window.cards["cpu"].update_summary.assert_called_once()
        self.assertEqual(window.snapshot.get("cpu").value, "90%")

    def test_component_result_before_any_full_snapshot_is_applied(self) -> None:
        window = make_window()
        window.snapshot = snapshot(summary("cpu", "CPU", "25%"))
        window.cards = {"cpu": Mock()}
        window._queue_component_result("cpu", 10.0, summary("cpu", "CPU", "90%"))

        window.cards["cpu"].update_summary.assert_called_once()
        self.assertEqual(window.snapshot.get("cpu").value, "90%")

    def test_dropped_component_error_keeps_last_valid_and_releases_scheduler(
        self,
    ) -> None:
        window = make_window()
        window._full_snapshot_applied_at = 100.0
        window.snapshot = snapshot(summary("cpu", "CPU", "25%"))
        window.cards = {"cpu": Mock()}
        window._queue_component_result("cpu", 50.0, RuntimeError("boom"))

        window.cards["cpu"].update_summary.assert_not_called()
        self.assertEqual(window.snapshot.get("cpu").value, "25%")
        self.assertFalse(window._component_scheduler.in_flight("cpu"))

    def test_show_snapshot_records_full_snapshot_applied_time(self) -> None:
        window = make_window()
        window.snapshot = None
        window.cards = {}
        window._refresh_health = Mock()
        window._set_busy = Mock()
        window._schedule_component_poll = Mock()
        window._full_snapshot_applied_at = None

        window._show_snapshot(snapshot())

        self.assertIsNotNone(window._full_snapshot_applied_at)

    def test_show_snapshot_refreshes_all_systems_projection(self) -> None:
        window = make_window()
        window.snapshot = None
        window.cluster_page = Mock()

        window._show_snapshot(snapshot())

        window.cluster_page.refresh_nodes.assert_called_once_with([])

    def test_show_snapshot_defers_hidden_all_systems_projection(self) -> None:
        window = make_window()
        window.snapshot = None
        window.cluster_page = Mock()
        window._page_router = Mock()
        window._page_router.is_mapped.return_value = False

        window._show_snapshot(snapshot())

        window.cluster_page.refresh_nodes.assert_not_called()

    def test_close_stops_background_workers_when_available(self) -> None:
        window = make_window()
        window.analyzer = Mock()
        window._component_poll_id = None
        window._pending_after_ids = set()

        window._close()

        window.analyzer.stop_background_workers.assert_called_once()
        self.assertTrue(window.master.destroyed)

    def test_close_tolerates_analyzer_without_stop_hook(self) -> None:
        window = make_window()
        window.analyzer = object()
        window._component_poll_id = None
        window._pending_after_ids = set()

        window._close()

        self.assertTrue(window.master.destroyed)

    def test_run_in_background_marks_busy_at_start(self) -> None:
        window = make_window()
        window._set_busy = Mock()
        window._run_daemon = Mock()

        window._run_in_background(lambda: None)

        window._set_busy.assert_called_once_with(True)
        self.assertEqual(window._background_tasks, 1)

    def test_show_snapshot_clears_busy_state(self) -> None:
        window = make_window()
        window.snapshot = None
        window.cards = {}
        window._set_busy = Mock()
        window._schedule_component_poll = Mock()

        window._show_snapshot(snapshot())

        window._set_busy.assert_called_once_with(False)

    def test_failed_component_summary_uses_catalog_title(self) -> None:
        window = make_window()

        failed = window._failed_component_summary("battery")

        self.assertEqual(failed.title, "Battery")
        self.assertEqual(failed.value, "Unavailable")
        self.assertTrue(failed.failed)

    def test_failed_component_summary_falls_back_to_unknown_key(self) -> None:
        window = make_window()

        failed = window._failed_component_summary("weird")

        self.assertEqual(failed.title, "weird")
        self.assertEqual(failed.value, "Unavailable")

    def test_cancel_analysis_disables_cancel_button(self) -> None:
        window = make_window()
        window._analysis_cancel_event = threading.Event()

        window._cancel_analysis()

        self.assertTrue(window._analysis_cancel_event.is_set())
        self.assertEqual(
            window.cancel_button.options["state"],
            tk.DISABLED,
        )


if __name__ == "__main__":
    unittest.main()

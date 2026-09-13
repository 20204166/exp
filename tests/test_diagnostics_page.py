"""Headless presentation tests for the Diagnostics page."""

import unittest
from unittest.mock import Mock

from maintenance.diagnostics import (
    ClusterDiagnostic,
    ComponentDiagnostic,
    DiagnosticsSnapshot,
    NodeDiagnostic,
    OperationDiagnostic,
    PlacementDiagnostic,
    RenderDiagnostic,
    serialize_diagnostics,
)
from maintenance.ui import layout as ui_layout
from maintenance.ui.action_coordinator import ButtonCoordinator
from maintenance.ui.diagnostics_page import DiagnosticsPage, DiagnosticsPageCallbacks
from tests.support.widget_recording import WidgetRecorder


def empty_snapshot() -> DiagnosticsSnapshot:
    return DiagnosticsSnapshot(
        components=(),
        operations=(),
        nodes=(),
        render=RenderDiagnostic(0, 0, 0, 0, 0),
    )


def live_snapshot() -> DiagnosticsSnapshot:
    return DiagnosticsSnapshot(
        components=(
            ComponentDiagnostic(
                "storage",
                "failed",
                "supported",
                False,
                None,
                "execution_failed",
                "disk unavailable",
            ),
        ),
        operations=(
            OperationDiagnostic("scan", 7, True, False, None, None),
            OperationDiagnostic("cleanup", 8, True, False, None, "timed out"),
        ),
        nodes=(
            NodeDiagnostic(
                "node-a", "Worker A", "trusted", "paired", "online", None, ()
            ),
            NodeDiagnostic(
                "node-b", "Worker B", "trusted", "paired", "online", None, ()
            ),
        ),
        render=RenderDiagnostic(3, 9, 6, 2, 1),
        most_recent_failure="cleanup: timed out",
    )


def label_options(widget: object) -> dict[str, object]:
    """Read both constructor and update options from a recorded label."""

    assert hasattr(widget, "kwargs")
    assert hasattr(widget, "config_options")
    return {**widget.kwargs, **widget.config_options}  # type: ignore[attr-defined]


def labels_with_text(recorder: WidgetRecorder, text: str) -> list[object]:
    return [
        widget
        for widget in (*recorder.widgets("label"), *recorder.widgets("style_label"))
        if label_options(widget).get("text") == text
    ]


class DiagnosticsPageTests(unittest.TestCase):
    def make_page(self):
        recorder = WidgetRecorder()
        back_callback = Mock()
        copy_callback = Mock()
        callbacks = DiagnosticsPageCallbacks(
            on_back=back_callback, on_copy=copy_callback
        )
        page = DiagnosticsPage(
            recorder.parent(),
            callbacks=callbacks,
            snapshot=empty_snapshot(),
            **recorder.page_kwargs(),
        )
        return page, callbacks, copy_callback, recorder

    def test_empty_state_messages_are_visible(self) -> None:
        _page, _callbacks, _copy_callback, recorder = self.make_page()
        texts = recorder.label_texts()
        self.assertIn("No recent failures", texts)
        self.assertIn("Nothing currently running", texts)
        self.assertIn("No remote nodes configured", texts)
        self.assertIn("No placement decision yet", texts)

    def test_placement_row_is_visible(self) -> None:
        page, _callbacks, _copy_callback, recorder = self.make_page()
        page.render(
            DiagnosticsSnapshot(
                components=(),
                operations=(),
                nodes=(),
                render=RenderDiagnostic(0, 0, 0, 0, 0),
                placement=PlacementDiagnostic("placement", "worker-a", 2, "selected"),
            )
        )
        texts = recorder.label_texts()
        self.assertIn("placement", texts)
        self.assertIn("worker-a · 2 eligible · selected", texts)

    def test_cluster_history_row_is_labeled_as_logical_bytes(self) -> None:
        page, _callbacks, _copy_callback, recorder = self.make_page()
        page.render(
            DiagnosticsSnapshot(
                components=(),
                operations=(),
                nodes=(),
                render=RenderDiagnostic(0, 0, 0, 0, 0),
                cluster=ClusterDiagnostic(
                    "coordinator",
                    "coord",
                    2,
                    1.0,
                    10,
                    20,
                    0,
                    256,
                    "normal",
                    100.0,
                    False,
                    None,
                ),
            )
        )
        texts = recorder.label_texts()
        self.assertIn("History (logical bytes)", texts)
        self.assertIn("10 / 20 bytes", texts)

    def test_copy_callback_receives_serialized_snapshot(self) -> None:
        page, _callbacks, copy_callback, _recorder = self.make_page()
        page.copy_button.kwargs["command"]()
        copy_callback.assert_called_once()
        self.assertIn("components", copy_callback.call_args.args[0])

    def test_live_health_pulse_exposes_snapshot_derived_values(self) -> None:
        page, _callbacks, _copy_callback, recorder = self.make_page()
        snapshot = live_snapshot()

        page.render(snapshot)

        texts = recorder.label_texts()
        self.assertIn("Active work", texts)
        self.assertIn("Recent failures", texts)
        self.assertIn("Nodes", texts)
        self.assertIn("Render pressure", texts)
        self.assertIn("2", texts)
        self.assertIn("1", texts)
        self.assertIn("3 pending", texts)

    def test_live_health_pulse_uses_semantic_state_presentation(self) -> None:
        page, _callbacks, _copy_callback, recorder = self.make_page()

        page.render(live_snapshot())

        active_value = labels_with_text(recorder, "2")
        failure_value = labels_with_text(recorder, "cleanup: timed out")
        self.assertTrue(active_value)
        self.assertTrue(failure_value)
        self.assertTrue(
            any(
                label_options(widget).get("fg") == page.colors["warning"]
                or label_options(widget).get("foreground") == page.colors["warning"]
                or label_options(widget).get("style") == "Busy.Status.TLabel"
                for widget in active_value
            )
        )
        self.assertTrue(
            any(
                label_options(widget).get("fg") == page.colors["danger"]
                or label_options(widget).get("foreground") == page.colors["danger"]
                or label_options(widget).get("style") == "Danger.TLabel"
                for widget in failure_value
            )
        )

    def test_component_rows_distinguish_normal_and_disabled_states(self) -> None:
        page, _callbacks, _copy_callback, recorder = self.make_page()
        page.render(
            DiagnosticsSnapshot(
                components=(
                    ComponentDiagnostic(
                        "idle", "idle", "supported", False, None, None, None
                    ),
                    ComponentDiagnostic(
                        "paused", "paused", "supported", False, None, None, None
                    ),
                ),
                operations=(),
                nodes=(),
                render=RenderDiagnostic(0, 0, 0, 0, 0),
            )
        )

        idle_value = labels_with_text(recorder, "idle · supported · No data yet")
        paused_value = labels_with_text(recorder, "paused · supported · No data yet")
        self.assertTrue(idle_value)
        self.assertTrue(paused_value)
        self.assertEqual(label_options(idle_value[0]).get("fg"), page.colors["success"])
        self.assertEqual(
            label_options(paused_value[0]).get("fg"), page.colors["muted_text"]
        )

    def test_diagnostic_rows_use_shared_metric_value_wrap_contract(self) -> None:
        page, _callbacks, _copy_callback, _recorder = self.make_page()
        page.render(live_snapshot())

        page._pulse_body.winfo_width = lambda: 300
        page._rewrap_section(page._pulse_body)

        value_label = page._section_rows[page._pulse_body][0][2]
        self.assertEqual(
            value_label.config_options["wraplength"],
            ui_layout.metric_value_wrap(300),
        )

    def test_refresh_reuses_pulse_and_section_widgets(self) -> None:
        page, _callbacks, _copy_callback, recorder = self.make_page()
        page.render(live_snapshot())
        frames_before = tuple(recorder.widgets("frame"))
        labels_before = tuple(recorder.widgets("label"))
        changed = live_snapshot()
        changed = DiagnosticsSnapshot(
            components=changed.components,
            operations=(
                OperationDiagnostic("scan", 9, True, False, None, None),
                OperationDiagnostic("cleanup", 10, True, False, None, "timed out"),
            ),
            nodes=changed.nodes,
            render=RenderDiagnostic(0, 10, 10, 2, 1),
            most_recent_failure="cleanup: timed out again",
        )

        page.render(changed)

        self.assertEqual(tuple(recorder.widgets("frame")), frames_before)
        self.assertEqual(tuple(recorder.widgets("label")), labels_before)
        self.assertTrue(labels_with_text(recorder, "cleanup: timed out again"))
        self.assertTrue(labels_with_text(recorder, "No pending renders"))

    def test_copy_action_preserves_serialized_changed_snapshot(self) -> None:
        page, _callbacks, copy_callback, _recorder = self.make_page()
        snapshot = live_snapshot()
        page.render(snapshot)

        page.copy_button.kwargs["command"]()

        copy_callback.assert_called_once_with(serialize_diagnostics(snapshot))

    def test_copy_button_registers_stable_action_id_when_coordinator_present(
        self,
    ) -> None:
        recorder = WidgetRecorder()
        coordinator = ButtonCoordinator()
        copy_callback = Mock()
        callbacks = DiagnosticsPageCallbacks(on_back=Mock(), on_copy=copy_callback)
        DiagnosticsPage(
            recorder.parent(),
            callbacks=callbacks,
            snapshot=empty_snapshot(),
            button_coordinator=coordinator,
            **recorder.page_kwargs(),
        )

        self.assertIn("diagnostics:copy", coordinator.registered_ids())
        coordinator.dispatch("diagnostics:copy")

        copy_callback.assert_called_once()

    def test_refresh_reuses_existing_row_widgets(self) -> None:
        page, _callbacks, _copy_callback, recorder = self.make_page()
        frame_count = len(recorder.widgets("frame"))

        page.render(empty_snapshot())

        self.assertEqual(len(recorder.widgets("frame")), frame_count)


if __name__ == "__main__":
    unittest.main()

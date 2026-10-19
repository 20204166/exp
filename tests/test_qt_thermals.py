"""Behavioral coverage for the standalone Qt thermal page and graph."""

from __future__ import annotations

import math
import unittest
from datetime import timedelta
from unittest.mock import Mock

from PySide6.QtCore import QCoreApplication, QEvent, Qt

from maintenance.components.temperature import (
    TemperatureEvent,
    TemperatureRenderState,
    TemperatureSeriesSnapshot,
    TemperatureState,
    TemperatureTelemetry,
)
from maintenance.models import CapabilityState
from maintenance.ui.action_coordinator import ButtonCoordinator
from maintenance.ui.qt_thermal_graph import (
    QtThermalGraph,
    build_qt_thermal_graph_layout,
)
from maintenance.ui.qt_thermals_page import QtThermalsPage
from tests.support.models import make_summary
from tests.support.qt import get_qapplication
from tests.support.temperature import FIXED_TEMPERATURE_AT, make_temperature_sample


def _snapshot(
    component: str = "cpu",
    *,
    state: TemperatureState = TemperatureState.VALID,
    values: tuple[float, ...] = (42.0, 46.0),
    warning: float | None = 50.0,
    critical: float | None = 60.0,
    error: str | None = None,
) -> TemperatureSeriesSnapshot:
    samples = tuple(
        make_temperature_sample(component, value, sampled_monotonic=float(index))
        for index, value in enumerate(values)
    )
    return TemperatureSeriesSnapshot(
        component=component,
        title=f"{component.upper()} Temperature",
        state=state,
        current_celsius=values[-1] if values else None,
        minimum_celsius=min(values) if values else None,
        maximum_celsius=max(values) if values else None,
        warning_celsius=warning,
        critical_celsius=critical,
        samples=samples,
        events=(),
        error=error,
    )


class QtThermalGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapplication()

    def test_geometry_handles_boundaries_constant_series_and_thresholds(self) -> None:
        layout = build_qt_thermal_graph_layout(_snapshot(values=(50.0, 50.0)), 200, 100)
        self.assertIsNotNone(layout)
        assert layout is not None
        self.assertEqual(layout.points[0][0], layout.left)
        self.assertEqual(layout.points[-1][0], layout.right)
        assert layout.warning_y is not None
        assert layout.critical_y is not None
        self.assertTrue(layout.top <= layout.warning_y <= layout.bottom)
        self.assertTrue(layout.top <= layout.critical_y <= layout.bottom)
        tiny = build_qt_thermal_graph_layout(_snapshot(values=(50.0,)), 1, 1)
        self.assertIsNotNone(tiny)
        assert tiny is not None
        self.assertTrue(
            all(math.isfinite(value) for point in tiny.points for value in point)
        )

    def test_geometry_ignores_nonfinite_values_and_bounds_points(self) -> None:
        snapshot = _snapshot(values=(float("nan"), float("inf"), *range(300)))
        layout = build_qt_thermal_graph_layout(snapshot, 520, 108, max_points=24)
        self.assertIsNotNone(layout)
        assert layout is not None
        self.assertLessEqual(len(layout.points), 24)
        self.assertTrue(all(math.isfinite(y) for _x, y in layout.points))
        self.assertIsNone(
            build_qt_thermal_graph_layout(_snapshot(values=(float("nan"),)), 200, 100)
        )

    def test_graph_exposes_text_alternative_and_empty_state_labels(self) -> None:
        graph = QtThermalGraph("CPU Temperature")
        graph.resize(520, 108)
        graph.render(_snapshot(values=(42.0, 46.0)))
        self.assertIn("Current 46°C", graph.accessibleDescription())
        self.assertIn("Min 42°C", graph.accessibleDescription())
        self.assertIn("Max 46°C", graph.accessibleDescription())
        self.assertIn("Warning", graph.accessibleDescription())
        graph.render(_snapshot(state=TemperatureState.NO_DATA, values=()))
        self.assertIn("Waiting for the first sample", graph.accessibleDescription())
        graph.render(_snapshot(state=TemperatureState.UNSUPPORTED, values=()))
        self.assertIn("Temperature not supported", graph.accessibleDescription())
        graph.render(
            _snapshot(
                state=TemperatureState.ERROR, values=(), error="Permission required"
            )
        )
        self.assertIn("Permission required", graph.accessibleDescription())
        graph.close()


class QtThermalsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapplication()

    def make_page(self, **kwargs) -> QtThermalsPage:
        page = QtThermalsPage(**kwargs)
        page.resize(900, 680)
        page.show()
        self.app.processEvents()
        return page

    def test_visibility_uses_capability_separately_from_series_state(self) -> None:
        page = self.make_page(on_back=Mock())
        page.render(
            TemperatureRenderState(
                series=(
                    _snapshot("cpu", state=TemperatureState.NO_DATA, values=()),
                    _snapshot("gpu", state=TemperatureState.UNSUPPORTED, values=()),
                    _snapshot(
                        "storage",
                        state=TemperatureState.ERROR,
                        values=(),
                        error="Read denied",
                    ),
                    _snapshot("battery", state=TemperatureState.VALID, values=(31.0,)),
                ),
                events=(),
            ),
            {
                "cpu": CapabilityState.SUPPORTED,
                "gpu": CapabilityState.SUPPORTED,
                "storage": CapabilityState.SUPPORTED,
                "battery": CapabilityState.UNSUPPORTED,
            },
        )
        self.assertEqual(set(page.graphs), {"cpu", "gpu", "storage"})
        self.assertIn(
            "Waiting for the first sample", page.graphs["cpu"].accessibleDescription()
        )
        self.assertGreaterEqual(page.graphs["cpu"].plot.height(), 108)
        self.assertIn(
            "Temperature not supported", page.graphs["gpu"].accessibleDescription()
        )
        self.assertIn("Read denied", page.graphs["storage"].accessibleDescription())
        self.assertIn("Waiting for thermal samples", page.status_label.text())
        page.close()

    def test_render_recovery_events_bounds_and_node_independent_input(self) -> None:
        page = self.make_page(on_back=Mock())
        event = TemperatureEvent(
            component="cpu",
            sensor_id="cpu0",
            sensor_name="A very long thermal sensor label " * 10,
            started_at=FIXED_TEMPERATURE_AT,
            started_monotonic=10.0,
            peak_celsius=91.0,
            baseline_celsius=60.0,
            severity="warning",
            samples=(make_temperature_sample("cpu", 91.0),),
        )
        events = tuple(
            TemperatureEvent(
                component="cpu",
                sensor_id=str(index),
                sensor_name=str(index),
                started_at=FIXED_TEMPERATURE_AT + timedelta(minutes=index),
                started_monotonic=float(index),
                peak_celsius=91.0,
                baseline_celsius=60.0,
                severity="warning",
                samples=(make_temperature_sample("cpu", 91.0),),
            )
            for index in range(9)
        ) + (event,)
        first = TemperatureRenderState(
            series=(_snapshot("cpu", values=(70.0, 91.0)),), events=events
        )
        page.render(first, {"cpu": CapabilityState.SUPPORTED})
        self.assertLessEqual(len(page.event_buttons), 6)
        self.assertTrue(any(len(label.text()) > 80 for label in page.event_labels))
        self.assertTrue(all(label.wordWrap() for label in page.event_labels))
        page.event_buttons[-1].click()
        event_snapshot = page.graphs["cpu"].snapshot
        assert event_snapshot is not None
        self.assertEqual(event_snapshot.current_celsius, 91.0)
        page.render(
            TemperatureRenderState(
                series=(_snapshot("cpu", values=(48.0,)),), events=()
            ),
            {"cpu": CapabilityState.SUPPORTED},
        )
        # Drain row.deleteLater() while the owning page is still retained.
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertIn("Current 48°C", page.graphs["cpu"].accessibleDescription())
        independent = TemperatureRenderState(
            series=(_snapshot("cpu", values=(32.0,)),), events=()
        )
        page.render(independent, {"cpu": CapabilityState.SUPPORTED})
        self.assertIn("Current 32°C", page.graphs["cpu"].accessibleDescription())
        page.close()

    def test_learn_more_action_focus_back_and_scroll_layout(self) -> None:
        learn_more, on_back = Mock(), Mock()
        coordinator = ButtonCoordinator()
        page = self.make_page(
            on_back=on_back,
            on_learn_more=learn_more,
            button_coordinator=coordinator,
        )
        self.assertEqual(
            page.learn_more_button.accessibleName(), "Why isn't a sensor available?"
        )
        page.learn_more_button.click()
        learn_more.assert_called_once_with()
        self.assertIn("thermals:learn-more", coordinator.registered_ids())
        page.back_button.setFocus()
        page.focus_back()
        self.app.processEvents()
        self.assertTrue(page.back_button.hasFocus())
        for width in (900, 1280, 1600):
            page.resize(width, 680)
            self.app.processEvents()
            self.assertEqual(
                page.scroll_area.horizontalScrollBarPolicy(),
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )
        page.close()

    def test_empty_and_recovery_do_not_fabricate_samples_or_merge_nodes(self) -> None:
        telemetry = TemperatureTelemetry()
        summary = make_summary(
            "cpu", "CPU", capability=CapabilityState.SUPPORTED, temperatures=()
        )
        for _ in range(telemetry.policy_for("cpu").unsupported_confirm_samples - 1):
            telemetry.record_summary("cpu", summary)
        before = telemetry.series_snapshot("cpu")
        self.assertEqual(before.state, TemperatureState.NO_DATA)
        self.assertEqual(before.samples, ())
        telemetry.record_summary("cpu", summary)
        unsupported = telemetry.series_snapshot("cpu")
        self.assertEqual(unsupported.state, TemperatureState.UNSUPPORTED)
        self.assertEqual(unsupported.samples, ())
        telemetry.record_summary(
            "cpu",
            make_summary(
                "cpu",
                "CPU",
                capability=CapabilityState.SUPPORTED,
                temperatures=(make_temperature_sample("cpu", 44.0),),
            ),
        )
        recovered = telemetry.render_state(("cpu",))
        page = self.make_page(on_back=Mock())
        page.render(recovered, {"cpu": CapabilityState.SUPPORTED})
        self.assertIn("Current 44°C", page.graphs["cpu"].accessibleDescription())
        other_node = TemperatureTelemetry().render_state(("cpu",))
        other_cpu = other_node.series_for("cpu")
        assert other_cpu is not None
        self.assertEqual(other_cpu.samples, ())
        page.close()


if __name__ == "__main__":
    unittest.main()

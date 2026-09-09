"""Focused tests for the shared thermal graph renderer."""

from __future__ import annotations

import unittest
from typing import Any, cast
from unittest.mock import Mock

from maintenance.components.temperature import (
    TemperatureSeriesSnapshot,
    TemperatureState,
)
from maintenance.ui.layout import build_telemetry_graph_layout
from maintenance.ui.telemetry_graph import TelemetryMiniGraph
from tests.support.temperature import make_temperature_sample


class TelemetryGraphTests(unittest.TestCase):
    def _graph(self) -> Any:
        graph: Any = object.__new__(TelemetryMiniGraph)
        graph.colors = {
            "card": "#fff",
            "text": "#000",
            "secondary": "#666",
            "accent": "#00f",
            "border": "#ddd",
        }
        graph._height = 108
        graph._width = 520
        graph._snapshot = None
        graph._canvas = cast(Any, Mock())
        graph._canvas.winfo_width.return_value = 520
        graph._canvas.winfo_height.return_value = 108
        graph._state_label = cast(Any, Mock())
        return graph

    def test_empty_graph_draws_placeholder(self) -> None:
        graph = self._graph()

        graph._redraw()

        graph._canvas.delete.assert_called_once_with("all")
        self.assertIn(
            "No temperature data", graph._state_label.config.call_args.kwargs["text"]
        )

    def test_valid_series_draws_line_and_current_label(self) -> None:
        graph = self._graph()
        graph._snapshot = TemperatureSeriesSnapshot(
            component="cpu",
            title="CPU Temperature",
            state=TemperatureState.VALID,
            current_celsius=46.0,
            minimum_celsius=42.0,
            maximum_celsius=46.0,
            warning_celsius=90.0,
            critical_celsius=95.0,
            samples=(
                make_temperature_sample("cpu", 42.0, sampled_monotonic=1.0),
                make_temperature_sample("cpu", 44.0, sampled_monotonic=2.0),
                make_temperature_sample("cpu", 46.0, sampled_monotonic=3.0),
            ),
            events=(),
        )

        graph._redraw()

        graph._canvas.create_line.assert_called()
        self.assertIn(
            "Current 46°C", graph._canvas.create_text.call_args_list[0].kwargs["text"]
        )

    def test_single_sample_draws_point_without_invalid_line(self) -> None:
        graph = self._graph()
        graph._snapshot = TemperatureSeriesSnapshot(
            component="storage",
            title="Storage Temperature",
            state=TemperatureState.VALID,
            current_celsius=40.0,
            minimum_celsius=40.0,
            maximum_celsius=40.0,
            warning_celsius=None,
            critical_celsius=None,
            samples=(make_temperature_sample("storage", 40.0, sampled_monotonic=1.0),),
            events=(),
        )

        graph._redraw()

        graph_lines = [
            call
            for call in graph._canvas.create_line.call_args_list
            if call.kwargs.get("smooth")
        ]
        self.assertEqual(graph_lines, [])
        graph._canvas.create_oval.assert_called_once()

    def test_large_series_is_bounded_before_canvas_render(self) -> None:
        graph = self._graph()
        values = tuple(float(index) for index in range(600))
        graph._snapshot = TemperatureSeriesSnapshot(
            component="cpu",
            title="CPU Temperature",
            state=TemperatureState.VALID,
            current_celsius=599.0,
            minimum_celsius=0.0,
            maximum_celsius=599.0,
            warning_celsius=None,
            critical_celsius=None,
            samples=tuple(
                make_temperature_sample("cpu", value, sampled_monotonic=float(index))
                for index, value in enumerate(values)
            ),
            events=(),
        )

        graph._redraw()

        line_args = graph._canvas.create_line.call_args.args
        self.assertLessEqual(len(line_args) // 2, graph.MAX_PLOT_POINTS)
        self.assertEqual(line_args[1], 90.0)

    def test_layout_builder_is_tk_free_and_preserves_endpoints(self) -> None:
        graph = self._graph()
        graph._snapshot = TemperatureSeriesSnapshot(
            component="gpu",
            title="GPU Temperature",
            state=TemperatureState.VALID,
            current_celsius=46.0,
            minimum_celsius=42.0,
            maximum_celsius=46.0,
            warning_celsius=90.0,
            critical_celsius=95.0,
            samples=(
                make_temperature_sample("gpu", 42.0, sampled_monotonic=1.0),
                make_temperature_sample("gpu", 46.0, sampled_monotonic=2.0),
            ),
            events=(),
        )

        layout = build_telemetry_graph_layout(graph._snapshot, 520, 108)

        self.assertIsNotNone(layout)
        assert layout is not None
        self.assertEqual(layout.points[0][0], layout.left)
        self.assertEqual(layout.points[-1][0], layout.right)
        self.assertIsNotNone(layout.warning_y)

    def test_thresholds_remain_inside_plot_for_cool_samples(self) -> None:
        snapshot = TemperatureSeriesSnapshot(
            component="cpu",
            title="CPU Temperature",
            state=TemperatureState.VALID,
            current_celsius=45.0,
            minimum_celsius=40.0,
            maximum_celsius=45.0,
            warning_celsius=90.0,
            critical_celsius=95.0,
            samples=(
                make_temperature_sample("cpu", 40.0, sampled_monotonic=1.0),
                make_temperature_sample("cpu", 45.0, sampled_monotonic=2.0),
            ),
            events=(),
        )

        layout = build_telemetry_graph_layout(snapshot, 200, 100)

        self.assertIsNotNone(layout)
        assert layout is not None
        assert layout.warning_y is not None
        assert layout.critical_y is not None
        self.assertTrue(layout.top <= layout.warning_y <= layout.bottom)
        self.assertTrue(layout.top <= layout.critical_y <= layout.bottom)

    def test_non_finite_thresholds_are_not_drawn(self) -> None:
        snapshot = TemperatureSeriesSnapshot(
            component="cpu",
            title="CPU Temperature",
            state=TemperatureState.VALID,
            current_celsius=45.0,
            minimum_celsius=40.0,
            maximum_celsius=45.0,
            warning_celsius=float("nan"),
            critical_celsius=float("inf"),
            samples=(make_temperature_sample("cpu", 45.0),),
            events=(),
        )

        layout = build_telemetry_graph_layout(snapshot, 200, 100)

        self.assertIsNotNone(layout)
        assert layout is not None
        self.assertIsNone(layout.warning_y)
        self.assertIsNone(layout.critical_y)


if __name__ == "__main__":
    unittest.main()

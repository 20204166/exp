"""Focused tests for the shared thermal graph renderer."""

from __future__ import annotations

import unittest
from typing import Any, cast
from unittest.mock import Mock

from maintenance.components.temperature import (
    TemperatureSeriesSnapshot,
    TemperatureState,
)
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

        graph._canvas.create_line.assert_not_called()
        graph._canvas.create_oval.assert_called_once()


if __name__ == "__main__":
    unittest.main()

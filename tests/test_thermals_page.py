"""Focused tests for the dedicated Thermals presentation page."""

import unittest
from typing import Any
from unittest.mock import Mock

from maintenance.components.temperature import TemperaturePolicy, TemperatureTelemetry
from maintenance.models import CapabilityState
from maintenance.ui.thermals_page import ThermalsPage
from tests.support.models import make_summary
from tests.support.temperature import make_temperature_sample


def _telemetry(*components: str) -> TemperatureTelemetry:
    telemetry = TemperatureTelemetry(
        policies={
            component: TemperaturePolicy(
                warning_celsius=50.0,
                critical_celsius=60.0,
                recovery_celsius=40.0,
                consecutive_samples=1,
            )
            for component in components
        }
    )
    for index, component in enumerate(components):
        telemetry.record_summary(
            component,
            make_summary(
                component,
                component.upper(),
                capability=CapabilityState.SUPPORTED,
                temperatures=(
                    make_temperature_sample(
                        component,
                        40.0 + index,
                        sampled_monotonic=float(index + 1),
                    ),
                ),
            ),
        )
    return telemetry


class ThermalsPageStateTests(unittest.TestCase):
    def _page(self) -> Any:
        page: Any = object.__new__(ThermalsPage)
        page._graphs = {}
        page._graph_sections = {}
        page._event_rows = []
        page._events_card = None
        page._events_body = None
        page._last_event_signature = None
        page._telemetry = None
        page._capabilities = {}
        page.status_label = Mock()
        page._refresh_scrollbar = Mock()
        page._refresh_events = Mock()
        return page

    def test_refresh_uses_existing_component_histories(self) -> None:
        page = self._page()
        graphs: dict[str, Mock] = {}

        def ensure(component: str) -> Mock:
            graph = graphs.setdefault(component, Mock())
            page._graphs[component] = graph
            return graph

        page._ensure_component = ensure
        telemetry = _telemetry("cpu", "gpu", "storage")

        page.refresh_from_telemetry(
            telemetry,
            {
                "cpu": CapabilityState.SUPPORTED,
                "gpu": CapabilityState.SUPPORTED,
                "storage": CapabilityState.SUPPORTED,
                "battery": CapabilityState.UNSUPPORTED,
            },
        )

        self.assertEqual(set(graphs), {"cpu", "gpu", "storage"})
        self.assertEqual(
            graphs["cpu"].render.call_args.args[0].current_celsius,
            40.0,
        )
        self.assertNotIn("battery", graphs)
        page._refresh_scrollbar.assert_called_once()

    def test_battery_is_omitted_when_unsupported(self) -> None:
        page = self._page()
        page._ensure_component = Mock()
        telemetry = _telemetry("battery")

        page.refresh_from_telemetry(
            telemetry,
            {"battery": CapabilityState.UNSUPPORTED},
        )

        page._ensure_component.assert_not_called()
        self.assertIn("No supported", page.status_label.config.call_args.kwargs["text"])

    def test_repeated_refresh_keeps_graph_widgets_owned_by_page(self) -> None:
        page = self._page()
        graph = Mock()
        page._graphs = {"cpu": graph}
        creations: list[str] = []

        def ensure(component: str) -> Mock:
            if component not in page._graphs:
                creations.append(component)
                page._graphs[component] = graph
            return page._graphs[component]

        page._ensure_component = ensure
        telemetry = _telemetry("cpu")

        page.refresh_from_telemetry(
            telemetry,
            {"cpu": CapabilityState.SUPPORTED},
        )
        page.refresh_from_telemetry(
            telemetry,
            {"cpu": CapabilityState.SUPPORTED},
        )

        self.assertEqual(creations, [])
        self.assertEqual(graph.render.call_count, 2)

    def test_events_are_read_from_existing_telemetry_store(self) -> None:
        page = self._page()
        page._graphs = {"cpu": Mock()}
        telemetry = TemperatureTelemetry(
            policies={
                "cpu": TemperaturePolicy(
                    warning_celsius=50.0,
                    critical_celsius=60.0,
                    recovery_celsius=40.0,
                    consecutive_samples=1,
                )
            }
        )
        for value, monotonic in ((55.0, 1.0), (35.0, 2.0)):
            telemetry.record_summary(
                "cpu",
                make_summary(
                    "cpu",
                    "CPU",
                    capability=CapabilityState.SUPPORTED,
                    temperatures=(
                        make_temperature_sample(
                            "cpu",
                            value,
                            sampled_monotonic=monotonic,
                        ),
                    ),
                ),
            )
        page._telemetry = telemetry

        events = page._events()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].peak_celsius, 55.0)


if __name__ == "__main__":
    unittest.main()

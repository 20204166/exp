"""Agent 5 Superpower Evidence Audit test for PATCH-20260912-001.

Resolves four contested validator findings with executable evidence:

1. Reachability of the "Temperature not supported" copy through the real
   ``ThermalsPage.render`` flow (cpu/gpu/storage removed vs battery kept).
2. ``record_scan`` recording a valid sample without resetting the
   empty-read budget.
3. "Consecutive" semantics across interleaved failed reads.
4. Controller capability-counter independence from empty temperature reads.

This test changes no app code and no normal repo tests.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import Mock

from maintenance.components.temperature import (
    TemperatureScan,
    TemperatureState,
    TemperatureTelemetry,
)
from maintenance.models import CapabilityState
from maintenance.ui.thermals_page import ThermalsPage
from maintenance.ui.window_components import observe_capability
from tests.support.models import make_summary
from tests.support.temperature import make_temperature_sample

SCAN_AT = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)


def _empty_supported_card(key: str, title: str) -> Any:
    return make_summary(
        key, title, capability=CapabilityState.SUPPORTED, temperatures=()
    )


class Agent5PatchEvidenceTests(unittest.TestCase):
    """Evidence scoped to the PATCH-20260912-001 contested findings."""

    def _page(self) -> Any:
        page: Any = object.__new__(ThermalsPage)
        page._graphs = {}
        page._graph_sections = {}
        page._event_rows = []
        page._events_card = None
        page._events_body = None
        page._last_event_signature = None
        page._state = None
        page._capabilities = {}
        page.status_label = Mock()
        page._refresh_scrollbar = Mock()
        page._refresh_events = Mock()
        return page

    def test_page_flow_cpu_removed_battery_renders_unsupported(self) -> None:
        """Resolve Agent 1 F1 vs Agent 2 finding 5: where the copy is reachable.

        Twenty empty SUPPORTED summaries for cpu and battery (the real
        ingestion path), then the real ``ThermalsPage.render`` flow with the
        capabilities the controller actually records (SUPPORTED for a present
        battery, per ``_battery_resource`` and ``observe_capability``).
        """
        telemetry = TemperatureTelemetry()
        cpu_card = _empty_supported_card("cpu", "CPU")
        battery_card = _empty_supported_card("battery", "Battery")
        for _ in range(20):
            telemetry.record_summary("cpu", cpu_card)
            telemetry.record_summary("battery", battery_card)

        page = self._page()
        graphs: dict[str, Mock] = {}

        def ensure(component: str) -> Mock:
            graph = graphs.setdefault(component, Mock())
            page._graphs[component] = graph
            return graph

        page._ensure_component = ensure

        page.render(
            telemetry.render_state(("cpu", "gpu", "storage", "battery")),
            {
                "cpu": CapabilityState.SUPPORTED,
                "battery": CapabilityState.SUPPORTED,
            },
        )

        # cpu/gpu/storage: an UNSUPPORTED snapshot is removed (Agent 1 F1 holds
        # for non-battery components).
        self.assertNotIn("cpu", graphs)
        self.assertNotIn("gpu", graphs)
        self.assertNotIn("storage", graphs)
        # battery: capability SUPPORTED keeps the graph visible with an
        # UNSUPPORTED snapshot, so "Temperature not supported" IS reachable in
        # the real page flow for battery-equipped nodes.
        self.assertIn("battery", graphs)
        self.assertEqual(
            graphs["battery"].render.call_args.args[0].state,
            TemperatureState.UNSUPPORTED,
        )
        # The battery graph remains, so the page keeps the live-history status
        # (not "No supported temperature sensors detected.").
        self.assertEqual(
            page.status_label.config.call_args.kwargs["text"],
            "Live history from shared node telemetry.",
        )

    def test_record_scan_valid_sample_leaves_stale_empty_reads_budget(self) -> None:
        """record_scan sets VALID without resetting empty_reads.

        Corroborates Agent 1 F2 / Agent 3 finding 1 with independent evidence,
        and contrasts with the record_summary recovery path.
        """
        telemetry = TemperatureTelemetry()
        cpu_card = _empty_supported_card("cpu", "CPU")
        for _ in range(19):
            telemetry.record_summary("cpu", cpu_card)
        self.assertEqual(
            telemetry.series_snapshot("cpu").state, TemperatureState.NO_DATA
        )

        telemetry.record_scan(
            TemperatureScan(
                captured_at=SCAN_AT,
                captured_monotonic=20.0,
                lines=("Temperature: 50°C",),
                samples_by_component=(
                    (
                        "cpu",
                        (make_temperature_sample("cpu", 50.0, sampled_monotonic=20.0),),
                    ),
                ),
            )
        )
        self.assertEqual(telemetry.series_snapshot("cpu").state, TemperatureState.VALID)

        telemetry.record_summary("cpu", cpu_card)
        self.assertEqual(
            telemetry.series_snapshot("cpu").state,
            TemperatureState.UNSUPPORTED,
            "one post-scan empty read must not confirm unsupported",
        )

        # Contrast: the record_summary recovery path does reset the budget.
        recovering = TemperatureTelemetry()
        for _ in range(19):
            recovering.record_summary("cpu", cpu_card)
        recovering.record_summary(
            "cpu",
            make_summary(
                "cpu",
                "CPU",
                capability=CapabilityState.SUPPORTED,
                temperatures=(make_temperature_sample("cpu", 50.0),),
            ),
        )
        for _ in range(19):
            recovering.record_summary("cpu", cpu_card)
        self.assertEqual(
            recovering.series_snapshot("cpu").state, TemperatureState.NO_DATA
        )

    def test_interleaved_failed_reads_do_not_break_empty_streak(self) -> None:
        """Failed reads neither increment nor reset the counter.

        Agent 1 F2 (first half) / Agent 2 finding 4: "consecutive" overstates
        the implemented semantics. No two empty reads are adjacent here, yet
        the limit is still reached.
        """
        telemetry = TemperatureTelemetry()
        empty = _empty_supported_card("cpu", "CPU")
        failed = make_summary(
            "cpu", "CPU", capability=CapabilityState.SUPPORTED, failed=True
        )
        for _ in range(19):
            telemetry.record_summary("cpu", failed)
            telemetry.record_summary("cpu", empty)
        self.assertEqual(
            telemetry.series_snapshot("cpu").state,
            TemperatureState.NO_DATA,
            "19 non-consecutive empty reads must stay in NO_DATA",
        )

        telemetry.record_summary("cpu", failed)
        telemetry.record_summary("cpu", empty)
        self.assertEqual(
            telemetry.series_snapshot("cpu").state,
            TemperatureState.UNSUPPORTED,
            "empty reads were never consecutive, yet the limit was reached",
        )

    def test_controller_capability_counter_independent_of_empty_reads(self) -> None:
        """The 2-read controller limit observes capability, not thermal samples.

        Resolves Agent 3 finding 2: the controller and telemetry counters are
        signal-separated by design (plan Phase 3 Step 2 / spec "Card-level
        capability remains unchanged"), not accidentally desynchronized.
        """

        class FakeController:
            UNSUPPORTED_CONFIRM_LIMIT = 2

        controller = FakeController()
        cpu_card = _empty_supported_card("cpu", "CPU")
        for _ in range(20):
            observe_capability(controller, "cpu", cpu_card)

        self.assertEqual(
            controller.__dict__["_capabilities"]["cpu"],
            CapabilityState.SUPPORTED,
        )
        self.assertEqual(
            controller.__dict__["_capability_counts"]["cpu"],
            0,
            "SUPPORTED capability resets the controller counter on every read",
        )


if __name__ == "__main__":
    unittest.main()

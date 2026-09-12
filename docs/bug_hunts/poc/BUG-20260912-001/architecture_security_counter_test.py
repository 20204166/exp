"""Architecture/Security Skeptic PoC for BUG-20260912-001.

This PoC examines the candidate from an architecture and security-boundary
perspective. It does not change app code or normal repo tests. It focuses on:

1. Data-flow symmetry: local and remote summaries share the same normalized
   `ResourceSummary` -> `TemperatureTelemetry.record_summary` path.
2. Node boundaries: telemetry is per-node, so the defect is isolated per node.
3. Fail-soft behaviour: only the SUPPORTED-but-empty thermal path fails to reach
   a terminal state; UNSUPPORTED and failed summaries terminate correctly.
4. Remote propagation: a remote node sending a SUPPORTED `ResourceSummary` with
   empty temperatures will keep the local Thermals page waiting indefinitely.
5. Regression/impact: any fix must not conflate card-level capability with
   thermal capability, and must recover when samples finally arrive.
"""

from __future__ import annotations

import unittest

from maintenance.cluster import (
    resource_summary_from_dict,
    resource_summary_to_dict,
)
from maintenance.components.temperature import (
    TemperatureState,
    TemperatureTelemetry,
)
from maintenance.models import CapabilityState
from maintenance.ui.thermals_page import ThermalsPage
from tests.support.models import make_summary
from tests.support.temperature import make_temperature_sample


class ArchitectureSecurityCounterTests(unittest.TestCase):
    """Independent architecture/security evidence for BUG-20260912-001."""

    def _make_page(self, capabilities: dict[str, CapabilityState]) -> ThermalsPage:
        """Build a ThermalsPage without a live Tk root."""
        page: ThermalsPage = object.__new__(ThermalsPage)
        page._capabilities = capabilities
        return page

    def test_red_test_confirms_supported_empty_stays_no_data(self) -> None:
        """Reproduce the failing invariant: SUPPORTED + empty temps -> NO_DATA."""
        telemetry = TemperatureTelemetry()
        cpu_card = make_summary(
            "cpu", "CPU", capability=CapabilityState.SUPPORTED, temperatures=()
        )

        for _ in range(1000):
            telemetry.record_summary("cpu", cpu_card)

        snapshot = telemetry.series_snapshot("cpu")
        self.assertEqual(snapshot.state, TemperatureState.NO_DATA)
        self.assertEqual(snapshot.current_celsius, None)
        self.assertEqual(len(snapshot.samples), 0)

    def test_remote_wire_propagates_indefinite_no_data(self) -> None:
        """Remote summaries decode into the same path and hit the same gap."""
        local_summary = make_summary(
            "cpu",
            "CPU",
            capability=CapabilityState.SUPPORTED,
            temperatures=(),
        )
        wire = resource_summary_to_dict(local_summary)
        decoded = resource_summary_from_dict(wire)

        self.assertEqual(decoded.capability, CapabilityState.SUPPORTED)
        self.assertEqual(decoded.temperatures, ())

        telemetry = TemperatureTelemetry()
        for _ in range(100):
            telemetry.record_summary("cpu", decoded)

        snapshot = telemetry.series_snapshot("cpu")
        self.assertEqual(snapshot.state, TemperatureState.NO_DATA)

    def test_fail_soft_paths_terminate(self) -> None:
        """UNSUPPORTED and failed summaries reach terminal UI states."""
        telemetry = TemperatureTelemetry()

        unsupported_cpu = make_summary(
            "cpu",
            "CPU",
            capability=CapabilityState.UNSUPPORTED,
            temperatures=(),
        )
        telemetry.record_summary("cpu", unsupported_cpu)
        cpu_snapshot = telemetry.series_snapshot("cpu")
        self.assertEqual(cpu_snapshot.state, TemperatureState.UNSUPPORTED)

        failed_gpu = make_summary(
            "gpu",
            "GPU",
            capability=CapabilityState.SUPPORTED,
            failed=True,
            temperatures=(),
        )
        telemetry.record_summary("gpu", failed_gpu)
        gpu_snapshot = telemetry.series_snapshot("gpu")
        self.assertEqual(gpu_snapshot.state, TemperatureState.ERROR)

        page = self._make_page(
            {
                "cpu": CapabilityState.UNSUPPORTED,
                "gpu": CapabilityState.SUPPORTED,
            }
        )
        # UNSUPPORTED removes the graph; ERROR keeps the graph but renders an
        # explicit unavailable message instead of an indefinite "waiting" one.
        self.assertFalse(page._should_show("cpu", TemperatureState.UNSUPPORTED))
        self.assertTrue(page._should_show("gpu", TemperatureState.ERROR))

    def test_supported_empty_does_not_fail_soft(self) -> None:
        """SUPPORTED + empty temps keeps the graph visible and waiting."""
        telemetry = TemperatureTelemetry()
        telemetry.record_summary(
            "cpu",
            make_summary(
                "cpu",
                "CPU",
                capability=CapabilityState.SUPPORTED,
                temperatures=(),
            ),
        )
        snapshot = telemetry.series_snapshot("cpu")
        self.assertEqual(snapshot.state, TemperatureState.NO_DATA)

        page = self._make_page({"cpu": CapabilityState.SUPPORTED})
        self.assertTrue(page._should_show("cpu", TemperatureState.NO_DATA))

    def test_telemetry_is_isolated_per_node(self) -> None:
        """Telemetry state is per-NodeContext; the bug does not leak across nodes."""
        local = TemperatureTelemetry()
        remote = TemperatureTelemetry()

        local.record_summary(
            "cpu",
            make_summary(
                "cpu",
                "CPU",
                capability=CapabilityState.SUPPORTED,
                temperatures=(make_temperature_sample("cpu", 55.0),),
            ),
        )
        for _ in range(10):
            remote.record_summary(
                "cpu",
                make_summary(
                    "cpu",
                    "CPU",
                    capability=CapabilityState.SUPPORTED,
                    temperatures=(),
                ),
            )

        self.assertEqual(local.series_snapshot("cpu").state, TemperatureState.VALID)
        self.assertEqual(remote.series_snapshot("cpu").state, TemperatureState.NO_DATA)

    def test_capability_is_card_level_not_thermal_level(self) -> None:
        """The offending field is card capability, not thermal capability."""
        cpu_card = make_summary(
            "cpu",
            "CPU",
            capability=CapabilityState.SUPPORTED,
            temperatures=(),
        )

        # The CPU card is reported as supported because CPU metrics exist,
        # even though no thermal samples are present. There is no separate
        # thermal capability field on ResourceSummary.
        self.assertEqual(cpu_card.capability, CapabilityState.SUPPORTED)
        self.assertEqual(cpu_card.temperatures, ())

    def test_late_samples_can_recover_from_unsupported_state(self) -> None:
        """If a fix transitions to UNSUPPORTED after empty reads, recovery works."""
        telemetry = TemperatureTelemetry()

        # Simulate an early terminal UNSUPPORTED classification.
        telemetry.record_summary(
            "cpu",
            make_summary(
                "cpu",
                "CPU",
                capability=CapabilityState.UNSUPPORTED,
                temperatures=(),
            ),
        )
        self.assertEqual(
            telemetry.series_snapshot("cpu").state, TemperatureState.UNSUPPORTED
        )

        # Later valid samples must transition back to VALID.
        telemetry.record_summary(
            "cpu",
            make_summary(
                "cpu",
                "CPU",
                capability=CapabilityState.SUPPORTED,
                temperatures=(make_temperature_sample("cpu", 60.0),),
            ),
        )
        self.assertEqual(telemetry.series_snapshot("cpu").state, TemperatureState.VALID)


if __name__ == "__main__":
    unittest.main()

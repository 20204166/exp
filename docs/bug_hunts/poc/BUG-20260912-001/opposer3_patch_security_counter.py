"""Opposing Agent 3 architecture/security counter-test for PATCH-20260912-001.

This test challenges state-integrity and lifecycle symmetry of the new bounded
empty-read transition. It does not change app code or normal repo tests.
"""

from __future__ import annotations

import unittest

from maintenance.components.temperature import (
    TemperaturePolicy,
    TemperatureSample,
    TemperatureScan,
    TemperatureState,
    TemperatureTelemetry,
)
from maintenance.models import CapabilityState
from maintenance.ui.thermals_page import ThermalsPage
from tests.support.models import make_summary
from tests.support.temperature import make_temperature_sample


class Opposer3PatchSecurityCounterTests(unittest.TestCase):
    """Architecture/security evidence scoped to the PATCH-20260912-001 change."""

    def test_record_scan_does_not_reset_empty_reads_counter(self) -> None:
        """record_scan sets state VALID but leaves empty_reads at the prior count."""
        telemetry = TemperatureTelemetry()
        empty_card = make_summary(
            "cpu", "CPU", capability=CapabilityState.SUPPORTED, temperatures=()
        )
        for _ in range(19):
            telemetry.record_summary("cpu", empty_card)
        self.assertEqual(
            telemetry.series_snapshot("cpu").state, TemperatureState.NO_DATA
        )

        scan = TemperatureScan(
            captured_at=None,  # type: ignore[arg-type]
            captured_monotonic=20.0,
            lines=("Temperature: 50°C",),
            samples_by_component=(
                ("cpu", (make_temperature_sample("cpu", 50.0, sampled_monotonic=20.0),)),
            ),
        )
        telemetry.record_scan(scan)

        snapshot = telemetry.series_snapshot("cpu")
        self.assertEqual(snapshot.state, TemperatureState.VALID)

        # The next empty read should immediately transition to UNSUPPORTED
        # because empty_reads was not reset by record_scan.
        telemetry.record_summary("cpu", empty_card)
        snapshot = telemetry.series_snapshot("cpu")
        self.assertEqual(
            snapshot.state,
            TemperatureState.UNSUPPORTED,
            "empty_reads must be reset when samples arrive via record_scan",
        )

    def test_record_summary_resets_empty_reads_counter(self) -> None:
        """record_summary with samples resets empty_reads to 0."""
        telemetry = TemperatureTelemetry()
        empty_card = make_summary(
            "cpu", "CPU", capability=CapabilityState.SUPPORTED, temperatures=()
        )
        for _ in range(19):
            telemetry.record_summary("cpu", empty_card)

        telemetry.record_summary(
            "cpu",
            make_summary(
                "cpu",
                "CPU",
                capability=CapabilityState.SUPPORTED,
                temperatures=(make_temperature_sample("cpu", 50.0),),
            ),
        )

        # After a valid sample, the empty-read budget should be fully restored.
        for _ in range(19):
            telemetry.record_summary("cpu", empty_card)
        self.assertEqual(
            telemetry.series_snapshot("cpu").state, TemperatureState.NO_DATA
        )

    def test_empty_scan_never_increments_empty_reads(self) -> None:
        """An empty TemperatureScan does not count toward the unsupported limit."""
        telemetry = TemperatureTelemetry()
        scan = TemperatureScan(
            captured_at=None,  # type: ignore[arg-type]
            captured_monotonic=1.0,
            lines=(),
            samples_by_component=(),
        )
        for _ in range(100):
            telemetry.record_scan(scan)

        snapshot = telemetry.series_snapshot("cpu")
        self.assertEqual(snapshot.state, TemperatureState.NO_DATA)
        self.assertEqual(snapshot.samples, ())

    def test_lifecycle_context_switch_preserves_empty_reads_per_node(self) -> None:
        """Each NodeContext owns its telemetry; counts do not leak across nodes."""
        local = TemperatureTelemetry()
        remote = TemperatureTelemetry()
        empty_card = make_summary(
            "cpu", "CPU", capability=CapabilityState.SUPPORTED, temperatures=()
        )

        for _ in range(25):
            remote.record_summary("cpu", empty_card)
        local.record_summary(
            "cpu",
            make_summary(
                "cpu",
                "CPU",
                capability=CapabilityState.SUPPORTED,
                temperatures=(make_temperature_sample("cpu", 55.0),),
            ),
        )

        self.assertEqual(local.series_snapshot("cpu").state, TemperatureState.VALID)
        self.assertEqual(
            remote.series_snapshot("cpu").state, TemperatureState.UNSUPPORTED
        )

    def test_telemetry_unsupported_hides_graph_while_card_capability_stays_supported(
        self,
    ) -> None:
        """Dashboard capability (unchanged SUPPORTED) diverges from telemetry state."""
        telemetry = TemperatureTelemetry()
        empty_card = make_summary(
            "cpu", "CPU", capability=CapabilityState.SUPPORTED, temperatures=()
        )
        for _ in range(20):
            telemetry.record_summary("cpu", empty_card)

        snapshot = telemetry.series_snapshot("cpu")
        self.assertEqual(snapshot.state, TemperatureState.UNSUPPORTED)

        page = object.__new__(ThermalsPage)
        page._capabilities = {"cpu": CapabilityState.SUPPORTED}
        # The dashboard card remains visible because resource.capability is still
        # SUPPORTED, but the thermals page hides the graph because telemetry
        # reached its independent unsupported threshold.
        self.assertFalse(page._should_show("cpu", snapshot.state))

    def test_zero_confirm_samples_transition_immediately(self) -> None:
        """A malformed policy with zero threshold transitions on first empty read."""
        telemetry = TemperatureTelemetry(
            policies={"cpu": TemperaturePolicy(unsupported_confirm_samples=0)}
        )
        empty_card = make_summary(
            "cpu", "CPU", capability=CapabilityState.SUPPORTED, temperatures=()
        )
        telemetry.record_summary("cpu", empty_card)

        self.assertEqual(
            telemetry.series_snapshot("cpu").state, TemperatureState.UNSUPPORTED
        )


if __name__ == "__main__":
    unittest.main()

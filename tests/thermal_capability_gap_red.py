"""Regression proof for a thermal series that never receives a sample."""

from __future__ import annotations

import unittest

from maintenance.components.temperature import TemperatureState, TemperatureTelemetry
from maintenance.models import CapabilityState
from tests.support.models import make_summary


class ThermalCapabilityGapTests(unittest.TestCase):
    def test_permanently_empty_temperature_samples_never_report_unsupported(
        self,
    ) -> None:
        telemetry = TemperatureTelemetry()
        cpu_card = make_summary(
            "cpu", "CPU", capability=CapabilityState.SUPPORTED, temperatures=()
        )
        for _ in range(1000):
            telemetry.record_summary("cpu", cpu_card)
        snapshot = telemetry.series_snapshot("cpu")
        self.assertNotEqual(
            snapshot.state,
            TemperatureState.NO_DATA,
            "thermal state must resolve to a terminal state, not remain no_data",
        )

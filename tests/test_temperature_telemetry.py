"""Focused tests for the shared thermal telemetry store."""

from __future__ import annotations

import unittest

from maintenance.components.temperature import (
    TemperaturePolicy,
    TemperatureSeriesSnapshot,
    TemperatureState,
    TemperatureTelemetry,
    parse_temperature_value,
)
from maintenance.models import CapabilityState
from tests.support.models import make_summary
from tests.support.temperature import make_temperature_sample


class TemperatureTelemetryTests(unittest.TestCase):
    def test_parse_temperature_value_handles_valid_and_malformed_text(self) -> None:
        self.assertEqual(parse_temperature_value("Temperature: 45°C"), 45.0)
        self.assertEqual(parse_temperature_value("Drive temperature: 38.5°C"), 38.5)
        self.assertIsNone(parse_temperature_value("Temperature: unavailable"))

    def test_record_summary_populates_current_and_history(self) -> None:
        telemetry = TemperatureTelemetry(
            policies={
                "cpu": TemperaturePolicy(history_limit=4, rapid_rise_celsius=None)
            }
        )
        summary = make_summary(
            "cpu",
            "CPU",
            value="45%",
            subtitle="running",
            percent=45.0,
            details=("Temperature: 45°C",),
            capability=CapabilityState.SUPPORTED,
            temperatures=(make_temperature_sample("cpu", 45.0),),
        )

        telemetry.record_summary("cpu", summary)
        snapshot = telemetry.series_snapshot("cpu", title="CPU Temperature")

        self.assertIsInstance(snapshot, TemperatureSeriesSnapshot)
        self.assertEqual(snapshot.state, TemperatureState.VALID)
        self.assertEqual(snapshot.current_celsius, 45.0)
        self.assertEqual(len(snapshot.samples), 1)
        self.assertEqual(snapshot.samples[0].value_celsius, 45.0)

    def test_history_is_bounded_and_oldest_sample_is_discarded(self) -> None:
        telemetry = TemperatureTelemetry(
            policies={
                "cpu": TemperaturePolicy(history_limit=3, rapid_rise_celsius=None)
            }
        )
        for index, value in enumerate((40.0, 41.0, 42.0, 43.0), start=1):
            telemetry.record_summary(
                "cpu",
                make_summary(
                    "cpu",
                    "CPU",
                    value="45%",
                    subtitle="running",
                    percent=45.0,
                    details=(f"Temperature: {value:.0f}°C",),
                    capability=CapabilityState.SUPPORTED,
                    temperatures=(
                        make_temperature_sample(
                            "cpu", value, sampled_monotonic=float(index)
                        ),
                    ),
                ),
            )

        history = telemetry.history("cpu")
        self.assertEqual(
            [sample.value_celsius for sample in history], [41.0, 42.0, 43.0]
        )

    def test_unsupported_summary_marks_state_without_fabricating_history(self) -> None:
        telemetry = TemperatureTelemetry()
        summary = make_summary(
            "battery",
            "Battery",
            value="No battery",
            subtitle="Not present",
            percent=None,
            details=("No temperature sensors detected.",),
            capability=CapabilityState.UNSUPPORTED,
        )

        telemetry.record_summary("battery", summary)
        snapshot = telemetry.series_snapshot("battery", title="Battery Temperature")

        self.assertEqual(snapshot.state, TemperatureState.UNSUPPORTED)
        self.assertEqual(snapshot.samples, ())
        self.assertIsNone(snapshot.current_celsius)

    def test_heat_event_is_bounded_and_recovers(self) -> None:
        telemetry = TemperatureTelemetry(
            policies={
                "cpu": TemperaturePolicy(
                    warning_celsius=90.0,
                    critical_celsius=95.0,
                    rapid_rise_celsius=None,
                    history_limit=8,
                )
            }
        )
        samples = (91.0, 92.0, 84.0)
        for index, value in enumerate(samples, start=1):
            telemetry.record_summary(
                "cpu",
                make_summary(
                    "cpu",
                    "CPU",
                    value="45%",
                    subtitle="running",
                    percent=45.0,
                    details=(f"Temperature: {value:.0f}°C",),
                    capability=CapabilityState.SUPPORTED,
                    temperatures=(
                        make_temperature_sample(
                            "cpu", value, sampled_monotonic=float(index)
                        ),
                    ),
                ),
            )

        events = telemetry.recent_events("cpu")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].peak_celsius, 92.0)
        self.assertGreaterEqual(len(events[0].samples), 3)


if __name__ == "__main__":
    unittest.main()

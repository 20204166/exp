"""Focused tests for the shared thermal telemetry store."""

from __future__ import annotations

import unittest

from maintenance.cluster import resource_summary_from_dict, resource_summary_to_dict
from maintenance.components.temperature import (
    TemperaturePolicy,
    TemperatureSeriesSnapshot,
    TemperatureState,
    TemperatureTelemetry,
    parse_temperature_value,
    temperature_sample_to_dict,
)
from maintenance.models import CapabilityState
from tests.support.models import make_summary
from tests.support.temperature import make_temperature_sample


class TemperatureTelemetryTests(unittest.TestCase):
    def test_temperature_value_uses_finite_local_range(self) -> None:
        from maintenance.components.temperature import is_valid_temperature_value

        for value in (0.1, 249.9):
            self.assertTrue(is_valid_temperature_value(value))
        for value in (
            0,
            250,
            -1,
            float("nan"),
            float("inf"),
            float("-inf"),
            True,
            "45",
        ):
            with self.subTest(value=value):
                self.assertFalse(is_valid_temperature_value(value))

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

    def test_invalid_decoded_sample_does_not_change_history_current_or_events(
        self,
    ) -> None:
        telemetry = TemperatureTelemetry()
        telemetry.record_summary(
            "cpu",
            make_summary(
                "cpu",
                "CPU",
                capability=CapabilityState.SUPPORTED,
                temperatures=(make_temperature_sample("cpu", 90.0),),
            ),
        )
        before = telemetry.series_snapshot("cpu")

        invalid_payload = resource_summary_to_dict(
            make_summary(
                "cpu",
                "CPU",
                capability=CapabilityState.SUPPORTED,
                temperatures=(make_temperature_sample("cpu", 90.0),),
            )
        )
        invalid_payload["temperatures"] = [
            {
                **temperature_sample_to_dict(make_temperature_sample("cpu", 90.0)),
                "value_celsius": float("nan"),
            }
        ]
        telemetry.record_summary("cpu", resource_summary_from_dict(invalid_payload))

        after = telemetry.series_snapshot("cpu")
        self.assertEqual(after.samples, before.samples)
        self.assertEqual(after.current_celsius, before.current_celsius)
        self.assertEqual(after.events, before.events)

    def test_record_returns_update_and_render_state_is_cached_data(self) -> None:
        telemetry = TemperatureTelemetry()
        update = telemetry.record_summary(
            "cpu",
            make_summary(
                "cpu",
                "CPU",
                capability=CapabilityState.SUPPORTED,
                temperatures=(make_temperature_sample("cpu", 45.0),),
            ),
        )

        state = telemetry.render_state(("cpu", "battery"))

        self.assertEqual(update.component, "cpu")
        self.assertEqual(update.snapshot.current_celsius, 45.0)
        cpu = state.series_for("cpu")
        battery = state.series_for("battery")
        assert cpu is not None
        assert battery is not None
        self.assertEqual(cpu.current_celsius, 45.0)
        self.assertEqual(battery.samples, ())
        self.assertEqual(state.events, ())

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

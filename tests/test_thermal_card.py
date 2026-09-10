"""Focused tests for the Battery/Thermal card behaviour."""

import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from maintenance.models import CapabilityState
from maintenance.scanner import SystemScanner
from tests.support.scanner import make_baseline_psutil, scanner_environment


def _temp(current: float | None, label: str = "sensor") -> SimpleNamespace:
    return SimpleNamespace(current=current, high=80.0, critical=100.0, label=label)


def _battery(percent: float, power_plugged: bool) -> SimpleNamespace:
    return SimpleNamespace(percent=percent, power_plugged=power_plugged)


def _thermal_psutil(sensors: Any) -> SimpleNamespace:
    return SimpleNamespace(sensors_temperatures=sensors)


class TemperatureLinesTests(unittest.TestCase):
    def test_temperature_lines_attribute_readings_by_category(self) -> None:
        fake = _thermal_psutil(
            lambda: {
                "coretemp": [_temp(45.0, "Core 0"), _temp(47.0, "Core 1")],
                "nvme": [_temp(38.0, "Composite")],
                "iwlwifi": [_temp(30.0, "wifi")],
            }
        )

        self.assertEqual(
            SystemScanner._temperature_lines(fake),
            ["CPU: 47°C", "NVMe: 38°C"],
        )

    def test_temperature_lines_report_gpu(self) -> None:
        fake = _thermal_psutil(lambda: {"amdgpu": [_temp(51.0, "edge")]})

        self.assertEqual(
            SystemScanner._temperature_lines(fake),
            ["GPU: 51°C"],
        )

    def test_temperature_lines_skip_nonsense_readings(self) -> None:
        fake = _thermal_psutil(
            lambda: {
                "coretemp": [
                    _temp(None),
                    _temp(0.0),
                    _temp(-5.0),
                    _temp(999.0),
                    _temp(42.0),
                ],
            }
        )

        self.assertEqual(
            SystemScanner._temperature_lines(fake),
            ["CPU: 42°C"],
        )

    def test_temperature_lines_return_empty_for_missing_sensors(self) -> None:
        fake = _thermal_psutil(dict)
        self.assertEqual(SystemScanner._temperature_lines(fake), [])

        def raises() -> Any:
            raise NotImplementedError("unsupported")

        self.assertEqual(SystemScanner._temperature_lines(_thermal_psutil(raises)), [])

    def test_temperature_lines_tolerate_malformed_entries(self) -> None:
        fake = _thermal_psutil(
            lambda: {
                "coretemp": None,
                "nvme": [_temp(38.0)],
            }
        )

        self.assertEqual(
            SystemScanner._temperature_lines(fake),
            ["NVMe: 38°C"],
        )

    def test_sensible_temperature_bounds(self) -> None:
        for value, expected in (
            (None, False),
            (0, False),
            (-1, False),
            (250, False),
            (249.9, True),
            (42.0, True),
        ):
            with self.subTest(value=value):
                self.assertEqual(SystemScanner._sensible_temperature(value), expected)


class BatteryCardTests(unittest.TestCase):
    def test_battery_card_preserved_for_laptop(self) -> None:
        scanner = SystemScanner(Path("Downloads"))

        summary = scanner._battery_resource(_battery(75.0, True), None, [])

        self.assertEqual(summary.value, "75%")
        self.assertEqual(summary.subtitle, "Charging")
        self.assertEqual(summary.percent, 75.0)
        self.assertEqual(
            summary.details,
            ("Charge: 75.0%", "Power: Charging"),
        )

    def test_battery_card_includes_temperature_lines(self) -> None:
        scanner = SystemScanner(Path("Downloads"))

        summary = scanner._battery_resource(
            _battery(75.0, True),
            None,
            ["CPU: 45°C", "NVMe: 38°C"],
        )

        self.assertEqual(
            summary.details,
            (
                "Charge: 75.0%",
                "Power: Charging",
                "CPU: 45°C",
                "NVMe: 38°C",
            ),
        )

    def test_no_battery_card_points_to_section_temperatures(self) -> None:
        scanner = SystemScanner(Path("Downloads"))

        summary = scanner._battery_resource(None, None, ["CPU: 45°C", "NVMe: 38°C"])

        self.assertEqual(summary.value, "No battery")
        self.assertEqual(summary.subtitle, "Not present on this system")
        self.assertIsNone(summary.percent)
        self.assertEqual(
            summary.details,
            ("CPU: 45°C", "NVMe: 38°C"),
        )

    def test_no_battery_without_sensors_is_clearly_marked(self) -> None:
        scanner = SystemScanner(Path("Downloads"))

        summary = scanner._battery_resource(None, None, [])

        self.assertEqual(summary.value, "No battery")
        self.assertEqual(summary.subtitle, "Not present on this system")
        self.assertEqual(
            summary.details,
            ("No temperature sensors detected.",),
        )

    def test_unreadable_battery_keeps_clear_unavailable_message(self) -> None:
        scanner = SystemScanner(Path("Downloads"))

        summary = scanner._battery_resource(
            None,
            PermissionError("denied"),
            ["CPU: 52°C"],
        )

        self.assertEqual(summary.value, "Unavailable")
        self.assertEqual(summary.subtitle, "Battery unavailable")
        self.assertEqual(
            summary.details,
            ("Battery information is unavailable.",),
        )

    def test_unreadable_battery_without_sensors_preserves_message(self) -> None:
        scanner = SystemScanner(Path("Downloads"))

        summary = scanner._battery_resource(None, PermissionError("denied"), [])

        self.assertEqual(summary.value, "Unavailable")
        self.assertEqual(
            summary.details,
            ("Battery information is unavailable.",),
        )

    def test_read_battery_distinguishes_absent_from_unreadable(self) -> None:
        absent = SimpleNamespace(sensors_battery=lambda: None)
        self.assertEqual(
            SystemScanner._read_battery(absent),
            (None, None),
        )

        def raises() -> Any:
            raise PermissionError("denied")

        unreadable = SimpleNamespace(sensors_battery=raises)
        battery, error = SystemScanner._read_battery(unreadable)
        self.assertIsNone(battery)
        self.assertIsInstance(error, PermissionError)

    def test_battery_capability_is_supported_when_present(self) -> None:
        scanner = SystemScanner(Path("Downloads"))
        summary = scanner._battery_resource(_battery(75.0, True), None, [])
        self.assertEqual(summary.capability, CapabilityState.SUPPORTED)

    def test_battery_capability_is_unsupported_when_absent(self) -> None:
        scanner = SystemScanner(Path("Downloads"))
        summary = scanner._battery_resource(None, None, ["CPU: 45°C"])
        self.assertEqual(summary.capability, CapabilityState.UNSUPPORTED)

    def test_battery_capability_requires_permission_when_denied(self) -> None:
        scanner = SystemScanner(Path("Downloads"))
        summary = scanner._battery_resource(
            None,
            PermissionError("denied"),
            ["CPU: 45°C"],
        )
        self.assertEqual(summary.capability, CapabilityState.PERMISSION_LIMITED)

    def test_battery_card_end_to_end_desktop(self) -> None:
        scanner = SystemScanner(Path("Downloads"))
        fake = make_baseline_psutil(
            swap_memory=lambda: SimpleNamespace(total=0, used=0, percent=0.0),
            net_io_counters=lambda: SimpleNamespace(bytes_sent=0, bytes_recv=0),
            sensors_battery=lambda: None,
            sensors_temperatures=lambda: {"coretemp": [_temp(45.0)]},
        )

        with scanner_environment(scanner, fake, trash_size=0):
            snapshot = scanner.scan_dashboard()

        battery_card = snapshot.get("battery")
        self.assertEqual(battery_card.value, "No battery")
        self.assertEqual(battery_card.subtitle, "Not present on this system")
        self.assertEqual(
            battery_card.details,
            ("CPU: 45°C",),
        )
        self.assertIn("Temperature: 45°C", snapshot.get("cpu").details)


class SectionTemperatureTests(unittest.TestCase):
    def _card_fake(self) -> SimpleNamespace:
        return make_baseline_psutil(
            swap_memory=lambda: SimpleNamespace(total=0, used=0, percent=0.0),
            net_io_counters=lambda: SimpleNamespace(bytes_sent=0, bytes_recv=0),
            sensors_battery=lambda: None,
            sensors_temperatures=lambda: {
                "coretemp": [_temp(45.0)],
                "amdgpu": [_temp(51.0)],
                "nvme": [_temp(38.0)],
            },
        )

    def test_section_temperatures_are_in_their_home_cards(self) -> None:
        scanner = SystemScanner(Path("Downloads"))
        fake = self._card_fake()

        with scanner_environment(scanner, fake, trash_size=0):
            snapshot = scanner.scan_dashboard()

        self.assertIn("Temperature: 45°C", snapshot.get("cpu").details)
        self.assertIn("Temperature: 51°C", snapshot.get("gpu").details)
        self.assertIn("Drive temperature: 38°C", snapshot.get("storage").details)
        self.assertEqual(snapshot.get("cpu").temperatures[0].value_celsius, 45.0)
        self.assertIn("CPU: 45°C", snapshot.get("battery").details)
        self.assertIn("GPU: 51°C", snapshot.get("battery").details)
        self.assertIn("NVMe: 38°C", snapshot.get("battery").details)

    def test_sections_omit_temperature_when_sensor_missing(self) -> None:
        scanner = SystemScanner(Path("Downloads"))
        fake = self._card_fake()
        fake.sensors_temperatures = dict

        with scanner_environment(scanner, fake, trash_size=0):
            snapshot = scanner.scan_dashboard()

        for line in snapshot.get("cpu").details:
            self.assertNotIn("Temperature", line)
        for line in snapshot.get("gpu").details:
            self.assertNotIn("Temperature", line)
        for line in snapshot.get("storage").details:
            self.assertNotIn("Drive temperature", line)

    def test_temperature_value_returns_category_suffix(self) -> None:
        lines = ["CPU: 45°C", "GPU: 51°C", "NVMe: 38°C"]

        self.assertEqual(SystemScanner._temperature_value(lines, "CPU"), "45°C")
        self.assertEqual(SystemScanner._temperature_value(lines, "GPU"), "51°C")
        self.assertEqual(SystemScanner._temperature_value(lines, "NVMe"), "38°C")
        self.assertIsNone(SystemScanner._temperature_value(lines, "Other"))

    def test_cached_temperature_lines_reuse_until_expiry(self) -> None:
        scanner = SystemScanner(Path("Downloads"))
        calls = {"count": 0}

        def sensors() -> Any:
            calls["count"] += 1
            return {"coretemp": [_temp(45.0)]}

        fake = SimpleNamespace(sensors_temperatures=sensors)

        with patch(
            "maintenance.scanner.time.monotonic",
            side_effect=[0.0, 1.0, 1.0, 4.9, 6.1, 7.1, 8.1],
        ):
            first = scanner._cached_temperature_lines(fake)
            second = scanner._cached_temperature_lines(fake)
            third = scanner._cached_temperature_lines(fake)

        self.assertEqual(first, ["CPU: 45°C"])
        self.assertEqual(second, ["CPU: 45°C"])
        self.assertEqual(third, ["CPU: 45°C"])
        self.assertEqual(calls["count"], 2)


if __name__ == "__main__":
    unittest.main()

"""Focused tests for the Battery/Thermal card behaviour."""

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from maintenance.models import CapabilityState
from maintenance.scanner import SystemScanner
from tests.support.scanner import (
    make_baseline_psutil,
    make_scanner,
    scanner_environment,
)


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

    def test_temperature_scan_degrades_gracefully_on_macos_style_psutil(self) -> None:
        fake = SimpleNamespace()  # macOS psutil exposes no sensors_temperatures.
        scan = SystemScanner._temperature_scan(fake)

        self.assertEqual(scan.lines, ())
        self.assertEqual(scan.samples_by_component, ())

    def test_temperature_sensor_support_matches_platform(self) -> None:
        self.assertTrue(SystemScanner._temperature_sensors_supported("Linux"))
        self.assertTrue(SystemScanner._temperature_sensors_supported("Darwin"))
        self.assertFalse(SystemScanner._temperature_sensors_supported("Windows"))
        self.assertFalse(SystemScanner._temperature_sensors_supported("FreeBSD"))

    def test_temperature_scan_uses_smc_on_macos(self) -> None:
        from maintenance.scanner_support import dashboard as dashboard_module

        captured: dict[str, object] = {}

        def fake_read(is_valid=None):
            captured["validator"] = is_valid
            return {
                "cpu": [("smc:TC0P", "TC0P", 61.5)],
                "battery": [("smc:TB0T", "TB0T", 32.25)],
            }

        with (
            patch.object(dashboard_module, "read_smc_temperatures", fake_read),
            patch("maintenance.scanner.platform.system", return_value="Darwin"),
        ):
            scan = SystemScanner._temperature_scan(_thermal_psutil(dict))

        self.assertEqual(
            {
                key: samples[0].value_celsius
                for key, samples in scan.samples_by_component
            },
            {"cpu": 61.5, "battery": 32.25},
        )
        self.assertEqual(scan.lines, ("CPU: 62°C", "Battery: 32°C"))
        self.assertIsNotNone(captured["validator"])

    def test_temperature_scan_skips_sensors_on_macos_and_windows(self) -> None:
        for system in ("Darwin", "Windows"):
            with self.subTest(system=system):
                probed: list[int] = []
                fake = _thermal_psutil(
                    lambda probed=probed: (
                        probed.append(1),
                        {"coretemp": [_temp(45.0)]},
                    )[1]
                )

                with patch("maintenance.scanner.platform.system", return_value=system):
                    scan = SystemScanner._temperature_scan(fake)

                self.assertEqual(scan.lines, ())
                self.assertEqual(scan.samples_by_component, ())
                self.assertEqual(probed, [], "sensors must never be probed off Linux")

    def test_temperature_scan_reads_sensors_on_linux(self) -> None:
        fake = _thermal_psutil(lambda: {"coretemp": [_temp(45.0)]})

        with patch("maintenance.scanner.platform.system", return_value="Linux"):
            scan = SystemScanner._temperature_scan(fake)

        self.assertEqual(scan.lines, ("CPU: 45°C",))
        self.assertEqual(dict(scan.samples_by_component)["cpu"][0].value_celsius, 45.0)

    def test_temperature_scan_degrades_when_sensors_return_none(self) -> None:
        scan = SystemScanner._temperature_scan(_thermal_psutil(lambda: None))

        self.assertEqual(scan.lines, ())
        self.assertEqual(scan.samples_by_component, ())

    def test_temperature_scan_degrades_when_sensors_return_non_dict(self) -> None:
        scan = SystemScanner._temperature_scan(_thermal_psutil(lambda: [1, 2]))

        self.assertEqual(scan.lines, ())
        self.assertEqual(scan.samples_by_component, ())

    def test_temperature_scan_skips_entry_without_current(self) -> None:
        fake = _thermal_psutil(
            lambda: {"coretemp": [SimpleNamespace(high=80.0, label="x")]}
        )

        scan = SystemScanner._temperature_scan(fake)

        self.assertEqual(scan.lines, ())
        self.assertEqual(scan.samples_by_component, ())

    def test_temperature_scan_groups_samples_by_component(self) -> None:
        fake = _thermal_psutil(
            lambda: {
                "coretemp": [_temp(45.0, "Core 0"), _temp(47.0, "Core 1")],
                "nvme": [_temp(38.0, "Composite")],
            }
        )

        scan = SystemScanner._temperature_scan(fake)

        self.assertEqual(scan.lines, ("CPU: 47°C", "NVMe: 38°C"))
        by_component = dict(scan.samples_by_component)
        self.assertEqual(tuple(by_component), ("cpu", "storage"))
        cpu = by_component["cpu"]
        self.assertEqual([sample.value_celsius for sample in cpu], [45.0, 47.0])
        self.assertEqual(cpu[0].sensor_id, "coretemp:0:Core 0")
        self.assertEqual(cpu[0].sensor_name, "Core 0")

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
        scanner = make_scanner()

        summary = scanner._battery_resource(_battery(75.0, True), None, [])

        self.assertEqual(summary.value, "75%")
        self.assertEqual(summary.subtitle, "Charging")
        self.assertEqual(summary.percent, 75.0)
        self.assertEqual(
            summary.details,
            ("Charge: 75.0%", "Power: Charging"),
        )

    def test_battery_card_includes_temperature_lines(self) -> None:
        scanner = make_scanner()

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
        scanner = make_scanner()

        summary = scanner._battery_resource(None, None, ["CPU: 45°C", "NVMe: 38°C"])

        self.assertEqual(summary.value, "No battery")
        self.assertEqual(summary.subtitle, "Not present on this system")
        self.assertIsNone(summary.percent)
        self.assertEqual(
            summary.details,
            ("CPU: 45°C", "NVMe: 38°C"),
        )

    def test_no_battery_without_sensors_is_clearly_marked(self) -> None:
        scanner = make_scanner()

        summary = scanner._battery_resource(None, None, [])

        self.assertEqual(summary.value, "No battery")
        self.assertEqual(summary.subtitle, "Not present on this system")
        self.assertEqual(
            summary.details,
            ("No temperature sensors detected.",),
        )

    def test_unreadable_battery_keeps_clear_unavailable_message(self) -> None:
        scanner = make_scanner()

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
        scanner = make_scanner()

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
        scanner = make_scanner()
        summary = scanner._battery_resource(_battery(75.0, True), None, [])
        self.assertEqual(summary.capability, CapabilityState.SUPPORTED)

    def test_battery_capability_is_unsupported_when_absent(self) -> None:
        scanner = make_scanner()
        summary = scanner._battery_resource(None, None, ["CPU: 45°C"])
        self.assertEqual(summary.capability, CapabilityState.UNSUPPORTED)

    def test_battery_capability_requires_permission_when_denied(self) -> None:
        scanner = make_scanner()
        summary = scanner._battery_resource(
            None,
            PermissionError("denied"),
            ["CPU: 45°C"],
        )
        self.assertEqual(summary.capability, CapabilityState.PERMISSION_LIMITED)

    def test_battery_card_end_to_end_desktop(self) -> None:
        scanner = make_scanner()
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
        scanner = make_scanner()
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
        scanner = make_scanner()
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
        scanner = make_scanner()
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

"""Focused tests for the restrained System Health summary."""

import unittest

from maintenance.health import (
    CONSECUTIVE_LIMIT,
    health_warnings,
)
from maintenance.models import DashboardSnapshot, ResourceSummary
from tests.support.models import make_snapshot, make_summary


def _summary(
    key: str,
    title: str,
    *,
    percent: float | None = None,
    details: tuple[str, ...] = (),
) -> ResourceSummary:
    return make_summary(
        key,
        title,
        value="value",
        subtitle="subtitle",
        percent=percent,
        details=details,
    )


def _snapshot(*resources: ResourceSummary) -> DashboardSnapshot:
    return make_snapshot(*resources)


def _full_snapshot(
    *,
    storage_percent: float | None = 50.0,
    memory_percent: float | None = 50.0,
    cpu_temp: str | None = "Temperature: 50°C",
    gpu_temp: str | None = "Temperature: 50°C",
    nvme_temp: str | None = "Drive temperature: 50°C",
    swap: str | None = "Swap: 1.00 GiB used of 4.00 GiB",
) -> DashboardSnapshot:
    cpu_details: tuple[str, ...] = ()
    if cpu_temp is not None:
        cpu_details = (cpu_temp,)
    gpu_details: tuple[str, ...] = ()
    if gpu_temp is not None:
        gpu_details = (gpu_temp,)
    storage_details: tuple[str, ...] = ()
    if nvme_temp is not None:
        storage_details = (nvme_temp,)
    memory_details: tuple[str, ...] = ()
    if swap is not None:
        memory_details = (swap,)
    return _snapshot(
        _summary("cpu", "CPU", details=cpu_details),
        _summary("memory", "Memory", percent=memory_percent, details=memory_details),
        _summary(
            "storage", "Storage", percent=storage_percent, details=storage_details
        ),
        _summary("gpu", "GPU", details=gpu_details),
    )


class HealthThresholdTests(unittest.TestCase):
    def test_healthy_snapshot_produces_no_warnings(self) -> None:
        self.assertEqual(health_warnings(_full_snapshot()), ())

    def test_storage_warns_at_capacity_boundary(self) -> None:
        self.assertEqual(
            health_warnings(_full_snapshot(storage_percent=89.9)),
            (),
        )
        self.assertEqual(
            health_warnings(_full_snapshot(storage_percent=90.0)),
            ("Storage is 90% full",),
        )

    def test_memory_warns_only_after_sustained_pressure(self) -> None:
        state: dict[str, int] = {}
        snapshot = _full_snapshot(memory_percent=95.0)
        self.assertEqual(health_warnings(snapshot, state), ())
        self.assertEqual(
            health_warnings(snapshot, state),
            ("Memory pressure is high (95%)",),
        )

    def test_temperature_warns_only_after_sustained_heat(self) -> None:
        state: dict[str, int] = {}
        snapshot = _full_snapshot(cpu_temp="Temperature: 95°C")
        self.assertEqual(health_warnings(snapshot, state), ())
        self.assertEqual(
            health_warnings(snapshot, state),
            ("CPU temperature is 95°C",),
        )

    def test_swap_warns_only_after_sustained_pressure(self) -> None:
        state: dict[str, int] = {}
        snapshot = _full_snapshot(swap="Swap: 3.50 GiB used of 4.00 GiB")
        self.assertEqual(health_warnings(snapshot, state), ())
        self.assertEqual(
            health_warnings(snapshot, state),
            ("Swap is 88% in use",),
        )


class HealthUnavailableDataTests(unittest.TestCase):
    def test_missing_temperatures_never_warn(self) -> None:
        snapshot = _full_snapshot(
            cpu_temp=None,
            gpu_temp=None,
            nvme_temp=None,
            storage_percent=95.0,
        )
        self.assertEqual(
            health_warnings(snapshot),
            ("Storage is 95% full",),
        )

    def test_no_swap_and_unavailable_swap_never_warn(self) -> None:
        for swap in (None, "Swap: none configured", "Swap: Unavailable"):
            with self.subTest(swap=swap):
                state: dict[str, int] = {}
                snapshot = _full_snapshot(swap=swap)
                self.assertEqual(health_warnings(snapshot, state), ())

    def test_missing_percent_fields_never_warn(self) -> None:
        snapshot = _full_snapshot(storage_percent=None, memory_percent=None)
        self.assertEqual(health_warnings(snapshot), ())

    def test_partial_snapshot_with_unknown_resources_is_neutral(self) -> None:
        snapshot = _snapshot(_summary("only", "Only"))
        self.assertEqual(health_warnings(snapshot), ())


class HealthSpikeTests(unittest.TestCase):
    def test_transient_spike_resets_after_recovery(self) -> None:
        state: dict[str, int] = {}
        hot = _full_snapshot(cpu_temp="Temperature: 95°C")
        cool = _full_snapshot(cpu_temp="Temperature: 45°C")

        self.assertEqual(health_warnings(hot, state), ())
        self.assertEqual(health_warnings(cool, state), ())
        self.assertEqual(state["temp_CPU"], 0)
        self.assertEqual(health_warnings(hot, state), ())
        self.assertEqual(
            health_warnings(hot, state),
            ("CPU temperature is 95°C",),
        )

    def test_consecutive_limit_constant_is_two(self) -> None:
        self.assertEqual(CONSECUTIVE_LIMIT, 2)


if __name__ == "__main__":
    unittest.main()

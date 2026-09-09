"""Agent 4 evidence probes for BUG-20260909-001.

This is an isolated reviewer probe. It does not alter application state or
invoke installers/network services; it exercises pure/local code paths only.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from maintenance.cluster import ClusterStore
from maintenance.components.scan_support import call_legacy_compatible
from maintenance.preferences import PreferencesStore
from maintenance.ui.thermal_graph import build_telemetry_graph_layout


def malformed_utf8_escapes_fallback() -> tuple[type[object], ...]:
    escaped: list[type[object]] = []
    with TemporaryDirectory() as directory:
        for store_type in (PreferencesStore, ClusterStore):
            path = Path(directory) / f"{store_type.__name__}.json"
            path.write_bytes(b"\xff")
            try:
                store_type(path).load()
            except UnicodeDecodeError:
                escaped.append(store_type)
    return tuple(escaped)


def threshold_coordinates_are_unclamped() -> bool:
    # The public geometry function is intentionally exercised with a threshold
    # above the sample range, matching the candidate's thermal concern.
    from datetime import datetime, timezone

    from maintenance.components.temperature import (
        TemperatureSample,
        TemperatureSeriesSnapshot,
        TemperatureState,
    )

    snapshot = TemperatureSeriesSnapshot(
        component="cpu",
        title="CPU",
        state=TemperatureState.VALID,
        current_celsius=105.0,
        minimum_celsius=100.0,
        maximum_celsius=105.0,
        warning_celsius=90.0,
        critical_celsius=95.0,
        samples=tuple(
            TemperatureSample(
                component="cpu",
                sensor_id=str(index),
                sensor_name="sensor",
                value_celsius=value,
                sampled_at=datetime.now(timezone.utc),
                sampled_monotonic=float(index),
            )
            for index, value in enumerate((100.0, 105.0))
        ),
        events=(),
    )
    layout = build_telemetry_graph_layout(snapshot, 200, 100)
    assert layout is not None
    assert layout.warning_y is not None and layout.critical_y is not None
    return layout.warning_y > layout.bottom and layout.critical_y > layout.bottom


def legacy_fallback_repeats_after_partial_primary() -> tuple[int, int]:
    calls = {"primary": 0, "fallback": 0}

    def primary() -> None:
        calls["primary"] += 1
        raise TypeError("unexpected keyword argument 'cancel_event'")

    def fallback() -> None:
        calls["fallback"] += 1

    call_legacy_compatible(primary, fallback)
    return calls["primary"], calls["fallback"]


def main() -> None:
    escaped = malformed_utf8_escapes_fallback()
    thresholds_outside = threshold_coordinates_are_unclamped()
    primary_calls, fallback_calls = legacy_fallback_repeats_after_partial_primary()
    print("invalid_utf8_escaped:", [item.__name__ for item in escaped])
    print("thermal_thresholds_outside:", thresholds_outside)
    print("legacy_calls:", primary_calls, fallback_calls)


if __name__ == "__main__":
    main()

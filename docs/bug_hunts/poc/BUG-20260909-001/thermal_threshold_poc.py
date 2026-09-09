"""Candidate PoC: threshold coordinates outside the sample plot range."""

from datetime import datetime, timezone

from maintenance.components.temperature import (
    TemperatureSample,
    TemperatureSeriesSnapshot,
    TemperatureState,
)
from maintenance.ui.thermal_graph import build_telemetry_graph_layout


def snapshot(values: tuple[float, ...]) -> TemperatureSeriesSnapshot:
    return TemperatureSeriesSnapshot(
        component="cpu",
        title="CPU",
        state=TemperatureState.VALID,
        current_celsius=values[-1],
        minimum_celsius=min(values),
        maximum_celsius=max(values),
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
            for index, value in enumerate(values)
        ),
        events=(),
    )


for values in ((40.0, 45.0), (100.0, 105.0)):
    layout = build_telemetry_graph_layout(snapshot(values), 200, 100)
    assert layout is not None
    print(values, layout.warning_y, layout.critical_y, layout.top, layout.bottom)
    warning_y = layout.warning_y
    critical_y = layout.critical_y
    assert warning_y is not None
    assert critical_y is not None
    assert layout.top <= warning_y <= layout.bottom
    assert layout.top <= critical_y <= layout.bottom

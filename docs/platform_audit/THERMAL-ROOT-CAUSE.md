# Thermal Pipeline Root Cause

## BugGuard Declaration

BugGuard mode: Mode B - standalone bug-hunt

Candidate: BUG-20260912-001, "Thermals page stuck at Waiting for samples on non-Linux"

Threshold: full B7, because this is a user-facing state that survived multiple
thermal-focused changes and crosses acquisition, normalized state, and UI boundaries.

## Boundary Trace

| Boundary | Current behavior | Evidence |
| --- | --- | --- |
| A. Sensor availability | Platform can attempt reads, but hardware absence is not distinguished from an empty cycle. | `maintenance/scanner_support/dashboard.py` sensor support and platform probes |
| B. Acquisition | Windows and SMC providers fail soft to empty scans. | `_temperature_scan_windows`; `read_smc_temperatures` |
| C. Raw shape | Provider lines/samples are normalized by the dashboard scanner. | `scanner_support/dashboard.py` |
| D. Classification | Empty provider output has no thermal-specific classification. | dashboard scan path |
| E. Validation | Valid samples are retained; empty output remains empty. | `maintenance/components/temperature.py` |
| F. `TemperatureSample` | Samples carry component, sensor identity, Celsius value, and timestamps. | `TemperatureSample` |
| G. `ResourceSummary.temperatures` | Card summaries carry a tuple of samples plus card capability. | `maintenance/models.py` |
| H. `record_summary` input | Local and remote summaries reach the same telemetry method. | `window_presentation.py`, `window_components.py` |
| I. History | Samples append to bounded history; empty summaries append nothing. | `TemperatureTelemetry.record_summary` |
| J. `TemperatureRenderState` | Snapshot reports `NO_DATA` when no sample and no explicit unsupported capability exist. | `temperature.py` |
| K. `ThermalsPage.render` | Each series is rendered from selected-node telemetry. | `maintenance/ui/thermals_page.py` |
| L. `_should_show` | It reads the card-level capability map. | `thermals_page.py` |
| M. Mini graph | `NO_DATA` remains a waiting placeholder. | `maintenance/ui/thermal_graph.py` |
| N. Graph draw | The waiting message is drawn instead of a terminal unsupported message. | `thermal_graph.py` |
| O. Remote decode | Remote summaries decode into the same `ResourceSummary` contract. | `maintenance/cluster.py` |
| P. Node selection | Selected context owns the capability map and telemetry; coordinator does not transform thermal state. | `window_node_runtime.py`, `coordinator.py` |

## Root-Cause Questions

The defect is capability-signal conflation. CPU, GPU, and Storage card capability
is `SUPPORTED` because those cards can report non-thermal metrics. The same
card-level map is the only capability signal consumed by the Thermals page.
Windows and Apple SMC acquisition can repeatedly return no samples while leaving
that card capability supported. `TemperatureTelemetry.record_summary` then has no
counter or bounded transition and repeatedly assigns `NO_DATA`.

The failure boundary is therefore the normalized thermal state transition, not
the platform acquisition fallback. Prior attempts changed acquisition, platform
gating, and graph behavior, but did not add a thermal-specific terminal state.
The smallest scoped fix belongs in `TemperatureTelemetry`; remote summaries
already use the same path. Empty-state wording is already truthful once the
unsupported state becomes reachable: `thermal_graph.py` uses
`Temperature not supported`.

## RED Evidence

`tests/test_thermal_capability_gap.py` was added before any production change.
Against the current tree it fails after 1000 empty supported summaries because
the snapshot remains `TemperatureState.NO_DATA`, proving the hypothesis rather
than merely checking a mocked platform branch.

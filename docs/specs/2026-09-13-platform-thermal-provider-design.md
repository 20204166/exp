# Platform Thermal Provider Extraction

## Goal

Make the Windows and macOS thermal acquisition paths independently testable and
extensible so the Windows thermal graphs can use an installed hardware-sensor
provider when the native ACPI WMI class returns no readings. Preserve the
existing Linux `psutil` path and its behavior.

## Current Boundary

`SystemScanner._temperature_scan` currently owns platform dispatch. Linux reads
`psutil.sensors_temperatures()` directly. Darwin delegates to the SMC/IOKit
reader, and Windows executes a PowerShell query for
`MSAcpi_ThermalZoneTemperature`. The Darwin and Windows implementations are
embedded in `maintenance/scanner_support/dashboard.py`, which makes provider
fallbacks difficult to test without constructing the scanner module boundary.

The scanner's component work already runs through the application coordinator;
the new component must not create its own thread, scheduler, or UI dependency.

## Design

Add `maintenance/components/temperature_platform.py` as the canonical owner for
non-Linux temperature acquisition. It will expose a narrow provider-facing API
that returns the existing immutable `TemperatureScan` model and accepts the
existing command runner seam for tests.

### Windows

Try providers in this order:

1. The existing PowerShell/WMI `MSAcpi_ThermalZoneTemperature` query.
2. LibreHardwareMonitor's WMI sensor namespace, when available.
3. OpenHardwareMonitor's WMI sensor namespace, when available.
4. An empty scan when no provider returns valid readings.

Each provider converts valid Celsius readings into `TemperatureSample` values.
Provider-specific WMI failures, missing namespaces, malformed JSON, and invalid
values are fail-soft. A failed provider must not prevent the next provider from
running. The implementation may log provider diagnostics, but it must not
fabricate readings or change the `TemperatureScan` schema solely for logging.

Hardware-monitor sensor records will be classified conservatively from their
provider metadata and names. CPU/package readings map to `cpu`, GPU readings to
`gpu`, storage/NVMe readings to `storage`, and battery readings to `battery`.
Unknown records are ignored rather than guessed into a component.

### macOS

Move the existing SMC/IOKit acquisition and its normalization into the new
component. Keep its current fail-closed behavior, validation predicate, sample
identity, and component mapping unchanged. No fallback provider is introduced
for macOS in this change; the extracted boundary leaves room for one later.

### Linux

Do not route Linux through the new component. The existing `psutil` branch,
driver mapping, value validation, ordering, cache behavior, and failure
handling remain in `DashboardMixin` unchanged except for any import cleanup
required by the extraction.

### Scanner Integration

`DashboardMixin._temperature_scan` will retain the OS dispatch and call the
platform component only for Darwin and Windows. The scanner remains the owner
of cache/TTL behavior and the application coordinator remains the owner of
background execution and cancellation. The platform component owns provider
ordering, command construction, parsing, normalization, and fail-soft logging.

## Testing

Add focused unit tests before implementation for:

- Windows ACPI success and Celsius conversion.
- Windows fallback when ACPI is empty or fails.
- LibreHardwareMonitor and OpenHardwareMonitor record parsing and component
  classification.
- Provider ordering and continuation after malformed or unavailable output.
- Invalid, missing, scalar, and multi-record JSON handling.
- macOS delegation preserving current SMC readings and failure behavior.
- Linux continuing to use `psutil` and never invoking platform providers.
- Existing telemetry/UI rendering behavior for valid, no-data, and unsupported
  states.

Tests will use the existing subprocess and SMC seams. No test will require
Windows, macOS, PowerShell, or a hardware-monitor service to be installed.

## Non-Goals

- No change to the Linux provider or its output contract.
- No new dependency on LibreHardwareMonitor or OpenHardwareMonitor.
- No bundled hardware-monitor service or installer.
- No UI redesign or change to thermal state semantics.
- No unmanaged worker thread in the platform component.
- No claim that Windows readings are available when the operating system and
  optional hardware provider expose none.

## Acceptance Criteria

1. The Windows ACPI provider remains the first attempt and still produces the
   same normalized readings for the existing case.
2. A Windows installation with either supported monitor service can produce
   graph samples when ACPI has no readings.
3. Missing providers and malformed output remain fail-soft and never block the
   dashboard scan.
4. macOS SMC output is behaviorally unchanged after extraction.
5. Linux thermal tests and the full configured validation suite remain green.
6. The new component has no Tkinter, scheduler, or coordinator dependency.

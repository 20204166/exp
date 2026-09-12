# Platform Thermal Provider Extraction

## Goal

Make the Windows and macOS thermal acquisition paths independently testable
and extensible so Windows thermal graphs can use an installed hardware-sensor
provider when the native ACPI WMI class returns no readings. Preserve the
existing Linux `psutil` path, the existing macOS SMC path, and the Phase 3
thermal-capability confirm-limit fix (`TemperatureTelemetry.record_summary`'s
`empty_reads` counter, `maintenance/components/temperature.py:202-223`)
unchanged — this work only changes what a scan *acquires*, never how
`TemperatureTelemetry` interprets an empty result.

## Current Boundary (verified against real source, not the prior draft's
assumption)

`DashboardMixin._temperature_scan` (`maintenance/scanner_support/dashboard.py:1093-1109`)
owns platform dispatch by `platform.system()`. The three branches are **not
equally extracted today**:

- **Linux** (`:1106-1158`) calls `psutil.sensors_temperatures()` directly and
  does all driver-mapping/validation inline in `DashboardMixin`. Untouched by
  this change.
- **Darwin** (`_temperature_scan_smc`, `:1160-1197`) already delegates the
  hard part — SMC key iteration, IOKit/ctypes calls, per-key validation — to
  `maintenance/scanner_support/smc.py::read_smc_temperatures`, which has its
  own test file (`tests/test_smc.py`) and needs no scanner construction to
  test. **Only** the wrapping of its `dict[str, list[tuple[id, name, celsius]]]`
  result into a `TemperatureScan` (grouping, line formatting) still lives in
  `dashboard.py`.
- **Windows** (`_temperature_scan_windows`, `:1199-1261`) is the one branch
  with no extraction at all: PowerShell command text, `run_json_command` call,
  tenths-of-Kelvin conversion, and zone-to-sample mapping are all inline in
  `DashboardMixin`, reachable only by testing through `dashboard.py` (as
  `tests/test_thermal_card.py:150-188` already does, via
  `test_temperature_scan_reads_windows_acpi_zone` /
  `test_temperature_scan_handles_multiple_windows_acpi_zones`).

So the real gap this change closes is **Windows provider extraction and
fallback**, plus finishing macOS's extraction so both non-Linux platforms
share one shape. It is not "both platforms currently unextracted," as the
initial draft implied.

The scanner's component work already runs through the application
coordinator; the new module must not create its own thread, scheduler, or UI
dependency.

## Design

### Module placement — corrected from the initial draft

Add **`maintenance/scanner_support/temperature_platform.py`**, not
`maintenance/components/temperature_platform.py`. This repo's existing split
is consistent and enforced by test:
`maintenance/scanner_support/` holds platform-specific *acquisition* (this is
exactly what `smc.py` and `scanner_support/gpu.py` already are — subprocess
and ctypes calls, no Tk, no coordinator), while `maintenance/components/`
holds normalized models and cross-platform business logic (`temperature.py`'s
`TemperatureTelemetry`, `components/gpu.py`'s message helpers) and has a
**publicly declared, test-enforced surface** — `tests/test_package_structure.py`
asserts `components.__all__` matches its re-exports and checks specific
`import maintenance.components...` invariants. Acquisition code placed under
`components/` would need to justify a new public name there for no reason;
`scanner_support/` has no such surface (its own module docstring says
explicitly: "without creating a second public API") and is the lower-friction,
pattern-consistent home.

### Provider interface (shared shape, reusing the SMC convention)

Every provider — ACPI, LibreHardwareMonitor, OpenHardwareMonitor — returns the
same raw shape `read_smc_temperatures` already established, so the wrapping
into `TemperatureSample`/`TemperatureScan` is written once and shared, not
duplicated per provider:

```python
# maintenance/scanner_support/temperature_platform.py

RawReadings = dict[str, list[tuple[str, str, float]]]  # component -> [(sensor_id, sensor_name, celsius), ...]

def windows_temperature_scan(
    *,
    runner: CommandRunner | None = None,
) -> TemperatureScan: ...

def macos_temperature_scan(
    *,
    is_valid: Callable[[object], bool] = is_valid_temperature_value,
) -> TemperatureScan: ...
```

`windows_temperature_scan` and `macos_temperature_scan` are the only two names
`dashboard.py` imports. Everything else (individual provider functions,
classification tables) is a module-private implementation detail, matching
how `dashboard.py` today only calls `read_smc_temperatures`, not SMC's
internal key-reading helpers.

### Windows

Try providers **in this fixed order, stopping at the first one that returns
at least one valid sample** — this is a fallback chain, not a merge. Running
all three providers every scan when the first already works would triple the
PowerShell process cost (each `Get-CimInstance` invocation is a real,
non-trivial subprocess spawn) for no benefit; the TTL cache
(`TEMPERATURE_REFRESH_SECONDS`, see Scanner Integration below) already bounds
*how often* this runs, but not how many subprocesses one run costs:

1. **ACPI** (existing): `Get-CimInstance -Namespace root/WMI -ClassName
   MSAcpi_ThermalZoneTemperature` — unchanged query, moved verbatim from
   `_temperature_scan_windows`.
2. **LibreHardwareMonitor**, when its WMI namespace responds.
3. **OpenHardwareMonitor**, when its WMI namespace responds (legacy successor
   relationship: try the actively maintained project first).
4. Empty `RawReadings` (`{}`) when no provider returns a sample — the caller
   converts this to the existing empty `TemperatureScan`, identical to
   today's fail-closed behavior.

**Open item, flagged rather than fabricated:** this repo has no existing
integration with LibreHardwareMonitor or OpenHardwareMonitor, and no Windows
machine was used to verify a WMI query against either. The commonly
documented namespaces are `root\LibreHardwareMonitor` (class `Sensor`, fields
including `Name`, `SensorType`, `Value`, `Identifier`/`Parent`) and the legacy
`root\OpenHardwareMonitor` (same `Sensor` shape). **Do not treat these as
verified** — confirm the exact namespace, class, and field names against the
installed provider's own documentation or a native Windows machine before
writing the query string, at implementation time, per this repo's own
established rule against treating unverified platform behavior as proven
(`docs/plans/2026-09-12-cross-platform-compat-audit.md`'s native-verification
requirement applies here too, not just to the audit pass). If neither can be
confirmed before implementation starts, land steps 1 and 4 (ACPI fallback to
empty) first as an independent, immediately shippable slice, and treat steps
2–3 as a follow-up once a real provider install is available to test against.

Each provider function:

- Builds its own PowerShell command string (`Select-Object` + `ConvertTo-Json`
  to reuse `run_json_command`'s existing JSON-decoding seam, exactly as ACPI
  and the GPU probes already do).
- Calls `run_json_command(..., runner=runner, empty_stdout_fallback="[]",
  creationflags=...)` — the same `maintenance/external_commands.py` seam every
  other Windows probe uses; no new subprocess-invocation path is introduced.
- Treats a non-`None` error, a non-list/dict payload, or an empty decoded
  result as "provider unavailable" and returns `{}` (empty `RawReadings`) —
  never raises. A missing WMI namespace and a malformed JSON payload are
  indistinguishable to the caller and handled identically: move to the next
  provider.
- Filters every numeric reading through `is_valid_temperature_value` before
  accepting it (same 0–250°C plausibility bound the ACPI and SMC paths
  already enforce) — a provider returning a sentinel value (e.g. `-1`, `0`,
  or an implausible `4500`) is treated as no reading for that sensor, not
  clamped or corrected.

**Sensor classification** (LibreHardwareMonitor/OpenHardwareMonitor only —
ACPI is always `cpu`, matching today's behavior): classify conservatively
from the provider's own `SensorType` field plus a name-substring check,
mirroring the existing driver-keyword approach in `CPU_TEMP_DRIVERS` /
`GPU_TEMP_DRIVERS` / `NVME_TEMP_DRIVERS` (`dashboard.py`) rather than
inventing a new classification style:

| `SensorType` | Name contains | Component |
|---|---|---|
| `Temperature` | `cpu`, `core`, `package` | `cpu` |
| `Temperature` | `gpu` | `gpu` |
| `Temperature` | `nvme`, `ssd`, `hdd`, `disk` | `storage` |
| `Temperature` | `battery` | `battery` |
| anything else | — | ignored |

A record matching none of the name patterns, or whose `SensorType` isn't
`Temperature` (voltage/fan/power/load sensors are present in the same WMI
class and must not be misread as temperatures), is dropped rather than
guessed into a component — matching the existing "unknown records are
ignored" rule, made concrete instead of left abstract. If a future finding
shows real-world sensor names this table misses, that is a follow-up fixture
addition, not a reason to loosen the match to "anything with a numeric
value."

### macOS

Finish the extraction already mostly done: move `_temperature_scan_smc`'s
9-line wrapping loop (`dashboard.py:1160-1197` — group `read_smc_temperatures`'s
result into `TemperatureSample`s, build the summary line) into
`macos_temperature_scan` in the new module, calling the existing, unmoved
`read_smc_temperatures` from `smc.py`. `smc.py` itself does not move — it is
already the correctly-scoped acquisition module and already independently
tested. Keep current fail-closed behavior, validation predicate
(`is_valid_temperature_value`, reused rather than `_sensible_temperature`
duplicated — confirm at implementation time whether `_sensible_temperature`
in `dashboard.py` is identical to `is_valid_temperature_value` in
`temperature.py` or has diverged; if identical, this is also a chance to stop
passing a redundant `is_valid=` callable through `read_smc_temperatures` and
default it there instead), sample identity, and component mapping unchanged.
No fallback provider is introduced for macOS in this change; the extracted
boundary leaves room for one later (e.g. a future `powermetrics`-based
Apple Silicon path, out of scope here).

### Linux

Do not route Linux through the new module. The existing `psutil` branch,
driver mapping, value validation, ordering, cache behavior, and failure
handling remain in `DashboardMixin` unchanged except for any import cleanup
required by the extraction (e.g. `TemperatureSample`/`is_valid_temperature_value`
imports that become unused in `dashboard.py` once Darwin/Windows move out).

### Scanner Integration

`DashboardMixin._temperature_scan` retains the OS dispatch and calls the new
module only for Darwin and Windows:

```python
if system == "Darwin":
    return temperature_platform.macos_temperature_scan()
if system == "Windows":
    return temperature_platform.windows_temperature_scan(
        runner=scanner_module.subprocess.run,
    )
```

The scanner remains the sole owner of cache/TTL behavior
(`_cached_temperature_scan` / `TEMPERATURE_REFRESH_SECONDS`, unchanged) and
the application coordinator remains the owner of background execution and
cancellation. The platform module owns provider ordering, command
construction, parsing, normalization, and fail-soft logging. This means a
Windows machine with a slow or hung hardware-monitor WMI query pays that cost
once per `TEMPERATURE_REFRESH_SECONDS` window, same as ACPI does today, not
per UI refresh tick — no new polling cadence is introduced.

## Testing

Add focused `unittest.TestCase` tests, written before implementation, in a
new `tests/test_temperature_platform.py` (the existing Windows-ACPI cases in
`tests/test_thermal_card.py:150-188` move here once the code they exercise
moves; leaving them in `test_thermal_card.py` after the extraction would test
through a `dashboard.py` indirection that no longer does the real work):

- Windows ACPI success and Celsius conversion (migrated from
  `tests/test_thermal_card.py:150-169`).
- Windows ACPI multi-zone handling (migrated from
  `tests/test_thermal_card.py:170-188`).
- Windows fallback to LibreHardwareMonitor when ACPI's `run_json_command`
  returns an error or an empty/`[]` payload.
- Windows fallback to OpenHardwareMonitor when both ACPI and
  LibreHardwareMonitor are unavailable.
- Windows returns an empty scan (not an exception) when all three providers
  are unavailable.
- LibreHardwareMonitor and OpenHardwareMonitor record parsing: one test per
  classification row in the table above, plus one asserting an unmatched
  `SensorType`/name combination is dropped rather than guessed.
- Provider ordering: a fixture returning valid ACPI data must never invoke
  the LibreHardwareMonitor/OpenHardwareMonitor runner at all (assert the
  fallback `runner` mock has zero calls) — this is the perf-cost guard from
  the Scanner Integration section, made into a test rather than left as
  prose.
- Invalid, missing, scalar, and multi-record JSON handling per provider
  (reuse the malformed-payload fixtures `tests/test_thermal_card.py` already
  has for ACPI as a template).
- macOS delegation: `macos_temperature_scan()` produces byte-identical
  `TemperatureScan` output to today's `_temperature_scan_smc` for the same
  `read_smc_temperatures` fixture (a characterization test — confirm it fails
  if the grouping/line-formatting logic is altered, before trusting it as a
  regression guard).
- Linux continues to use `psutil` directly and never imports or calls
  anything from `temperature_platform.py` — assert via
  `sys.modules`/patch-not-called, not just by inspection.
- End-to-end: feed a `windows_temperature_scan()` / `macos_temperature_scan()`
  result through the real `TemperatureTelemetry.record_summary` and confirm
  the Phase 3 confirm-limit behavior (`empty_reads`) is unaffected — this
  change must not require touching `temperature.py` at all; a test that fails
  here means the boundary wasn't kept clean.

Tests use the existing subprocess (`run_json_command`'s `runner=`) and SMC
(`read_smc_temperatures`'s `is_valid=`) seams already proven in
`tests/test_thermal_card.py` and `tests/test_smc.py`. No test requires
Windows, macOS, PowerShell, or a hardware-monitor service to be installed.

## Non-Goals

- No change to the Linux provider or its output contract.
- No new runtime dependency on LibreHardwareMonitor or OpenHardwareMonitor
  (they are optional, user-installed Windows services probed via WMI, not
  Python packages).
- No bundled hardware-monitor service or installer.
- No UI redesign or change to thermal state semantics.
- No change to `TemperatureTelemetry`, `TemperaturePolicy`, or the Phase 3
  `empty_reads` confirm-limit fix — this change only affects what a
  `TemperatureScan` contains, not how `record_summary` interprets one.
- No unmanaged worker thread in the platform module.
- No claim that Windows readings are available when the operating system and
  every optional hardware provider expose none.
- No new public name added to `maintenance.components.__all__` — the new
  module lives in `scanner_support` specifically to avoid touching that
  test-enforced surface.

## Open Questions / Risks

- LibreHardwareMonitor's and OpenHardwareMonitor's exact WMI namespace/class/
  field names are not verified in this repo and must be confirmed (vendor
  docs or a native Windows machine with the service installed) before their
  provider functions are written — see the Windows section's "Open item"
  above. If no native verification is possible before this ships, land only
  the ACPI-extraction slice (provider 1 + empty fallback) and track 2–3 as a
  follow-up.
- `_sensible_temperature` (`dashboard.py`) vs. `is_valid_temperature_value`
  (`temperature.py`) may already be redundant; confirm during implementation
  rather than assuming, and consolidate to one predicate if so
  (`consolidating-responsibilities`-style check, not a new invention).

## Acceptance Criteria

1. The Windows ACPI provider remains the first attempt and still produces the
   same normalized readings for the existing case, verified by the migrated
   `tests/test_thermal_card.py` cases now passing unchanged from
   `tests/test_temperature_platform.py`.
2. A Windows installation with either supported monitor service can produce
   graph samples when ACPI has no readings — provable in tests via fixtures;
   native confirmation tracked as an Open Question, not assumed.
3. Missing providers and malformed output remain fail-soft and never block
   the dashboard scan; a fixture that fails ACPI, LibreHardwareMonitor, and
   OpenHardwareMonitor all at once still returns a valid (empty)
   `TemperatureScan`, not an exception.
4. macOS SMC output is behaviorally unchanged after extraction (byte-identical
   `TemperatureScan` for the same `read_smc_temperatures` fixture).
5. When ACPI already returns valid samples, no LibreHardwareMonitor/
   OpenHardwareMonitor subprocess is invoked (asserted by mock call count,
   not just implied by prose).
6. Linux thermal tests and the full configured validation suite
   (`python -m unittest discover -s tests -q`, `ruff check .`,
   `ruff format --check .`, `pyright`, `mypy --ignore-missing-imports .`)
   remain green.
7. The new module has no Tkinter, scheduler, or coordinator dependency, and
   adds no new name to `maintenance.components.__all__`.

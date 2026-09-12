# Platform Thermal Provider Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract Darwin and Windows thermal acquisition and add Windows hardware-monitor fallbacks while leaving Linux acquisition unchanged.

**Architecture:** `maintenance/scanner_support/temperature_platform.py` owns non-Linux provider commands, parsing, classification, and conversion to the existing `TemperatureScan`. `DashboardMixin` keeps OS dispatch, Linux acquisition, caching, and scanner seams; it delegates only Darwin and Windows. No new thread or UI dependency is introduced.

**Tech Stack:** Python, Tk-free scanner support, PowerShell/WMI, ctypes/IOKit SMC, `unittest`, existing `run_json_command` and subprocess seams.

---

## File Map

- Create: `maintenance/scanner_support/temperature_platform.py` for Windows provider fallback, macOS scan wrapping, and shared normalized scan construction.
- Create: `tests/test_temperature_platform.py` for provider ordering, parsing, conversion, and macOS characterization.
- Modify: `maintenance/scanner_support/dashboard.py:1093-1285` to delegate Darwin/Windows and retain Linux unchanged.
- Modify: `tests/test_thermal_card.py:150-188` to remove tests moved to the platform module while retaining scanner dispatch coverage.
- Modify: `maintenance/scanner_support/smc.py` only if implementation confirms its validator default can be safely consolidated without changing behavior.
- Modify: `docs/platform_audit/PLATFORM-MATRIX.md` only after native or fixture-backed behavior is validated, without claiming native Windows verification.

## Task 1: Confirm Provider Contracts

**Files:**
- Read: `maintenance/scanner_support/smc.py`
- Read: `maintenance/external_commands.py`
- Read: `maintenance/scanner_support/gpu.py`
- Test: `tests/test_smc.py`, `tests/test_thermal_card.py`

- [ ] **Step 1: Record the existing contracts before editing.** Confirm SMC tuple shape, command-runner arguments, Windows creation flags, and `TemperatureScan` timestamp construction.
- [ ] **Step 2: Confirm provider metadata fields from authoritative documentation or available fixtures.** Use `Sensor`, `SensorType`, `Name`, `Value`, and `Identifier`/`Parent` only if the provider contract is verified. If verification is unavailable, implement ACPI extraction plus empty fallback and leave optional providers as a separately tracked follow-up rather than inventing a query.
- [ ] **Step 3: Commit the contract decision.**

```bash
git add docs/plans/2026-09-13-platform-thermal-provider-extraction.md
git commit -m "docs: plan platform thermal provider extraction"
```

## Task 2: Add Failing Platform Tests

**Files:**
- Create: `tests/test_temperature_platform.py`
- Read: `tests/test_thermal_card.py:150-188`

- [ ] **Step 1: Add tests for ACPI conversion and multiple zones using a runner fixture that returns JSON.** Assert the exact Celsius values, `cpu` component, sensor IDs, and summary line.
- [ ] **Step 2: Add fallback tests.** Return an empty/error ACPI response, then valid LibreHardwareMonitor/OpenHardwareMonitor JSON; assert the first valid provider wins and later providers are not called.
- [ ] **Step 3: Add classification tests for CPU, GPU, storage, battery, and ignored non-temperature/unmatched records.** Assert invalid values are dropped.
- [ ] **Step 4: Add all-provider failure and malformed-payload tests.** Assert an empty `TemperatureScan`, never an exception.
- [ ] **Step 5: Add macOS characterization tests using the existing SMC seam and a Linux-dispatch test proving platform support is never called for Linux.**
- [ ] **Step 6: Run the new tests and verify they fail for missing module/API behavior, not test syntax.**

```bash
.venv/bin/python -m unittest tests.test_temperature_platform -v
```

Expected result: FAIL because `temperature_platform.py` and its public scan functions do not yet exist.

## Task 3: Implement Platform Module Skeleton and Shared Conversion

**Files:**
- Create: `maintenance/scanner_support/temperature_platform.py`

- [ ] **Step 1: Create the module with imports, `RawReadings`, provider command-runner typing, and the two public function signatures from the approved spec.** Do not import Tkinter, schedulers, coordinators, or `SystemScanner`.
- [ ] **Step 2: Implement one shared converter from `RawReadings` to `TemperatureScan`.** Create timestamps once, preserve provider order and sensor tuple order, format component labels consistently, and filter through `is_valid_temperature_value` before constructing samples.
- [ ] **Step 3: Run the focused tests to confirm the shared conversion tests pass while provider tests remain red.**

```bash
.venv/bin/python -m unittest tests.test_temperature_platform -v
```

Expected result: only provider acquisition tests remain failing.

## Task 4: Implement Windows Providers

**Files:**
- Modify: `maintenance/scanner_support/temperature_platform.py`

- [ ] **Step 1: Move the existing ACPI PowerShell command verbatim into a private provider function.** Reuse `run_json_command`, `runner=`, `empty_stdout_fallback="[]"`, and Windows `CREATE_NO_WINDOW` handling.
- [ ] **Step 2: Implement verified LibreHardwareMonitor parsing.** Query only `SensorType=Temperature`, classify with the approved conservative name table, and return normalized raw readings.
- [ ] **Step 3: Implement verified OpenHardwareMonitor parsing with the same parser contract and independent namespace.
- [ ] **Step 4: Implement fixed-order fallback that stops after the first non-empty valid raw result.** Provider errors, malformed payloads, empty payloads, and invalid values return `{}` and continue.
- [ ] **Step 5: Run focused Windows tests and confirm all pass.**

```bash
.venv/bin/python -m unittest tests.test_temperature_platform -v
```

## Task 5: Implement macOS Extraction

**Files:**
- Modify: `maintenance/scanner_support/temperature_platform.py`

- [ ] **Step 1: Move only the existing SMC result-wrapping loop into `macos_temperature_scan`.** Keep `read_smc_temperatures` in `scanner_support/smc.py`.
- [ ] **Step 2: Preserve validator, timestamps, component mapping, sensor IDs, line formatting, and empty/failure behavior exactly.**
- [ ] **Step 3: Run SMC and platform characterization tests.**

```bash
.venv/bin/python -m unittest tests.test_smc tests.test_temperature_platform -v
```

## Task 6: Integrate Without Touching Linux

**Files:**
- Modify: `maintenance/scanner_support/dashboard.py:1093-1285`
- Modify: `tests/test_thermal_card.py:150-188`

- [ ] **Step 1: Import the platform module and replace only Darwin/Windows branch bodies with calls to `macos_temperature_scan()` and `windows_temperature_scan(runner=scanner_module.subprocess.run)`.**
- [ ] **Step 2: Leave the Linux sensor query, driver mapping, ordering, cache, and validation path unchanged.**
- [ ] **Step 3: Remove duplicated Windows/macOS helpers and unused imports only after tests pass.**
- [ ] **Step 4: Move ACPI tests to the new module and retain one scanner dispatch test.**
- [ ] **Step 5: Run thermal, dashboard, and telemetry tests.**

```bash
.venv/bin/python -m unittest tests.test_temperature_platform tests.test_thermal_card tests.test_telemetry_graph tests.test_thermal_node_isolation -v
```

## Task 7: Validate Boundaries and Static Quality

**Files:**
- Read: `maintenance/scanner_support/temperature_platform.py`
- Read: `maintenance/scanner_support/dashboard.py`

- [ ] **Step 1: Search for remaining duplicated Windows/macOS provider logic and classify every match as implementation, caller, or test fixture.**
- [ ] **Step 2: Confirm the platform module imports no Tkinter, scheduler, coordinator, or `maintenance.components.__all__` surface.**
- [ ] **Step 3: Run the complete configured validation suite and fix only regressions introduced by this change.**

```bash
.venv/bin/python -m unittest discover -s tests -q
ruff check .
ruff format --check .
pyright
mypy --ignore-missing-imports .
```

- [ ] **Step 4: Run compile and package checks.**

```bash
.venv/bin/python -m compileall -q maintenance tests
./install/build.sh
wheel=$(.venv/bin/python -c 'from pathlib import Path; print(max(Path("dist").glob("system_analyzer-*.whl"), key=lambda p: p.stat().st_mtime))')
.venv/bin/python -m maintenance._release verify-wheel "$wheel"
```

## Task 8: Document and Commit

**Files:**
- Modify: `docs/platform_audit/PLATFORM-MATRIX.md` only if the implementation changes documented capability wording.
- Modify: `docs/specs/2026-09-13-platform-thermal-provider-design.md` only to record verified provider facts.

- [ ] **Step 1: Document that Windows fallbacks are optional-provider based and native verification status remains honest.**
- [ ] **Step 2: Review the complete diff, excluding pre-existing `.claude/`, and check for secrets or unrelated changes.**
- [ ] **Step 3: Commit implementation, tests, and documentation as bounded commits.**

```bash
git diff --check
git diff --stat
```

## Task 9: Final Evidence

- [ ] **Step 1: Confirm Linux behavior with the existing Linux thermal fixtures and the full test suite.**
- [ ] **Step 2: Confirm the wheel contains the new scanner-support module and reports the expected version.**
- [ ] **Step 3: Record native Windows testing as verified only if a real Windows run produces samples; otherwise record the exact unverified boundary.**
- [ ] **Step 4: Report changed files, validation outcomes, wheel filename/hash, and final working-tree status.**

## Self-Review Checklist

- Spec coverage: Tasks 2–4 cover Windows provider ordering, parsing, fallback,
  malformed data, and conservative classification; Task 5 covers macOS
  extraction; Task 6 protects Linux and integrates dispatch; Tasks 7–9 cover
  boundaries, validation, packaging, documentation, and evidence.
- Placeholder scan: this plan contains no `TBD`, `TODO`, or unspecified
  implementation step; provider metadata verification is an explicit gate in
  Task 1 with a defined ACPI-only alternative.
- Type consistency: both public functions return `TemperatureScan`, provider
  functions return `RawReadings`, and scanner dispatch passes the existing
  subprocess runner seam exactly as defined in the approved spec.

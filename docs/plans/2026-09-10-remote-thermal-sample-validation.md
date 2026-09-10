# Remote Thermal Sample Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make remote decoded thermal samples obey the same finite, plausible Celsius value rules as local samples while rejecting only bad samples.

**Architecture:** Keep wire/schema decoding in `maintenance/components/temperature.py` and `maintenance/cluster.py`, but put the single thermal-domain numeric predicate in the temperature component module. The local scanner and remote decoder both call that predicate; resource-summary decoding catches malformed thermal entries individually so valid non-thermal and thermal entries remain usable.

**Tech Stack:** Python 3, dataclasses, JSON codecs, `unittest`, `ruff`, `pyright`, and `mypy`.

---

## File Map

- Modify: `maintenance/components/temperature.py` — owns `TemperatureSample`, serialization, and the canonical Celsius-value validity predicate.
- Modify: `maintenance/scanner_support/dashboard.py:1138-1140` — routes local psutil values through the shared predicate without changing acquisition.
- Modify: `maintenance/cluster.py:114-153` — decodes each remote temperature sample independently and drops invalid samples.
- Modify: `tests/test_temperature_telemetry.py` — tests shared validity and unchanged telemetry after invalid input.
- Modify: `tests/test_cluster.py` — tests remote wire decoding and per-sample fail-closed behavior.
- Modify: `tests/test_remote_contract.py` — tests invalid samples inside signed remote responses and preservation of valid component data.

## Validation Contract

| Field | Local sample | Remote decoded sample |
| --- | --- | --- |
| Numeric value | psutil `int`/`float`, excluding `bool`; finite; `0 < value < 250` Celsius | JSON numeric `int`/`float`, excluding `bool`; finite; `0 < value < 250` Celsius |
| NaN/infinity | Reject before `TemperatureSample` creation | Reject after schema type check, before telemetry sees it |
| Timestamp | Scanner creates timezone-aware wall-clock and finite monotonic capture time | Require parseable ISO timestamp and finite numeric monotonic time |
| Component | Scanner assigns a known component key | Require non-empty string and retain the wire component identity |
| Sensor identity | Scanner derives non-empty `sensor_id` and `sensor_name` | Require non-empty `sensor_id` and `sensor_name` strings |
| Missing/malformed fields | Cannot occur from the scanner constructor path | Reject only that sample; do not fail the node response |

The existing local range is the semantic range to preserve: strictly above `0` and strictly below `250` Celsius. This is a validation hardening pass, not a `TemperatureTelemetry` redesign or a change to local sensor acquisition.

### Task 1: Establish Shared Domain Validation

**Files:**
- Modify: `maintenance/components/temperature.py:16-23`
- Modify: `maintenance/scanner_support/dashboard.py:1138-1140`
- Test: `tests/test_temperature_telemetry.py`

- [ ] **Step 1: Add failing value-contract tests.** Add a table-driven test for `0.1`, `249.9`, `0`, `250`, `-1`, `float("nan")`, positive infinity, negative infinity, `True`, and `"45"`. The first two must be accepted; all others must be rejected.

```python
    def test_temperature_value_uses_finite_local_range(self) -> None:
        from maintenance.components.temperature import is_valid_temperature_value

        for value in (0.1, 249.9):
            self.assertTrue(is_valid_temperature_value(value))
        for value in (0, 250, -1, float("nan"), float("inf"), float("-inf"), True, "45"):
            with self.subTest(value=value):
                self.assertFalse(is_valid_temperature_value(value))
```

- [ ] **Step 2: Run the focused test and verify it fails.** Run `python -m unittest tests.test_temperature_telemetry.TemperatureTelemetryTests.test_temperature_value_uses_finite_local_range -v`. Expected: `ImportError` because the shared predicate does not yet exist.

- [ ] **Step 3: Implement the one canonical predicate.** In `temperature.py`, import `math` and add `is_valid_temperature_value(value: object) -> TypeGuard[int | float]`. Return true only for `int`/`float` values that are not `bool`, are finite, and satisfy `0 < float(value) < 250`. Import and call it from `_sensible_temperature`; do not retain a second range expression there.

- [ ] **Step 4: Run the focused thermal tests.** Run `python -m unittest tests.test_temperature_telemetry -v`. Expected: all tests pass.

- [ ] **Step 5: Commit the shared-rule change.** Run:

```bash
git add maintenance/components/temperature.py maintenance/scanner_support/dashboard.py tests/test_temperature_telemetry.py
git commit -m "fix: share finite thermal value validation"
```

### Task 2: Harden Remote Sample Decoding

**Files:**
- Modify: `maintenance/components/temperature.py:465-504`
- Modify: `maintenance/cluster.py:114-153`
- Test: `tests/test_cluster.py`

- [ ] **Step 1: Add failing decoder tests.** Test `temperature_sample_from_dict` with a valid sample, each invalid numeric value from Task 1, malformed numeric text, missing `sensor_id`, missing `sensor_name`, malformed timestamp, and non-finite monotonic time. Assert invalid samples raise `TypeError` or `ValueError` before construction.

```python
    def test_temperature_sample_decoder_rejects_invalid_domain_and_metadata(self) -> None:
        payload = temperature_sample_to_dict(make_temperature_sample("cpu", 45.0))
        for value in (0, 250, -1, float("nan"), float("inf"), float("-inf"), "45"):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                temperature_sample_from_dict({**payload, "value_celsius": value})
        for field in ("sensor_id", "sensor_name"):
            invalid = dict(payload)
            invalid.pop(field)
            with self.subTest(field=field), self.assertRaises(TypeError):
                temperature_sample_from_dict(invalid)
```

- [ ] **Step 2: Run the decoder test and verify it fails.** Run `python -m unittest tests.test_cluster -v`. Expected: the new invalid-value cases fail because NaN, infinity, and out-of-range values currently decode.

- [ ] **Step 3: Keep schema checks separate and add domain checks.** In `temperature_sample_from_dict`, retain the existing field/type checks, reject empty component and sensor strings, call `is_valid_temperature_value` for `value_celsius`, require a parseable timestamp, and require finite `sampled_monotonic`. Convert the accepted numeric fields to `float` only after validation. Do not add JSON/signature checks to this thermal helper.

- [ ] **Step 4: Filter samples at the resource boundary.** In `resource_summary_from_dict`, decode each list item in a loop. Catch only the sample-decoding `TypeError`, `ValueError`, and `OverflowError`, skip that item, and construct the `ResourceSummary` with the surviving tuple. Continue raising `ClusterDataError` for malformed resource-summary fields and for a non-list `temperatures` field.

```python
    decoded_temperatures = []
    for item in temperatures:
        try:
            decoded_temperatures.append(temperature_sample_from_dict(item))
        except (TypeError, ValueError, OverflowError):
            continue
```

- [ ] **Step 5: Run codec and compatibility tests.** Run `python -m unittest tests.test_cluster tests.test_remote_compatibility -v`. Expected: all tests pass, including old payloads without a `temperatures` field.

- [ ] **Step 6: Commit the decoder change.** Run:

```bash
git add maintenance/components/temperature.py maintenance/cluster.py tests/test_cluster.py
git commit -m "fix: reject invalid remote thermal samples"
```

### Task 3: Prove Fail-Closed Telemetry Behavior

**Files:**
- Modify: `maintenance/cluster.py:114-153` only if the per-item loop needs a typed local annotation.
- Test: `tests/test_temperature_telemetry.py`
- Test: `tests/test_remote_contract.py`

- [ ] **Step 1: Add the telemetry invariant test.** Record a valid 90°C sample, save history, current, and event tuples, then decode a signed resource response containing an invalid thermal sample and pass the resulting resource to `record_summary`. Assert history, current, and events are byte-for-byte unchanged and no exception escapes.

```python
    def test_invalid_sample_does_not_change_history_or_events(self) -> None:
        telemetry = TemperatureTelemetry()
        telemetry.record_summary("cpu", make_summary(
            "cpu", "CPU", capability=CapabilityState.SUPPORTED,
            temperatures=(make_temperature_sample("cpu", 90.0),),
        ))
        before = telemetry.series_snapshot("cpu")
        invalid = make_summary(
            "cpu", "CPU", capability=CapabilityState.SUPPORTED,
            temperatures=(make_temperature_sample("cpu", float("nan")),),
        )
        telemetry.record_summary("cpu", invalid)
        after = telemetry.series_snapshot("cpu")
        self.assertEqual(after.samples, before.samples)
        self.assertEqual(after.current_celsius, before.current_celsius)
        self.assertEqual(after.events, before.events)
```

- [ ] **Step 2: Add signed-envelope preservation coverage.** Extend the remote contract fixture so one signed dashboard response contains one valid CPU sample, one invalid CPU sample, and a valid storage summary. Call the authenticated provider’s dashboard operation and assert the valid CPU/storage resources remain present while the invalid sample is absent.

- [ ] **Step 3: Add all requested remote cases.** Use subtests for valid normal value, `0.1`, `249.9`, `0`, `250`, NaN, both infinities, absurd high/low, malformed numeric text, missing sensor metadata, and a valid signed envelope carrying invalid thermal data. Assert only the invalid sample is dropped and the provider/session remains usable for a second valid request.

- [ ] **Step 4: Run remote and thermal validation.** Run:

```bash
python -m unittest tests.test_temperature_telemetry tests.test_cluster tests.test_remote_contract tests.test_remote_compatibility -v
```

Expected: all tests pass; invalid samples produce no history or events and do not make the authenticated node unusable.

- [ ] **Step 5: Commit the regression coverage.** Run:

```bash
git add tests/test_temperature_telemetry.py tests/test_remote_contract.py
git commit -m "test: cover fail-closed remote thermal samples"
```

### Task 4: Repository Validation and Handoff

**Files:**
- Modify: `docs/plans/2026-09-10-remote-thermal-sample-validation.md` — check completed steps and record validation evidence.

- [ ] **Step 1: Run the complete required validation.** Run:

```bash
ruff check .
ruff format --check .
pyright
mypy --ignore-missing-imports .
python -m unittest discover -s tests -v
```

Expected: every command exits with status 0; the full unittest suite reports `OK`.

- [x] **Step 2: Inspect the final diff.** Run `git diff --check` and `git status --short`. Confirm only the listed thermal, cluster, and test files changed; confirm no changes were made to `TemperatureTelemetry` state transitions or local sensor acquisition.

- [x] **Step 3: Record the audit conclusion.** Update this plan with the observed comparison: local and remote values share one finite/range predicate; remote wire shape remains separately validated; invalid samples are discarded individually; timestamps and sensor metadata remain required for remote samples.

### Task 4 Evidence

- `git diff --check`: passed with no whitespace errors.
- `git status --short`: only the six listed thermal/cluster/test files and this plan are changed or untracked; the diff contains no `TemperatureTelemetry` state-transition or local sensor-acquisition changes.
- Audit conclusion: local and remote values call `is_valid_temperature_value`; wire/schema checks remain in the remote decoder; `resource_summary_from_dict` discards invalid samples independently; remote timestamps and sensor metadata remain required.
- `ruff check .`, `ruff format --check .`, `pyright`, `mypy --ignore-missing-imports .`, and the exact `python -m unittest discover -s tests -v` command were blocked because the executables `ruff`, `pyright`, `mypy`, and `python` are unavailable on `PATH`.
- Equivalent `python3 -m unittest discover -s tests -v`: passed, `Ran 1171 tests in 44.570s`, `OK`.

- [ ] **Step 4: Commit the final plan evidence.** Run:

```bash
git add docs/plans/2026-09-10-remote-thermal-sample-validation.md
git commit -m "docs: complete remote thermal validation plan"
```

## Self-Review Checklist

- [x] **Spec coverage:** Tasks 1-2 compare and align numeric, finite, NaN, infinity, range, timestamp, component, sensor identity, and malformed-field validation. Task 3 covers valid, boundaries, non-finite values, absurd values, malformed numbers, missing metadata, signed envelopes, and unchanged history/events. The plan does not change telemetry architecture or local acquisition.
- [x] **Placeholder scan:** This plan contains no `TBD`, `TODO`, or unspecified validation step; every implementation step identifies a file, behavior, command, and expected result.
- [x] **Type consistency:** `is_valid_temperature_value` is the only domain predicate; `temperature_sample_from_dict` remains the strict sample decoder; `resource_summary_from_dict` owns per-sample filtering; `TemperatureTelemetry` continues receiving only validated samples.

## Execution Handoff

Plan complete and saved to `docs/plans/2026-09-10-remote-thermal-sample-validation.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh sub-agent per task with review checkpoints.
2. **Inline Execution** — execute the tasks in this session with checkpoints.

## Execution Record

- Task 1 completed by a fresh implementation worker and reviewed in-session.
- Task 2 completed by a fresh implementation worker and reviewed in-session.
- Task 3 completed by a fresh test worker and reviewed in-session.
- Task 4 completed with `python3 -m unittest discover -s tests -v`: 1,171 tests passed.
- `git diff --check` passed.
- `ruff`, `pyright`, and `mypy` were unavailable on `PATH`; no static-pass claim is made.

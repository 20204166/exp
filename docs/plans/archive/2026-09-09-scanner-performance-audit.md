# Scanner Performance Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-write, evidence-gated performance audit loop for all scanner APIs and `AppCoordinator`, beginning with low-risk optimizations and expanding only after proof.

**Architecture:** Keep benchmark orchestration outside application behavior. A reusable measurement model and runner will exercise injected scanner/coordinator seams, emit JSON and Markdown evidence, and rank candidates. Confirmed candidates are implemented in separate focused changes with regression and counter-tests.

**Tech Stack:** Python 3, `unittest`, `psutil`, `time.perf_counter`, `tracemalloc`, `unittest.mock`, existing `AppCoordinator` and `SystemScanner` seams, Ruff, Pyright, and Mypy.

---

## File Structure

- Create `maintenance/performance_audit.py`: immutable measurement records,
  workload definitions, resource counters, interleaved runner, and report
  serialization. It must not mutate scanner policy or UI state.
- Create `tools/scanner_performance_audit.py`: command-line entry point that
  constructs native or fake environments, runs the workload matrix, and writes
  JSON plus Markdown reports.
- Create `tests/support/performance_audit.py`: deterministic fake scanner,
  coordinator delivery queue, clocks, and resource-counter seams.
- Create `tests/test_performance_audit.py`: unit tests for measurements,
  interleaving, percentile calculations, platform labels, report output, and
  failure classification.
- Do not modify `pyproject.toml`; the first version is source-only and runs as
  `python -m tools.scanner_performance_audit`.
- Do not modify `docs/bug_hunts/performance_reviews/` during harness work. A
  separate candidate plan owns Mode C packets after a confirmed optimization
  is selected.

## Task 1: Define Measurement Models

**Files:**
- Create: `maintenance/performance_audit.py`
- Test: `tests/test_performance_audit.py`

- [ ] **Step 1: Write failing model tests**

  Test a `MeasurementRecord` containing workload, scenario, platform evidence,
  cold/warm state, samples, resource counters, error classification, and
  scanner/coordinator timing split. Assert that JSON serialization preserves
  those fields and that a missing required scenario raises `ValueError`.

- [ ] **Step 2: Run the focused tests**

  Run: `.venv/bin/python -m unittest tests.test_performance_audit -v`
  Expected: import or assertion failures because the audit models do not exist.

- [ ] **Step 3: Implement immutable models**

  Add frozen, slotted dataclasses for `WorkloadSpec`, `ResourceCounters`,
  `MeasurementRecord`, and `CandidateFinding`. Use explicit string literals for
  evidence (`native`, `simulated`, `unavailable`) and status (`confirmed`,
  `noise`, `not actionable`, `requires design`). Add `to_dict()` methods that
  emit JSON-compatible primitives only.

- [ ] **Step 4: Run focused tests and static checks**

  Run the focused unittest command, `.venv/bin/ruff check maintenance/performance_audit.py tests/test_performance_audit.py`, and `.venv/bin/pyright maintenance/performance_audit.py tests/test_performance_audit.py`.
  Expected: all focused tests pass and both static commands report no errors.

## Task 2: Implement Measurement And Statistics

**Files:**
- Modify: `maintenance/performance_audit.py`
- Modify: `tests/test_performance_audit.py`

- [ ] **Step 1: Add failing statistic tests**

  Verify median, p95, quartiles, and outlier values for a fixed sample set.
  Verify that interleaving alternates baseline and candidate runs, rejects a
  non-positive repetition count, and separates cold samples from warm samples.

- [ ] **Step 2: Implement the runner**

  Add `percentiles()`, `interleave_modes()`, and `AuditRunner.run()` using
  `time.perf_counter()` and injected callables. Capture CPU time with
  `time.process_time()` and allocations with `tracemalloc` when enabled.
  Record exceptions as classified failure results instead of hiding them.

- [ ] **Step 3: Add coordinator/scanner timing split tests**

  Use injected runner and delivery callbacks to assert that `AppCoordinator`
  queue/delivery time is recorded separately from the task body. Use a fake
  scanner to assert that dashboard and component workloads report distinct
  workload keys.

- [ ] **Step 4: Run focused validation**

  Run: `.venv/bin/python -m unittest tests.test_performance_audit -v`
  Expected: all measurement, interleaving, failure, and timing-split tests pass.

## Task 3: Add Deterministic Workload Fixtures

**Files:**
- Create: `tests/support/performance_audit.py`
- Modify: `tests/test_performance_audit.py`

- [ ] **Step 1: Define fake environments**

  Add fresh fake scanner and coordinator factories with counters for probe
  calls, cache hits, cancellation, retries, delivery, and late results. Add
  native/simulated/unavailable platform descriptors and fixed empty, typical,
  and large fixture profiles.

- [ ] **Step 2: Cover failure and lifecycle cases**

  Test missing optional dependency, permission failure, subprocess failure,
  timeout, cancellation, coalescing, stale generation, and post-shutdown
  delivery. Assert each case is classified without changing the fake's public
  result contract.

- [ ] **Step 3: Run the support and repository tests**

  Run: `.venv/bin/python -m unittest tests.test_performance_audit tests.test_coordinator_discovery tests.test_scanner_static_cache -v`
  Expected: all focused tests pass.

## Task 4: Define The Full Workload Matrix

**Files:**
- Modify: `maintenance/performance_audit.py`
- Modify: `tests/test_performance_audit.py`

- [ ] **Step 1: Add workload specifications**

  Define workload specs for dashboard refresh, every `scan_component` key,
  GPU/temperature reads, network discovery, downloads, process scans,
  background delivery, and coordinator operations. Include cold, warm,
  repeated-failure, concurrent, cancellation, timeout, and late-completion
  scenarios.

- [ ] **Step 2: Add matrix completeness tests**

  Assert that all `ResourceFeatureCatalog` keys are represented, the dashboard
  workload is present, and every coordinator lifecycle scenario has a spec.
  Assert that native, simulated, and unavailable platform labels are emitted
  distinctly.

- [ ] **Step 3: Run focused tests**

  Run: `.venv/bin/python -m unittest tests.test_performance_audit -v`
  Expected: the complete workload matrix and platform-label tests pass.

## Task 5: Build The Audit CLI And Reports

**Files:**
- Create: `tools/scanner_performance_audit.py`
- Modify: `maintenance/performance_audit.py`
- Modify: `tests/test_performance_audit.py`

- [ ] **Step 1: Write CLI/report tests**

  Invoke the command with a temporary output directory and deterministic fake
  mode. Assert it writes `scanner-performance.json` and
  `scanner-performance.md`, includes median/p95/quartiles/outliers, labels
  evidence provenance, separates scanner and coordinator timings, and emits a
  candidate register with the four defined statuses.

- [ ] **Step 2: Implement the CLI**

  Add `main(argv)` with `--output-dir`, `--repetitions`, `--platform-mode`,
  `--include-memory`, and `--seed` arguments. The default mode must run the
  available native environment; fake modes must be explicit. Use atomic writes
  for both report files and return non-zero only for harness failures, not
  expected unavailable-path observations.

- [ ] **Step 3: Verify source-only invocation**

  Keep the tool source-only. Run
  `.venv/bin/python -m tools.scanner_performance_audit --help` and assert that
  the documented arguments are listed without importing the GUI entry point.

- [ ] **Step 4: Run CLI and packaging tests**

  Run: `.venv/bin/python -m unittest tests.test_performance_audit tests.test_packaging -v`
  Expected: report and packaging tests pass.

## Task 6: Run The Baseline Audit

**Files:**
- Create: `docs/performance/scanner-performance-baseline.json`
- Create: `docs/performance/scanner-performance-baseline.md`
- Create: `docs/performance/simulated-windows/scanner-performance.json`
- Create: `docs/performance/simulated-macos/scanner-performance.json`

- [ ] **Step 1: Run the native baseline**

  Run: `.venv/bin/python -m tools.scanner_performance_audit --output-dir docs/performance --repetitions 30 --platform-mode native --include-memory`
  Expected: both baseline reports are written with native/unavailable labels
  for every platform-dependent path.

- [ ] **Step 2: Run simulated platform coverage**

  Run with `--output-dir docs/performance/simulated-windows
  --platform-mode simulated-windows` and then with
  `--output-dir docs/performance/simulated-macos --platform-mode
  simulated-macos`.
  Expected: simulated results are present and explicitly marked simulated.

- [ ] **Step 3: Review findings**

  For each confirmed finding, record the exact workload, attributable operation,
  median/p95 result, resource cost, contract touched, and proposed low-risk
  change. Findings without reproducible attribution receive `noise` status.

## Task 7: Close The Audit And Handoff Candidates

**Files:**
- Modify: `docs/performance/scanner-performance-baseline.md`
- Create: `docs/performance/scanner-performance-handoff.md`

- [ ] **Step 1: Classify every baseline finding**

  Record one of `confirmed`, `noise`, `not actionable`, or `requires design`
  for every workload. For each `confirmed` finding, record the exact workload,
  attributable operation, median/p95 result, resource cost, contract touched,
  and the smallest proposed change.

- [ ] **Step 2: Write the handoff report**

  Create `scanner-performance-handoff.md` with one section per confirmed
  candidate. Each section must name the exact application file and test module
  that a candidate-specific plan must inspect, list cache/freshness,
  cancellation, fallback, logging, and coordinator-generation contracts, and
  state the required before/after evidence.

- [ ] **Step 3: Define the controlled-change gate**

  Require the next candidate-specific plan to add one regression test and one
  counter-test, implement one seam only, preserve public signatures and result
  wording, and produce a Mode C BugGuard evidence packet.

- [ ] **Step 4: Run the audit validation gates**

  Run `.venv/bin/python -m unittest discover -s tests -v`, `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`, `.venv/bin/pyright`, and `.venv/bin/mypy --ignore-missing-imports`.
  Expected: all checks pass for the audit harness; candidate implementation
  checks belong to the candidate-specific plan.

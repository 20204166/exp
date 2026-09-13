# Runtime Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one bounded, local-only runtime observer that supplies useful performance and lifecycle metrics to Diagnostics and performance tools without taking ownership from existing coordinators.

**Architecture:** `maintenance/observability.py` owns generic thread-safe metric recording, bounded samples, percentile summaries, and immutable snapshots. `window.py` owns one observer and injects it into existing runtime owners. `maintenance/diagnostics.py` projects observer data, while `maintenance/performance_audit.py` and tools consume the same distribution mechanism without duplicating it.

**Tech Stack:** Python, dataclasses, threading locks, `unittest`, Tkinter composition root, JSON/Markdown CLI reports.

---

## File Map

- Create: `maintenance/observability.py` for the runtime observer, event methods, bounded metric storage, and immutable snapshots.
- Modify: `maintenance/performance_audit.py` to delegate sample summaries to the canonical distribution implementation.
- Modify: `maintenance/components/coordinator.py` to emit operation lifecycle metrics through an optional observer.
- Modify: `maintenance/ui/render_coordinator.py` to emit request/commit/rejection timing through the observer while retaining its domain counters.
- Modify: `maintenance/ui/action_coordinator.py` to emit dispatch success/failure metrics through the observer.
- Modify: `maintenance/components/temperature.py` to record observation timing/outcomes without replacing thermal history or capability state.
- Modify: `window.py` to construct and inject the single observer and expose it to diagnostics.
- Modify: `maintenance/diagnostics.py` and `maintenance/ui/diagnostics_page.py` to display bounded observer data.
- Create: `tools/application_performance_audit.py` for whole-application benchmark reporting.
- Modify: `tools/scanner_performance_audit.py` only where shared summaries are consumed.
- Test: `tests/test_observability.py`, plus focused owner and diagnostics tests.

## Task 1: Define the observer contract

- [ ] Add failing tests for bounded retention, thread-safe recording, empty and single-sample summaries, p50/p95/p99, sanitized target/detail values, immutable snapshots, and reset behavior.
- [ ] Run `scripts/run_tests.sh tests.test_observability -v`; confirm failure is caused by the missing observer API.
- [ ] Implement the smallest `ObservabilityWatcher`, immutable `MetricSnapshot`, and `ObservabilitySnapshot` API needed by those tests.
- [ ] Re-run the focused tests and then `ruff check maintenance/observability.py tests/test_observability.py`.

## Task 2: Consolidate performance statistics

- [ ] Add a failing test proving `maintenance.performance_audit.summarize_samples()` matches the observer’s canonical distribution output.
- [ ] Move the compatible percentile/statistics mechanism to the observer module and make `summarize_samples()` delegate without changing its existing dictionary contract.
- [ ] Run `scripts/run_tests.sh tests.test_performance_audit -v`.

## Task 3: Integrate runtime owners

- [ ] Add focused failing tests for AppCoordinator operation completion/error/cancellation/coalescing, UICoordinator render timing/rejection, ButtonCoordinator dispatch outcomes, and TemperatureTelemetry sample timing.
- [ ] Add optional observer injection with no-op behavior when absent; preserve all existing ownership, safety, cancellation, stale-generation, and UI-thread rules.
- [ ] Run the focused owner tests and the full suite.

## Task 4: Project diagnostics

- [ ] Add failing diagnostics tests for observer metrics appearing in immutable snapshots and serialized JSON with bounded fields only.
- [ ] Extend `DiagnosticsSnapshot` and the Diagnostics page using existing layout primitives; keep diagnostics read-only and refresh-safe.
- [ ] Run diagnostics, UI, and live-Tk tests where available.

## Task 5: Add the application performance tool

- [ ] Add tests for deterministic simulated reports and explicit native/unavailable evidence.
- [ ] Create `tools/application_performance_audit.py` to orchestrate existing `AuditRunner` workloads and observer snapshots, writing JSON and Markdown without duplicating statistics or runtime coordination.
- [ ] Keep `tools/scanner_performance_audit.py` scanner-specific and update only shared-summary usage.

## Task 6: Final validation

- [ ] Run `scripts/run_tests.sh`.
- [ ] Run `ruff check .`, `ruff format --check .`, `pyright`, and `mypy --ignore-missing-imports`.
- [ ] Run `git diff --check`, inspect the final diff and working-tree status, and report any unrelated pre-existing changes without reverting them.

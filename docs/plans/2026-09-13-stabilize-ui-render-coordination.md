# Stabilize UI Render Coordination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep Tk widget commits stable and responsive under bursts of scan, discovery, and node updates by moving expensive preparation behind the existing worker coordinator while retaining latest-wins render safety.

**Architecture:** `UICoordinator` remains a Tk-thread presentation gate: it batches, coalesces, visibility-gates, and rejects stale `RenderIntent` values, but never owns workers or touches widgets from a worker thread. Reuse the existing `AppCoordinator` for keyed cancellable background preparation and deliver completed render intents through its established UI delivery path; only add a small existing-owner extension if measured call sites need it.

**Tech Stack:** Python 3.12, Tkinter/ttk, `AppCoordinator`, `UICoordinator`, `BackgroundOrchestrator`, `RenderIntent`, `threading`, `unittest` fakes, live-Tk resize tests, Ruff, Pyright, and Mypy.

---

## File Map

- Modify `maintenance/ui/render_coordinator.py`: preserve the render gate and add only measured instrumentation or a narrow preparation seam if required.
- Modify `maintenance/components/coordinator.py` only if an existing keyed run/delivery capability is insufficient; preserve cancellation and generation contracts.
- Modify `maintenance/components/background_orchestration.py` only where the existing Tk queue needs a bounded render-drain integration; do not duplicate `AppCoordinator`.
- Modify measured callers in `maintenance/ui/window_components.py`, `window_scan.py`, `window_discovery.py`, `window_node_runtime.py`, or page modules only after profiling identifies a costly preparation path.
- Modify `tests/test_render_coordinator.py`, coordinator tests, and affected window tests for thread, ordering, stale-generation, cancellation, and coalescing contracts.
- Modify `tests/test_live_tk_resize.py` only for a proven live-Tk responsiveness/render-stability contract.

## Task 1: Measure the current render path

- [ ] Add or use timing counters around render request, queue, preparation, and widget-commit phases without changing scheduling behavior.
- [ ] Exercise dashboard refresh, rapid node switching, discovery bursts, thermal updates, and background completion bursts with repeated p50/p95/p99 measurements.
- [ ] Record which callable accounts for the commit or preparation time; do not move work based on method size or apparent complexity.
- [ ] Run `scripts/run_tests.sh tests.test_render_coordinator tests.test_background_orchestration tests.test_window tests.test_window_nodes -v` before implementation.

## Task 2: Strengthen render-thread contracts

- [ ] Add failing tests proving every `RenderIntent.apply` callback runs on the Tk thread, stale generations and node owners are rejected, hidden targets do not commit, and shutdown drops pending work.
- [ ] Add burst tests proving multiple updates for one target produce one latest-wins commit while priority and target ordering remain deterministic.
- [ ] Keep `UICoordinator` free of scanner, network, worker-pool, and widget-construction dependencies.

## Task 3: Move only measured preparation work

- [ ] For each measured expensive caller, define a pure preparation callable that accepts a cancellation event and returns immutable render data; leave Tk reads/writes and final widget application on the UI thread.
- [ ] Run that callable through `AppCoordinator.run` under a stable per-target key, using its existing coalescing, cancellation, retry, cached-result, and injected delivery path.
- [ ] On delivery, validate node identity and generation, then submit one `RenderIntent` to `UICoordinator`; never let a worker call `request`, `flush`, or a widget method directly.
- [ ] If `AppCoordinator` lacks one required seam, extend it narrowly instead of creating a second worker abstraction or putting a thread pool in `render_coordinator.py`.

## Task 4: Preserve lifecycle and degraded states

- [ ] Define behavior for initial loading, refresh with existing content, partial component failure, stale node delivery, cancellation, closed widgets, hidden pages, and executor shutdown.
- [ ] Keep old rendered content visible while preparation runs; use existing status/progress delivery for work longer than one second and retain retry/error paths.
- [ ] Ensure a node switch cancels or invalidates old preparation before the new node can commit, preserving `UICoordinator.invalidate` generation and node checks.
- [ ] Ensure background polling and discovery event delivery still use `BackgroundOrchestrator`/`AppCoordinator` rather than creating duplicate queues.

## Task 5: Re-measure and validate

- [ ] Re-run the identical workload matrix and compare p50/p95/p99 preparation latency, UI commit duration, pending depth, stale rejections, and rendered update count.
- [ ] Keep the change only if the measured target improves without increasing stale commits, dropped visible updates, cancellation latency, or error frequency; otherwise revert the optimization.
- [ ] Run `scripts/run_tests.sh tests.test_render_coordinator tests.test_background_orchestration tests.test_coordinator_discovery tests.test_window tests.test_window_nodes -v`.
- [ ] Run `scripts/run_tests.sh`, `ruff check .`, `ruff format --check .`, `pyright`, `mypy --ignore-missing-imports`, and `git diff --check`.
- [ ] Run `tests/test_live_tk_resize.py` under `scripts/run_tests.sh tests.test_live_tk_resize -v` and verify no visible layout regression under repeated refreshes.
- [ ] Add or update the committed benchmark/evidence output only after the before/after comparison is complete.

## Explicit Non-Goals

- [ ] Do not make Tkinter widget mutations from workers.
- [ ] Do not replace `UICoordinator` with a generic worker manager.
- [ ] Do not remove stale-generation, node-identity, visibility, batching, or shutdown checks as “duplicate” work.
- [ ] Do not optimize render code until Task 1 names the measured bottleneck.

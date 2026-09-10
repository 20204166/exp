# Smoothness Coordination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce avoidable UI stalls and redundant work while preserving refresh freshness, cancellation, discovery trust, and existing public behavior.

**Architecture:** Extend the existing `AppCoordinator` as the single coordination boundary. Coalesce UI delivery by logical key, defer hidden non-urgent refresh work until the owning surface is visible, and add a bounded discovery stabilization window that does not alter discovery TTL or trust semantics. Add deterministic audit scenarios and regression tests before production changes.

**Tech Stack:** Python 3, Tkinter, `unittest`, `ruff`, `pyright`, `mypy`, existing `AppCoordinator`, `DiscoverySession`, and performance-audit harness.

---

## File Map

- Modify `maintenance/components/coordinator.py`: keyed UI-delivery coalescing and visibility-safe scheduling hooks.
- Modify `maintenance/components/discovery_session.py`: bounded discovery stabilization scheduling and cancellation.
- Modify `maintenance/components/network_discovery.py`: expose no new policy; retain transport, TTL, and trust behavior unchanged.
- Modify `maintenance/ui/discovery_refresh.py`: batch refresh work at the existing presentation boundary.
- Modify `window.py`: connect visibility state and non-urgent refresh deferral to the coordinator without changing visible refresh intervals.
- Modify `maintenance/performance_audit.py`: add callback/delivery-pressure and hidden-work measurements.
- Modify `tools/scanner_performance_audit.py`: expose deterministic coordination scenarios in reports.
- Modify `tests/test_coordinator_discovery.py`: delivery coalescing, stale-generation, cancellation, and visibility tests.
- Modify `tests/test_discovery_session.py`: stabilization-window lifecycle tests.
- Modify `tests/test_discovery_refresh.py`: one-batch presentation assertions.
- Modify `tests/test_window.py` and/or `tests/test_dashboard_ui.py`: hidden refresh deferral and visible-refresh regression tests.
- Modify `tests/test_performance_audit.py`: deterministic audit metrics and scenario coverage.

## Task 1: Establish Failing Coordination Tests

**Files:**
- Modify: `tests/test_coordinator_discovery.py`
- Modify: `tests/test_window.py` or `tests/test_dashboard_ui.py`

- [ ] **Step 1: Add a failing keyed-delivery test.**

Add a test that posts several callbacks for the same logical key before the fake UI drain runs, then asserts only the latest callback is delivered while callbacks for different keys remain independent. Use the repository's fake delivery/master helpers; do not start a live Tk root.

- [ ] **Step 2: Add a failing hidden-work test.**

Trigger a non-urgent refresh while its owning page is hidden and assert the task is not started. Make the page visible, flush the deferred trigger, and assert exactly one task starts. Add a separate assertion that an explicit visible refresh starts immediately.

- [ ] **Step 3: Run the focused tests and verify failure.**

Run:

```bash
python -m unittest tests.test_coordinator_discovery tests.test_dashboard_ui -v
```

Expected: the new tests fail because keyed delivery and hidden-work deferral do not yet exist.

## Task 2: Implement Keyed UI Delivery Coalescing

**Files:**
- Modify: `maintenance/components/coordinator.py`
- Test: `tests/test_coordinator_discovery.py`

- [ ] **Step 1: Add the minimal keyed delivery state.**

Store one pending callback and generation per delivery key. Add a method with this contract:

```python
def post_coalesced(self, key: str, callback: Callable[[], None]) -> None:
    """Schedule at most one pending callback for ``key``."""
```

The method must call `_note_activity()`, schedule through the injected `_deliver`, and discard a queued callback when a newer callback for the same key replaces it.

- [ ] **Step 2: Preserve lifecycle generation checks.**

Use a monotonically increasing token per key. The delivered wrapper must no-op unless its token is still current. `clear()` must invalidate pending tokens. Existing `post()` remains unchanged for events where every event is semantically required.

- [ ] **Step 3: Run coordinator tests.**

Run:

```bash
python -m unittest tests.test_coordinator_discovery -v
```

Expected: keyed delivery, stale lifecycle, cancellation, and existing discovery tests pass.

- [ ] **Step 4: Commit the isolated coordinator change.**

```bash
git add maintenance/components/coordinator.py tests/test_coordinator_discovery.py
git commit -m "Coalesce keyed UI delivery"
```

## Task 3: Defer Hidden Non-Urgent Refreshes

**Files:**
- Modify: `window.py`
- Modify: `maintenance/components/coordinator.py`
- Test: `tests/test_dashboard_ui.py` or `tests/test_window.py`

- [ ] **Step 1: Add explicit visibility/deferred-trigger hooks.**

Add coordinator methods for one deferred trigger per key:

```python
def defer(self, key: str, trigger: Callable[[], None]) -> None: ...
def flush_deferred(self, key: str) -> None: ...
```

`defer` replaces only the pending non-urgent trigger for that key. `flush_deferred` removes it before invoking it, so a trigger cannot duplicate itself.

- [ ] **Step 2: Route only hidden, non-urgent work through the hooks.**

At the window/page visibility boundary, defer background refreshes for hidden surfaces and flush them on visibility restoration. Do not defer explicit user refreshes, visible-page refreshes, cancellation, or teardown. Keep existing interval values unchanged.

- [ ] **Step 3: Run UI regression tests.**

Run:

```bash
python -m unittest tests.test_dashboard_ui tests.test_window -v
```

Expected: hidden refreshes are suppressed/coalesced, visible refreshes remain immediate, and existing page switching tests pass.

- [ ] **Step 4: Commit hidden-work deferral.**

```bash
git add window.py maintenance/components/coordinator.py tests/test_dashboard_ui.py tests/test_window.py
git commit -m "Defer hidden non-urgent refreshes"
```

## Task 4: Batch Discovery Presentation Safely

**Files:**
- Modify: `maintenance/ui/discovery_refresh.py`
- Modify: `maintenance/components/coordinator.py`
- Test: `tests/test_discovery_refresh.py`

- [ ] **Step 1: Add a failing burst-refresh test.**

Deliver multiple candidate/lost notifications before the UI drain and assert the page, cluster view, and status label are refreshed once with the final candidate set. Assert that trusted-list refresh remains conditional on trusted-peer involvement.

- [ ] **Step 2: Route discovery presentation through a keyed coalesced callback.**

Keep registry updates and trust decisions on their existing UI-thread path. Only coalesce the downstream presentation callback. The final callback must read current state at execution time, so intermediate candidates are not rendered as stale final state.

- [ ] **Step 3: Run discovery presentation tests.**

Run:

```bash
python -m unittest tests.test_discovery_refresh tests.test_coordinator_discovery tests.test_discovery_end_to_end -v
```

Expected: burst updates render once, stale lifecycle deliveries are ignored, and trust/registry behavior is unchanged.

- [ ] **Step 4: Commit the presentation batching change.**

```bash
git add maintenance/ui/discovery_refresh.py maintenance/components/coordinator.py tests/test_discovery_refresh.py tests/test_coordinator_discovery.py tests/test_discovery_end_to_end.py
git commit -m "Batch discovery presentation updates"
```

## Task 5: Add Bounded Discovery Stabilization

**Files:**
- Modify: `maintenance/components/discovery_session.py`
- Test: `tests/test_discovery_session.py`

- [ ] **Step 1: Add failing lifecycle tests.**

Cover these cases: multiple discovery events schedule one stabilization callback; the callback runs within the configured bounded grace window; stop cancels it; and restart cannot execute a callback from the prior lifecycle generation.

- [ ] **Step 2: Add injected scheduling parameters.**

Add a small, testable stabilization delay using the existing `schedule_timer`/`cancel_timer` dependencies. Keep it bounded and internal; do not change `NetworkDiscovery` TTL or `REAP_TICK_SECONDS`.

- [ ] **Step 3: Preserve event semantics.**

Candidate/lost registry events remain delivered as before. Stabilization only controls when downstream refresh work is requested. Discovery unavailable, disabled, identity persistence, and shutdown paths retain their current results.

- [ ] **Step 4: Run session tests.**

```bash
python -m unittest tests.test_discovery_session tests.test_network_discovery tests.test_discovery_end_to_end -v
```

Expected: stabilization lifecycle tests pass and all transport/TTL/trust tests remain green.

- [ ] **Step 5: Commit stabilization.**

```bash
git add maintenance/components/discovery_session.py tests/test_discovery_session.py
git commit -m "Stabilize discovery refresh bursts"
```

## Task 6: Extend Deterministic Performance Evidence

**Files:**
- Modify: `maintenance/performance_audit.py`
- Modify: `tools/scanner_performance_audit.py`
- Test: `tests/test_performance_audit.py`

- [ ] **Step 1: Add failing metric assertions.**

Add deterministic scenarios for callback delivery count, duplicate task starts, hidden-work starts, visible refresh latency, and discovery-burst render count. Assert the audit distinguishes event count from rendered update count.

- [ ] **Step 2: Implement audit scenarios with fake clocks and runners.**

Use existing fixture adapters and fake UI delivery. Keep native and simulated outputs labeled. Do not claim platform performance from simulation.

- [ ] **Step 3: Run the audit tests and CLI.**

```bash
python -m unittest tests.test_performance_audit -v
python tools/scanner_performance_audit.py --output-dir docs/performance
```

Expected: deterministic coordination metrics are present and reports retain provenance labels.

- [ ] **Step 4: Commit audit evidence.**

```bash
git add maintenance/performance_audit.py tools/scanner_performance_audit.py tests/test_performance_audit.py docs/performance
git commit -m "Measure smoothness coordination"
```

## Task 7: Full Verification and Final Review

- [ ] **Step 1: Run the focused regression suite.**

```bash
python -m unittest tests.test_coordinator_discovery tests.test_discovery_session tests.test_network_discovery tests.test_discovery_refresh tests.test_discovery_end_to_end tests.test_dashboard_ui tests.test_window tests.test_performance_audit -v
```

- [ ] **Step 2: Run repository quality gates.**

```bash
ruff check .
ruff format --check .
pyright
mypy --ignore-missing-imports
```

Record known pre-existing generated-build and historical BugGuard duplicate-module findings separately; do not treat them as validation evidence for this change.

- [ ] **Step 3: Run the complete test suite.**

```bash
python -m unittest discover -s tests -v
```

Expected: all repository tests pass.

- [ ] **Step 4: Review the diff against the design spec.**

Confirm no visible interval changed, no trust/TTL semantics changed, no worker touches Tk widgets, hidden work is bounded, and simulated metrics are labeled.

- [ ] **Step 5: Commit the final integration if needed.**

```bash
git status --short
git diff --check
```

Commit only intended files with a concise message after the complete review.

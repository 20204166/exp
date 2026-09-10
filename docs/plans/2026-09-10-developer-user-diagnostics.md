# Developer/User Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded, themed Settings > Diagnostics page that projects existing runtime state without creating telemetry infrastructure.

**Architecture:** Existing schedulers, coordinators, node contexts, and UI counters remain authoritative. A new immutable diagnostics module normalizes their current state for a presentation-only page; AppWindow owns composition and visible-page refresh.

**Tech Stack:** Python 3.12, Tkinter/ttk, frozen dataclasses, existing `PageRouter`, `TimerDelivery`, unittest, Ruff, Pyright, and mypy.

---

## File Structure

- Create `maintenance/diagnostics.py`: immutable records, bounded normalization, snapshot construction, and JSON-safe serialization.
- Create `maintenance/ui/diagnostics_page.py`: theme-aware, dependency-injected Tk presentation only.
- Modify `maintenance/components/coordinator.py`: retain only bounded last-success/error metadata at existing owners.
- Modify `maintenance/nodes.py`: expose any missing read-only diagnostic projection needed from existing node state.
- Modify `window.py`: compose the snapshot, register the retained page, and manage visible refresh.
- Modify `maintenance/ui/window_page_data.py`: add the Settings category and diagnostic data adapter.
- Modify `maintenance/ui/window_pages.py`: build, route, show, refresh, and copy the page.
- Modify `maintenance/ui/layout.py` only if an existing page primitive cannot represent the compact sections; do not add a generic diagnostics widget.
- Create `tests/test_diagnostics.py`: model, normalization, serialization, and bounded-state tests.
- Create `tests/test_diagnostics_page.py`: headless presentation and empty-state tests.
- Modify `tests/test_components.py`: scheduler metadata behavior.
- Modify `tests/test_coordinator_discovery.py` or the narrowest existing coordinator test module: operation metadata behavior.
- Modify `tests/test_window.py` and `tests/test_window_nodes.py`: routing, refresh, and node-switching integration.

## Ownership Decisions

- **REUSE:** `AppCoordinator`, `ComponentRefreshScheduler`, `NodeContext`, `NodeRegistry`, `UICoordinator`, `TimerDelivery`, `PageRouter`, layout primitives, theme tokens, and `classify_peer_failure`.
- **EXTEND:** Existing runtime owners only for one last success timestamp and one last normalized error where the requested state is not already available.
- **EXTRACT:** One diagnostics projection/serialization owner in `maintenance/diagnostics.py` only after confirming no existing equivalent.
- **KEEP SEPARATE:** Component health, operation lifecycle, node connectivity, and render rejection semantics; they must not be merged behind mode flags.
- **REJECT:** A telemetry registry, event bus, persistent history, monitoring backend, generic utility module, or remote diagnostics protocol.

### Task 1: Extend Existing Runtime Metadata

**Files:**
- Modify: `maintenance/components/coordinator.py` (`_RefreshEntry`, `AppRunState`, completion paths)
- Test: `tests/test_components.py`, `tests/test_coordinator_discovery.py`

- [ ] **Step 1: Write failing scheduler metadata tests.**

Add tests asserting a successful `finish` records one completion timestamp and an error callback records one bounded error category/detail without changing `in_flight`, pause, due-time, or rerun behavior.

```python
entry = scheduler.diagnostic_state("cpu")
self.assertIsNone(entry.last_success)
scheduler.begin("cpu", 0.0)
scheduler.finish("cpu", completed_at=12.5)
self.assertEqual(scheduler.diagnostic_state("cpu").last_success, 12.5)
```

- [ ] **Step 2: Run the focused tests and verify they fail.**

Run: `python -m unittest tests.test_components.ComponentRefreshSchedulerTests -v`
Expected: FAIL because the diagnostic accessor and completion metadata do not exist.

- [ ] **Step 3: Add the minimal bounded fields and accessor.**

Keep one timestamp and one normalized error record per component. Preserve existing callers by making new arguments optional and keep scheduling transitions unchanged.

```python
@dataclass(slots=True)
class _RefreshEntry:
    interval: float
    next_due: float = 0.0
    in_flight: bool = False
    paused: bool = False
    refresh_requested: bool = False
    last_success: float | None = None
    last_error: tuple[str, str] | None = None
```

Expose a read-only `diagnostic_state(key)` value and update it only from existing completion/error boundaries.

- [ ] **Step 4: Add coordinator metadata tests and implementation.**

Assert `AppCoordinator` exposes active keys, generation, cached-result presence, and last error without retaining event history. Update completion/error paths only; cancellation must clear in-flight state but not fabricate success.

```python
state = coordinator.state("scan")
self.assertEqual(state.generation, 1)
self.assertTrue(state.in_flight)
self.assertIsNone(state.last_error)
```

- [ ] **Step 5: Run focused tests and commit.**

Run: `python -m unittest tests.test_components tests.test_coordinator_discovery -v`
Expected: PASS with existing scheduler/coordinator tests unchanged.

```bash
git add maintenance/components/coordinator.py tests/test_components.py tests/test_coordinator_discovery.py
git commit -m "feat: expose bounded runtime diagnostics state"
```

### Task 2: Add Immutable Diagnostics Projection

**Files:**
- Create: `maintenance/diagnostics.py`
- Test: `tests/test_diagnostics.py`

- [ ] **Step 1: Write failing model and serializer tests.**

Cover frozen records, tuple-backed collections, 160-character detail truncation, stable failure categories, `no_data_yet`, and secret exclusion.

```python
snapshot = build_diagnostics_snapshot(
    scheduler=scheduler,
    coordinator=coordinator,
    registry=registry,
    ui_coordinator=ui_coordinator,
)
self.assertIsInstance(snapshot.components, tuple)
self.assertNotIn("secret", json.dumps(serialize_diagnostics(snapshot)))
```

- [ ] **Step 2: Run the new tests and verify they fail.**

Run: `python -m unittest tests.test_diagnostics -v`
Expected: FAIL because `maintenance.diagnostics` does not exist.

- [ ] **Step 3: Create the model skeleton and bounded helpers.**

Define frozen, slotted `ComponentDiagnostic`, `OperationDiagnostic`, `NodeDiagnostic`, `RenderDiagnostic`, and `DiagnosticsSnapshot`. Define `MAX_DETAIL_LENGTH = 160`, `truncate_detail`, and stable category normalization using the existing peer failure classifier.

- [ ] **Step 4: Implement snapshot projection and serialization.**

Read existing owner state only. Return tuples, never mutable owner references. Serialize enums and timestamps to JSON-safe strings/numbers; omit secrets, credentials, payloads, and raw exception objects.

- [ ] **Step 5: Run tests and commit.**

Run: `python -m unittest tests.test_diagnostics -v`
Expected: PASS.

```bash
git add maintenance/diagnostics.py tests/test_diagnostics.py
git commit -m "feat: add immutable diagnostics snapshot"
```

### Task 3: Build the Diagnostics Page

**Files:**
- Create: `maintenance/ui/diagnostics_page.py`
- Test: `tests/test_diagnostics_page.py`

- [ ] **Step 1: Write failing headless page tests.**

Use the repository recording widgets. Assert the page renders the summary, component/node/operation sections, explicit empty states, secondary failure detail, theme colors, Back callback, and Copy callback.

```python
page = DiagnosticsPage(parent, callbacks=callbacks, snapshot=empty_snapshot, **fakes)
self.assertIn("No data yet", recorded_text(page))
self.assertIn("No recent failures", recorded_text(page))
```

- [ ] **Step 2: Run the page tests and verify they fail.**

Run: `python -m unittest tests.test_diagnostics_page -v`
Expected: FAIL because the page module does not exist.

- [ ] **Step 3: Create the page skeleton and callback contract.**

Define frozen `DiagnosticsPageCallbacks` with `on_back` and `on_copy`, then inject widget classes, colors, fonts, button coordinator, and a `snapshot` value. Keep imports limited to Tk, layout, styles, and diagnostics model types.

- [ ] **Step 4: Implement compact sections incrementally.**

Use the existing page shell and navigation/card primitives. Add summary rows, then components, operations, nodes, and rendering rows. Render stable status labels and bounded secondary details; do not add page-local state history.

- [ ] **Step 5: Implement empty states and copy action.**

Show `No data yet`, `Nothing currently running`, `No recent failures`, and `No remote nodes configured` for the corresponding empty collections. Route copy through `on_copy(serialize_diagnostics(snapshot))`; the page must not access secrets or the clipboard directly.

- [ ] **Step 6: Run page tests and commit.**

Run: `python -m unittest tests.test_diagnostics_page -v`
Expected: PASS.

```bash
git add maintenance/ui/diagnostics_page.py tests/test_diagnostics_page.py
git commit -m "feat: add themed diagnostics page"
```

### Task 4: Integrate Settings Navigation

**Files:**
- Modify: `window.py`
- Modify: `maintenance/ui/window_page_data.py`
- Modify: `maintenance/ui/window_pages.py`
- Test: `tests/test_window.py`, `tests/test_settings_home.py`

- [ ] **Step 1: Write failing navigation tests.**

Assert the Settings categories include `diagnostics`, selecting it routes to `DIAGNOSTICS_PAGE`, and Back returns to Settings.

```python
self.assertIn("diagnostics", [item.key for item in window._settings_categories()])
window._on_select_settings_category("diagnostics")
self.assertEqual(window._page_router.active_key, "diagnostics")
```

- [ ] **Step 2: Run focused tests and verify they fail.**

Run: `python -m unittest tests.test_window tests.test_settings_home -v`
Expected: FAIL because the category and route are absent.

- [ ] **Step 3: Add the route and page builder.**

Register `DIAGNOSTICS_PAGE` beside existing retained pages. Add one Settings category, route it in `select_settings_category`, and build the page with the current theme and button coordinator.

- [ ] **Step 4: Add snapshot composition and copy callback.**

Add a controller method that calls `build_diagnostics_snapshot` with the selected context, scheduler, app coordinator, node registry, and UI coordinator. Copy only the returned serialized text through the Tk clipboard boundary owned by `AppWindow`.

- [ ] **Step 5: Run integration tests and commit.**

Run: `python -m unittest tests.test_window tests.test_settings_home -v`
Expected: PASS.

```bash
git add window.py maintenance/ui/window_page_data.py maintenance/ui/window_pages.py tests/test_window.py tests/test_settings_home.py
git commit -m "feat: route diagnostics from settings"
```

### Task 5: Add Visible-Page Refresh and State Coverage

**Files:**
- Modify: `window.py`, `maintenance/ui/window_pages.py`
- Test: `tests/test_window.py`, `tests/test_window_nodes.py`, `tests/test_diagnostics.py`

- [ ] **Step 1: Write failing lifecycle tests.**

Assert a visible Diagnostics page schedules one refresh through the existing timer delivery, hidden pages cancel it, closing cancels it, and switching nodes rebuilds from the new context rather than reusing the prior snapshot.

```python
window._page_router.show("diagnostics")
window._show_diagnostics_page()
self.assertEqual(window._diagnostics_refresh_id, "after-1")
window._show_settings_page()
self.assertIn("after-1", master.cancelled)
```

- [ ] **Step 2: Run focused lifecycle tests and verify they fail.**

Run: `python -m unittest tests.test_window tests.test_window_nodes -v`
Expected: FAIL because Diagnostics has no refresh lifecycle.

- [ ] **Step 3: Implement visible-only refresh.**

Use `TimerDelivery.schedule` with a bounded interval, store one timer ID, refresh the page from a newly composed snapshot, and reschedule only while the active route is Diagnostics and the window is not closing. Cancel the ID on route changes and close.

- [ ] **Step 4: Connect existing state transitions.**

After existing scan/component completion, connection-state changes, node selection, and render commits, request a diagnostics refresh only when the page is visible. Do not create a second event queue or worker.

- [ ] **Step 5: Add state matrix tests.**

Cover healthy component, failed component, in-flight operation, unsupported hardware, peer refused/timeout/authentication/identity failure, discovery unavailable, no data, stale rejection, and node switching. Assert diagnostics contain categories/details but never secrets.

- [ ] **Step 6: Run lifecycle tests and commit.**

Run: `python -m unittest tests.test_window tests.test_window_nodes tests.test_diagnostics -v`
Expected: PASS.

```bash
git add window.py maintenance/ui/window_pages.py tests/test_window.py tests/test_window_nodes.py tests/test_diagnostics.py
git commit -m "feat: refresh diagnostics from live app state"
```

### Task 6: Consolidation Audit and Final Validation

**Files:**
- Review: all files changed by Tasks 1-5 and their direct callers/tests
- Modify: only if the audit finds an actual duplicate or failed check

- [ ] **Step 1: Search for duplicate diagnostic ownership.**

Run searches for `last_error`, `last_success`, `in_flight`, `generation`, `stale_rejections`, `diagnostic`, and failure-category mappings across `maintenance/`, `window.py`, and `tests/`. Classify each match as canonical state, projection, caller, test double, or intentional specialization.

- [ ] **Step 2: Remove redundant tracking if found.**

Keep one canonical field at the existing runtime owner. Remove any page-local cache, duplicate failure classifier, duplicate serializer, or unbounded list introduced during implementation. Add or update the narrow regression test before proceeding.

- [ ] **Step 3: Run focused and complete validation.**

```bash
ruff check .
ruff format --check .
pyright
mypy --ignore-missing-imports .
python -m unittest discover -s tests -v
git diff --check
```

Expected: all commands exit successfully; full unittest discovery reports `OK`.

- [ ] **Step 4: Review the final diff and working tree.**

Confirm only diagnostics implementation/tests/docs plus the previously existing `remote.py` consolidation changes are present. Confirm no secrets, generated telemetry, or accidental `.superpowers` artifacts are tracked.

- [ ] **Step 5: Commit the plan and implementation changes separately if needed.**

The plan is committed before implementation. Each code task should retain its focused commit; do not squash unrelated pre-existing changes.

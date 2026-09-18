# UICoordinator Transition Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `UICoordinator` to manage named delayed transitions via `PendingTransition` internally, making it the single UI timing authority for both render commits and delayed state changes.

**Architecture:** `UICoordinator` gains `schedule_transition(name, delay, apply)` and `cancel_transition(name)` methods. It holds a `dict[str, PendingTransition]` keyed by caller-chosen name. Each slot is a real `PendingTransition` instance — created on first use, using the same injected `schedule`/`cancel` callables. `transition.py` is untouched. Existing `PendingTransition` users are unaffected. The one current call site (`_completion_transition`) is migrated to use the new API.

**Tech Stack:** Python 3.12, Tkinter, `maintenance.ui.render_coordinator`, `maintenance.ui.transition`

---

## File Structure

| File | Change |
|------|--------|
| `maintenance/ui/render_coordinator.py` | Add `schedule`/`cancel` init params, `_transitions` dict, `schedule_transition()`, `cancel_transition()`, extend `shutdown()` |
| `maintenance/ui/window_lifecycle.py` | Remove `completion_transition()` helper, 2 cancel call sites updated, remove `ui_transition` import |
| `maintenance/ui/window_presentation.py` | Replace `.start()` call site |
| `window.py` | Pass `schedule`/`cancel` lambdas to `UICoordinator()`, remove `_completion_transition()` method |
| `tests/test_render_coordinator.py` | Add `UICoordinatorTransitionTests` class |

`transition.py` — **not touched**.

---

## Task 1: Extend `UICoordinator` with transition management

**Files:**
- Modify: `maintenance/ui/render_coordinator.py`

- [ ] **Step 1: Write the failing tests first**

Add a new class to `tests/test_render_coordinator.py` — after the existing `UICoordinatorTests` class, before `if __name__ == "__main__"`:

```python
class UICoordinatorTransitionTests(unittest.TestCase):
    """UICoordinator must manage named PendingTransition slots."""

    def _make_coordinator(self) -> tuple["UICoordinator", list[tuple[int, Any]], list[Any]]:
        scheduled: list[tuple[int, Any]] = []
        cancelled: list[Any] = []
        timer_id = 0

        def fake_schedule(delay: int, callback: Any) -> int:
            nonlocal timer_id
            timer_id += 1
            scheduled.append((delay, callback))
            return timer_id

        def fake_cancel(identifier: Any) -> bool:
            cancelled.append(identifier)
            return True

        coordinator = UICoordinator(schedule=fake_schedule, cancel=fake_cancel)
        return coordinator, scheduled, cancelled

    def test_schedule_transition_fires_after_delay(self) -> None:
        coordinator, scheduled, _ = self._make_coordinator()
        applied: list[str] = []

        coordinator.schedule_transition("status", 200, lambda: applied.append("done"))

        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0][0], 200)
        self.assertEqual(applied, [])

        scheduled[0][1]()  # fire the timer
        self.assertEqual(applied, ["done"])

    def test_schedule_transition_supersedes_pending(self) -> None:
        coordinator, scheduled, cancelled = self._make_coordinator()
        applied: list[str] = []

        coordinator.schedule_transition("status", 200, lambda: applied.append("first"))
        coordinator.schedule_transition("status", 200, lambda: applied.append("second"))

        self.assertEqual(len(cancelled), 1, "first timer must be cancelled")
        self.assertEqual(len(scheduled), 2)

        scheduled[1][1]()  # fire only the second timer
        self.assertEqual(applied, ["second"])

    def test_schedule_transition_different_names_are_independent(self) -> None:
        coordinator, scheduled, cancelled = self._make_coordinator()
        applied: list[str] = []

        coordinator.schedule_transition("status", 200, lambda: applied.append("status"))
        coordinator.schedule_transition("peer", 100, lambda: applied.append("peer"))

        self.assertEqual(len(cancelled), 0, "different names must not cancel each other")
        self.assertEqual(len(scheduled), 2)

    def test_cancel_transition_prevents_apply(self) -> None:
        coordinator, scheduled, cancelled = self._make_coordinator()
        applied: list[str] = []

        coordinator.schedule_transition("status", 200, lambda: applied.append("done"))
        coordinator.cancel_transition("status")

        self.assertEqual(len(cancelled), 1)
        scheduled[0][1]()  # fire the timer — apply must not run (id already cleared)
        self.assertEqual(applied, [])

    def test_cancel_transition_unknown_name_is_safe(self) -> None:
        coordinator, _, _ = self._make_coordinator()
        coordinator.cancel_transition("nonexistent")  # must not raise

    def test_shutdown_cancels_all_pending_transitions(self) -> None:
        coordinator, scheduled, cancelled = self._make_coordinator()

        coordinator.schedule_transition("status", 200, lambda: None)
        coordinator.schedule_transition("peer", 100, lambda: None)

        coordinator.shutdown()

        self.assertEqual(len(cancelled), 2, "shutdown must cancel all pending transitions")

    def test_no_schedule_callable_means_transitions_are_noop(self) -> None:
        coordinator = UICoordinator()  # no schedule/cancel injected
        coordinator.schedule_transition("status", 200, lambda: None)  # must not raise
        coordinator.cancel_transition("status")  # must not raise
        coordinator.shutdown()  # must not raise
```

- [ ] **Step 2: Run the tests to verify they fail**

```
pytest tests/test_render_coordinator.py::UICoordinatorTransitionTests -x -q
```

Expected: `AttributeError: 'UICoordinator' object has no attribute 'schedule_transition'`

- [ ] **Step 3: Add the import to `render_coordinator.py`**

At the top of `maintenance/ui/render_coordinator.py`, after the existing imports, add:

```python
from maintenance.ui.transition import PendingTransition
```

- [ ] **Step 4: Extend `UICoordinator.__init__`**

In `render_coordinator.py`, change the `__init__` signature and body:

```python
def __init__(
    self,
    *,
    schedule: Callable[[int, Callable[[], None]], Any] | None = None,
    cancel: Callable[[Any], bool] | None = None,
    observer: ObservabilityWatcher | None = None,
) -> None:
    self._pending: dict[str, _PendingRender] = {}
    self._visible: dict[str, bool] = {}
    self._generations: dict[str, int] = {}
    self._target_nodes: dict[str, Any | None] = {}
    self._batch_depth = 0
    self._flushing = False
    self._closed = False
    self.pending_peak = 0
    self.last_commit_seconds = 0.0
    self._observer = observer or ObservabilityWatcher()
    self._schedule = schedule or (lambda _delay, _callback: None)
    self._cancel = cancel or (lambda _identifier: False)
    self._transitions: dict[str, PendingTransition] = {}
```

- [ ] **Step 5: Add `schedule_transition` and `cancel_transition` methods**

Add these two methods after `shutdown()` in `UICoordinator`:

```python
def schedule_transition(
    self, name: str, delay: int, apply: Callable[[], None]
) -> None:
    """Schedule a named delayed callback, superseding any pending one of the same name."""
    if name not in self._transitions:
        self._transitions[name] = PendingTransition(self._schedule, self._cancel)
    self._transitions[name].start(delay, apply)

def cancel_transition(self, name: str) -> None:
    """Cancel a pending transition by name; safe when nothing is pending."""
    transition = self._transitions.get(name)
    if transition is not None:
        transition.cancel()
```

- [ ] **Step 6: Extend `shutdown()` to cancel all transitions**

Change the existing `shutdown()` method:

```python
def shutdown(self) -> None:
    self._closed = True
    self.clear()
    for transition in self._transitions.values():
        transition.cancel()
    self._transitions.clear()
```

- [ ] **Step 7: Run the new tests to verify they pass**

```
pytest tests/test_render_coordinator.py -x -q
```

Expected: all tests pass including the new `UICoordinatorTransitionTests`.

- [ ] **Step 8: Commit**

```bash
git add maintenance/ui/render_coordinator.py tests/test_render_coordinator.py
git commit -m "feat: UICoordinator gains schedule_transition / cancel_transition

Embeds PendingTransition management into UICoordinator so callers with
a render coordinator reference can schedule named delayed callbacks
without wiring separate PendingTransition instances. Each named slot is
a real PendingTransition created on first use; shutdown() cancels all
pending transitions alongside clearing the render queue."
```

---

## Task 2: Pass timer callables to `UICoordinator` at construction

**Files:**
- Modify: `window.py` line ~248

The `UICoordinator` is constructed before the window is fully open but `_schedule_timer` and `_cancel_timer` are available immediately via `self` — lambdas are safe because they are only invoked at transition time (after full init).

- [ ] **Step 1: Write the test first**

This is a wiring change; the integration is covered by the transition tests in Task 1 plus the migration test in Task 3. No new unit test is needed here beyond verifying the app starts cleanly.

- [ ] **Step 2: Update `UICoordinator` construction in `window.py`**

Find line ~248:
```python
self._ui_coordinator = ui_render.UICoordinator(observer=self._observer)
```

Change to:
```python
self._ui_coordinator = ui_render.UICoordinator(
    schedule=lambda delay, callback: self._schedule_timer(delay, callback),
    cancel=lambda identifier: self._cancel_timer(identifier),
    observer=self._observer,
)
```

- [ ] **Step 3: Run the full test suite**

```
pytest tests/ -x -q --ignore=tests/test_ui
```

Expected: all existing tests pass (no behaviour change yet).

- [ ] **Step 4: Commit**

```bash
git add window.py
git commit -m "wiring: inject schedule/cancel into UICoordinator at construction

Passes the window's _schedule_timer/_cancel_timer callables into
UICoordinator so named transitions scheduled through it use the same
Tk timer infrastructure as the rest of the window. Lambdas are used
so the binding is deferred until first use, safe at __init__ time."
```

---

## Task 3: Migrate `_completion_transition` to `UICoordinator`

**Files:**
- Modify: `maintenance/ui/window_lifecycle.py`
- Modify: `maintenance/ui/window_presentation.py`
- Modify: `window.py`

This is the only existing `PendingTransition` call site. After this task, `ui_transition` is no longer imported in `window_lifecycle.py`.

- [ ] **Step 1: Write the migration test first**

Add to `tests/test_render_coordinator.py` inside `UICoordinatorTransitionTests`:

```python
def test_completion_slot_supersedes_on_new_scan(self) -> None:
    """Models the scan-complete → new-scan flow: the hold timer is cancelled."""
    coordinator, scheduled, cancelled = self._make_coordinator()
    applied: list[str] = []

    # scan completes — schedule the hold
    coordinator.schedule_transition(
        "completion", 3000, lambda: applied.append("ready")
    )
    self.assertEqual(len(scheduled), 1)

    # new scan starts before hold fires — cancel the transition
    coordinator.cancel_transition("completion")
    self.assertEqual(len(cancelled), 1)

    # hold timer fires late — apply must NOT run (PendingTransition clears id on cancel)
    scheduled[0][1]()
    self.assertEqual(applied, [])
```

- [ ] **Step 2: Run the test to verify it passes** (it tests existing `UICoordinator` behaviour, should pass immediately)

```
pytest tests/test_render_coordinator.py::UICoordinatorTransitionTests::test_completion_slot_supersedes_on_new_scan -x -q
```

Expected: PASS.

- [ ] **Step 3: Update `window_presentation.py` — replace `.start()` call**

Find in `maintenance/ui/window_presentation.py` (~line 58):
```python
controller._completion_transition().start(
    controller.COMPLETION_HOLD_MILLISECONDS,
    controller._show_ready_after_completion_hold,
)
```

Replace with:
```python
render = controller._render_coordinator()
if render is not None:
    render.schedule_transition(
        "completion",
        controller.COMPLETION_HOLD_MILLISECONDS,
        controller._show_ready_after_completion_hold,
    )
```

- [ ] **Step 4: Update `window_lifecycle.py` — replace two `.cancel()` calls**

In `set_busy()` (~line 151):
```python
controller._completion_transition().cancel()
```
Replace with:
```python
render = controller._render_coordinator()
if render is not None:
    render.cancel_transition("completion")
```

In `reset_progress_bar()` (~line 341):
```python
controller._completion_transition().cancel()
```
Replace with:
```python
render = controller._render_coordinator()
if render is not None:
    render.cancel_transition("completion")
```

- [ ] **Step 5: Remove `completion_transition()` helper from `window_lifecycle.py`**

Delete the entire function (~lines 169–175):
```python
def completion_transition(controller: Any) -> ui_transition.PendingTransition:
    return controller.__dict__.setdefault(
        "_completion_transition_obj",
        ui_transition.PendingTransition(
            controller._schedule_timer, controller._cancel_timer
        ),
    )
```

- [ ] **Step 6: Remove the `ui_transition` import from `window_lifecycle.py`**

Remove line ~17:
```python
from maintenance.ui import transition as ui_transition
```

- [ ] **Step 7: Remove `_completion_transition()` method from `window.py`**

Delete lines ~998–999:
```python
def _completion_transition(self) -> ui_transition.PendingTransition:
    return ui_window_lifecycle.completion_transition(self)
```

Also remove the `ui_transition` import in `window.py` if it's no longer used anywhere else:

```bash
grep -n "ui_transition\|from maintenance.ui import transition" window.py
```

Remove only if the result shows no other uses.

- [ ] **Step 8: Run the full test suite**

```
pytest tests/ -x -q --ignore=tests/test_ui
```

Expected: all tests pass.

- [ ] **Step 9: Commit**

```bash
git add maintenance/ui/window_lifecycle.py maintenance/ui/window_presentation.py window.py tests/test_render_coordinator.py
git commit -m "refactor: migrate completion_transition to UICoordinator.schedule_transition

Removes the standalone PendingTransition instance (_completion_transition_obj)
wired in window_lifecycle.py. The completion hold is now scheduled through
UICoordinator so shutdown() cancels it automatically alongside the render
queue. completion_transition() helper, _completion_transition() window method,
and the ui_transition import in window_lifecycle.py are all removed.

No behaviour change: PendingTransition is used as-is internally; supersede
and cancel semantics are identical."
```

---

## Task 4: Final review and version bump

- [ ] **Step 1: Verify no stale references remain**

```bash
grep -rn "_completion_transition\|completion_transition" maintenance/ window.py
grep -rn "from maintenance.ui import transition" maintenance/ window.py
```

Expected: no results (transition.py itself is fine — it's a standalone module, just no longer imported from the window layer).

- [ ] **Step 2: Run the full test suite one final time**

```
pytest tests/ -q --ignore=tests/test_ui
```

Expected: all tests pass including the new transition tests.

- [ ] **Step 3: Build wheel**

```bash
python3 -m maintenance._release prepare-build --package-dir .
source .venv/bin/activate && python3 -m build --wheel --no-isolation -q
python3 -m maintenance._release sync-artifacts --package-dir .
```

- [ ] **Step 4: Commit and push**

```bash
git add dist/ maintenance/_version.py
git commit -m "chore: bump version for UICoordinator transition management"
git push
```

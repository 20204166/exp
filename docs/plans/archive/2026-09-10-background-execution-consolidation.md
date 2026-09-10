# Background Execution Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete one bounded audit and low-risk consolidation pass over System Analyzer's asynchronous execution paths without collapsing specialized lifecycles.

**Architecture:** Treat `AppCoordinator` plus its injected runner and delivery callback as the canonical general-purpose application mechanism. Keep dashboard scan lifecycle, dialog lifetime, scanner sensor workers, remote socket admission, and Tk timer delivery as specialized owners. Migrate only the two proven internal legacy callers, Storage cleanup and manual Test Connection, to existing coordinator instances; do not add another coordinator or executor abstraction.

**Tech Stack:** Python 3.10+, Tkinter, `threading`, `concurrent.futures.ThreadPoolExecutor`, `queue.Queue`, `unittest`, Ruff, Pyright, Mypy.

---

## Scope Check

This is intentionally one cross-cutting audit because the deliverable is ownership
mapping plus one bounded consolidation. It is not a request to redesign five
independent subsystems. The implementation boundary is narrow enough to produce
working software without unifying unrelated lifecycles.

## File Structure And Responsibilities

- Modify: `maintenance/dialogs.py` — route Storage `move_to_trash` through the
  dialog's existing `AppCoordinator`; retain specialized result rendering and
  confirmation behavior.
- Modify: `maintenance/ui/window_node_actions.py` — route manual authenticated
  `test_connection` through the window's existing `AppCoordinator` while
  preserving node identity/error wording.
- Modify: `window.py:447-455` — stop injecting the legacy dialog runner into
  manual Test Connection.
- Modify: `tests/test_storage_dialog.py` — characterize success, error,
  cancellation/close, stale delivery, submission failure, and repeated action
  ownership for the migrated path.
- Modify: `tests/test_window_nodes.py` — characterize manual connection
  submission, success/error delivery, and stale node cancellation.
- Modify: `tests/test_components.py` — add the missing canonical coordinator
  failed-submission and bounded-state assertions.
- Test: `tests/test_lifecycle_stress.py` — run existing bounded repeated
  start/stop coverage; no change is planned because `AppCoordinator` already
  has state-growth and cancellation stress tests.
- Create: `docs/BACKGROUND_EXECUTION_AUDIT_2026-09-10.md` — final path-by-path
  audit and consolidation report, including findings deliberately kept separate.
- Do not modify: `maintenance/components/coordinator.py` unless a focused test
  proves an existing canonical failure path is incorrect; it already owns the
  general worker submission, generation, cancellation, result delivery, and
  executor shutdown mechanisms.

## Current Execution-Path Inventory

| Path | Owner | Classification | Decision |
|---|---|---|---|
| Per-key application work | `AppCoordinator` | Canonical general mechanism | Reuse as-is; test missing submission edge. |
| Dashboard full scan | `DashboardScanLifecycle` + `BackgroundOrchestrator` | Specialized lifecycle | Keep separate for progress, timeout, grace lease, rerun, and busy state. |
| Process/storage dialog scans and process actions | `AppCoordinator` | Canonical mechanism with specialized dialog meaning | Keep dialog callbacks and keys; reuse coordinator. |
| Storage Move to Trash | `BackgroundTaskRunner` from `dialogs.py` | Duplicated/legacy internal mechanism | Migrate this caller to the dialog `AppCoordinator`. |
| Manual Test Connection | `window_node_actions.test_connection` -> `dialogs.run_in_thread` | Duplicated/legacy internal mechanism | Migrate this caller to the window `AppCoordinator` with a node-qualified key. |
| CPU sampler | `SystemScanner` / `scanner_support/dashboard.py` | Specialized persistent worker | Keep one request worker; it is not an application task executor. |
| GPU probe | `scanner_support/gpu.py` | Specialized bounded probe worker | Keep timeout, abandon generation, and no-join semantics. |
| Remote socket server | `RemoteSocketServer` | Specialized bounded request lifecycle | Keep bounded semaphore, framed I/O, timeout, and daemon handlers. |
| Tk delivery | `AppCoordinator.deliver`, `BackgroundOrchestrator` queue, `TkDeliveryQueue`, `TimerDelivery` | Multiple specialized delivery seams | Keep each seam; workers must never call Tk directly. |

The audit must record owner, work, thread model, queueing, concurrency limit,
cancellation, timeout, result delivery, Tk handoff, shutdown, stale-result and
node binding, tests, and verification status for every row above.

## Classification Rules

- **Canonical general mechanism:** reusable submission, exception, cancellation,
  generation, delivery, or shutdown behavior already owned by `AppCoordinator`.
- **Specialized lifecycle:** state that encodes product semantics such as a
  dashboard timeout lease, dialog ownership, sensor request protocol, or remote
  admission.
- **Duplicated mechanism:** an internal caller independently performs general
  task submission/delivery where an existing owner already provides it.
- **Legacy/redundant:** compatibility surface with no production caller after
  migration; preserve only when repository exports or tests require it.
- **Not verified:** behavior not demonstrated by source inspection or a test.

### Task 1: Establish The Audit Baseline

**Files:**
- Create: `docs/BACKGROUND_EXECUTION_AUDIT_2026-09-10.md`
- Test: existing path-specific tests listed in the steps below

- [ ] **Step 1: Record the current worker and delivery inventory**

Run:

```bash
rg -n "ThreadPoolExecutor|threading\.Thread|Thread\(|Queue\[|\.after\(|socketserver|BoundedSemaphore" maintenance window.py tests
```

Expected: matches for `AppCoordinator`, `BackgroundOrchestrator`,
`BackgroundTaskRunner`, `DashboardScanLifecycle`, CPU/GPU workers, remote
handlers, and Tk delivery seams. Do not treat every match as duplication.

- [ ] **Step 2: Run focused characterization tests before editing**

Run:

```bash
python -m unittest tests.test_components tests.test_background_orchestration tests.test_dashboard_scan tests.test_storage_dialog tests.test_lifecycle_stress -v
```

Expected: PASS. If a baseline test fails, record the exact failing test in the
audit report and stop before changing asynchronous behavior.

- [ ] **Step 3: Write the audit report skeleton**

Create `docs/BACKGROUND_EXECUTION_AUDIT_2026-09-10.md` with these completed
headings and the inventory table from this plan:

```markdown
# Background Execution Audit

**Scope:** One bounded consolidation pass; current repository is authoritative.

## Execution Paths
## Ownership And Semantics Matrix
## Duplicate Mechanisms Proven
## Mechanisms Kept Separate
## Consolidation Performed
## Boundedness And Shutdown
## Tk Delivery Verification
## Tests And Results
## Unresolved Risks
## Working-Tree Status
```

Populate the first two sections from source and tests only. Mark a field
`NOT VERIFIED` when no source or test proves it; do not infer guarantees from
class names.

- [ ] **Step 4: Commit the baseline audit artifact**

```bash
git add docs/BACKGROUND_EXECUTION_AUDIT_2026-09-10.md
git commit -m "docs: map background execution paths"
```

Expected: one documentation-only commit containing the baseline inventory.

### Task 2: Prove The Canonical Coordinator Submission Edge

**Files:**
- Modify: `tests/test_components.py:1280-1410` — extend `AppCoordinatorRunTests`.
- Modify: `maintenance/components/coordinator.py:408-436` only if the new
  test demonstrates a bug in the existing failed-submission path.

- [ ] **Step 1: Add the failed-submission characterization test**

Add this test to `AppCoordinatorRunTests`:

```python
def test_failed_submission_delivers_error_and_settles_run(self) -> None:
    delivered: list[object] = []

    def reject(_worker: object) -> None:
        raise RuntimeError("executor closed")

    coordinator = AppCoordinator(
        runner=reject,
        deliver=lambda callback: (delivered.append(callback), callback())[1],
    )
    errors: list[str] = []

    generation = coordinator.run(
        "storage",
        lambda _event, _progress: "never runs",
        on_error=lambda _key, message: errors.append(message),
    )

    self.assertEqual(generation, 1)
    self.assertEqual(errors, ["executor closed"])
    self.assertFalse(coordinator.in_flight("storage"))
    self.assertEqual(len(delivered), 1)
```

- [ ] **Step 2: Run the new test and confirm the current behavior**

Run:

```bash
python -m unittest tests.test_components.AppCoordinatorRunTests.test_failed_submission_delivers_error_and_settles_run -v
```

Expected: PASS against the current implementation. A passing test proves this
mechanism already belongs to `AppCoordinator`; do not extract a second helper.

- [ ] **Step 3: Add repeated failed-submission boundedness coverage**

Add this test:

```python
def test_repeated_failed_submissions_do_not_grow_state(self) -> None:
    coordinator = AppCoordinator(
        runner=lambda _worker: (_ for _ in ()).throw(RuntimeError("closed")),
        deliver=lambda callback: callback(),
    )

    for _ in range(200):
        coordinator.run("storage", lambda _event, _progress: None)

    self.assertEqual(len(coordinator._states), 1)
    self.assertFalse(coordinator.has_pending_work)
    self.assertIsNone(coordinator.state("storage").cancel_event)
```

- [ ] **Step 4: Run the focused coordinator tests**

```bash
python -m unittest tests.test_components.AppCoordinatorRunTests tests.test_lifecycle_stress.AppCoordinatorStressTests -v
```

Expected: PASS with no implementation change. If a code change is necessary,
keep it inside the existing `_start_run` submission/settlement path and show
that the same tests pass before continuing.

- [ ] **Step 5: Commit the canonical-mechanism tests**

```bash
git add tests/test_components.py
git commit -m "test: cover coordinator submission settlement"
```

### Task 3: Migrate Storage Cleanup To The Existing Coordinator

**Files:**
- Modify: `maintenance/dialogs.py:1330-1675` — add a node-qualified trash
  operation key, track dialog closure, and replace `run_in_thread` in
  `StorageDialog.move_selected` with `AppCoordinator.run`.
- Modify: `tests/test_storage_dialog.py:173-549` — replace the direct-thread
  test seam and add coordinator lifecycle tests; import `FileActionResult` from
  `maintenance.models` alongside `FileCandidate`.

- [ ] **Step 1: Add a failing test for coordinator-owned trash work**

Replace the direct `run_in_thread` patch in
`test_move_selected_passes_all_selected_files_to_manager` with a deferred
coordinator and assert the task is pending before it is executed:

```python
runner = DeferredRunner()
dialog.coordinator = AppCoordinator(
    runner=runner,
    deliver=lambda callback: callback(),
)
dialog._operation_key = "storage"
dialog._trash_operation_key = "storage_trash"
dialog._closed = False
dialog._trash_active = False
dialog._on_close = Mock()
dialog._read_only = False
dialog.on_changed = Mock()
dialog.scan = Mock()

with patch("maintenance.dialogs.messagebox.askyesno", return_value=True):
    with patch("maintenance.dialogs.messagebox.showinfo"):
        dialog.move_selected()

self.assertTrue(dialog._trash_active)
self.assertTrue(dialog.coordinator.in_flight("storage_trash"))
self.assertEqual(manager.paths, [])
runner.run_next()
self.assertEqual(manager.paths, [first, second])
self.assertFalse(dialog.coordinator.in_flight("storage_trash"))
```

Expected before implementation: the test fails because `move_selected` still
calls the legacy `run_in_thread` path and does not claim `storage_trash`.

- [ ] **Step 2: Add the dialog state required by the new key**

In `StorageDialog.__init__`, immediately after `_operation_key`, add:

```python
self._trash_operation_key = operation_key(node_id, "storage_trash")
self._closed = False
self._trash_active = False
```

Keep `_operation_key` unchanged for shared Downloads scanning. The cleanup
operation must not coalesce with a scan or with another node's cleanup.

- [ ] **Step 3: Replace `move_selected`'s direct thread submission**

Replace the `run_in_thread(...)` call at the end of `StorageDialog.move_selected`
with this coordinator submission:

```python
if self._trash_active or self._closed:
    return


def trash_task(
    _cancel_event: threading.Event,
    _progress: Callable[[str], None],
) -> FileActionResult:
    return self.manager.move_to_trash(paths)


self._trash_active = True
self.coordinator.run(
    self._trash_operation_key,
    trash_task,
    on_result=lambda _key, result: self._after_trash(result),
    on_error=lambda _key, message: self._after_trash_error(message),
)
```

The coordinator owns worker submission, exception capture, generation checks,
and UI delivery. The dialog still owns the destructive-action confirmation,
button state, user-facing message, refresh, and file-action semantics.

- [ ] **Step 4: Add result and close guards**

Replace `_after_trash` with the guarded implementation and add the error helper:

```python
def _after_trash(self, result: FileActionResult) -> None:
    self._trash_active = False
    if self._closed:
        return
    show_action_result(
        self,
        "Storage Cleanup",
        f"Moved {len(result.moved)} file(s) to Trash.",
        result.errors,
    )
    self.on_changed()
    self.scan()


def _after_trash_error(self, message: str) -> None:
    self._trash_active = False
    if not self._closed:
        self._show_error(message)
```

Update `_close` so every close path, including an injected owner callback,
invalidates the trash operation before the dialog is destroyed:

```python
def _close(self) -> None:
    self._closed = True
    self.coordinator.cancel(self._trash_operation_key)
    self._on_close()
```

Keep `_default_close` as the existing scan unsubscribe/cancel/destroy callback;
`_close` is the single dialog entry point that adds the trash cancellation.

- [ ] **Step 5: Run the migrated Storage tests**

```bash
python -m unittest tests.test_storage_dialog -v
```

Expected: PASS, including the existing shared-scan tests and the new deferred
cleanup test. No test should patch `BackgroundTaskRunner` for the production
Storage cleanup path.

- [ ] **Step 6: Add failure, close, stale, and repeated-start tests**

Add these cases to `StorageDialogCoordinatorTests` using `DeferredRunner` and
`object.__new__(StorageDialog)` fixtures:

```python
def test_trash_exception_returns_to_dialog_error(self) -> None:
    runner = DeferredRunner()
    dialog = self._dialog()
    dialog.coordinator = AppCoordinator(runner=runner, deliver=lambda cb: cb())
    dialog._trash_operation_key = "storage_trash"
    dialog._trash_active = False
    dialog._closed = False
    dialog._show_error = Mock()
    dialog.manager = Mock(move_to_trash=Mock(side_effect=RuntimeError("denied")))
    dialog.tree = FakeTree(("0",))
    dialog.candidates = {
        "0": FileCandidate(Path("x"), 1, datetime.now(timezone.utc), "large")
    }
    dialog.scan_button = FakeControl()
    dialog.trash_button = FakeControl()
    dialog.status_label = FakeControl()

    with patch("maintenance.dialogs.messagebox.askyesno", return_value=True):
        dialog.move_selected()
    runner.run_next()

    dialog._show_error.assert_called_once_with("denied")
    self.assertFalse(dialog._trash_active)


def test_close_cancels_trash_and_late_result_is_ignored(self) -> None:
    runner = DeferredRunner()
    dialog = self._dialog()
    dialog.coordinator = AppCoordinator(runner=runner, deliver=lambda cb: cb())
    dialog._trash_operation_key = "storage_trash"
    dialog._closed = False
    dialog._trash_active = False
    dialog._show_error = Mock()
    dialog.on_changed = Mock()
    dialog.destroy = Mock()
    dialog.tree = FakeTree(("0",))
    dialog.candidates = {
        "0": FileCandidate(Path("x"), 1, datetime.now(timezone.utc), "large")
    }
    dialog.manager = Mock(move_to_trash=lambda _paths: FileActionResult(1, (), ()))
    dialog.scan = Mock()
    dialog._read_only = False

    with patch("maintenance.dialogs.messagebox.askyesno", return_value=True):
        dialog.move_selected()
    self.assertEqual(runner.pending, 1)
    cancel_event = dialog.coordinator.state("storage_trash").cancel_event
    self.assertIsNotNone(cancel_event)
    dialog._on_close = dialog._default_close
    dialog._close()
    self.assertTrue(dialog._closed)
    self.assertTrue(cancel_event.is_set())  # type: ignore[union-attr]
    with patch("maintenance.dialogs.show_action_result") as show_result:
        runner.run_next()
    dialog.on_changed.assert_not_called()
    dialog.scan.assert_not_called()
    show_result.assert_not_called()
```

The close test must also start a deferred task before calling `_close`;
then execute the deferred worker and assert `on_changed` and
`show_action_result` are not called. Add a repeated `move_selected()` assertion
that `len(runner.workers) == 1` while `_trash_active` is true.

- [ ] **Step 7: Run lint and the complete dialog/coordinator suite**

```bash
python -m unittest tests.test_storage_dialog tests.test_components tests.test_lifecycle_stress -v
ruff check maintenance/dialogs.py tests/test_storage_dialog.py tests/test_components.py
ruff format --check maintenance/dialogs.py tests/test_storage_dialog.py tests/test_components.py
```

Expected: all tests pass and both Ruff commands exit 0.

- [ ] **Step 8: Commit the bounded migration**

```bash
git add maintenance/dialogs.py tests/test_storage_dialog.py tests/test_components.py
git commit -m "refactor: route storage actions through app coordinator"
```

### Task 4: Migrate Manual Test Connection To The Window Coordinator

**Files:**
- Modify: `maintenance/ui/window_node_actions.py:469-529` — replace the
  `run_in_thread_fn` submission with the controller's existing `AppCoordinator`.
- Modify: `tests/test_window_nodes.py` — add deterministic coordinator tests for
  submission, success, failure, cancellation, and stale node delivery.

- [ ] **Step 1: Add a failing test for node-qualified coordinator submission**

Create a focused test fixture with a fake cluster record, a deferred runner,
`window._coordinator = AppCoordinator(runner=runner, deliver=lambda cb: cb())`,
and a fake `provider_cls` returning `{"node_id": "peer-a", "app_version": "x"}`.
Call `window_node_actions.test_connection(window, "peer-a", provider_cls=provider,
transport_cls=Mock)` and assert:

```python
self.assertEqual(runner.pending, 1)
self.assertTrue(window._coordinator.in_flight("node:peer-a:test_connection"))
```

Expected before implementation: FAIL because the function invokes the injected
legacy `run_in_thread_fn` instead of claiming a coordinator key.

- [ ] **Step 2: Submit the manual connection task through `AppCoordinator`**

Import `node_operation_key` in `maintenance/ui/window_node_actions.py`, remove
the `run_in_thread_fn` parameter, and replace the final `run_in_thread_fn(...)`
call with:

```python
key = node_operation_key(node, "test_connection")


def coordinated_task(
    _cancel_event: threading.Event,
    _progress: Callable[[str], None],
) -> dict[str, Any]:
    return task()


controller._coordinator.run(
    key,
    coordinated_task,
    on_result=lambda _key, result: on_success(result),
    on_error=lambda _key, message: on_error(message),
)
```

Repository search finds only the internal `window.py` caller, so remove the
`run_in_thread_fn` parameter and its call-site argument. Preserve all existing
authenticated hello and identity validation in `on_success`; this change shares
submission and delivery only.

- [ ] **Step 3: Add success, error, cancellation, and stale-node tests**

Add these assertions to `tests/test_window_nodes.py`:

```python
runner.run_next()
messagebox.showinfo.assert_called_once()

provider_cls.side_effect = RuntimeError("connection refused")
window_node_actions.test_connection(
    window, "peer-a", provider_cls=provider_cls, transport_cls=Mock
)
runner.run_next()
messagebox.showerror.assert_called_once()

window._coordinator.cancel("node:peer-a:test_connection")
self.assertTrue(
    window._coordinator.state("node:peer-a:test_connection").cancel_event.is_set()
)
runner.run_next()
messagebox.showinfo.assert_not_called()
```

Use separate fresh fixtures for each case. For stale delivery, start one run,
cancel it, start a replacement under the same key, execute the old deferred
worker first, and assert that only the replacement result can show success.
This proves node-qualified generation handling without touching Tk.

- [ ] **Step 4: Run and commit the manual connection migration**

```bash
python -m unittest tests.test_window_nodes -v
ruff check maintenance/ui/window_node_actions.py tests/test_window_nodes.py
ruff format --check maintenance/ui/window_node_actions.py tests/test_window_nodes.py
git add maintenance/ui/window_node_actions.py tests/test_window_nodes.py
git commit -m "refactor: coordinate manual connection checks"
```

Expected: tests and both Ruff commands pass; one commit contains only the
manual connection migration and its tests.

### Task 5: Verify Specialized Lifecycles Were Not Collapsed

**Files:**
- Test: `tests/test_dashboard_scan.py` — dashboard timeout, grace, rerun, and
  stale-generation behavior.
- Test: `tests/test_gpu_concurrency.py` — GPU timeout, abandon, and stop behavior.
- Test: `tests/test_cpu_sampling.py` — persistent CPU worker and idempotent stop.
- Test: `tests/test_remote_contract.py` — bounded handler admission and shutdown.
- Test: `tests/test_network_discovery.py`, `tests/test_discovery_session.py` —
  repeated start/stop and late-event shutdown behavior.
- Test: `tests/test_window.py`, `tests/test_window_nodes.py` — application
  shutdown and node-stale delivery behavior.
- Modify: `docs/BACKGROUND_EXECUTION_AUDIT_2026-09-10.md` — record proof and
  deliberate non-migrations.

- [ ] **Step 1: Run the specialized lifecycle tests**

```bash
python -m unittest tests.test_dashboard_scan tests.test_gpu_concurrency tests.test_cpu_sampling tests.test_remote_contract tests.test_network_discovery tests.test_discovery_session tests.test_window tests.test_window_nodes -v
```

Expected: PASS. These tests must remain on their existing owners; do not route
sensor probes or remote request handlers through `AppCoordinator`.

- [ ] **Step 2: Verify dashboard ownership from the source**

Confirm `DashboardScanLifecycle.start` still creates the cancellation event,
schedules timeout/grace timers, and delegates only worker start. Confirm
`BackgroundOrchestrator` still owns dashboard queue polling, task counts, busy
state, and render batching. Record the following in the audit report:

| Concern | Owner | Preserved reason |
|---|---|---|
| Scan generation/rerun | `DashboardScanLifecycle` + `ScanCoordinator` | Manual scan semantics. |
| Timeout/grace lease | `DashboardScanLifecycle` | A timed-out worker cannot overlap a replacement scan. |
| Dashboard queue/task count | `BackgroundOrchestrator` | Legacy dashboard callback protocol and busy indicator. |
| Snapshot render | `UICoordinator` and window render callbacks | Tk presentation and node-generation gating. |

- [ ] **Step 3: Verify scanner worker boundedness**

Confirm CPU uses one persistent request worker per scanner and GPU refuses to
stack probes while one is in flight, abandons only after its explicit budget,
and invalidates late completion with a generation. Record that these are
specialized sensor protocols, not duplicated application submission.

- [ ] **Step 4: Verify remote handler boundedness**

Confirm `RemoteSocketServer` retains `BoundedSemaphore`, `request_queue_size`,
socket timeout, maximum frame size, daemon handler threads, and
`block_on_close = False`. Record that each accepted request is bounded and
over-admission is rejected, while provider cancellation remains cooperative.

- [ ] **Step 5: Verify shutdown ordering**

Confirm `maintenance/ui/window_lifecycle.py:finalize_shutdown` still stops the
peer server and discovery, shuts down peer connections, cancels dashboard
lifecycle and all `AppCoordinator` work, calls `AppCoordinator.shutdown`, stops
node scanner workers, cancels Tk timers, and shuts down render delivery. Record
that `AppCoordinator.shutdown(wait=False, cancel_futures=True)` does not claim
to join uninterruptible sensor or provider calls.

- [ ] **Step 6: Commit the specialized-lifecycle evidence**

```bash
git add docs/BACKGROUND_EXECUTION_AUDIT_2026-09-10.md
git commit -m "docs: record preserved async lifecycles"
```

### Task 6: Complete Tk-Handoff And Stale-Result Verification

**Files:**
- Modify: `tests/test_storage_dialog.py` — add main-thread delivery and stale
  close assertions.
- Test: `tests/test_components.py`, `tests/test_background_orchestration.py`,
  `tests/test_render_coordinator.py`, `tests/test_window_nodes.py`.
- Modify: `docs/BACKGROUND_EXECUTION_AUDIT_2026-09-10.md` — add the handoff
  evidence table.

- [ ] **Step 1: Add a Storage coordinator delivery-boundary test**

Use a delivery callback that records the current thread and executes callbacks,
then run the deferred worker. Assert the manager runs in the worker callback,
the result callback runs only through `deliver`, and no callback is invoked
after `_closed` becomes true:

```python
def test_trash_delivery_stays_on_injected_ui_boundary(self) -> None:
    runner = DeferredRunner()
    delivery_threads: list[threading.Thread] = []

    def deliver(callback: Callable[[], None]) -> None:
        delivery_threads.append(threading.current_thread())
        callback()

    dialog = self._dialog()
    dialog.coordinator = AppCoordinator(runner=runner, deliver=deliver)
    dialog._trash_operation_key = "storage_trash"
    dialog._trash_active = False
    dialog._closed = False
    dialog.tree = FakeTree(("0",))
    dialog.candidates = {
        "0": FileCandidate(Path("x"), 1, datetime.now(timezone.utc), "large")
    }
    dialog.manager = Mock(move_to_trash=lambda _paths: FileActionResult(1, (), ()))
    dialog.scan = Mock()
    dialog.on_changed = Mock()
    dialog._read_only = False
    with patch("maintenance.dialogs.messagebox.askyesno", return_value=True):
        dialog.move_selected()

    self.assertEqual(runner.pending, 1)
    self.assertTrue(dialog.coordinator.in_flight("storage_trash"))
    dialog._closed = True
    dialog.coordinator.cancel("storage_trash")
    self.assertIsNotNone(dialog.coordinator.state("storage_trash").cancel_event)
    assert dialog.coordinator.state("storage_trash").cancel_event is not None
    self.assertTrue(dialog.coordinator.state("storage_trash").cancel_event.is_set())
    runner.run_next()
    self.assertTrue(
        all(thread is threading.main_thread() for thread in delivery_threads)
    )
    dialog.on_changed.assert_not_called()
```

The test must not create a live Tk root.

- [ ] **Step 2: Run all existing delivery and stale-generation tests**

```bash
python -m unittest tests.test_components tests.test_background_orchestration tests.test_render_coordinator tests.test_window_nodes tests.test_storage_dialog -v
```

Expected: PASS. The evidence must cover worker result -> injected delivery ->
main-thread callback, UI destruction before result, stale node generation, and
late callback suppression.

- [ ] **Step 3: Write the handoff table in the audit report**

Add this completed handoff table and replace a named test only when the
implementation adds a more precise test:

| Path | Worker emits | Delivery seam | Stale/closed guard | Evidence |
|---|---|---|---|---|
| AppCoordinator operation | result/error/progress | injected `deliver` | key generation and cancelled state | `test_run_delivers_progress_and_result_through_delivery`, `test_failed_submission_delivers_error_and_settles_run` |
| Dashboard scan | snapshot/error/finished marker | `BackgroundOrchestrator` queue + `TimerDelivery` | scan generation/node id/closing | `test_timeout_reports_immediately_and_worker_completion_releases_lease`, `test_late_scan_completion_after_timeout_is_dropped` |
| Dialog standalone fallback | result/error/progress | `TkDeliveryQueue` | widget destroy/closed state | `test_real_tk_delivery_queue_never_calls_after_from_worker`, `test_run_ignores_runtime_error_during_widget_teardown` |
| Remote handler | framed response | socket, never Tk | request auth and service bounds | `test_socket_server_shutdown_releases_handler_permits`, `test_cancelled_request_raises_before_send` |

- [ ] **Step 4: Commit delivery evidence**

```bash
git add tests/test_storage_dialog.py docs/BACKGROUND_EXECUTION_AUDIT_2026-09-10.md
git commit -m "test: verify async Tk delivery boundaries"
```

### Task 7: Finish The Audit Report And Run Repository Validation

**Files:**
- Modify: `docs/BACKGROUND_EXECUTION_AUDIT_2026-09-10.md` — complete all final
  findings and exact command results.
- No runtime files beyond the two bounded caller migrations are expected to
  change.

- [ ] **Step 1: Record the proven duplicate and the intentional separations**

Complete the report with these conclusions, changing wording only when test or
source evidence contradicts them:

```markdown
## Duplicate Mechanisms Proven

The Storage dialog's `move_to_trash` action and manual authenticated Test
Connection were the remaining internal callers that submitted general work
through `BackgroundTaskRunner` instead of an existing `AppCoordinator`. Storage
now uses the node-qualified `storage_trash` key; Test Connection uses the
node-qualified `test_connection` key. The exported legacy runner remains
untouched because it is a historical compatibility surface and is no longer an
internal production dependency.

## Mechanisms Kept Separate

Dashboard scan lifecycle, dashboard queue polling, CPU sampling, GPU probing,
remote socket request handling, and Tk timer/delivery adapters remain separate.
Each has distinct ownership semantics that a generic executor would erase.
```

- [ ] **Step 2: Record executor and thread-count implications**

State precisely: the migration removes two production uses of one-thread-per-
action submission; it does not remove the compatibility class, the dashboard
daemon worker model, scanner CPU/GPU workers, remote listener thread, or the
bounded `AppCoordinator` default executor (`max_workers=4`). Do not claim a
global thread-count reduction without measuring a runtime scenario.

- [ ] **Step 3: Run the full established validation gate**

```bash
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
pyright
mypy --ignore-missing-imports
```

Expected: all commands pass. A pre-existing repository-wide failure must be
reported with its exact command, file, and output; do not call the migration
validated while relying on an unready test or static check.

- [ ] **Step 4: Check the final working-tree scope**

```bash
git diff --check
git status --short
git diff --stat HEAD
```

Expected: only the planned dialog/tests/report files are changed. Do not stage
generated artifacts, unrelated user changes, or the plan document unless the
implementation workflow explicitly includes it.

- [ ] **Step 5: Complete the report's twelve required final sections**

The final report must explicitly answer, with source paths and test names:

1. All execution paths found.
2. Ownership of each path.
3. Mechanisms proven duplicate.
4. Mechanisms intentionally kept separate and why.
5. Common mechanisms reused or extracted.
6. Callers migrated.
7. Thread/executor count implications.
8. Cancellation and shutdown behavior.
9. Tk-delivery verification.
10. Exact tests and results.
11. Unresolved risks.
12. Working-tree status.

- [ ] **Step 6: Commit the final report**

```bash
git add docs/BACKGROUND_EXECUTION_AUDIT_2026-09-10.md
git commit -m "docs: report background execution consolidation"
```

## Self-Review Checklist

- [ ] Every execution path has an owner, work type, thread model, queueing,
  concurrency, cancellation, timeout, delivery, shutdown, stale-result,
  node-binding, and test entry.
- [ ] Only the two proven legacy internal callers, Storage `move_to_trash` and
  manual Test Connection, are migrated.
- [ ] No `AsyncCoordinator`, `ThreadCoordinator`, `ExecutionCoordinator`, or
  `GlobalTaskManager` is created.
- [ ] Dashboard progress/timeout/rerun and dialog lifetime semantics remain
  specialized.
- [ ] CPU/GPU workers and remote handlers remain bounded and separately owned.
- [ ] Worker-to-Tk delivery is tested through injected/main-thread seams.
- [ ] Success, exception, cancellation, timeout, destroyed UI, stale node,
  failed submission, active shutdown, repeated start/stop, and state-growth
  cases have exact test names or are explicitly marked not verified.
- [ ] Search the completed plan/report for placeholder language before handoff;
  zero matches are required.

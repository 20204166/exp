# Window Controller Extraction and Reuse Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract cohesive, already-tested controller responsibilities from `window.py` into the existing `maintenance.ui` structure so `window.py` is at or below 900 lines while preserving every callback, monkeypatch seam, public method, error path, and user-visible behaviour.

**Architecture:** Keep `AppWindow` as the composition root and compatibility facade. Move implementation bodies into explicit-controller adapter modules, following the existing `window_pages.py` and `window_node_actions.py` pattern; each adapter calls controller methods dynamically so existing test seams remain valid. Reuse existing domain services (`DashboardScanLifecycle`, `BackgroundOrchestrator`, `TimerDelivery`, `DiscoverySession`, `card_policy`, and `snapshot_state`) rather than introducing generic infrastructure.

**Tech Stack:** Python 3, Tkinter/ttk, `unittest`, `ruff`, `pyright`, `mypy`, existing `maintenance.ui` adapters and coordinator services.

---

## Scope and Audit Result

This is one bounded refactoring pass. It does not add features, change public data models, change discovery or scan protocols, alter scanner algorithms, or redesign the package.

The repository audit found these Python files above 900 lines:

- `window.py` — 2,702 lines; primary extraction target.
- `maintenance/scanner.py` — 2,061 lines; domain scanner with intentional platform-specific and cache-sensitive behaviour; no safe extraction is included in this pass.
- `maintenance/dialogs.py` — 1,645 lines; process/storage dialog ownership and lifecycle are cohesive; no safe extraction is included in this pass.
- `maintenance/nodes.py` — 1,026 lines; node contracts and providers are already shared by local and remote implementations; no safe extraction is included in this pass.
- Several test modules exceed 900 lines; test consolidation would reduce evidence locality and is out of scope.

Existing reuse opportunities were also audited:

- External command execution is already shared by `maintenance.external_commands.run_text_command` and `run_json_command`.
- Cancellation, legacy-call compatibility, hashing, directory walking, and psutil guards are already shared by `maintenance.components.scan_support`.
- Dashboard scan lease state is already shared by `maintenance.components.dashboard_scan.DashboardScanLifecycle`.
- Background worker delivery and Tk timer ownership are already shared by `BackgroundOrchestrator` and `TimerDelivery`.
- Local and remote node providers intentionally expose the same provider contract through different implementations; merging them would hide security and capability differences.
- `SystemScanner` and component scanners intentionally retain distinct cache, timeout, platform, and failure semantics; moving them into a generic scanner would increase risk.

The only justified consolidation pass is therefore the controller extraction below. It reduces repeated controller plumbing and leaves domain behaviour in its existing owners.

## Target File Map

Create these focused adapters under the existing UI/controller package:

- `maintenance/ui/window_node_runtime.py`: node selection, selector construction, selected-context mirror synchronisation, node render invalidation, and node-operation cancellation.
- `maintenance/ui/window_discovery.py`: peer listener composition, discovery session lifecycle, peer reconciliation timers, discovery candidate/lost handling, trusted endpoint verification, and discovery presentation queuing.
- `maintenance/ui/window_scan.py`: dashboard scan lifecycle delegation, scan worker composition, generation guards, snapshot/error delivery, and scan status rendering.
- `maintenance/ui/window_components.py`: component polling, component worker launch/result delivery, capability observation, card visibility/layout, thermal update routing, and preference-driven polling reconciliation.
- `maintenance/ui/window_lifecycle.py`: background-task adapters, style/appearance adapters, Tk timer adapters, shutdown sequencing, worker stopping, and close/run/error cleanup.
- `maintenance/ui/window_context.py`: local/trusted node context setup and restoration helpers extracted from the final facade boundary.
- `maintenance/ui/window_page_data.py`: page-specific node, cluster, settings, interval, and card projection data helpers.
- `maintenance/ui/window_preferences.py`: preference candidate persistence and validation callbacks.
- `maintenance/ui/window_presentation.py`: snapshot presentation, health projection, and resource-dialog routing.

Modify:

- `window.py`: retain `AppWindow`, constants, construction order, imports, and thin compatibility wrappers; delegate moved bodies to the new adapters.
- `maintenance/ui/__init__.py`: export only the new modules if the package’s existing public import style requires it; do not add wildcard exports.

Tests:

- Add `tests/test_window_extraction.py` for adapter-level delegation and edge cases that are not readable in the large integration tests.
- Modify `tests/test_window.py`, `tests/test_window_nodes.py`, and `tests/test_dashboard_ui.py` only where imports or patch targets must follow moved implementation seams. Preserve existing behavioural assertions.
- Add a package-structure assertion to `tests/test_package_structure.py` if the new modules are not already covered by package discovery.

## Compatibility Rules

- Every currently defined `AppWindow` method remains defined with the same name and signature, including methods used by tests through `object.__new__(AppWindow)`.
- Wrappers must resolve controller attributes and callbacks at call time. Do not capture bound methods during module import or construction.
- Preserve import-time Tk safety: adapter imports must not create a root or instantiate widgets.
- Preserve `messagebox`, `simpledialog`, provider, transport, scheduler, and `run_in_thread` injection seams.
- Preserve exact timer cancellation order, generation checks, node-id checks, close guards, failure messages, logging levels, and fail-closed behaviour.
- Do not move domain code from `maintenance.scanner`, `maintenance.nodes`, `maintenance.remote`, or `maintenance.components` merely to reduce line count.
- Keep each new module below 900 lines and keep `window.py` at or below 900 lines after the final extraction.

## Validation Contract

Every extraction task uses the existing fake masters and widget fakes. Run the focused tests after each module, then run the complete required gate:

```bash
python -m unittest tests.test_window tests.test_window_nodes tests.test_dashboard_ui tests.test_window_extraction -v
ruff check .
ruff format --check .
pyright
mypy --ignore-missing-imports
python -m unittest discover -s tests -v
wc -l window.py maintenance/ui/window_*.py
git diff --check
```

The final line-count check must show `window.py` at no more than 900 lines. A failed static check or test is a stop condition, not evidence to waive.

## Task 1: Capture the Baseline and Public Seam Inventory

**Files:**
- Read: `window.py`
- Read: `tests/test_window.py`
- Read: `tests/test_window_nodes.py`
- Read: `tests/test_dashboard_ui.py`
- Create: `tests/test_window_extraction.py`

- [ ] **Step 1: Record the current line count and focused test baseline**

Run:

```bash
wc -l window.py
python -m unittest tests.test_window tests.test_window_nodes tests.test_dashboard_ui -v
```

Expected: the command reports the current 2,702-line controller and the existing focused tests pass before edits.

- [ ] **Step 2: Add adapter contract tests before moving implementation**

Create tests that construct `object.__new__(AppWindow)` with `Mock` collaborators and verify that each adapter delegates through the controller seam rather than requiring a live Tk root. Begin with this concrete contract:

```python
import unittest
from unittest.mock import Mock

from maintenance.nodes import NodeId
from maintenance.ui import window_lifecycle, window_node_runtime
from window import AppWindow


def callback(*_args: object) -> None:
    return None


class WindowExtractionTests(unittest.TestCase):
    def test_node_runtime_switch_delegates_to_selection_component(self) -> None:
        controller = object.__new__(AppWindow)
        selection = Mock()
        controller._node_selection = Mock(return_value=selection)

        window_node_runtime.switch_selected_node(controller, NodeId("peer"))

        selection.switch.assert_called_once_with(NodeId("peer"))

    def test_lifecycle_timer_adapter_preserves_timer_delivery_seam(self) -> None:
        controller = object.__new__(AppWindow)
        delivery = Mock()
        controller.__dict__["_timer_delivery"] = delivery

        window_lifecycle.schedule_timer(controller, 25, callback, "value")

        delivery.schedule.assert_called_once_with(25, callback, "value")
```

Use a local `callback` function and the repository’s `TimerMaster` only where a real scheduling edge case is needed. Do not make these tests assert implementation-private helper names.

- [ ] **Step 3: Run the new contract tests and confirm they fail for missing adapters**

Run:

```bash
python -m unittest tests.test_window_extraction -v
```

Expected: failure because the new adapter modules/functions do not yet exist. Do not interpret this intentional red state as a regression.

## Task 2: Extract Node Runtime Responsibilities

**Files:**
- Create: `maintenance/ui/window_node_runtime.py`
- Modify: `window.py`
- Modify: `tests/test_window_nodes.py`
- Test: `tests/test_window_extraction.py`

Move the implementation bodies for `_selected_context`, `_operation_key`, `_multi_node_selectable`, `_node_selection`, `_schedule_selected_node_scan`, `_rebuild_node_selector`, `_build_node_selector`, `_on_node_selector_change`, `_switch_selected_node`, `_invalidate_node_render_targets`, `_refresh_selected_node_thermals`, `_cancel_active_scan`, `_cancel_node_operations`, `_cancel_all_node_operations`, `_sync_selected_context_mirrors`, and `_render_selected_node` into explicit-controller functions.

- [ ] **Step 1: Create the module skeleton with typed public adapter functions**

Use imports from the existing modules and define functions such as:

```python
def switch_selected_node(controller: Any, node_id: NodeId) -> None:
    selection = controller._node_selection()
    if selection is None:
        return
    selection.switch(node_id)
```

Keep the module free of Tk root creation. Functions that build widgets receive the controller’s existing `actions` parent and use `controller.ttk` and `controller.tk` exactly as the current body does.

- [ ] **Step 2: Move one node-runtime body at a time and replace it with a wrapper**

Each wrapper must retain its existing signature and delegate directly, for example:

```python
def _switch_selected_node(self, node_id: NodeId) -> None:
    ui_node_runtime.switch_selected_node(self, node_id)
```

Do not change the `NodeSelection` callback wiring. Its callbacks must continue to resolve `self._cancel_active_scan`, `self._cancel_node_operations`, `self._sync_selected_context_mirrors`, `self._render_selected_node`, and `self._refresh_selected_node_thermals` at runtime.

- [ ] **Step 3: Run node integration and extraction tests**

Run:

```bash
python -m unittest tests.test_window_nodes tests.test_window_supports tests.test_window_extraction -v
```

Expected: all selected-node switching, duplicate-name, render invalidation, operation cancellation, and partial-window tests pass.

## Task 3: Extract Discovery and Peer-Reconciliation Responsibilities

**Files:**
- Create: `maintenance/ui/window_discovery.py`
- Modify: `window.py`
- Modify: `tests/test_window_nodes.py`
- Modify: `tests/test_coordinator_discovery.py`
- Test: `tests/test_window_extraction.py`

Move `_get_discovery_session`, `_listener_endpoint`, `_start_peer_listener`, `_start_discovery`, `_tick_discovery`, `_peer_connections`, `_cancel_peer_connection`, `_reconcile_peer_connections`, `_schedule_peer_reconciliation`, `_run_peer_reconciliation`, `_on_discovered_candidate`, `_on_discovered_lost`, `_queue_discovery_presentation`, `_sync_trusted_node_endpoint`, `_refresh_discovery_status`, and `_stop_discovery`.

- [ ] **Step 1: Define explicit-controller discovery adapters**

The session factory must preserve all current injected callbacks:

```python
def get_discovery_session(controller: Any) -> DiscoverySession:
    session = controller.__dict__.get("_discovery_session")
    if session is None:
        session = DiscoverySession(
            coordinator=controller._coordinator,
            registry=controller._node_registry,
            get_cluster_state=lambda: controller.__dict__.get("_cluster_state"),
            set_cluster_state=lambda state: setattr(
                controller, "_cluster_state", state
            ),
            save_cluster_state=controller._save_cluster_state,
            schedule_timer=controller._schedule_timer,
            cancel_timer=controller._cancel_timer,
            start_background_poll=controller._start_background_poll,
            on_candidate=controller._on_discovered_candidate,
            on_lost=controller._on_discovered_lost,
            on_stabilized=lambda: controller._queue_discovery_presentation(False),
            discovery_factory=NetworkDiscovery,
            app_version=__version__,
            is_closing=lambda: controller._is_closing,
            get_listener_endpoint=controller._listener_endpoint,
            on_presence_changed=controller._reconcile_peer_connections,
        )
        session.timer_id = controller.__dict__.get("_discovery_tick_id")
        controller._discovery_session = session
    return session
```

Use the current implementation as the source of truth for the remaining functions; retain its identity-fingerprint checks, authenticated hello validation, persistence failure handling, and status messages byte-for-byte.

- [ ] **Step 2: Replace discovery methods with compatibility wrappers**

Keep all method names and callback targets on `AppWindow`. The wrappers must call the adapter and copy timer IDs back to `controller` exactly where the current method does.

- [ ] **Step 3: Run discovery tests**

Run:

```bash
python -m unittest tests.test_window_nodes tests.test_coordinator_discovery tests.test_peer_connection tests.test_remote_compatibility -v
```

Expected: discovery startup, disabled/unavailable transport, candidate/lost events, trusted endpoint verification, identity mismatch, peer reconciliation, and shutdown tests pass.

## Task 4: Extract Dashboard Scan Orchestration

**Files:**
- Create: `maintenance/ui/window_scan.py`
- Modify: `window.py`
- Modify: `tests/test_window.py`
- Modify: `tests/test_window_nodes.py`
- Test: `tests/test_window_extraction.py`

Move `_scan_coordinator_state`, `_dashboard_scan_lifecycle`, `_sync_dashboard_scan_state`, `handle_analyze`, `_claim_scan_resolution`, `_handle_scan_timeout`, `_release_timed_out_lease`, `_release_lease_after_grace`, `_resolve_completed_worker`, `_cancel_scan_timeout`, `_resolve_generation`, `_schedule_rerun_if_requested`, `_resolution_for_generation`, `_show_snapshot_for_generation`, `_show_node_snapshot_if_current`, `_show_snapshot_if_current`, and `_show_error_for_generation`.

- [ ] **Step 1: Preserve the lifecycle adapter construction exactly**

The extracted lifecycle factory must continue to inject the controller’s timer, close, timeout, rerun, and lease callbacks. The adapter must synchronize the legacy mirror attributes after every lifecycle mutation, because tests and existing callers read `_analysis_cancel_event`, `_scan_timeout_id`, `_lease_grace_id`, `_timed_out_generation`, and `_resolved_scan_generation` directly.

- [ ] **Step 2: Move `handle_analyze` without changing closure ownership**

Keep `source_node_id`, `source_context`, and `source_provider` captured at scan start. Preserve the nested `report_progress`, `apply_progress`, `dashboard_task`, `queue_snapshot`, and `start_worker` closures. The worker must still validate `NodeSnapshot`, reject a wrong node ID, reject missing dashboard data, use `call_legacy_compatible`, and deliver only through `_submit_ui` and `_request_render`.

- [ ] **Step 3: Keep AppWindow scan method wrappers intact**

Use wrappers with the existing signatures, for example:

```python
def handle_analyze(self) -> None:
    ui_window_scan.handle_analyze(self)


def _show_snapshot_if_current(
    self,
    generation: int,
    snapshot: DashboardSnapshot,
    *,
    node_snapshot: NodeSnapshot | None = None,
    node_id: NodeId | None = None,
) -> None:
    ui_window_scan.show_snapshot_if_current(
        self,
        generation,
        snapshot,
        node_snapshot=node_snapshot,
        node_id=node_id,
    )
```

- [ ] **Step 4: Run scan lifecycle tests**

Run:

```bash
python -m unittest tests.test_window tests.test_window_nodes tests.test_dashboard_scan tests.test_coordinator_discovery tests.test_window_extraction -v
```

Expected: coalesced scans, timeout and grace handling, cancellation, stale generation rejection, rerun scheduling, progress delivery, legacy provider calls, and node-target guards pass.

## Task 5: Extract Component Polling and Dashboard Projection Responsibilities

**Files:**
- Create: `maintenance/ui/window_components.py`
- Modify: `window.py`
- Modify: `tests/test_window.py`
- Modify: `tests/test_dashboard_ui.py`
- Modify: `tests/test_components.py`
- Test: `tests/test_window_extraction.py`

Move `_component_poll_delay`, `_schedule_component_poll`, `_run_component_cycle`, `_launch_component_scan`, `_queue_component_result`, `_failed_component_summary`, `_record_thermal_summary`, `_thermal_render_state`, `_refresh_thermals_page`, `_fallback_component_title`, `_apply_component`, `_observe_capability`, `_is_card_visible`, `_polling_policy`, `_grid_card`, `_layout_dashboard_cards`, `_reconcile_cards_and_polling`, `_request_component_refresh`, `_reconcile_intervals`, `_update_snapshot_resource`, `_merge_snapshot`, and `_merge_resource`.

- [ ] **Step 1: Reuse existing pure helpers instead of recreating them**

The adapter must continue calling `snapshot_state.merge_snapshot`, `snapshot_state.merge_resource`, `snapshot_state.replace_snapshot_resource`, `card_policy.is_card_visible`, and `card_policy.should_pause_polling`. It must not duplicate those algorithms or move them into a new generic module.

- [ ] **Step 2: Preserve scheduler and coordinator ordering**

Keep the current order of `begin`, coordinator `run`, scheduler `finish`, stale-node checks, full-snapshot timestamp checks, result application, and forced rescheduling. In particular, retain the `source_scheduler.finish(key)` recovery when `coordinator.run` returns `None`.

- [ ] **Step 3: Preserve UI-only rendering seams**

The extracted functions must still use `controller._request_render`, `controller._refresh_health`, `controller.cards`, `controller._page_router`, and `controller.thermals_page`. Do not move Canvas drawing or telemetry ownership into this adapter; `ThermalsPage` and the telemetry/graph modules remain the owners of those concerns.

- [ ] **Step 4: Run component and dashboard tests**

Run:

```bash
python -m unittest tests.test_window tests.test_dashboard_ui tests.test_components tests.test_thermals_page tests.test_temperature_telemetry tests.test_window_extraction -v
```

Expected: capability confirmation, unavailable-card retention, card reflow, polling pause/resume, stale component result rejection, thermal updates, and snapshot merge tests pass.

## Task 6: Extract Background, Presentation, Timer, and Shutdown Adapters

**Files:**
- Create: `maintenance/ui/window_lifecycle.py`
- Modify: `window.py`
- Modify: `tests/test_window.py`
- Modify: `tests/test_dashboard_ui.py`
- Modify: `tests/test_live_tk_resize.py`
- Test: `tests/test_window_extraction.py`

Move `_make_background_orchestrator`, `_background_service`, `_render_coordinator`, `_request_render`, `_sync_render_visibility`, `_configure_styles`, `_apply_appearance`, `_presentation_targets`, `_for_each_presentation_target`, `_set_busy`, `_completion_transition`, `_cancel_analysis`, `_show_progress`, `_progress_total`, `_run_daemon`, `_run_in_background`, `_submit_ui`, `_start_background_poll`, `_drain_background_queue`, `_invoke_delivered`, `_schedule_timer`, `_cancel_timer`, `_cancel_pending_timers`, `_timer_delivery_for_window`, `_finalize_shutdown`, `_stop_all_node_workers`, `_close`, `_show_error`, `_reset_progress_bar`, and `run`.

- [ ] **Step 1: Keep existing service ownership and fail-safe timer behavior**

The lifecycle adapter must continue constructing `BackgroundOrchestrator` with the controller’s queue, close predicate, timer callbacks, task counters, busy callback, render coordinator, coordinator-work predicate, discovery predicate, and delivery callback. It must continue resolving `TimerDelivery` lazily for partial test windows.

- [ ] **Step 2: Preserve shutdown sequencing**

Retain the current order: stop peer server, stop discovery, shut down peer connections, cancel reconciliation, cancel dashboard lifecycle, cancel/shut down the coordinator, cancel node operations, dispose the cluster page, cancel all Tk timers, clear IDs, shut down the render coordinator, stop scanner workers, and only then destroy the master.

- [ ] **Step 3: Preserve presentation behaviour without visual changes**

Move only controller wiring. Keep `scan_status`, `ui_styles`, and existing widget configuration unchanged. No visual audit artifact or UI redesign is required because this pass changes ownership, not rendered tokens, layout, states, or copy.

- [ ] **Step 4: Run lifecycle and live-Tk tests**

Run:

```bash
python -m unittest tests.test_window tests.test_dashboard_ui tests.test_background_orchestration tests.test_live_tk_resize tests.test_window_extraction -v
```

Expected: fake-master timer failure handling, background queue delivery, close guards, worker shutdown, preferences-page scan controls, and display-guarded live-Tk tests preserve their existing results.

## Task 7: Finish the Window Facade and Prove the Line-Count Boundary

**Files:**
- Modify: `window.py`
- Modify: `maintenance/ui/__init__.py` only if package exports require it
- Modify: `tests/test_package_structure.py`
- Modify: `tests/test_ui_primitives.py`
- Test: `tests/test_window_extraction.py`

- [ ] **Step 1: Remove only imports made obsolete by extraction**

Keep imports required by `AppWindow.__init__`, constants, type annotations, composition, and compatibility wrappers. Do not remove imports solely because a moved adapter uses the same symbol until the adapter has its own explicit import.

- [ ] **Step 2: Keep composition methods in `window.py`**

Retain `__init__`, `_build_window`, page registration, local context bootstrapping, preference/cluster store construction, constants, and the thin wrappers required by existing callbacks and tests. The facade remains the only place that assembles the full application.

- [ ] **Step 3: Verify import order and package structure**

Run:

```bash
python -m unittest tests.test_package_structure tests.test_ui_primitives tests.test_window_extraction -v
python -c "import main; import window; import maintenance.ui.window_node_runtime; import maintenance.ui.window_discovery; import maintenance.ui.window_scan; import maintenance.ui.window_components; import maintenance.ui.window_lifecycle"
```

Expected: imports create no Tk root, all adapter modules import successfully, and the existing package dependency assertions remain valid.

- [ ] **Step 4: Measure the bounded extraction result**

Run:

```bash
wc -l window.py maintenance/ui/window_node_runtime.py maintenance/ui/window_discovery.py maintenance/ui/window_scan.py maintenance/ui/window_components.py maintenance/ui/window_lifecycle.py
```

Expected: `window.py` is no more than 900 lines, every new adapter is below 900 lines, and no implementation body remains duplicated between `window.py` and an adapter.

## Task 8: Full Validation and Consolidation Report

**Files:**
- Modify: `docs/plans/2026-09-10-window-controller-extraction.md` only if implementation evidence requires a factual correction

- [ ] **Step 1: Run focused tests once after all wrappers are stable**

Run:

```bash
python -m unittest tests.test_window tests.test_window_nodes tests.test_dashboard_ui tests.test_window_supports tests.test_coordinator_discovery tests.test_background_orchestration tests.test_window_extraction -v
```

- [ ] **Step 2: Run the complete repository test suite**

Run:

```bash
python -m unittest discover -s tests -v
```

Expected: zero failures and zero errors. Report display-dependent skips exactly as emitted; do not convert an unavailable display into a pass claim.

- [ ] **Step 3: Run required Python quality gates**

Run:

```bash
ruff check .
ruff format --check .
pyright
mypy --ignore-missing-imports
git diff --check
```

Expected: each command exits successfully. Any pre-existing failure touched by the extraction must be fixed or explicitly reported before the refactor is considered ready.

- [ ] **Step 4: Review the diff for behavioural preservation**

Run:

```bash
git diff --stat
git diff -- window.py maintenance/ui/window_node_runtime.py maintenance/ui/window_discovery.py maintenance/ui/window_scan.py maintenance/ui/window_components.py maintenance/ui/window_lifecycle.py
git status --short
```

Check every moved method against its original body for changed callback order, changed exception handling, changed logging, changed strings, changed timer ownership, changed node/generation guards, and changed patch targets.

- [ ] **Step 5: Record the required consolidation report**

The implementation handoff must state:

1. Reusable opportunities found: controller responsibilities that now share adapter ownership; existing scanner/external-command opportunities already shared and left unchanged.
2. Shared functions/helpers created or reused: the five adapters plus `DashboardScanLifecycle`, `BackgroundOrchestrator`, `TimerDelivery`, `snapshot_state`, and `card_policy`.
3. Callers migrated: each retained `AppWindow` wrapper and any internal callback registration updated to call the adapters.
4. Functions intentionally kept separate and why: local/remote providers, scanner platform paths, dialog workflows, and security-sensitive node actions.
5. Actual reduction in repeated system work: expected to be none; this is an ownership/consolidation refactor, not a speculative performance change. State any measured change only if a before/after measurement was actually run.
6. Exact tests and checks run with results, including skips and failures.
7. Remaining risks: hidden consumers of private `AppWindow` methods, monkeypatch target changes, and platform/display coverage limits.
8. Working-tree status, including unrelated skill migration changes already present before this refactor.

## Self-Review Checklist

- [ ] Every `window.py` responsibility above 900 lines has a named owner or an explicit reason to remain in the facade.
- [ ] Every moved method retains an `AppWindow` compatibility wrapper.
- [ ] No new feature, public model, provider contract, protocol, persistence format, or visual design was introduced.
- [ ] Existing shared implementations were reused instead of duplicated.
- [ ] Full test, formatting, lint, Pyright, Mypy, line-count, and diff checks are included.
- [ ] The plan contains no unresolved design choice or unspecified implementation step.
- [ ] The final report distinguishes code changes from the pre-existing uncommitted skill migration.

## Execution Handoff

Plan complete and saved to `docs/plans/2026-09-10-window-controller-extraction.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh sub-agent per extraction task, review the diff and focused tests between tasks, then run the final repository gates.
2. **Inline Execution** - execute the tasks in this session in order with focused checkpoints after each adapter.

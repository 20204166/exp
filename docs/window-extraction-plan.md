# Bounded `window.py` Extraction Plan

## Status

Implementation completed for the bounded extraction and the later user-approved
runtime-component expansion. The document remains the scope and ownership
record; implementation details and validation evidence are recorded in
`docs/bug_hunts/patch_reviews/PATCH-20260909-006-review.md`.

The expanded runtime components are:

- `maintenance/components/background_orchestration.py`
- `maintenance/components/dashboard_scan.py`
- `maintenance/components/discovery_session.py`
- `maintenance/components/node_context.py`
- `maintenance/components/node_selection.py`

## Objective

Audit the repository as it currently exists and reduce the size and coupling
of `window.py` through one sensible extraction pass.

The extraction is specifically focused on `window.py` and the possible use of
`maintenance/ui/window_supports/`, but responsibility must determine ownership.
If an extracted class or function belongs to an existing application component
or domain module, it must be placed there instead of being forced into
`window_supports`.

The pass must:

- preserve public and private behaviour;
- preserve existing imports and monkeypatch/test seams where practical;
- reuse existing helpers instead of creating duplicate implementations;
- avoid redesigning the application architecture;
- avoid adding features;
- avoid moving domain responsibilities into the presentation layer;
- stop after one bounded, reviewable extraction pass.

## Repository Context

`window.py` is the application controller and composition root. It currently
owns:

- Tk root creation and shutdown;
- page construction and routing composition;
- dashboard rendering;
- preferences callbacks;
- node selection and context switching;
- discovery lifecycle callbacks;
- trust, pairing, and cluster persistence callbacks;
- full dashboard scan lifecycle;
- component refresh launching;
- background queue delivery;
- timer registration and cancellation;
- snapshot retention and partial resource updates;
- card visibility and polling policy decisions.

The repository already has responsibility-oriented modules. Existing ownership
must be preferred over creating generic support files:

| Responsibility | Existing owner |
| --- | --- |
| Resource metadata, feature titles, feature action kinds | `maintenance/components/catalog.py` |
| Standard unavailable resource construction | `maintenance/models.py` |
| Component refresh timing, leases, and coalescing | `maintenance/components/coordinator.py` |
| Legacy scan callback compatibility | `maintenance/components/scan_support.py` |
| Temperature telemetry and render state | `maintenance/components/temperature.py` |
| Node identity, trust, selection, and operation keys | `maintenance/nodes.py` |
| Cluster state, persistence, and trusted records | `maintenance/cluster.py` |
| Shared scan wording and widget presentation | `maintenance/ui/scan_status.py` |
| Discovery list/status presentation | `maintenance/ui/discovery_refresh.py` |
| General widget construction and layout | `maintenance/ui/layout.py` |
| Page routing | `maintenance/ui/navigation.py` |
| Render batching and stale-render rejection | `maintenance/ui/render_coordinator.py` |
| Direct button action registration | `maintenance/ui/action_coordinator.py` |
| Window-controller-specific support | `maintenance/ui/window_supports/` |

## Ownership Principle

Do not classify a candidate as reusable solely because its name resembles
another function. For every candidate, inspect:

- all callers;
- inputs and outputs;
- state read and written;
- widget or Tk side effects;
- persistence and authentication side effects;
- error and timeout behaviour;
- cancellation behaviour;
- edge cases;
- existing tests and monkeypatch paths;
- intentional differences from apparently similar code.

Use this decision order:

1. Reuse an existing helper if it already owns the operation.
2. Extend the existing domain/component module if the operation belongs to
   that module.
3. Extend an existing presentation module if the operation is reusable UI
   presentation logic.
4. Add a file under `window_supports` only when the responsibility is truly
   specific to the `AppWindow` controller and does not belong elsewhere.
5. Keep the code in `window.py` if extraction would obscure lifecycle,
   ownership, trust, or generation semantics.

## Proposed Package Layout

Only create the following package and files if implementation confirms the
audited boundaries below:

```text
maintenance/ui/window_supports/
    __init__.py
    snapshot_state.py
    card_policy.py
    timer_delivery.py
```

The package must remain small and responsibility-oriented, matching the
existing one-module-per-responsibility structure.

The expanded runtime orchestration components live under
`maintenance/components/` because they coordinate domain/runtime state rather
than reusable widget presentation.

`window_supports` must not import:

- `window.py`;
- scanners;
- network discovery;
- remote providers;
- cluster persistence;
- destructive action managers.

It may import narrowly required models, enums, standard-library types, and Tk
types where the timer support requires them.

## Candidate A: Snapshot State Support

### Current code

The following methods in `window.py` implement dashboard-state retention and
partial snapshot mutation:

- `AppWindow._merge_snapshot`
- `AppWindow._merge_resource`
- `AppWindow._update_snapshot_resource`

Their current callers include:

- `_show_snapshot`, after a full dashboard scan;
- `_apply_component`, after an individual component scan;
- tests in `tests/test_window.py` covering failure retention and partial
  updates.

### Correct ownership

This logic is not scanner logic and is not a general model constructor. It
belongs to window/dashboard state support, so it is an appropriate candidate
for `maintenance/ui/window_supports/snapshot_state.py`.

It must not be moved into:

- `maintenance/components/scan_support.py`, because it does not execute or
  support scanning;
- `maintenance/models.py`, because the failure-count policy is application
  presentation state rather than immutable model construction;
- `maintenance/components/coordinator.py`, because it does not coordinate
  work or leases.

### Proposed functions

```python
merge_resource(
    *,
    previous_snapshot: DashboardSnapshot | None,
    failed_counts: dict[str, int],
    key: str,
    resource: ResourceSummary,
    failed_card_keep_limit: int,
) -> ResourceSummary
```

```python
merge_snapshot(
    *,
    previous_snapshot: DashboardSnapshot | None,
    failed_counts: dict[str, int],
    snapshot: DashboardSnapshot,
    failed_card_keep_limit: int,
) -> DashboardSnapshot
```

```python
replace_snapshot_resource(
    snapshot: DashboardSnapshot | None,
    key: str,
    resource: ResourceSummary,
) -> DashboardSnapshot | None
```

The implementation should use the existing `DashboardSnapshot`,
`ResourceSummary`, and `unavailable_summary` contracts without introducing a
new snapshot model.

### Compatibility wrapper design

Keep the existing `AppWindow` methods as thin wrappers. The wrappers continue
to own access to instance state:

```text
AppWindow._merge_resource(...)
    -> window_supports.snapshot_state.merge_resource(...)

AppWindow._merge_snapshot(...)
    -> window_supports.snapshot_state.merge_snapshot(...)

AppWindow._update_snapshot_resource(...)
    -> window_supports.snapshot_state.replace_snapshot_resource(...)
```

This keeps existing test calls and monkeypatch seams stable while moving the
actual reusable state transformation out of the controller.

### Behaviour that must remain unchanged

- A valid resource replaces the previous value.
- A failed resource with no previous value remains unavailable.
- A transient failed resource retains the previous valid resource.
- Repeated failures eventually show the incoming unavailable resource once
  `FAILED_CARD_KEEP_LIMIT` is reached.
- A successful result resets that resource's failure count.
- A failure in one resource does not erase unrelated resources.
- A component update changes only the matching resource.
- A missing snapshot remains supported.
- The existing resource ordering and snapshot metadata remain unchanged.

### Tests

Retain and adapt the existing tests in `tests/test_window.py`, especially:

- transient failure retention;
- sustained failure threshold;
- unrelated cards continuing to update;
- first-scan failure;
- recovery resetting failure counts;
- component application and partial snapshot updates.

Add direct helper tests for:

- successful merge;
- first failure;
- transient failure retention;
- sustained failure threshold;
- successful recovery;
- missing previous snapshot;
- missing matching resource;
- replacement of exactly one resource;
- preservation of unrelated resources.

## Candidate B: Card Visibility and Polling Policy

### Current code

The following methods contain pure policy decisions mixed into the window
controller:

- `AppWindow._is_card_visible`
- `AppWindow._polling_policy`

Their inputs are effectively:

- the component key;
- `AppPreferences | None`;
- observed `CapabilityState` values.

Their callers include:

- `_layout_dashboard_cards` through `_is_card_visible`;
- `_reconcile_cards_and_polling` through `_polling_policy`;
- tests in `tests/test_window.py` covering preferences and capability
  transitions.

### Correct ownership

This is runtime application policy. It does not belong in `AppPreferences`,
because preferences owns persisted user data and validation, not hardware
observations. It does not belong in `ComponentRefreshScheduler`, because the
scheduler owns timing and leases, not UI visibility or health-driven polling
policy.

It is therefore appropriate for
`maintenance/ui/window_supports/card_policy.py`, provided the functions remain
free of widgets and scheduling side effects.

### Proposed functions

```python
is_card_visible(
    key: str,
    *,
    preferences: AppPreferences | None,
    capabilities: Mapping[str, CapabilityState],
) -> bool
```

```python
should_pause_polling(
    key: str,
    *,
    preferences: AppPreferences | None,
    capabilities: Mapping[str, CapabilityState],
) -> bool
```

The exact type used for the capability mapping may follow the repository’s
existing typing conventions.

### Compatibility wrapper design

Keep the existing `AppWindow` methods as wrappers that pass the current
instance values to the support functions:

```text
AppWindow._is_card_visible(key)
    -> window_supports.card_policy.is_card_visible(
           key,
           preferences=self._preferences,
           capabilities=self._capabilities,
       )

AppWindow._polling_policy(key)
    -> window_supports.card_policy.should_pause_polling(
           key,
           preferences=self._preferences,
           capabilities=self._capabilities,
       )
```

### Intentional policy differences to preserve

- A card manually removed from `visible_cards` is hidden.
- Automatic hiding only applies when `hide_unavailable_cards` is enabled.
- `CapabilityState.UNKNOWN` never proves that a component is unsupported.
- CPU, memory, and storage continue polling because their values feed health
  warnings even if their cards are hidden.
- GPU pauses only when it is automatically hidden as unsupported.
- Network and battery pause when manually hidden or automatically hidden as
  unsupported.
- Visibility and polling remain separate decisions.

### Tests

Retain and adapt the relevant tests in `tests/test_window.py`.

Add direct helper tests for every component policy category and these combinations:

- no preferences object;
- manually hidden;
- manually visible;
- automatic hiding disabled;
- automatic hiding enabled;
- supported capability;
- unsupported capability;
- unknown capability;
- CPU;
- memory;
- storage;
- GPU;
- network;
- battery.

## Candidate C: Tk Timer and Safe Delivery Support

### Current code

The following methods implement generic Tk timer lifecycle handling:

- `AppWindow._schedule_timer`
- `AppWindow._cancel_timer`
- `AppWindow._cancel_pending_timers`
- `AppWindow._invoke_delivered`

Their callers include:

- discovery reap scheduling;
- scan timeout and lease-grace timers;
- component polling;
- delayed rescan requests;
- completion transitions;
- shutdown cleanup;
- `maintenance/ui/transition.py` through injected schedule/cancel callbacks;
- tests in `tests/test_window.py`, `tests/dump_ui.py`, and
  `tests/test_live_tk_resize.py`.

### Correct ownership

These functions are not domain operations and do not belong in a scanner,
coordinator, or component module. They are generic controller-specific Tk
lifecycle support and are appropriate for
`maintenance/ui/window_supports/timer_delivery.py`.

### Proposed design

Prefer a small dependency-injected support class rather than free functions
with a large parameter list:

```python
class TimerDelivery:
    def __init__(
        self,
        *,
        master: Any,
        is_closing: Callable[[], bool],
        pending_ids: set[str],
        logger: logging.Logger,
    ) -> None: ...
```

The class should provide narrowly scoped operations equivalent to:

- `schedule(delay, callback, *args)`;
- `cancel(identifier)`;
- `cancel_all()`;
- `invoke(callback)`.

The support object must not know about scans, discovery, pages, nodes, or
preferences.

### Compatibility wrapper design

Keep the existing `AppWindow` methods so current seams remain valid:

```text
AppWindow._schedule_timer(...)
    -> self._timer_delivery.schedule(...)

AppWindow._cancel_timer(...)
    -> self._timer_delivery.cancel(...)

AppWindow._cancel_pending_timers()
    -> self._timer_delivery.cancel_all()

AppWindow._invoke_delivered(...)
    -> TimerDelivery.invoke(...)
```

The `TimerDelivery` instance must be created or lazily initialized in a way
that remains compatible with tests constructing `AppWindow` through
`object.__new__` rather than `AppWindow.__init__`.

### Behaviour that must remain unchanged

- No timer is scheduled after closing begins.
- Timer identifiers are tracked in `_pending_after_ids`.
- An identifier is removed before its callback runs.
- Callback arguments are delivered unchanged.
- `RuntimeError` and `tk.TclError` are handled as they are currently.
- Scheduling and cancellation failures retain current logging behaviour.
- Cancelling a missing or already-cleared identifier remains safe.
- Pending timers can all be cancelled during shutdown.
- A dead widget callback cannot terminate queue draining.
- Callback delivery remains on the Tk/UI thread through the existing queue
  path.

### Tests

Retain and adapt:

- timer scheduling tests in `tests/test_window.py`;
- callback cleanup tests;
- timer failure logging tests;
- close and shutdown tests;
- `tests/dump_ui.py` timer use;
- display-guarded live Tk tests in `tests/test_live_tk_resize.py`.

Cover:

- successful scheduling;
- callback argument delivery;
- callback identifier removal;
- scheduling failure;
- cancellation failure;
- repeated cancellation;
- closing-state suppression;
- pending timer bulk cancellation;
- dead-widget delivery callback handling.

## Existing Modules to Reuse or Extend

The following opportunities were found, but they should not become duplicate
files under `window_supports`.

### Resource titles

`AppWindow._fallback_component_title` should continue using
`ResourceFeatureCatalog.title_for(key) or key`.

Do not create a new title helper in `window_supports`. Feature metadata already
belongs to `maintenance/components/catalog.py`.

### Failed component summaries

`AppWindow._failed_component_summary` should continue using
`maintenance.models.unavailable_summary(...)`.

Do not create another unavailable-result builder. The existing model helper is
already shared by scanner and window paths.

### Operation keys

`AppWindow._operation_key` should continue delegating to
`maintenance.nodes.node_operation_key(...)`.

The window wrapper intentionally preserves the legacy unqualified key outside
the registry for existing tests, while the node module owns node-qualified
operation-key construction.

### Legacy callback compatibility

`handle_analyze` and `_launch_component_scan` should continue using
`maintenance.components.scan_support.call_legacy_compatible(...)`.

Do not duplicate optional-keyword fallback behaviour in the new package.

### Component timing and leases

`ComponentRefreshScheduler` remains the owner of component timing and leases.

Do not move `_component_poll_delay`, `_schedule_component_poll`, or
`_run_component_cycle` into `window_supports` during this pass. The methods
also coordinate selected-node context, UI timers, component launches, and
render delivery. A safe extraction would require a wider controller/scheduler
redesign.

### Discovery presentation

Continue using the existing functions in
`maintenance/ui/discovery_refresh.py`:

- `refresh_discovery_views`;
- `render_discovery_status`.

Do not duplicate discovery presentation logic in `window_supports`.

### Scan status presentation

Continue using `maintenance/ui/scan_status.py` for status wording, styles, and
progress-bar state. `window_supports` must not become another scan-status
presentation layer.

### Thermal handling

Keep the current thermal boundaries:

- telemetry state in `maintenance/components/temperature.py`;
- render coordination in `maintenance/ui/render_coordinator.py`;
- graph drawing in the thermal graph modules;
- render-intent preparation in `AppWindow`.

Do not extract thermal functions into generic window support.

## Functions Intentionally Kept in `window.py`

### Page construction

Keep:

- `_build_window`;
- `_build_dashboard_page`;
- `_build_settings_home_page`;
- `_build_preferences_page`;
- `_build_nodes_page`;
- `_build_cluster_page`;
- `_build_thermals_page`.

These are composition-root functions. They construct pages and bind
application callbacks. Moving them would create controller-specific page
modules without establishing reusable behaviour.

### Navigation

Keep:

- `_show_settings_page`;
- `_show_preferences_page`;
- `_show_dashboard_page`;
- `_show_thermals_page`;
- `_show_nodes_page`;
- `_show_cluster_page`.

`PageRouter` already owns reusable navigation mechanics. These methods own
application-specific page refresh and focus behaviour.

### Local and trusted node context setup

Keep:

- `_selected_context`;
- `_multi_node_selectable`;
- `_sync_selected_context_mirrors`;
- `_render_selected_node`.

`_build_local_node_context` and `_restore_trusted_nodes` are implemented in
`maintenance/components/node_context.py`. `_switch_selected_node` is
implemented in `maintenance/components/node_selection.py`; its UI/render
effects remain injected from `AppWindow`.

These functions operate on `NodeRegistry`, `NodeContext`, selected-node
mirrors, providers, schedulers, and render invalidation. Their similarity is
controller lifecycle similarity, not safe generic duplication.

### Node trust, pairing, and persistence

Keep:

- `_pair_discovered_node`;
- `_reject_discovered_node`;
- `_rename_node`;
- `_set_node_permissions`;
- `_set_node_color`;
- `_revoke_trusted_node`;
- `_add_manual_host`;
- `_remove_manual_host`;
- `_test_connection`;
- `_open_cluster_node`;
- `_activate_remote_node`.

These have distinct authentication, persistence, rollback, permission, trust,
and remote-provider behaviour. Similar callback shapes are intentional and do
not justify a generic action helper.

### Discovery lifecycle

Keep:

- `_start_discovery_from_nodes`;
- `_on_discovered_candidate`;
- `_on_discovered_lost`;
- `_sync_trusted_node_endpoint`;
- `_refresh_discovery_status`;

`_start_discovery`, `_tick_discovery`, and `_stop_discovery` are implemented in
`maintenance/components/discovery_session.py`. `NetworkDiscovery` remains the
transport/normalization owner; trust and UI mutation remain in `window.py`.

These combine network discovery, registry updates, identity verification,
cluster persistence, UI render intents, and trust-boundary decisions. Moving
them into a generic presentation folder would violate ownership boundaries.

The existing `maintenance/ui/discovery_refresh.py` remains the correct place
for presentation-only refresh and status formatting.

### Full scan lifecycle

Keep:

- `handle_analyze` as the provider/render composition adapter;
- `_show_snapshot_for_generation`;
- `_show_snapshot_if_current`;
- `_show_error_for_generation`;

Generation, cancellation, timeout, grace lease, and rerun transitions are
implemented in `maintenance/components/dashboard_scan.py`.

These encode scan generations, timeout grace, lease release, selected-node
identity, stale-result rejection, and UI render invalidation. Extracting them
would be a scan-lifecycle redesign rather than a bounded helper
consolidation.

### Background queue orchestration

Keep for this pass:

- thin compatibility adapters only.

`_run_daemon`, `_run_in_background`, `_submit_ui`, `_start_background_poll`,
and `_drain_background_queue` are implemented in
`maintenance/components/background_orchestration.py`. Worker threads still
never touch widgets.

These methods are related, but safe extraction would require changing queue
ownership, lifecycle state, and coordinator integration. The existing
`AppCoordinator` already owns the newer shared background-work path, so adding
a second general abstraction would increase complexity.

### Render coordination and presentation state

Keep:

- `_render_coordinator`;
- `_request_render`;
- `_sync_render_visibility`;
- `_presentation_targets`;
- `_for_each_presentation_target`;
- `_set_busy`;
- `_show_progress`;
- `_reset_progress_bar`;
- `_completion_transition`.

The actual shared status operations already belong to
`maintenance/ui/scan_status.py`, while these methods decide when and where
those operations apply. That controller-specific orchestration should remain
in `window.py`.

### Dashboard layout and reconciliation

Keep:

- `_grid_card`;
- `_layout_dashboard_cards`;
- `_reconcile_cards_and_polling`;
- `_request_component_refresh`;
- `_reconcile_intervals`.

`_grid_card` looks generic but is coupled to the dashboard’s responsive card
layout and is only used by the dashboard builder and reflow logic. Existing
`maintenance/ui/layout.py` owns reusable widget construction; moving one
dashboard-specific grid rule there would broaden that module without a second
consumer.

## Migration Sequence

### Preparation

1. Confirm the worktree state before editing.
2. Read the current implementations and tests again immediately before
   changing them.
3. Confirm no concurrent changes have modified the candidate methods.
4. Preserve unrelated user changes; do not reset or revert them.

### Package creation

5. Create `maintenance/ui/window_supports/__init__.py` with a concise module
   description.
6. Export only names that need to be stable. Prefer direct module imports if
   no package-level API is required.

### Snapshot extraction

7. Add `snapshot_state.py` with pure, typed functions.
8. Add focused direct tests before or alongside migration.
9. Replace the three `AppWindow` implementations with wrappers.
10. Confirm no duplicate snapshot merge logic remains in `window.py`.

### Card policy extraction

11. Add `card_policy.py` with pure policy functions.
12. Add focused tests for all component categories and capability states.
13. Replace the two `AppWindow` policy implementations with wrappers.
14. Confirm scheduling remains in `AppWindow` and
    `ComponentRefreshScheduler`.

### Timer extraction

15. Add `timer_delivery.py` with the narrowly scoped support class.
16. Make initialization safe for production construction and test fixtures
    using `object.__new__`.
17. Replace timer methods with compatibility wrappers.
18. Preserve `PendingTransition`’s injected schedule/cancel seam.
19. Confirm no second timer-tracking set is introduced.

### Final review

20. Review imports for cycles and unnecessary package exports.
21. Review all changed callers and tests.
22. Verify all extracted behaviour remains accessible through the existing
    `AppWindow` methods.
23. Stop after this pass. Do not continue into scan, discovery, trust, or
    remote architecture extraction.

## Compatibility Constraints

The implementation must not:

- rename existing `AppWindow` methods used by tests;
- remove existing monkeypatch targets without an explicit migration;
- change callback argument order;
- change timer error handling;
- change scan-generation state transitions;
- change node trust or authorization states;
- change discovery candidate selectability;
- change preference persistence;
- change card visibility semantics;
- create a Tk root during module import;
- import `window.py` from presentation support modules;
- duplicate existing catalog, model, scan, discovery, status, or coordinator
  logic.

## Error, Timeout, and Partial-Failure Requirements

The extraction must explicitly validate existing behaviour for:

- malformed or missing resource data;
- failed component results;
- partial component updates;
- repeated component failures;
- unknown capabilities;
- missing preferences in test fixtures;
- invalid or missing timer identifiers;
- Tk scheduling errors;
- Tk cancellation errors;
- callbacks delivered after closing;
- dead widgets during callback delivery;
- scan timeout and lease-grace paths remaining unchanged;
- discovery startup failure remaining unchanged.

The extraction must not absorb exceptions that currently propagate from
domain operations. Only the existing timer and safe UI-delivery boundaries
should retain their current exception handling.

## Test Plan

### Focused tests

Run the existing window and UI suites:

```bash
python -m unittest tests.test_window -v
python -m unittest tests.test_window_nodes -v
python -m unittest tests.test_dashboard_ui -v
python -m unittest tests.test_live_tk_resize -v
```

Run any new direct support tests, for example:

```bash
python -m unittest tests.test_window_supports -v
```

The exact test module name may be split by responsibility if that better fits
the repository’s existing test organization.

### Repository-wide tests and checks

Run:

```bash
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
pyright
mypy --ignore-missing-imports .
git diff --check
```

No test counts as validation evidence unless the changed code and tests pass:

- Ruff lint;
- Ruff formatting check;
- Pyright;
- Mypy with missing imports ignored.

### Structural checks

Review that:

- `window_supports` has no import cycle with `window.py`;
- support modules do not import scanners, network code, cluster persistence,
  or remote providers;
- existing `AppWindow` method seams remain available;
- direct helper functions have no unintended Tk side effects;
- no implementation was copied and left in both the support module and
  `window.py`;
- existing modules were reused where they already owned the responsibility;
- no unrelated files were modified.

## Expected Consolidation Result

The expected bounded result is:

- `snapshot_state.py` owns reusable dashboard snapshot transformations;
- `card_policy.py` owns reusable visibility and polling decisions;
- `timer_delivery.py` owns window-specific Tk timer lifecycle support;
- `AppWindow` remains the controller and composition root;
- existing domain and presentation modules remain the owners of their current
  responsibilities;
- existing private `AppWindow` method names remain as compatibility wrappers;
- no public behaviour changes;
- no new system queries, scans, subprocesses, network operations, or worker
  types are introduced;
- no actual reduction in system work is expected because this is structural
  consolidation only.

## Functions and Responsibilities Not Consolidated

The following are intentionally left separate because their behaviour is not
proven compatible or their ownership is already correct:

- page builders, because they are composition-root wiring;
- page navigation methods, because `PageRouter` owns shared routing;
- discovery lifecycle methods, because they cross network, registry, trust,
  persistence, and presentation boundaries;
- pairing and manual-host methods, because they have distinct trust,
  authentication, permissions, and rollback semantics;
- scan-generation methods, because they encode lifecycle and stale-result
  invariants;
- background queue orchestration, because extraction would require a larger
  queue/coordinator redesign;
- thermal functions, because telemetry and render ownership is already
  correctly separated;
- resource title lookup, because `ResourceFeatureCatalog` already owns it;
- unavailable summary construction, because `maintenance.models` already
  owns it;
- legacy callback compatibility, because `scan_support` already owns it;
- component timing, because `ComponentRefreshScheduler` already owns it;
- discovery status rendering, because `discovery_refresh` already owns it;
- scan status wording and widget state, because `scan_status` already owns it.

## Deliverables

If implementation is approved, the pass should produce:

- `maintenance/ui/window_supports/__init__.py`;
- `maintenance/ui/window_supports/snapshot_state.py`;
- `maintenance/ui/window_supports/card_policy.py`;
- `maintenance/ui/window_supports/timer_delivery.py`;
- focused tests for each extracted responsibility;
- migrated `AppWindow` compatibility wrappers;
- no unrelated architecture changes;
- a final report containing the requested audit evidence.

## Required Final Report

After implementation, report all of the following:

1. Reusable opportunities found.
2. Shared functions or classes created.
3. Existing shared functions or modules reused.
4. Callers migrated.
5. Responsibilities intentionally kept in `window.py` and why.
6. Responsibilities assigned to existing component/domain modules and why.
7. Any actual reduction in repeated system work.
8. Exact tests and checks run, with results.
9. Failures, skips, unavailable environmental checks, and remaining risks.
10. Exact working-tree status.

## Working-Tree Baseline at Plan Creation

The repository already contains unrelated uncommitted discovery work:

- `maintenance/components/coordinator.py`;
- `maintenance/components/network_discovery.py`;
- `tests/test_coordinator_discovery.py`;
- `tests/test_window_nodes.py`;
- `tests/test_discovery_end_to_end.py`;
- `docs/bug_hunts/patch_reviews/PATCH-20260909-003-review.md`.

The extraction implementation must not revert, overwrite, or mix these
changes accidentally. The final working-tree report must distinguish the
extraction files from these pre-existing changes.

## Stop Condition

The original bounded stop condition was expanded by explicit user request.
Stop after the snapshot-state, card-policy, timer-delivery, background
orchestration, node-context, node-selection, discovery-session, and dashboard
scan-lifecycle extraction pass, or earlier if another extraction would require
broader architectural changes than described here.

Do not continue into a second pass for:

- page-builder extraction;
- coordinator redesign.

If a candidate does not meet the ownership and behaviour-compatibility rules,
leave it in place and document why.

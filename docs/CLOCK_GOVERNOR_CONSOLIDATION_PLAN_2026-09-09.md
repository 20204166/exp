# Clock and Governor Consolidation Plan

Date: 2026-09-09

Repository state audited: `111a300` (`Add authenticated remote node management`)

Scope: remove the standalone `ClockCoordinator` and `ResourceGovernor`
architecture while preserving the existing component refresh scheduler,
`AppCoordinator`, `ScanCoordinator`, `UICoordinator`, discovery lifecycle,
node isolation, direct-action routing, and safety protections.

Implementation status: planning only. This document does not authorize broad
coordinator, worker, scanner, UI, discovery, node, or safety redesign.

## Executive Decision

The repository has an established `ComponentRefreshScheduler` that existed
before commit `75d62fa` (`Add clock coordinator and resource governor`). The
later change moved that scheduler's timing state behind a new standalone
`ClockCoordinator` and added a `ResourceGovernor` admission gate.

The current static evidence does **not** show two independent deadline engines
launching the same recurring component job. `AppWindow` owns one Tk wake-up
timer for the selected node's `ComponentRefreshScheduler`; the scheduler now
delegates deadline decisions to `ClockCoordinator`. This is still unnecessary
layering: the public, established scheduler is a facade over a second
standalone timing authority, with duplicated state aliases and a second policy
model between a due job and `AppCoordinator`.

`ResourceGovernor` is a confirmed additional execution gate. It admits or
defers dashboard and component work, keeps separate active-job accounting,
spawns pressure-sampling threads, and feeds deferral deadlines back into the
scheduler. This adds capacity/pressure policy, retry work, and failure paths
that duplicate or compete with existing in-flight, generation, coalescing,
cancellation, and stale-result protections.

The target architecture is therefore:

```text
Settings / persisted refresh intervals
                |
                v
Existing ComponentRefreshScheduler
  (small internal monotonic cadence state only)
                |
                v
          AppCoordinator
                |
                v
       providers, scanners, workers
                |
                v
              state
                |
                v
          UICoordinator
                |
                v
             rendering
```

The final decision target is **CONSOLIDATED WITH MINOR RETAINED TIMING LOGIC**:
the useful cadence mechanics will move directly into
`ComponentRefreshScheduler`; `ClockCoordinator`, `ResourceGovernor`, and their
admission/pressure model will be removed.

## Non-Goals and Guardrails

This consolidation must not:

- create a replacement scheduler, timer service, clock facade, governor, or
  policy helper;
- move governor policy wholesale into `AppCoordinator`;
- make manual actions wait for a periodic tick;
- remove `AppCoordinator` per-key coalescing, cancellation events, generation
  checks, last-good-result caching, or delivered UI-thread callbacks;
- merge `ScanCoordinator` into `AppCoordinator` as part of this work;
- merge `UICoordinator` into a scheduler or let it dispatch scans;
- remove dashboard timeout/grace handling, node cancellation, component
  isolation, process safety, cleanup revalidation, trust boundaries, or
  platform fail-soft behavior;
- treat all Tk `after(...)` callbacks as duplicate schedulers;
- add platform-specific CPU, memory, or pressure checks to replace the
  governor; or
- redesign remote-node transport, discovery protocol, settings UI, dialogs,
  rendering, or scanner data models unless a direct Clock/Governor reference
  prevents deletion.

The migration must retain one explicit recurring cadence authority per node:
its `ComponentRefreshScheduler`. A component can have one timer wake-up path
through `AppWindow._component_poll_id`, but it must not have another recurring
timer, deadline table, or admission clock.

## Evidence-Based Architecture Inventory

### Historical baseline

Git history establishes the following order:

| Evidence | Meaning |
| --- | --- |
| `14e916e` (2026-09-06), `Rebuild maintenance into a components package...` | Introduced the component subsystem, settings, and `ComponentRefreshScheduler` surface. |
| `389fc98` (2026-09-06), `Add multi-node discovery coordination` | Added per-node contexts and discovery before Clock/Governor. |
| `75d62fa` (2026-09-07), `Add clock coordinator and resource governor` | Added `maintenance/components/clock_coordinator.py`, refactored `ComponentRefreshScheduler`, changed `window.py`, and added Clock/Governor tests. |

This supports using `ComponentRefreshScheduler`, not `ClockCoordinator`, as the
single retained recurring scheduler API and ownership boundary.

### Current recurring component path

| Stage | Current owner and code evidence | Required post-migration owner |
| --- | --- | --- |
| Settings defaults | `RefreshIntervals` in `maintenance/components/coordinator.py:22-47` | Unchanged. |
| Persisted interval policy | `maintenance/preferences.py:39-131` | Unchanged. |
| Scheduler construction | `AppWindow.__init__` creates local `ComponentRefreshScheduler`; remote activation creates one scheduler per remote context | Unchanged. |
| Interval reconciliation | `AppWindow._reconcile_intervals()` calls `scheduler.set_interval(...)` | Unchanged. |
| Due/deadline state | `ComponentRefreshScheduler` now owns private per-key records directly | Keep one scheduler-owned state representation and remove all deleted-layer references. |
| Tk wake-up | `AppWindow._schedule_component_poll()` owns one `_component_poll_id` | Unchanged. |
| Due-job launch | `AppWindow._run_component_cycle()` calls `_launch_component_scan(key)` | Unchanged except governor removal. |
| Admission | `_launch_component_scan()` calls `ResourceGovernor.admit(...)` before scheduler `begin(...)` | Remove. Scheduler in-flight lease and `AppCoordinator` coalescing remain. |
| Worker and result routing | `_launch_component_scan()` calls `AppCoordinator.run(...)` | Unchanged. |
| UI application | `UICoordinator` gates/coalesces render intents; `AppWindow._queue_component_result()` applies valid current results | Unchanged. |

### Current independent timer and coordinator roles

The following are distinct lifecycle mechanisms. They must be audited, but are
not automatically duplicate component schedulers.

| Owner | Current responsibility | Post-migration decision |
| --- | --- | --- |
| `AppWindow._component_poll_id` | One-shot Tk wake-up at the selected scheduler's next deadline | Retain as the single component cadence wake-up. |
| `ScanCoordinator` | Manual full-dashboard scan generation, single active scan, one queued rerun | Retain unchanged. It is not a periodic component scheduler. |
| `AppWindow._scan_timeout_id` and `_lease_grace_id` | Dashboard timeout and completion grace | Retain unchanged. They are timeout safety, not recurring cadence. |
| `AppWindow._background_poll_id` | Drain thread-safe background/discovery delivery queue on the Tk thread | Retain unchanged. It is a UI handoff pump, not a work scheduler. |
| `AppWindow._discovery_tick_id` | Discovery stale-candidate reaping through `AppCoordinator.discovery_tick()` | Retain unless direct audit proves it was introduced by Clock/Governor. It is discovery maintenance, not component cadence. |
| `PendingTransition` | Delayed presentation/status transition via injected window timer wrappers | Retain unchanged. It is presentation timing. |
| `UICoordinator` | Batch, visibility-gate, coalesce, and reject stale render intents | Retain unchanged. It owns no worker or cadence timer. |
| `ButtonCoordinator` | Bind and route direct UI actions | Retain unchanged. It does not wait for polling. |
| `BackgroundTaskRunner` / dialog queues | Dialog-local delivery for process/storage action flows | Do not alter unless a direct Clock/Governor dependency is found. |
| `ResourceGovernor` | Admission accounting and on-demand pressure-sampling threads | Removed in the implementation; retain no policy replacement. |
| `ClockCoordinator` | Component deadlines, intervals, in-flight flags, refresh/defer state | Removed in the implementation; cadence state now belongs directly to `ComponentRefreshScheduler`. |

### Current direct-action and discovery paths

Direct actions are intentionally outside recurring component cadence:

```text
Button -> ButtonCoordinator -> action handler -> AppCoordinator or dialog worker
```

Examples include dialog scans through `AppCoordinator`, destructive process and
storage actions through the existing background-action path, and connection
tests through their existing threaded path. They must remain immediate and
must not acquire a periodic scheduler lease.

Discovery currently starts in `AppWindow._start_discovery()` and calls
`AppCoordinator.start_discovery(...)`. It is not gated by `ResourceGovernor`.
Its reaper is scheduled by `AppWindow._tick_discovery()`. The migration must
preserve this normal lifecycle and add no Clock/Governor dependency.

## Diagnosis to Verify Before Runtime Edits

The implementer must re-run the code search below before Wave 1 and record any
changed evidence in the implementation PR/commit notes.

```bash
git log --all --oneline -S'ClockCoordinator' -- maintenance
git log --all --oneline -S'ResourceGovernor' -- maintenance window.py
git log --all --oneline -S'ComponentRefreshScheduler' -- maintenance window.py
rg -n 'ClockCoordinator|ResourceGovernor|JobProfile|AdmissionDecision|PressureSnapshot' .
rg -n '_schedule_component_poll|_run_component_cycle|_launch_component_scan|_reconcile_intervals' window.py
rg -n '_start_discovery|_tick_discovery|start_discovery|discovery_tick' window.py maintenance tests
rg -n '_schedule_timer\(|\.after\(' window.py maintenance tests
```

Answer these questions from current code, not assumptions:

| Question | Current static answer | Required action if evidence changes |
| --- | --- | --- |
| Did the app already have a scheduler? | Yes. `ComponentRefreshScheduler` predates `75d62fa`. | Retain that pre-existing scheduler surface. |
| Did Clock introduce another timing authority? | Yes, internally: `ComponentRefreshScheduler` delegates deadline and lease decisions to a standalone `_core: ClockCoordinator`. | Inline the necessary state and algorithms; do not retain delegation. |
| Are the same recurring jobs represented in both? | Yes, duplicated representations exist: facade dictionaries/sets alias the core's deadline, in-flight, paused, refresh, and deferred state. | Remove duplicate facade/core split. |
| Are two recurring timers launching each component? | Not shown by static evidence. The window owns one selected-node wake-up; Clock has no timer thread. | Do not claim duplicate timer firing without a failing trace/test. |
| Can the scheduler and governor disagree? | Yes. A key can be due to the scheduler but deferred by governor admission and rewritten with a governor retry deadline. | Remove governor admission and scheduler deferral caused solely by it. |
| Can this delay, starve, duplicate, or never run work? | Deferral/capacity pressure can delay or starve; duplicate execution is guarded by scheduler and `AppCoordinator`. The prior review documented lease-release risk around cancellation. | Preserve release-independent completion and prove no overlap/catch-up behavior with tests. |
| Is the governor another gate before `AppCoordinator`? | Yes, for component scans and manual dashboards in `window.py`. | Remove calls, profiles, retry scheduling, and releases. |

If runtime tracing proves a second deadline producer besides the selected
`ComponentRefreshScheduler` and `_component_poll_id`, extend this plan with
the exact source and remove it in the relevant wave. If it proves no such
producer, do not introduce one merely to satisfy the wording of this plan.

## Target Ownership Model

### Recurring component refreshes

```text
AppPreferences.refresh_intervals
        -> ComponentRefreshScheduler.set_interval()
        -> ComponentRefreshScheduler.next_deadline()/due_keys()/begin()/finish()
        -> AppWindow._component_poll_id
        -> AppWindow._run_component_cycle()
        -> AppWindow._launch_component_scan()
        -> AppCoordinator.run()
        -> provider.component_summary()
        -> UICoordinator render intent
        -> state/card update on Tk thread
```

### Full dashboard scans

```text
Manual scan request
        -> ScanCoordinator.begin()
        -> existing dashboard background queue/worker
        -> ScanCoordinator.finish()
        -> UICoordinator render intent
```

This path is direct/manual rather than a recurring refresh. It is deliberately
out of scope to convert it to `AppCoordinator` during consolidation. Removing
the governor must not change its generation, rerun, cancellation, timeout,
grace, or UI-delivery semantics.

### Discovery

```text
AppWindow startup/settings action
        -> AppCoordinator.start_discovery()
        -> NetworkDiscovery advertisement/browser
        -> delivered candidate/lost callbacks
        -> NodeRegistry

AppWindow discovery reaper timer
        -> AppCoordinator.discovery_tick()
        -> NetworkDiscovery.expire_stale()
```

Discovery must not depend on host CPU, host memory, process RSS, pressure
sampling, governor capacity, scheduler slack, or component interval state.

## Clock Behavior Classification

All `ClockCoordinator` behavior must be classified before deletion. The table
is the required disposition unless tests expose a concrete dependency that
requires a narrowly documented adjustment.

| Current behavior | Evidence | Classification | Migration rule |
| --- | --- | --- | --- |
| Monotonic time source with backwards-clock clamping | `_make_monotonic_clock()` | KEEP IN EXISTING SCHEDULER | Move the private helper into `coordinator.py`; use it only inside `ComponentRefreshScheduler`. |
| Per-key interval and absolute `next_due` deadline | `_ClockEntry.interval`, `next_due` | KEEP IN EXISTING SCHEDULER | Make `_RefreshEntry` private to `ComponentRefreshScheduler`; keep no exported clock class. |
| Absolute cadence/no drift | `begin()` advances `next_due` by missed whole periods | KEEP IN EXISTING SCHEDULER | Preserve only if the migrated behavior tests pass with the existing scheduler API. |
| Skip missed intervals after overrun/suspend | `periods` calculation in `begin()` | KEEP IN EXISTING SCHEDULER | Advance to the next future normal boundary; never queue a catch-up run. |
| Per-key in-flight guard | `_ClockEntry.in_flight` | KEEP IN EXISTING SCHEDULER | Retain. It prevents duplicate same-component execution before `AppCoordinator` work settles. |
| `AppCoordinator` per-key coalescing | `AppCoordinator.run()` | ALREADY EXISTS ELSEWHERE | Preserve; do not copy it into the scheduler. |
| Explicit refresh coalescing | `request_refresh()` | KEEP IN EXISTING SCHEDULER | Keep one boolean/set per key; during an active scan it produces at most one future normal run. |
| Pause/resume | `pause()`/`resume()` | KEEP IN EXISTING SCHEDULER | Preserve public behavior and tests if used by node/page lifecycle. |
| Interval retiming after settings save | `update_interval()` | KEEP IN EXISTING SCHEDULER | Preserve `set_interval()` validation and reset next due from current monotonic time. |
| Deferred-until deadline | `defer()`/`deferred_until` | REMOVE | Its only runtime caller is governor denial. Remove after governor removal. Do not add a generic retry scheduler. |
| Missed-period counter | `missed_periods` | REMOVE unless diagnostics audit proves a public, cheap consumer | There is no current public diagnostics consumer. Do not retain hidden counters by default. |
| Phase/stagger support | `register(..., phase=0.0)` | NOT VERIFIED | No scheduler facade/UI caller exposes it. Remove rather than inventing deterministic staggering. |
| Clock public API and direct tests | `ClockCoordinatorTests` | REMOVE/MIGRATE | Convert to `ComponentRefreshScheduler` behavior tests; no test may import the removed class. |

### Required retained scheduler semantics

`ComponentRefreshScheduler` must remain responsible for the following and no
more:

1. Store the configured millisecond interval for each registered component.
2. Use a monotonic clock internally.
3. Report due keys and earliest deadline.
4. Grant one in-flight lease per component when due.
5. Release/cancel that lease on finalization/node cancellation.
6. Support one coalesced refresh request per component.
7. Retarget an interval after successful settings persistence.
8. Skip catch-up storms after a long overrun or suspend.
9. Remain data-only: no Tk calls, timer threads, worker threads, queue, UI, or
   discovery ownership.

It must not own pressure sampling, host-resource policy, worker capacity,
manual priority, per-node fairness, retry backoff, a second timer, or UI
delivery.

## ResourceGovernor Behavior Classification

| Current governor behavior | Evidence | Classification | Required disposition |
| --- | --- | --- | --- |
| Active-job map and release accounting | `_active`, `release()` | REMOVE | Scheduler and `AppCoordinator` already own per-component/per-operation in-flight state. Do not transplant a global map. |
| Global active job capacity | `max_active` | REMOVE | No evidence establishes a missing global executor limit. Preserve existing per-key coalescing rather than adding a hidden limit. |
| Periodic capacity and manual reserve | `max_periodic`, `manual_reserve` | REMOVE | This is a second priority policy; direct actions and dashboard scans have their existing paths. |
| Per-node active capacity | `max_per_node` | REMOVE | Node-qualified operation keys and scheduler leases remain. Do not add a replacement node governor. |
| Retry backoff | `_defer()` | REMOVE | Only feeds governor denial back into scheduler deferral. No generic retry loop is needed for normal cadence. |
| CPU/memory/swap/RSS pressure state | `PressureSnapshot`, sampler, hysteresis thresholds | REMOVE | Normal monitoring work must not depend on host metrics. |
| Pressure sampling daemon threads | `request_pressure_sample()` | REMOVE | Eliminate the self-monitoring loop/thread entirely. |
| Missing-metrics fail-open behavior | `_apply_pressure_snapshot()` | REMOVE WITH POLICY | It exists solely to make the governor safe. Removing the governor removes the platform dependency. |
| Manual dashboard governor admission | `handle_analyze()` | REMOVE | Preserve `ScanCoordinator`'s own single-flight/rerun behavior. |
| Component telemetry governor admission | `_launch_component_scan()` | REMOVE | Use scheduler lease plus `AppCoordinator.run()` coalescing. |
| Tests for admission/pressure internals | `test_governor_integration.py`, governor sections of `test_components.py` | REMOVE/MIGRATE | Replace only with behavior tests for preserved scheduler/coordinator boundaries. |

No ResourceGovernor behavior is presently approved to move into
`AppCoordinator`. If implementation discovers a concrete bounded-worker
executor that predates the governor and is already relied on, document it and
test it in its existing owner; do not recreate governor policy there.

## Exact File Plan

### Files to modify

| File | Exact change |
| --- | --- |
| `maintenance/components/coordinator.py` | Inline the minimal scheduler cadence implementation into `ComponentRefreshScheduler`; remove the `ClockCoordinator` import and facade aliases; retain only the public scheduler methods used by application code. |
| `maintenance/components/__init__.py` | Remove Clock/Governor-related imports and `__all__` exports. Preserve unrelated stable exports. |
| `window.py` | Remove `ResourceGovernor`, `JobProfile`, admission, defer/retry, release, construction, and pressure-sample wiring. Preserve scheduler-to-`AppCoordinator` flow, full scan lifecycle, discovery, UI handoff, and shutdown. |
| `tests/test_components.py` | Replace Clock/Governor implementation tests with behavior-first `ComponentRefreshScheduler` tests. |
| `tests/test_window.py` | Remove governor mocks/assertions; retain and strengthen full-scan, timer, interval, and scheduler-to-coordinator behavior tests. |
| `tests/test_governor_integration.py` | Delete or replace with a narrowly named behavior test module only if each retained test validates a post-migration cross-layer behavior. Do not retain a file whose purpose is deleted architecture. |
| `tests/test_lifecycle_stress.py` | Preserve and extend deterministic repeated-cycle/no-growth tests against the retained scheduler. |
| `tests/test_window_nodes.py` | Preserve per-node scheduler and discovery lifecycle tests; add custom-interval remote activation ordering coverage if absent. |
| `tests/test_package_structure.py` | Remove expectations for deleted modules/exports and assert the remaining public components surface. |
| `AGENTS.md` | Update only if it names ClockCoordinator/ResourceGovernor as active architecture. Keep the edit concise and factual. |
| Relevant architecture docs/README | Update only exact references found by search. Do not create duplicate architecture documentation. |

### Files to delete

| File | Deletion condition |
| --- | --- |
| `maintenance/components/clock_coordinator.py` | Delete after all Clock/Governor symbols, imports, tests, and package exports are gone and no unrelated component is in the file. Do not leave a compatibility wrapper. |

### Files explicitly not to redesign

- `maintenance/components/network_discovery.py`
- `maintenance/ui/render_coordinator.py`
- `maintenance/ui/action_coordinator.py`
- `maintenance/dialogs.py`
- `maintenance/actions.py`
- `maintenance/remote.py`
- `maintenance/nodes.py`
- scanner/provider modules
- thermal telemetry/rendering modules

They may receive only mechanical import or test updates if a direct deleted
symbol is found.

## Migration Waves

Each wave must be a small, independently testable commit or reviewable change.
Run its focused tests before starting the next wave. Do not combine deletion
with unrelated cleanup.

### Wave 0: Baseline and audit lock

1. Record `git status --short --branch`, `git log --oneline -10`, and the exact
   current commit.
2. Run the search commands in "Diagnosis to Verify Before Runtime Edits".
3. Run current focused tests without editing runtime code:

```bash
python -m unittest tests.test_components -v
python -m unittest tests.test_governor_integration -v
python -m unittest tests.test_window -v
python -m unittest tests.test_window_nodes -v
python -m unittest tests.test_coordinator_discovery -v
python -m unittest tests.test_render_coordinator -v
python -m unittest tests.test_lifecycle_stress -v
```

4. List every actual timer introduced by Clock/Governor. Expected result:
   Clock owns no timer; Governor creates on-demand pressure-sampling threads;
   the Window's component poll remains the sole component wake-up timer.
5. Stop and revise this plan if the code proves `ComponentRefreshScheduler`
   was introduced after Clock/Governor, if another recurring component timer
   exists, or if a non-governor feature relies on the core's deferred state.

### Wave 1: Add behavior-first regression tests

Write tests against existing public behavior before deleting implementation
classes. Do not assert `isinstance(..., ClockCoordinator)`, inspect
`_core`, or call governor methods.

Required scheduler tests:

1. Defaults match `RefreshIntervals` and stored values remain milliseconds.
2. Each configured component is initially due according to current startup
   semantics.
3. A successful `begin()` makes that component unavailable until `finish()`.
4. A duplicate `begin()` while in flight is rejected.
5. A refresh request during flight produces at most one later eligible run,
   never a queue of duplicate work.
6. Changing one interval resets only that component's next deadline from the
   supplied monotonic time.
7. A backwards test clock does not move deadlines backwards.
8. A long overrun/suspend advances to a future normal cadence boundary and
   does not produce catch-up launches.
9. Pause/resume behavior remains unchanged if it has real callers.
10. Cancel clears the lease without making another component due early.

Required window/integration tests:

1. One selected-node component scheduler produces one `_component_poll_id`
   wake-up path.
2. CPU, memory, network, GPU, storage, and battery refreshes launch only when
   due and use their configured intervals.
3. The scheduler calls `AppCoordinator.run()` with a node-qualified component
   key after granting its own lease.
4. `AppCoordinator` coalescing plus the scheduler lease prevents duplicate
   same-component work.
5. A slow component does not trigger a catch-up storm after completion.
6. A node switch or cancellation finishes/cancels the originating scheduler
   lease and cannot apply a stale result to the newly selected node.
7. Manual dashboard scans retain `ScanCoordinator` single-flight/rerun
   behavior and are no longer deferred by host pressure/capacity policy.
8. Button-routed actions remain immediate and never wait for a component poll.
9. Discovery starts when enabled without pressure sampling, available-memory,
   or scheduler-deadline prerequisites.
10. Discovery candidates reach the registry and stale reaping still works.
11. `UICoordinator` still batches, visibility-gates, and rejects stale renders
    while worker finalization occurs independently of hidden rendering.
12. Darwin and Linux simulation tests establish that absent resource metrics
    do not affect whether regular work begins; the test must not reintroduce
    pressure semantics.

Focused command after Wave 1:

```bash
python -m unittest tests.test_components tests.test_window tests.test_window_nodes tests.test_lifecycle_stress -v
```

### Wave 2: Inline minimal cadence logic

Modify only `maintenance/components/coordinator.py`.

1. Copy the minimal private monotonic-clock wrapper into this module, renamed
   only if necessary to avoid an exported Clock concept.
2. Add a private scheduler entry dataclass beside
   `ComponentRefreshScheduler`. It may contain only:
   `interval_seconds`, `next_due`, `in_flight`, `paused`, and
   `refresh_requested`.
3. Make `ComponentRefreshScheduler` own its records directly. Keep its
   current public API:
   `begin`, `finish`, `cancel`, `mark_all_refreshed`, `due_keys`,
   `collect_due`, `next_deadline`, `in_flight`, `set_interval`, `pause`,
   `resume`, `is_paused`, and `request_refresh` where behavior tests confirm
   their callers.
4. Preserve its public `intervals` millisecond mapping because preferences and
   tests rely on it.
5. Remove the `_core` object and all alias fields that point into it. Do not
   retain a facade or a property called `clock`/`core` for compatibility.
6. Remove `defer()` and deferred state unless Wave 0 finds a non-governor,
   necessary caller. The current runtime caller is governor denial only.
7. Do not retain `missed_periods` or phase/stagger parameters without a
   demonstrated consumer. The no-catch-up algorithm itself is sufficient.
8. Keep the timing implementation data-only. It must not create a thread,
   call `after`, start work, dispatch to `AppCoordinator`, or touch UI.

Required cadence algorithm:

```text
When begin(key, now) succeeds:
  reject if paused or already in flight
  reject if key is not due and has no refresh request
  grant the in-flight lease
  clear the coalesced refresh flag
  if now is at/after next_due:
      advance next_due by whole intervals until it is strictly future
  otherwise:
      set next_due to now + interval

When the job finishes:
  clear only the in-flight lease
  do not launch missed runs immediately
```

This preserves normal absolute cadence such as 00, 30, 60, 90 after a late
completion at 33, while skipping a missed 60 run if the prior task remains
active until 65. It must be expressed in the retained scheduler only.

Focused command after Wave 2:

```bash
python -m unittest tests.test_components tests.test_lifecycle_stress -v
ruff check maintenance/components/coordinator.py tests/test_components.py tests/test_lifecycle_stress.py
ruff format --check maintenance/components/coordinator.py tests/test_components.py tests/test_lifecycle_stress.py
```

### Wave 3: Remove component governor gating

Modify only direct component-scan references in `window.py`.

1. Remove the `ResourceGovernor.admit(...)` block from
   `_launch_component_scan()`.
2. Remove the governor-derived `scheduler.defer(...)` and forced retry path.
3. Keep the ordering: obtain the selected source context, calculate the
   node-qualified operation key, check existing coordinated activity, claim
   scheduler lease, and call `AppCoordinator.run()`.
4. Keep the existing stale coordinator fallback: if `AppCoordinator.run()`
   coalesces unexpectedly, release the scheduler lease, request one refresh,
   and re-arm the existing component poll. This is scheduler/coordinator
   consistency, not governor policy.
5. Keep `finish_component()` responsible for scheduler lease release and poll
   rearming. Remove only the governor release.
6. Do not change provider cancellation, result/render generation, source-node
   binding, component failure fallback, or UI request priority.

Focused command after Wave 3:

```bash
python -m unittest tests.test_window tests.test_window_nodes tests.test_lifecycle_stress -v
```

### Wave 4: Remove dashboard governor gating

Modify only direct dashboard-admission references in `window.py`.

1. Remove `JobProfile` construction and `ResourceGovernor.admit(...)` from
   `handle_analyze()`.
2. Do not add a capacity retry timer to replace governor denial.
3. Preserve the first `ScanCoordinator.begin()` call, the active-scan rerun
   behavior, render invalidation, cancellation event, scan timeout, queue
   delivery, success/error handling, and rerun scheduling.
4. Simplify `_run_in_background()` by removing `job_profile`, `admitted`, and
   `retry_callback` parameters and all governor admit/release behavior.
5. Keep `_background_tasks`, busy state, queue finalization, and failure to
   start a daemon behavior exactly correct. A failed thread start must still
   clear the dashboard scan state and timeout.
6. Do not move dashboard scanning to `AppCoordinator` in this wave. It is a
   separate pre-existing lifecycle refactor and not needed to remove the
   governor.

Focused command after Wave 4:

```bash
python -m unittest tests.test_window tests.test_governor_integration -v
```

At the end of this wave, rename/replace `test_governor_integration.py` so its
remaining tests describe generic behavior. Delete governor-specific pressure,
admission, reserve, and release assertions rather than preserving them through
mocked compatibility seams.

### Wave 5: Verify and restore independent lifecycle services

Audit before editing:

```bash
rg -n 'ResourceGovernor|ClockCoordinator|JobProfile|AdmissionDecision|PressureSnapshot' window.py maintenance tests
rg -n 'start_discovery|discovery_tick|stop_discovery|NetworkDiscovery' window.py maintenance tests
```

Required outcomes:

1. `AppWindow.__init__` no longer constructs a governor or launches a pressure
   sample.
2. `_start_discovery()` still runs through `AppCoordinator.start_discovery()`.
3. `_tick_discovery()` still performs normal stale-candidate maintenance.
4. No discovery start/restart/reap code imports or checks clock/governor
   state.
5. Remote-node scheduler activation still reconciles current persisted
   intervals before normal component polling; add a test with non-default
   saved intervals if current coverage is indirect.
6. Shutdown still stops discovery, cancels node operations, cancels tracked Tk
   callbacks, and shuts down UI coordination without a governor to release.

Focused command after Wave 5:

```bash
python -m unittest tests.test_coordinator_discovery tests.test_network_discovery tests.test_window_nodes -v
```

### Wave 6: Delete Clock/Governor implementation and public surface

Only begin after Waves 2-5 have passing behavior tests.

1. Remove Clock/Governor and associated data-class imports from
   `maintenance/components/__init__.py`.
2. Remove their names from `__all__`.
3. Update `tests/test_package_structure.py` to assert the retained public
   package structure, not deleted compatibility names.
4. Delete `maintenance/components/clock_coordinator.py`.
5. Use repository-wide search to prove no source, test, documentation, or
   package-export reference remains.
6. Do not add `deprecated_clock.py`, aliases, re-exports, or no-op classes.
   Git history is the compatibility record. If an actual external public API
   requirement is discovered, stop and request a product decision rather than
   quietly keeping architecture that violates this plan.

Focused command after Wave 6:

```bash
python -m unittest tests.test_package_structure tests.test_components -v
python -m py_compile maintenance/components/coordinator.py window.py
```

### Wave 7: Documentation and complexity check

1. Search documentation, README, package docstrings, and `AGENTS.md` for the
   deleted architecture.
2. Update only discovered active-architecture references to say:

```text
ComponentRefreshScheduler owns component cadence and no-drift/in-flight state.
AppWindow owns the single selected-node Tk component wake-up timer.
AppCoordinator owns keyed worker coalescing, cancellation, result routing, and
Tk delivery.
UICoordinator owns presentation-only render coalescing and stale render gating.
```

3. Document that `ScanCoordinator` owns manual full-scan generations and is
not a second recurring scheduler.
4. Document that discovery maintenance and dashboard timeout callbacks remain
separate lifecycle timers, not cadence authorities.
5. Do not update historical bug-hunt evidence files to rewrite history.
6. Record objective before/after structural counts using source searches,
   not invented performance measurements.

Expected count direction:

| Measure | Before | Expected after |
| --- | --- | --- |
| Standalone component cadence classes | `ComponentRefreshScheduler` plus `ClockCoordinator` | `ComponentRefreshScheduler` only |
| Resource-admission policy components | `ResourceGovernor` | none |
| Pressure sampler threads | Governor on-demand sampler | none |
| Governor retry/defer path | scheduler `defer` plus admission retry | none |
| Component cadence Tk wake-up paths | one `_component_poll_id` | one `_component_poll_id` |
| Per-component deadline state owners | scheduler facade plus core | scheduler only |

### Wave 8: Full validation and deterministic stress

Run each established test surface, then the full suite. Do not report a test
as evidence if static checks fail.

```bash
python -m unittest tests.test_components -v
python -m unittest tests.test_window -v
python -m unittest tests.test_window_nodes -v
python -m unittest tests.test_coordinator_discovery -v
python -m unittest tests.test_network_discovery -v
python -m unittest tests.test_render_coordinator -v
python -m unittest tests.test_process_table -v
python -m unittest tests.test_storage_dialog -v
python -m unittest tests.test_preferences -v
python -m unittest tests.test_lifecycle_stress -v
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
pyright
mypy --ignore-missing-imports .
git diff --check
```

Then run bounded deterministic repetitions using existing fake masters,
deferred runners, and test factories rather than sleeps or live host pressure:

1. Repeated component poll/run/finish cycles with every default interval.
2. A slow component spanning multiple deadlines.
3. Refresh requests while each component is active.
4. Custom interval changes while a component is idle and while it is active.
5. Manual dashboard scan requested during background component work.
6. Node switch during a component worker and during pending delivery.
7. Page switch/hidden render during completion.
8. Discovery start, candidate arrival, stale expiry, stop, and restart.
9. Application shutdown with component work and discovery active.

For each repetition, assert no duplicate timer IDs for the component poll,
no duplicate same-key worker starts, no pending work permanently stuck,
no worker-growth assumption violated by existing tests, no stale selected-node
result applied, no discovery starvation, and no shutdown hang.

## Required Regression Matrix

| Behavior | Primary test surface | Required assertion |
| --- | --- | --- |
| Application startup | `tests/test_window.py` | Local scheduler is created from loaded preferences; no Clock/Governor construction occurs. |
| Coordinator startup | `tests/test_components.py` / `tests/test_window.py` | Component work reaches existing `AppCoordinator` delivery path. |
| Scheduler startup | `tests/test_components.py` | Default intervals and initial due behavior are retained. |
| CPU, memory, network, GPU, storage, battery refresh | `tests/test_window.py` | Each starts only when due, with its configured cadence. |
| Settings interval changes | `tests/test_preferences.py`, `tests/test_window.py` | Persist first, then retime only the relevant existing scheduler entry. |
| No same-component overlap | scheduler/window/lifecycle tests | Lease and coordinator coalescing block duplicates. |
| No catch-up storm | scheduler/lifecycle tests | Late completion never launches accumulated missed copies. |
| Manual scan | `tests/test_window.py` | `ScanCoordinator` still coalesces and reruns directly, without governor admission. |
| Button/action route | existing action/window tests | Direct action does not wait for poll cadence. |
| UI rendering | `tests/test_render_coordinator.py` | UI remains presentation-only and stale-safe. |
| Node selection/polling | `tests/test_window_nodes.py` | Scheduler/provider/result stay bound to source node. |
| Discovery independence | discovery tests | Starts and reaps independent of pressure/capacity state. |
| Platform neutrality | component/window tests with Darwin/Linux fakes | Missing metrics cannot affect normal work execution. |
| Shutdown | window/lifecycle tests | Timers/work/discovery cleanly settle or cancel. |

## Invariants to Review on Every Wave

1. Exactly one `ComponentRefreshScheduler` instance owns recurring cadence per
   node context.
2. `AppWindow` owns at most one scheduled component poll callback for the
   selected context.
3. No `ClockCoordinator`, `ResourceGovernor`, `JobProfile`,
   `AdmissionDecision`, or `PressureSnapshot` remains after Wave 6.
4. Preferences remain the sole source of component interval configuration.
5. Direct user actions do not wait for a periodic timer.
6. Discovery does not wait for resource pressure, capacity, or slack.
7. Missing host metrics cannot prevent normal work from launching.
8. `AppCoordinator` remains the keyed component-worker orchestration boundary.
9. `ScanCoordinator` remains the manual dashboard scan state machine.
10. `UICoordinator` remains render-only and owns no worker/cadence policy.
11. Scheduler in-flight leases and AppCoordinator generations remain separate,
    complementary protections.
12. No catch-up storm occurs after overrun, suspend, cancellation, or a hidden
    render.
13. Node-qualified keys, source-node binding, and stale-result rejection remain
    intact.
14. Process protection, PID/create-time checks, cleanup revalidation,
    Trash-only cleanup, trust boundaries, and remote authorization are
    untouched.
15. The application remains platform-neutral with regard to normal scheduling.

## Completion Audit and Final Report Template

The implementation report must contain evidence for every item below:

1. Original scheduler identified, with history and source path.
2. Actual recurring deadline/timer paths found and whether any duplicate firing
   was reproduced.
3. All ClockCoordinator features and their KEEP/REMOVE/ALREADY EXISTS/NOT
   VERIFIED classification.
4. All ResourceGovernor policies and their removal disposition.
5. Exact scheduler mechanisms migrated into `ComponentRefreshScheduler`.
6. Confirmation that no Governor policy was pasted into `AppCoordinator`.
7. Discovery lifecycle before and after cleanup.
8. Direct action and UI coordinator boundaries preserved.
9. Deleted files, removed exports, and changed files.
10. Before/after structural counts from source searches.
11. Tests converted from implementation assertions to behavior assertions.
12. Exact focused-test, full-suite, lint, formatting, pyright, mypy, and diff
    commands with their actual results.
13. Any environmental constraint such as a missing display or disk-full test
    fixture, clearly separated from product failures.
14. Working-tree status and commit/push status.
15. Unresolved risks, including any deliberately retained timer that is not a
    recurring component scheduler.

Use exactly one final decision:

- **CONSOLIDATED - ONE SCHEDULER**: Clock/Governor are deleted and no retained
  scheduler logic beyond the existing scheduler is needed.
- **CONSOLIDATED WITH MINOR RETAINED TIMING LOGIC**: expected result; small
  monotonic/no-drift/in-flight mechanics now live directly in
  `ComponentRefreshScheduler`.
- **PARTIAL - SEPARATE COMPONENT STILL PROVEN NECESSARY**: only with concrete
  repository evidence, a narrowly documented exception, and explicit product
  approval.
- **BLOCKED**: state the precise missing evidence, failing test, or external
  dependency. Do not claim consolidation.

## Final Acceptance Criteria

The work is complete only when all conditions hold:

1. `maintenance/components/clock_coordinator.py` is deleted.
2. `ResourceGovernor` and its pressure sampler are absent from runtime and
   tests.
3. `ComponentRefreshScheduler` directly owns the retained small cadence state.
4. There is one component cadence wake-up path through the selected node's
   scheduler and `AppWindow._component_poll_id`.
5. No scheduler `defer()` path remains solely for governor denial.
6. Settings changes retime the retained scheduler, with no interval copy in a
   separate clock/governor layer.
7. Component workers continue through `AppCoordinator` and UI delivery remains
   on the Tk thread.
8. Manual scans, buttons, dialogs, discovery, node behavior, rendering,
   timeout safety, and shutdown retain their established responsibilities.
9. No stale-result, overlap, cancellation, or catch-up regression is observed
   in the required deterministic tests.
10. `ruff check .`, `ruff format --check .`, `pyright`,
    `mypy --ignore-missing-imports .`, `git diff --check`, and the full unittest
    suite pass.

The governing implementation principle is: retain the small proven cadence
mechanism in the existing scheduler, remove the standalone clock and governor
layers, and make no unrelated architectural change.

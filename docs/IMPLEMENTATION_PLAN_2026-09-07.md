# System Analyzer Reliability and Thermal UX Implementation Plan

Date: 2026-09-07
Repository commit audited: `30282c5` (`Rebuild wheel 1.3.2.0`)
Audit mode: evidence-led implementation planning; no production code changed during this audit
Scope: Tk widget lifecycle, Cluster page reliability, scan scheduling, governor leases, universal thermal presentation, screenshots, packaging/deployment, tests, and release validation

## Executive Decision

The reported Cluster traceback is a confirmed P1 user-facing reliability bug. It is caused by stale Tk button registrations surviving row destruction and being reused during Cluster page rebuilds.

The thermal behavior is also a confirmed product-contract defect: the Battery card tells systems without a battery to look elsewhere for temperatures, while the requested universal behavior is for the Battery card to be the user-facing home for thermal information even when no physical battery exists.

The scheduler/governor review found a separate high-risk correctness issue: cancelled component operations can suppress the callback that releases their `ResourceGovernor` admission. This can leak capacity and starve later work.

The implementation must be staged in this order:

1. Repair Cluster widget/action lifecycle.
2. Repair guaranteed operation finalization and governor lease release.
3. Define and enforce scan overlap policy.
4. Move thermal presentation ownership to Battery without fabricating battery data.
5. Improve governor fairness, pressure recovery, and retry timer ownership.
6. Validate the installed wheel, not only the source checkout.
7. Apply screenshot-driven UI improvements after correctness is stable.

## Evidence Inventory

### Production traceback evidence

The same traceback was supplied twice from the installed application. Every occurrence ends at:

```text
maintenance/ui/action_coordinator.py:103
config(state=state)
_tkinter.TclError: invalid command name "...!button"
```

The call path is:

```text
ButtonCoordinator.dispatch
window._show_cluster_page
window._refresh_cluster_page
ClusterPage.refresh_nodes
ClusterPage._node_row
ButtonCoordinator.register(replace=True)
ButtonCoordinator._apply_state
Tk widget.configure
```

The repeated path through both the Cluster settings category and the Settings home category proves this is not limited to one navigation entry point. It is triggered by rebuilding the same retained Cluster page.

### Source evidence

`maintenance/ui/cluster_page.py:134-149` destroys every existing row child during `refresh_nodes()` but does not clear Cluster action registrations.

`maintenance/ui/cluster_page.py:200-216` registers stable IDs such as `cluster:node:<id>:open` with `replace=True` and binds them to newly-created buttons.

`maintenance/ui/action_coordinator.py:42-53` preserves live widgets from the previous action record when replacing an action. A destroyed Tk button can therefore remain in the replacement record if its existence check is stale or incomplete.

`maintenance/ui/action_coordinator.py:58-72` catches `TypeError` in `bind()` but not `tk.TclError`.

`maintenance/ui/action_coordinator.py:103-119` catches `tk.TclError` in `_apply_state()`, but the reported call shows that the current installed package reaches a dead widget before it can safely remove it from the action lifecycle.

`maintenance/ui/nodes_connections.py` already has the safer pattern of clearing action prefixes before rebuilding rows. Cluster should use the same lifecycle rule.

`window.py:852-858` refreshes Cluster before showing it. `window.py` also refreshes retained pages from discovery and node-management callbacks while they may be hidden.

### Thermal evidence

The supplied no-battery screenshot shows:

```text
Battery Details
No battery
Temperature readings are shown in the CPU, GPU and Storage sections.
```

The Battery dashboard card contains the same redirect wording. This confirms the current UI does not satisfy universal thermal ownership.

The scanner currently attaches CPU, GPU, and storage samples to their respective summaries. Battery does not own those samples in its dashboard summary, even though Battery detail aggregation already considers multiple thermal components.

### Scheduler evidence

`ResourceGovernor` admissions are released on component success/error paths in `window.py`, but `AppCoordinator` suppresses those callbacks for cancelled runs. A cancelled component operation can therefore retain a governor lease after cancellation.

`ClockCoordinator.cancel()` clears scheduler in-flight state before physical worker completion. That creates a logical/physical cancellation mismatch: a replacement operation can become eligible while the old worker may still be running.

Full dashboard scans and periodic component scans are admitted separately and can overlap. The current code does not establish that this overlap is safe for all scanner/provider implementations.

### Screenshot evidence

The six supplied screenshots show:

- An analysis timeout dialog displayed while the user is on Preferences.
- A full scan reaching `Scanning Battery... (6/6)` and then reporting a 30-second timeout.
- Settings category navigation working visually before Cluster refresh causes repeated callback failures.
- A no-battery system with CPU, GPU, and storage temperatures available.
- Battery details that provide no thermal value despite valid system temperatures.
- CPU process and Network detail dialogs functioning, indicating the failure is localized rather than a total Tk startup failure.
- Wide-screen Preferences layout with excessive empty horizontal space and controls pushed to the far edge.
- Screenshot application version `1.2.9.0`, while the repository was already rebuilt as `1.3.2.0`.

### Repository state evidence

The source repository is clean at commit `30282c5`. The installed traceback path is under `/home/btn17/.local/lib/python3.12/site-packages/`, and the screenshots show `1.2.9.0`. The deployment is therefore not demonstrably running the current repository wheel.

## Confirmed Defects and Severity

### BUG-1: Cluster stale-widget action lifecycle

Severity: P1
Confidence: confirmed by production traceback and source path
Impact: repeated Tk callback exceptions, broken Cluster refresh/navigation, stale action references, possible memory retention

Root cause: Cluster rows are destroyed without unregistering the action records that reference them. Re-registration with `replace=True` does not provide a page lifecycle boundary.

### BUG-2: Cancelled component operation can leak governor admission

Severity: P1 reliability
Confidence: high from source control-flow evidence; requires a focused integration test for final reproduction

Impact: periodic work can be permanently deferred, active capacity can be exhausted, and node switching or shutdown can cause future scans to report already-running/deferred state.

Root cause: release depends on result/error delivery that is intentionally suppressed after cancellation.

### BUG-3: Logical cancellation can release scheduler eligibility before worker exit

Severity: P1/P2 concurrency reliability
Confidence: high design risk; final severity depends on integration reproduction

Impact: old and replacement component work can overlap, especially after node switching or cancellation.

Root cause: scheduler state is cleared on cancellation while physical worker lifetime is tracked elsewhere.

### BUG-4: Battery card is not the universal thermal home

Severity: P1 product-contract defect
Confidence: confirmed by screenshots, source, and existing tests

Impact: users on desktops or systems without a battery are directed away from the card that should expose available thermal readings. Valid CPU/GPU/storage temperatures are not presented in Battery details.

### BUG-5: Installed application/package version is stale or unverified

Severity: P1 release/deployment risk
Confidence: confirmed by screenshot and installed import path

Impact: fixes built in the repository may not reach users; runtime debugging can target the wrong source version.

### BUG-6: Full scans and periodic component scans have undefined overlap policy

Severity: P2 reliability/performance
Confidence: confirmed code path; safety is unproven

Impact: duplicate scanner work, contention, longer timeouts, wasted stale results, and possible provider thread-safety failures.

### BUG-7: Retry and pressure policy can cause avoidable starvation

Severity: P2
Confidence: high design risk

Impact: repeated deferral can make cards stale; failed pressure sampling can leave the governor degraded indefinitely; repeated manual clicks can create timer churn.

## Official Guidance Applied

### Tkinter and Tcl/Tk

The Python Tkinter documentation states that Tk widgets are represented by Tcl/Tk commands, that `destroy()` deletes the widget and its associated Tcl commands, and that `tkinter.TclError` is raised when a Tcl command fails. This directly supports treating a destroyed widget reference as invalid and cleaning action registrations before destruction.

The same documentation states that Tk is event-driven and single-threaded from the event-loop perspective. Long-running work should not block event handlers, and cross-thread UI calls depend on the interpreter event loop. All widget mutation must therefore remain on the Tk thread and must be guarded by page/window lifecycle state.

Sources:

- https://docs.python.org/3/library/tkinter.html#threading-model
- https://docs.python.org/3/library/tkinter.html#tkinter.Misc.destroy
- https://docs.python.org/3/library/tkinter.html#tkinter.TclError
- https://docs.python.org/3/library/tkinter.html#setting-options

### psutil

psutil documents `sensors_temperatures()` as returning a mapping of sensor groups to temperature readings and `sensors_battery()` as a separate API. The plan must keep battery presence and temperature sensor availability independent. An absent or unsupported battery API must not discard valid CPU/GPU/storage readings.

Source:

- https://psutil.readthedocs.io/en/latest/#psutil.sensors_temperatures

### Python packaging and pip

PyPA documents wheels as built distributions that can be installed without rebuilding, and recommends building from `pyproject.toml`. pip documents that it prefers an already-installed version unless `--upgrade` is supplied and supports local wheel installation. The release procedure must therefore explicitly install the target wheel with `--force-reinstall` or `--upgrade`, then verify the imported distribution and console-script path.

Sources:

- https://packaging.python.org/en/latest/tutorials/packaging-projects/
- https://packaging.python.org/en/latest/guides/distributing-packages-using-setuptools/
- https://pip.pypa.io/en/stable/cli/pip_install/

## Implementation Phases

## Phase 0: Establish Runtime Identity

Before changing behavior, add or run an explicit runtime identity check.

Required information:

- `system-analyzer` executable path.
- Python interpreter path used by that executable.
- `maintenance` import path.
- `window.py` import path.
- Installed distribution version.
- Source checkout version.
- Tcl/Tk patch level.

Recommended diagnostic command:

```bash
command -v system-analyzer
python -c 'import importlib.metadata as m, maintenance, window, sys, tkinter as tk; print(sys.executable); print(m.version("system-analyzer")); print(maintenance.__file__); print(window.__file__); root=tk.Tk(); print(root.tk.call("info", "patchlevel")); root.destroy()'
```

Do not use this as a permanent user-facing command unless the application gains a supported `--version` or diagnostics mode.

Acceptance criteria:

- The console script and imported modules come from the same installed release.
- The reported version matches the wheel being tested.
- No source/site-packages split-brain remains.

## Phase 1: Repair ButtonCoordinator Safely

Files:

- `maintenance/ui/action_coordinator.py`
- `maintenance/ui/cluster_page.py`
- `maintenance/ui/nodes_connections.py`
- `tests/test_action_coordinator.py`
- `tests/test_cluster_page.py`

Implementation:

1. Add a stable action-scope abstraction or, minimally, a documented prefix constant for Cluster actions.
2. Add `ButtonCoordinator.clear_prefix()` usage to `ClusterPage.refresh_nodes()` before destroying child rows.
3. Ensure the action record is removed before any old child is destroyed.
4. Change `bind()` to catch `tk.TclError` around command configuration.
5. On failed command/state configuration, remove the dead widget from the record.
6. Make `_widget_exists()` tolerate both `TclError` and `RuntimeError` from fake/live widgets.
7. Make `register(replace=True)` discard all dead widgets and never carry an unverified old reference forward.
8. Add a page `dispose()` method that clears the page scope and prevents future refreshes.
9. Ensure `refresh_nodes()` is idempotent and safe after disposal.
10. Preserve existing callback behavior for live widgets.

Important constraint: catching `TclError` is a last-line safety net, not the primary fix. The primary fix is action cleanup before row destruction.

Acceptance criteria:

- No destroyed Tk widget remains in any action record.
- Refreshing Cluster repeatedly produces no Tk callback exception.
- Removed node actions no longer dispatch.
- New node actions dispatch exactly once.
- No unrelated action IDs are removed.

## Phase 2: Repair Retained-Page Lifecycle

Files:

- `maintenance/ui/navigation.py`
- `maintenance/ui/cluster_page.py`
- `maintenance/ui/nodes_connections.py`
- `maintenance/ui/settings_home.py`
- `window.py`
- `maintenance/ui/render_coordinator.py`

Implementation:

1. Document that `PageRouter` retains page frames and does not recreate them during navigation.
2. Add a page lifecycle state: active, hidden, disposed.
3. Add `dispose()` to pages that own dynamic child widgets or registered actions.
4. Make `_refresh_cluster_page()` return during `_is_closing`.
5. Guard refreshes with `winfo_exists()` or equivalent page validity checks.
6. Ensure late discovery render intents are dropped when the page generation is stale.
7. Keep all Tk mutation on the Tk thread through the existing delivery path.
8. Clear dynamic page actions before page teardown and during application close.
9. Audit all page rebuilds for the same destroy-without-unregister pattern.

Acceptance criteria:

- Hidden pages may be refreshed safely while their frame still exists.
- Disposed pages ignore queued refreshes.
- Application shutdown cannot deliver a callback into destroyed widgets.
- Retained navigation continues to work.

## Phase 3: Repair Component Finalization and Governor Leases

Files:

- `maintenance/components/coordinator.py`
- `maintenance/components/clock_coordinator.py`
- `window.py`
- `tests/test_lifecycle_stress.py`
- `tests/test_components.py`
- `tests/test_window.py`

Implementation:

1. Add a guaranteed `on_finished`/finalizer path to `AppCoordinator`.
2. Guarantee exactly-once finalization for success, error, cancellation, runner-start failure, and timeout settlement.
3. Keep UI result/error delivery suppression for cancelled runs, but never suppress resource cleanup.
4. Move governor `release()` into the finalizer rather than result/error callbacks.
5. Attach a lease token or operation generation to each admission.
6. Make release idempotent.
7. Reject a late old finalizer from releasing a newer admission using the same key.
8. Split scheduler APIs into logical cancellation and physical completion:
   - `request_cancel()` prevents new claims and sets the event.
   - `finish()` settles the operation only after the worker exits.
9. Do not allow replacement work to start while the old physical worker is still running unless a deliberate force-release policy exists.
10. Add diagnostics for active leases, owner, generation, start time, cancellation time, and finalization time without exposing secrets.

Acceptance criteria:

- Every admitted operation has exactly one release.
- Cancellation cannot permanently consume governor capacity.
- Node switching cannot leave old work marked free while it is still executing.
- Shutdown settles all leases without delivering UI callbacks after destruction.

## Phase 4: Define Scan Overlap Policy

Recommended policy: suppress new periodic component launches while a full dashboard scan is active.

Files:

- `window.py`
- `maintenance/components/clock_coordinator.py`
- `maintenance/components/coordinator.py`
- `tests/test_window.py`
- `tests/test_components.py`

Implementation:

1. Add a clear full-scan-active state query.
2. Make `_run_component_cycle()` skip launches while a full scan is active.
3. Preserve a pending explicit component refresh if it was requested by the user.
4. After full-scan finalization, mark the snapshot-applied components refreshed.
5. Resume the component scheduler from a single wakeup path.
6. Retain stale-result guards even after overlap is disabled.
7. Test cancellation of a full scan while a component refresh is pending.

Alternative policy is allowed only if scanner/provider thread safety is proven and bounded concurrency tests pass. The default plan is conservative because the current code does not establish safe overlap.

## Phase 5: Make Battery the Universal Thermal Presentation Home

Files:

- `maintenance/scanner.py`
- `maintenance/components/temperature.py`
- `maintenance/models.py`
- `maintenance/health.py`
- `maintenance/dialogs.py`
- `window.py`
- `tests/test_thermal_card.py`
- `tests/test_temperature_telemetry.py`
- `tests/test_cluster.py`
- `tests/test_remote_contract.py`

Contract:

- Battery capability describes whether a physical battery is present and readable.
- Thermal state describes whether usable temperature samples exist.
- Battery details are the user-facing home for all available system thermal data.
- Internal samples retain their physical source component.
- No synthetic battery temperature is created.

Implementation:

1. Extend normalized temperature categorization with battery sensor aliases.
2. Preserve CPU, GPU, storage, and battery sample identity.
3. Continue using one cached temperature scan for all summaries.
4. Add an aggregated thermal view to the Battery summary without deleting source samples from other summaries unless the contract explicitly requires it.
5. Replace the redirect text with available thermal metrics and source labels.
6. Show thermal data on no-battery systems when valid readings exist.
7. Show a clear no-data state when no readings exist.
8. Show an error state for transient sensor failures while preserving last valid history.
9. Do not convert unsupported temperature into `CapabilityState.UNSUPPORTED` for the Battery resource.
10. Keep automatic Battery card hiding tied to confirmed battery absence only.
11. Ensure the Battery detail dialog builds its thermal section even when ordinary battery details are empty.
12. Update health extraction so warnings continue to use authoritative samples regardless of display ownership.
13. Preserve remote/cluster serialization and backward compatibility when `temperatures` is absent.

Expected state matrix:

| Battery metadata | Thermal samples | Battery card result |
|---|---|---|
| Present/readable | Present | Battery status plus thermal readings |
| Present/readable | None | Battery status plus `Temperature unavailable` |
| Read failed | Present | Thermal readings plus battery metadata error |
| Read failed | None | Battery metadata error plus thermal no-data state |
| Absent | Present | `No battery` plus system thermal readings |
| Absent | None | `No battery` plus `No temperature readings available` |
| Unsupported API | Present | Thermal readings; battery metadata remains independent |
| Unsupported API | None | Explicit unsupported/no-data wording, no crash |

Sensor validation requirements:

- Reject booleans as temperatures.
- Reject `NaN` and infinity.
- Reject zero, negative, and implausibly high readings.
- Handle missing, malformed, mapping, tuple, list, and generator-like sensor entries safely.
- Handle labels that are empty, missing, non-string, or raise during access.
- Verify stable sensor IDs for multiple sensors.
- Verify maximum concise card value while retaining individual history samples.
- Test Linux, Windows-style, macOS-style, and unsupported psutil behavior.

## Phase 6: Improve Governor Fairness and Pressure Recovery

Files:

- `maintenance/components/clock_coordinator.py`
- `maintenance/preferences.py` if policy becomes configurable
- `tests/test_components.py`
- `tests/test_lifecycle_stress.py`

Implementation:

1. Validate governor constructor values:
   - capacities must be positive where required;
   - reserve values must be nonnegative;
   - periodic and per-node limits must not exceed total capacity;
   - retry and sampling intervals must be positive;
   - pressure leave thresholds must be below entry thresholds.
2. Decide whether `priority` and `estimated_cost` are real policy inputs.
3. If retained, implement aging and cost-aware admission.
4. If not retained, remove or clearly document them as future API rather than decorative fields.
5. Add deferred-job age and missed-period tracking.
6. Serve the oldest eligible deferred component before repeatedly admitting newer work.
7. Protect a manual reserve without starving periodic work indefinitely.
8. Distinguish high pressure from pressure sampling unavailable.
9. Define a bounded degraded mode or a safe low-cost fallback when pressure sampling repeatedly fails.
10. Expose pressure sample age and reason in diagnostics.
11. Test recovery after pressure returns below leave thresholds.

The goal is not to make the governor permissive. The goal is to make its behavior bounded, explainable, and fair while preserving protection against resource exhaustion.

## Phase 7: Coalesce Retry Timers and Remove Private-State Coupling

Files:

- `window.py`
- `maintenance/components/clock_coordinator.py`
- `maintenance/components/coordinator.py`
- `tests/test_window.py`

Implementation:

1. Store a manual retry timer ID.
2. Do not schedule another manual retry when one already exists.
3. Cancel retry timers on scan start, cancellation, node switch, and close.
4. Provide a public scheduler status API for next deadline and pending work.
5. Stop reading private scheduler collections from `window.py`.
6. Use one component wakeup timer and one manual retry timer with explicit ownership.
7. Verify timers are removed when callbacks execute or are cancelled.

## Phase 8: Screenshot-Driven UI Corrections

Do not visually redesign the application before the correctness phases pass.

Files likely involved:

- `maintenance/ui/layout.py`
- `maintenance/ui/styles.py`
- `maintenance/ui/preferences_page.py`
- `maintenance/dialogs.py`
- `maintenance/ui/cluster_page.py`
- `window.py`
- `tests/test_ui_primitives.py`
- `tests/test_live_tk_resize.py`

Corrections:

1. Keep a maximum content width or responsive column layout on wide Preferences windows.
2. Keep labels and controls visually associated instead of placing controls at the far edge of a very wide row.
3. Preserve the existing colors, fonts, card borders, and accent tokens.
4. Attach scan error presentation to the scan/dashboard context rather than allowing a timeout dialog to obscure unrelated Preferences content where practical.
5. Improve Battery detail empty/no-data/error states.
6. Ensure dialogs have predictable minimum sizes and scrolling behavior.
7. Verify keyboard focus, disabled states, and close behavior.
8. Validate at 1280x720, 1920x1080, narrow widths, and high-DPI scaling.
9. Capture before/after screenshots without committing user-specific screenshots.

## Test Plan

### Unit tests

Add or update:

- `tests/test_action_coordinator.py`
- `tests/test_cluster_page.py`
- `tests/test_thermal_card.py`
- `tests/test_temperature_telemetry.py`
- `tests/test_components.py`
- `tests/test_lifecycle_stress.py`
- `tests/test_window.py`
- `tests/test_window_nodes.py`
- `tests/test_cluster.py`
- `tests/test_remote_contract.py`

Required cases:

1. Cluster action cleanup before row destruction.
2. Removed action cannot dispatch.
3. New action dispatches once.
4. `bind()` survives a `TclError` race.
5. State updates prune destroyed widgets.
6. Hidden-page refresh is safe.
7. Disposed-page refresh is ignored.
8. Queued callback after close is ignored.
9. Cancelled component lease releases exactly once.
10. Success, error, cancellation, timeout, and start failure all release leases.
11. Late old completion cannot release a newer lease.
12. Node switching prevents old/new overlap.
13. Full scan suppresses periodic launch according to selected policy.
14. Manual retry timers coalesce.
15. Pressure failure and recovery are bounded.
16. Governor invalid configurations are rejected.
17. Battery owns presentation for no-battery systems with valid thermal data.
18. Battery-present/no-temperature and battery-read-failure/thermal-valid states render correctly.
19. Thermal history survives transient failures.
20. Remote summaries preserve thermal samples and accept legacy payloads.

### Live Tk tests

When a display is available:

1. Build Cluster page.
2. Refresh rows repeatedly.
3. Alternate Dashboard, Settings, Nodes, and Cluster.
4. Inject discovery updates while Cluster is visible and hidden.
5. Close during an update.
6. Assert no Tcl errors reach the Tk callback handler.
7. Confirm action count remains bounded.
8. Confirm no dead widget path remains registered.

When no display is available, these tests must skip clearly and must not be treated as passing live-Tk evidence.

### Static and repository checks

Run after every implementation phase:

```bash
ruff check .
ruff format --check .
pyright
mypy --ignore-missing-imports maintenance tests window.py algo.py main.py
```

Then run:

```bash
python -m unittest discover -s tests -v
```

The repository rule is that no test counts as validation evidence unless the Ruff, format, Pyright, and Mypy gates are also clean.

## Packaging and Deployment Plan

1. Bump the version using `maintenance._release` after source changes are complete.
2. Build a pure Python wheel from `pyproject.toml`.
3. Avoid placing dependency wheels into `dist/` unless explicitly required.
4. Refresh `dist/SHA256SUMS` after the project wheel exists.
5. Run the repository wheel verifier.
6. Install the exact wheel into the target user environment:

```bash
python -m pip install --user --upgrade --force-reinstall dist/system_analyzer-<version>-py3-none-any.whl
```

7. Verify the console script path and imported module paths.
8. Run `pip check`.
9. Run the application from the installed console script.
10. Repeat the Cluster refresh/navigation reproduction.
11. Verify that the UI version and installed distribution version match.
12. Only then commit, rebuild release artifacts if needed, and push.

Do not assume that building or committing a wheel updates an already-installed user package. The screenshots prove that source and installed runtime can diverge.

## Release Acceptance Criteria

The change is not releasable until all conditions hold:

- The reported `invalid command name ...!button` traceback cannot be reproduced through repeated Cluster navigation and refresh.
- Cluster action registrations remain bounded and match live rows.
- No stale widget is configured after destruction.
- Component cancellation releases governor leases exactly once.
- No old component worker overlaps a replacement unless explicitly approved by policy and proven safe.
- Full scan/component overlap policy is explicit and tested.
- Battery details show valid CPU/GPU/storage/battery temperatures on systems without a physical battery.
- Battery absence does not fabricate a battery temperature.
- Battery metadata failures do not erase valid thermal readings.
- Health warnings remain authoritative.
- Remote and legacy snapshot compatibility remains intact.
- Wide and narrow UI states remain usable.
- Installed package version matches the built wheel and source release.
- `ruff check .` passes.
- `ruff format --check .` passes.
- `pyright` passes.
- `mypy --ignore-missing-imports maintenance tests window.py algo.py main.py` passes.
- Full unittest discovery passes.
- Live-Tk evidence passes where a display is available, or is explicitly recorded as unavailable.
- Wheel verification and installed-package smoke tests pass.

## Suggested Commit Breakdown

Use separate commits or a single release commit only after each phase is stable:

1. `Fix retained Cluster action lifecycle`
2. `Guarantee component operation finalization`
3. `Define scan overlap and retry scheduling`
4. `Make Battery the universal thermal home`
5. `Improve governor fairness and pressure recovery`
6. `Refine responsive settings and detail states`
7. `Rebuild wheel <version>`

If repository practice requires one commit, preserve these boundaries in the commit body and validation notes.

## Open Decisions Before Implementation

The plan recommends these defaults:

- Battery is the user-facing thermal home.
- Physical temperature samples retain their source component identity.
- No-battery systems still show available thermal readings in Battery details.
- Full dashboard scans suppress new periodic component launches.
- Cancellation is cooperative; physical worker completion controls final lease settlement.
- Governor remains conservative but gains fairness and bounded recovery.

Only the following decisions need explicit product confirmation if they differ:

1. Should the Battery card remain visible by default on a confirmed no-battery desktop, or should it be hidden only when automatic hiding is enabled?
2. Should CPU/GPU/Storage cards continue showing concise temperatures in addition to Battery details, or should Battery become the only visible thermal presentation?
3. Should a full manual scan pause already-running component work, or only prevent new component launches?

## Sources Consulted

- Python Tkinter documentation: https://docs.python.org/3/library/tkinter.html
- Tkinter threading model: https://docs.python.org/3/library/tkinter.html#threading-model
- Tkinter widget destruction: https://docs.python.org/3/library/tkinter.html#tkinter.Misc.destroy
- Tkinter `TclError`: https://docs.python.org/3/library/tkinter.html#tkinter.TclError
- psutil sensor API: https://psutil.readthedocs.io/en/latest/#psutil.sensors_temperatures
- Python Packaging User Guide: https://packaging.python.org/en/latest/tutorials/packaging-projects/
- Setuptools packaging guidance: https://packaging.python.org/en/latest/guides/distributing-packages-using-setuptools/
- pip install behavior: https://pip.pypa.io/en/stable/cli/pip_install/

## Audit Status

This document is a plan, not an implementation sign-off. The confirmed Cluster bug and the Battery thermal ownership defect should be fixed before further visual polish. The scheduler/governor findings require focused integration tests before their final severity is downgraded.

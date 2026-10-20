# System Analyzer Qt UI Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the System Analyzer Tkinter/ttk interface with a PySide6 Qt Widgets interface while preserving existing behavior and test coverage.

**Architecture:** Keep domain/scanning/coordinator policy outside Qt; make a Qt application shell the UI composition root; centralize Qt timer and worker-result delivery; port UI owners in small sections with tests written and run before each section's implementation. Remove Tk only after all corresponding Qt behavior is covered and the complete suite passes.

**Tech Stack:** Python 3.10+, PySide6/Qt Widgets, unittest, offscreen Qt (`QT_QPA_PLATFORM=offscreen`), Ruff, Pyright, Mypy.

---

## Preconditions and execution rules

- The approved design is `docs/specs/2026-10-18-qt-ui-migration-design.md`.
- `/home/btn17/Downloads/exp` has been initialized from the supplied GitHub remote and is currently on `feature/qt-ui-migration`, tracking `origin/main` through its base commit. The branch carries unrelated pre-existing user changes and untracked work. Preserve all of it; never reset, stash, overwrite, stage, or commit unrelated files/hunks.
- Use the repository test entry point `scripts/run_tests.sh`; tests are `unittest`, not pytest. Qt widget tests run with `QT_QPA_PLATFORM=offscreen`.
- Every section follows TDD: inspect current contract/tests → add/adapt focused Qt test → run and observe expected failure (or passing toolkit-independent characterization) → implement only the owned UI section → rerun focused tests → run adjacent tests → commit the coherent section. Never leave an entire converted suite red between sections.
- Keep Qt imports out of scanners/domain modules. Never call Qt widgets from worker threads. Preserve callbacks, cancellation, stale-result filtering, trust/security checks, and safe process/file action ownership.
- Agents may work only after shared interfaces are established. Give each agent an explicit list of files/tests; no overlapping ownership. Each agent must report exact test commands and outputs. Main agent integrates and reviews all changes.

## File ownership map

| Area | Primary files | Existing tests / contract owners |
|---|---|---|
| App entry and packaging | `main.py`, `window.py`, `pyproject.toml`, `requirements.txt`, `requirements-dev.txt` | `tests/test_window.py`, `tests/test_logging_setup.py`, `tests/test_instance_lock.py`, `tests/test_packaging.py`, `tests/test_package_structure.py` |
| Delivery/timers/navigation/layout | `maintenance/components/background.py`, `maintenance/ui/window_supports/timer_delivery.py`, `maintenance/ui/window_lifecycle.py`, `maintenance/ui/navigation.py`, `maintenance/ui/layout.py`, `maintenance/ui/styles.py` | `tests/test_background_orchestration.py`, `tests/test_window_supports.py`, `tests/test_navigation.py`, `tests/test_ui_primitives.py`, `tests/test_lifecycle_stress.py` |
| Dashboard/common rendering | `maintenance/dialogs.py` (`ResourceCard` only in this section), `maintenance/ui/dashboard_page.py`, `maintenance/ui/scan_status.py`, `maintenance/ui/transition.py`, `maintenance/ui/render_coordinator.py`, `maintenance/ui/target_state.py` | `tests/test_dashboard_ui.py`, `tests/test_thermal_card.py`, `tests/test_render_coordinator.py`, `tests/test_target_state_ui.py`, `tests/test_page_wiring_consistency.py` |
| Individual pages | `maintenance/ui/settings_home.py`, `preferences_page.py`, `nodes_connections.py`, `cluster_page.py`, `thermals_page.py`, `diagnostics_page.py`, `help_page.py`, `window_pages.py`, `thermal_graph.py`, `telemetry_graph.py` | `tests/test_settings_home.py`, `test_preferences_page.py`, `test_nodes_connections_page.py`, `test_cluster_page.py`, `test_thermals_page.py`, `test_telemetry_graph.py`, `test_diagnostics_page.py`, `test_help_page.py`, `test_help_content.py` |
| Dialogs | `maintenance/dialogs.py` (Info/Process/Storage dialogs), `maintenance/ui/connection_dialog.py`, `node_details_dialog.py`, `pairing_dialog.py`, `sharing_dialog.py`, `window_node_actions.py`, `window_node_actions_impl/` | `tests/test_info_dialog.py`, `test_process_table.py`, `test_storage_dialog.py`, `test_node_toplevel_dialogs.py`, `test_window_nodes.py`, `test_window.py` |
| Tk removal and integration | all remaining production/tests/docs/package references found by `rg` | full test suite, `tests/test_package_structure.py`, `tests/test_packaging.py`, static gates |

`maintenance/dialogs.py` is shared across ResourceCard and multiple dialogs. The dashboard agent may change only its `ResourceCard` section; dialog agents may change only their assigned dialog classes/helper sections. The integration owner resolves any necessary shared-file sequencing before delegation.

## Task 0: Establish a safe implementation checkout — complete

**Files:** Git metadata only; no source files were changed by this setup task.

- [x] Initialize local Git metadata from `https://github.com/20204166/exp.git`, fetch `origin/main`, and set local `main` to track the fetched baseline without changing working files.
- [x] Create `feature/qt-ui-migration` from local `main` without cleaning the dirty working tree.
- [x] Record current status: user-owned installer/release/dependency files, docs, wheel, and `tests/test_connect_runtime.py` are already modified/untracked. Keep them untouched and exclude them from migration commits.
- [x] Confirm Python 3.12.3, `scripts/run_tests.sh`, Xvfb availability, and that PySide6 is not installed in the system Python environment.
- [x] Run focused baseline `scripts/run_tests.sh tests.test_package_structure tests.test_navigation tests.test_ui_primitives -v`; 97 tests passed. Capture synthetic Tk visual baselines under `.ui/qt-ui-migration/evidence/screenshots/before/`.

**Gate:** stop and ask the user for a Git-backed checkout if the workspace cannot be made safely version-controlled.

## Task 1: Add Qt test foundation before UI changes

**Files:** `pyproject.toml`, `requirements.txt`, `tests/support/qt.py` (new), `tests/test_package_structure.py`, `tests/test_packaging.py`, `tests/test_qt_test_support.py` (new).

- [x] Add a focused test asserting Qt Widgets can be imported and one shared offscreen `QApplication` can be obtained/reused.
- [x] Run the test first; the initial failure identified the missing `tests.support.qt` helper.
- [x] Add `PySide6>=6.7` as a runtime dependency in `pyproject.toml` and `requirements.txt`, preserving the pre-existing `expra-connect` entries.
- [x] Create `/tmp/opencode/system-analyzer-qt-migration-venv` with system site packages; PySide6 6.11.2 was already available there.
- [x] Implement `tests/support/qt.py` for application reuse and offscreen mode.
- [x] Focused Qt/package tests passed (22 tests) and Ruff/format checks passed. One broader `tests.test_packaging` assertion remains failing because pre-existing `install/upgrade.sh` calls `install_release_wheels` while its legacy test expects literal `pip install`; this unrelated dirty-worktree mismatch is not changed here.
- [ ] Do not commit while unrelated user-owned work remains mixed in the branch unless the user separately authorizes a selective checkpoint commit.

## Task 2: Port delivery, timer, navigation, style, and reusable layout owners

**Files:** `maintenance/components/background.py`, `maintenance/ui/window_supports/timer_delivery.py`, `maintenance/ui/window_lifecycle.py`, `maintenance/ui/navigation.py`, `maintenance/ui/layout.py`, `maintenance/ui/styles.py`, `maintenance/ui/action_coordinator.py`; tests `test_background_orchestration.py`, `test_window_supports.py`, `test_navigation.py`, `test_ui_primitives.py`, `test_action_coordinator.py`.

- [x] Add/adapt focused Qt tests for GUI-thread queue delivery, queue close/drop, timer cancellation, navigation retention/rollback, and Qt layout/style behavior.
- [x] Characterize `AppCoordinator` delivery, dialog `BackgroundTaskRunner`, and manual `BackgroundOrchestrator`; cover thread affinity, bounded drains, coalesced progress, finished markers, close races, and no delivery after close.
- [x] Run red tests first, then implement Qt delivery/timer APIs, Qt-aware navigation, layout/style helpers, button bindings, and `BackgroundTaskRunner.run_with_delivery`; keep domain coordinator toolkit-neutral.
- [x] Focused verification: 143 tests passed with `QT_QPA_PLATFORM=offscreen PYTHON=/tmp/opencode/system-analyzer-qt-migration-venv/bin/python scripts/run_tests.sh tests.test_background_orchestration tests.test_window_supports tests.test_navigation tests.test_ui_primitives tests.test_action_coordinator tests.test_background_task_runner -v`.
- [x] Ruff check, Ruff format check, and `git diff --check` passed for Task 2 files.
- [ ] Final integration is intentionally deferred: legacy Tk consumers remain until their page/dialog sections and the later shell cutover. Qt infrastructure APIs are transitional alongside existing Tk paths; they must be the sole implementation after Task 6.

## Ordering correction: build Qt surfaces before switching the application shell

**Ordering correction:** the original plan put the `QMainWindow` cutover before
converting pages/dialogs. The current pages and dialogs are Tk widgets and cannot
be hosted by `QMainWindow`; this would leave no runnable intermediate app.
Per user direction, keep the current Tk entrypoint/shell operational while Qt
surfaces are developed and tested independently. Where necessary, add Qt-native
surface modules alongside existing Tk modules temporarily. Do not wire a
permanent runtime fallback. The final integration task removes the Tk path and
switches the app to Qt after all Qt surfaces are ready.

**Files:** Task 5 Qt page sections and Task 6 Qt dialogs; tests remain section-owned.

- [ ] Build each Qt page/dialog in a standalone QWidget/QDialog host with injected callbacks/data; do not require the application shell to be Qt yet.
- [ ] Keep existing Tk implementation files untouched until the corresponding Qt replacement passes focused tests and the final cutover is ready.
- [ ] Maintain non-overlapping ownership: one section owner per page/dialog family; the integrator owns final shell/page registration and shared adapters.
- [ ] After each surface, run its focused tests and capture the required rendered evidence before continuing.
- [ ] Do not claim full behavior parity until final application integration tests pass.

## Deferred shell integration: port Qt application/window shell and lifecycle

**Files:** `main.py`, `window.py`, `maintenance/ui/window_lifecycle.py`, `maintenance/ui/window_context.py`, `maintenance/ui/window_components.py`, `maintenance/ui/window_discovery.py`, `maintenance/ui/window_node_runtime.py`, `maintenance/ui/window_scan.py`, `maintenance/ui/window_preferences.py`, `maintenance/ui/window_presentation.py`, `maintenance/ui/window_placement.py`, `maintenance/ui/window_supports/timer_delivery.py`; tests `test_window.py`, `test_window_extraction.py`, `test_window_placement.py`, `test_window_supports.py`, `test_lifecycle_stress.py`, `test_instance_lock.py`, `test_logging_setup.py`.

- [ ] Add Qt-shell tests for QApplication startup, window construction, startup timer scheduling, close/shutdown idempotency, and preservation of logging/instance-lock order.
- [ ] Include startup-order assertions: preferences/cluster restoration before scheduler/node setup; TLS listener starts independently of discovery preference; discovery toggle semantics remain; first scan stays deferred until Qt can paint.
- [ ] Run those tests before implementation; check that failures concern missing Qt shell behavior.
- [ ] Replace Tk root ownership with `QMainWindow`; preserve constructor injection seams where useful for stores/managers and keep domain initialization/order unchanged.
- [ ] Add the Qt entry function that creates/reuses QApplication, sets application metadata, constructs the window, and starts `exec()`; retain CLI parsing, logging, single-instance locking, exit handling, and cleanup.
- [ ] Port lifecycle actions to Qt close events and the canonical delivery/timer adapters. Verify worker shutdown and pending callback cancellation cannot touch deleted widgets.
- [ ] Rerun the focused window/lifecycle tests and `tests.test_package_structure`; expected PASS.
- [ ] Integrate the previously standalone Qt pages/dialogs, then remove Tk shell ownership and activate Qt as the only application event loop.
- [ ] Commit only migration-owned files/hunks if a selective checkpoint is explicitly chosen; otherwise keep work uncommitted and preserve pre-existing user edits.

## Task 3: Port dashboard and common render state

**Files:** standalone `maintenance/ui/qt_dashboard.py` and `maintenance/ui/qt_scan_status.py` while the Tk shell remains active; tests `tests/test_qt_dashboard.py`. Existing `dashboard_page.py`, `dialogs.py`, `render_coordinator.py`, `target_state.py`, and shell wiring remain unchanged until final integration.

- [x] Add Qt tests first for catalog/card order, empty/populated summaries, capability/failure states, usage bars, card visibility/actions, scan ready/busy/progress/cancel/complete/error, focus/accessibility, scrolling, and resize behavior.
- [x] Implement standalone `QtDashboard`/`QtResourceCard` and Qt scan-status rendering without replacing active Tk modules. Keep callbacks injected and state/policy outside widgets.
- [x] Fixed test-discovered defects: initial progress bar visibility, initial resize column calculation, maximum three-column parity, populated-column width balance, and short-viewport card compression/scrolling.
- [x] Focused verification: `tests.test_qt_dashboard` + `tests.test_dashboard_ui` — 36 passed; combined Qt infrastructure/dashboard suite — 180 passed.
- [x] Ruff check and format check passed for the Qt dashboard and Task 2-owned files.
- [x] Rendered/inspected synthetic populated Qt dashboard screenshots at 900/1280/1600px under offscreen Qt; evidence is in `.ui/qt-ui-migration/evidence/screenshots/after/dashboard/`.
- [ ] Final shell integration and stale/cached render wiring remain deferred to Task 6; no end-to-end application parity claim is made.

## Task 4: Migrate pages in independent, test-first sections

Each subtask is one agent-owned section after Task 2 establishes the Qt primitives. Assign one agent per section; agents may edit only the listed Qt page implementation and its directly corresponding tests. The main agent owns final `window_pages.py`/shell integration and reviews results. The live Tk application remains unchanged until Task 4 cutover.

### 5A Settings and preferences

**Files:** `maintenance/ui/settings_home.py`, `maintenance/ui/preferences_page.py`, `maintenance/ui/window_preferences.py`; tests `test_settings_home.py`, `test_preferences_page.py`, `test_preferences.py`.

- [x] Add Qt tests first for navigation-only category selection, refresh interval bounds/commit, visibility and automatic-hide controls, reloading persisted values without emitting edits, scan state/progress, and callback-owned persistence.
- [x] Implement standalone `QtSettingsHome` and `QtPreferencesPage`; preserve `AppPreferences`/`PreferencesStore`, stable callback meaning, and `ButtonCoordinator` scan gating.
- [x] Visual review caught and fixed an unmounted preferences scroll area, duplicated checkbox label, and category-card border leakage; these are covered by tests.
- [x] Run `tests.test_qt_settings`, `tests.test_settings_home`, `tests.test_preferences_page`, and `tests.test_preferences`: 78 passed. Ruff and format checks passed.
- [x] Capture/inspect synthetic Qt Settings and Preferences renders at 900/1280/1600px; evidence under `.ui/qt-ui-migration/evidence/screenshots/after/settings/`.
- [ ] Final shell integration remains deferred.

### 5B Nodes and connections

**Files:** standalone `maintenance/ui/qt_nodes_connections.py` and `tests/test_qt_nodes_connections.py`. Existing projection/domain and Tk implementation files remain unchanged until final integration.

- [x] Add Qt tests for node projections, selection, refresh/action callbacks, accessible names, focus, long labels, and responsive/scroll layout.
- [x] Preserve trust, connection, and cluster axes independently and render joined-worker coordinator identity from the supplied epoch projection.
- [x] Focused Qt and legacy regression run passed; combined verification with Cluster and remote-role suites passed 126 tests. Ruff check/format passed.
- [ ] Final shell registration/wiring remains deferred.

### 5C Cluster

**Files:** standalone `maintenance/ui/qt_cluster.py` and `tests/test_qt_cluster.py`; role/action policy owners remain unchanged.

- [x] Add Qt tests for role/assignment display, injected policy visibility/enabled state, confirmation intent, callback dispatch, separate trust/connection/membership axes, coordinator identity, accessibility, and responsive scrolling.
- [x] Implement standalone `QtClusterPage`; no trust/authorization rules moved into the widget.
- [x] Qt Cluster tests (6), legacy Cluster tests (28), and selected remote-role tests (23) passed. Scoped Ruff/format and Pyright passed.
- [ ] Final shell registration/wiring remains deferred.

### 5D Thermals and graphs

**Files:** standalone `maintenance/ui/qt_thermals_page.py`, `maintenance/ui/qt_thermal_graph.py`, and `tests/test_qt_thermals.py`; telemetry, Tk page/graph, and coordinator remain unchanged.

- [x] Add Qt tests first for geometry, finite data, bounded points, thresholds, accessible textual readings, all sensor states, capability/state distinction, event bounds/actions, recovery, and independent node inputs.
- [x] Implement native QPainter graph + standalone page receiving prepared immutable state only; no telemetry polling or history ownership added.
- [x] Confirmed unsupported state at N−1/N via existing telemetry contract tests, no fabricated samples, recovery and independent histories.
- [x] Focused Qt and existing thermal suites passed: 61 tests. Ruff/format and Pyright passed; Mypy unavailable in the venv. `git diff --check` passed.
- [x] Captured and inspected representative empty/populated/unsupported-error offscreen renders at 900/1280/1600px under `.ui/qt-ui-migration/evidence/screenshots/after/thermals/`.
- [ ] Final shell registration/wiring remains deferred.

### 5E Diagnostics and help

**Files:** standalone `maintenance/ui/qt_diagnostics_page.py`, `maintenance/ui/qt_help_page.py`, and direct Qt tests; DiagnosticsSnapshot/HelpTopic owners and shell/router remain unchanged.

- [x] Add Qt tests first for empty/live/partial diagnostics, reusable refresh rows, serialization/copy, optional save-capture success/failure, explicit developer-mode visibility, Help topic order/callbacks/content fidelity, accessible focus, and long-content scrolling.
- [x] Implement standalone Qt Diagnostics and Help pages; diagnostics collectors/serialization and canonical `HELP_TOPICS` remain authoritative.
- [x] Captured/inspected diagnostics empty/live plus Help hub/detail at 900/1280/1600 widths; fixed a clipped diagnostics status line found during render review.
- [x] Combined focused Qt + existing diagnostics/help/developer-mode command passed 72 tests. Ruff/format and Pyright passed; Mypy unavailable.
- [ ] Final shell/router integration remains deferred.

## Task 5: Port dialogs and dialog-owned interactions

**Files:** `maintenance/dialogs.py` (Info/Process/Storage dialog classes and dialog adapters), `maintenance/ui/connection_dialog.py`, `node_details_dialog.py`, `pairing_dialog.py`, `sharing_dialog.py`, `window_node_actions.py`, `window_node_actions_impl/connections.py`, `pairing.py`, `permissions.py`; tests `test_info_dialog.py`, `test_process_table.py`, `test_storage_dialog.py`, `test_node_toplevel_dialogs.py`, selected `test_window_nodes.py`.

- [x] Add isolated Qt implementations/tests for resource detail, process, storage, connection, node-details, pairing, and dashboard-sharing dialogs; native `QDialog.open()` lifecycle, keyboard close, callbacks, confirmation/read-only/busy/unknown states covered.
- [x] Keep all cleanup/process/network/trust/authorization operations injected; widgets do not invoke managers, scanners, or network services.
- [x] Extract summary presentation formatters to `maintenance/ui/resource_details.py`; both Tk compatibility imports and Qt dashboard/dialogs now share one implementation rather than importing `maintenance.dialogs` from Qt.
- [x] Resource Qt + existing Info/Process/Storage suites passed 100 tests; Qt node-dialog + existing node-dialog and node-window suites passed (9 + 29 + 153). Dashboard/resource formatter regression group passed 68 tests.
- [x] Scoped Ruff/format passed for touched files except Pyright over `qt_dashboard.py` reports 12 existing layout optional-typing errors unrelated to the import-only migration hunk; Pyright passes for the new formatter, resource dialog, and focused tests. `git diff --check` passed.
- [x] Qt shell now routes informational, process, and storage review to the corresponding Qt resource dialogs with background task delivery, close guards, and scan cancellation. Pairing now requires Qt fingerprint review before the existing transaction, and successful completion releases the retained dialog without triggering cancel/abort; cancellation and retry remain covered by the existing pairing policy. Focused integration tests and independent spec/code-quality reviews passed.
- [x] Qt Cluster now projects and dispatches Open, Pause/Resume, Revoke, Remove connection, and Remove job through the existing policy owners with Qt confirmations and fresh action checks. Qt Nodes now opens retained trusted/manual-node Details dialogs, including manual-host Details, with fresh policy checks and characterization for stale/manual states and No-confirmation behavior. Independent spec and code-quality reviews approved these interaction batches.
- [x] `window_context` no longer imports `window` at runtime; `window.AppWindow` passes patchable compatibility symbols explicitly, with a regression test protecting the save-error/logger seam. Focused extraction/context/Qt tests and Ruff, format, Pyright, and diff checks passed.
- [x] Qt Nodes now exposes and wires rename, color, permissions, roles, manual-host removal, discovery/help, pairing, node details, sharing, revoke, pause/resume, connection/job removal, and legacy Test dispatch through injected callbacks and existing policy owners. Qt Cluster invite creation/join and dashboard-share actions dispatch through the existing policy/controller owners. Toolkit-neutral `ApplicationController` owns dashboard-share expiry and cleanup lifecycle. Focused Qt/legacy/security coverage passed 210 tests; independent source-contract reviews approved the node behavior and sharing lifecycle.
- [x] A fresh wheel was built into `/tmp/opencode/qt-migration-wheel` without replacing the existing untracked `dist/` wheel. Deployment-validation tests can target it via `SYSTEM_ANALYZER_TEST_WHEEL`; the fresh-wheel validation group passed.
- [x] Qt Cluster's local dashboard-share action now opens a retained `QtSharingDialog`, reflects the current active state, dispatches start/stop through the toolkit-neutral controller, and releases its retained reference on close. Shell integration tests cover the action and dialog dispatch.
- [ ] Legacy test conversion, repository-wide static gates, and rendered/accessibility acceptance remain incomplete. The latest configured full suite completed with 2,174 passing tests after fixing the thermal test's deferred-delete lifecycle; see `.ui/qt-ui-migration/reports/` for the still-blocked UI acceptance decision.
- [x] Qt shell adapters and action dispatch are integrated for current page/dialog workflows, including async resource task delivery/cancellation and close guards; continue end-to-end lifecycle acceptance across startup, active work, and shutdown before removing legacy owners.

## Task 6: Integrate, remove Tk, and validate release surface

**Files:** all production files, tests, `README.md`, `AGENTS.md`, `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `tests/dump_ui.py`, `tests/support/live_tk.py`, `tests/test_live_tk_resize.py`.

### Task 6A: Extract toolkit-neutral application ownership before final cutover

- [x] Add a fresh-process import-boundary regression proving `import main` succeeds without loading any `tkinter` module; keep it separate from component-only import checks. `tests.test_qt_import_boundary.QtImportBoundaryTests.test_import_main_does_not_load_tkinter` and `test_constructing_qt_application_window_does_not_load_tkinter` pass.
- [x] Extract application state/service initialization and non-widget orchestration from Tk `window.AppWindow` into a toolkit-neutral owner while retaining `window.AppWindow` as a compatibility-facing Tk composition until equivalent coverage exists. `maintenance/application_state.py` and `maintenance/application_controller.py` own the extracted initialization and orchestration.
- [x] Change the Qt controller to compose/use the neutral owner; it must not import or subclass `window.AppWindow`. `QtAppController` extends `ApplicationController`; its construction/import boundary tests pass.
- [ ] Preserve initialization order, preferences/cluster restoration, role-dependent persistence, node context/trusted-node restoration, listener/discovery startup, deferred first scan, timer/delivery ownership, cancellation, shutdown, and legacy patch seams. Do not change domain or trust policy.
- [ ] Split only the shared imports that are proven to pull Tk into the active Qt closure; preserve APIs required by the still-live Tk implementation until final removal.
- [ ] Run the import-boundary regression red before implementation and green after; also run targeted legacy `AppWindow` characterization tests and Qt application/window tests. Continue only when the active `main` import closure is verified Tk-free.
- [ ] This batch was absent from the original sequence and is an integration prerequisite, not permission to use dynamic-import tricks or to claim full Tk removal.

- [x] Search production/test/package files for Tk imports and event-loop calls. Remaining production Tk owners are `window.py`, `maintenance/dialogs.py`, `maintenance/components/tk_delivery.py` and the legacy `BackgroundTaskRunner.run_in_thread` adapter, plus the legacy modules under `maintenance/ui/` (`layout`, page/dialog implementations, `navigation` adapter, `window_lifecycle`, `window_supports/timer_delivery`, and `thermal_graph`). Tk-bound tests/helpers remain in `test_window.py`, legacy page/dialog tests, `test_page_wiring_consistency.py`, `test_live_tk_resize.py`, `tests/support/live_tk.py`, and `tests/dump_ui.py`; they must be converted or replaced before their production owners are removed. Qt equivalents are present but do not yet replace every legacy lifecycle/acceptance assertion.
- [x] Remove direct Tk imports from the Qt integration test modules by importing presentation contracts from toolkit-neutral `page_specs` and `node_dialog_contracts`; `tests.test_qt_import_boundary.QtImportBoundaryTests.test_qt_integration_test_modules_do_not_import_tkinter` checks all Qt test modules in fresh interpreters. Qt app/window and dialog/node suites passed 61 tests after conversion.
- [x] Move `TkDeliveryQueue` into `maintenance/components/tk_delivery.py`; legacy Tk callers import it directly, and the toolkit-neutral `maintenance.components.background` no longer exposes the Tk compatibility alias. Importing `maintenance.components.background` and the `BackgroundTaskRunner` package export is Tk-free. The existing legacy delivery/dialog tests and fresh-process import regression pass. The `run_in_thread` Tk adapter remains until legacy dialog callers are migrated. Latest full suite: 2,174 tests passed in 172.590s.
- [x] Add/update package/import-boundary tests for the toolkit-neutral component package and active app startup. `tests.test_package_structure.PackageImportChainTests.test_component_package_import_does_not_require_tkinter` and `tests.test_qt_import_boundary` verify those boundaries; they intentionally do not assert that legacy compatibility modules are Tk-free before their removal.
- [ ] Remove Tk-only test helpers and live-Tk tests after equivalent Qt/offscreen coverage exists. Replace UI dump/render evidence harness with a Qt-compatible test helper only if still needed; do not delete evidence coverage without replacement.
- [ ] Remove active Tk imports, Tk symbols, obsolete Tk adapters, and Tk dependency references from production/tests/docs/package metadata. Keep only historical mentions when clearly labeled as migration history.
- [x] Run the full suite with the migration Python and fresh-wheel override: `QT_QPA_PLATFORM=offscreen PYTHON=/tmp/opencode/system-analyzer-qt-migration-venv/bin/python SYSTEM_ANALYZER_TEST_WHEEL=/tmp/opencode/qt-migration-wheel/system_analyzer-1.6.5.0-py3-none-any.whl scripts/run_tests.sh` — latest recorded run: 2,174 tests passed in 172.590s. The fresh wheel override is required because the preserved `dist/` wheel predates these source files.
- [ ] Capture matched synthetic Qt after-renders at 900/1280/1600px for each materially different page and representative dense/error/empty states; include long dialog/table/form content. Compare with the Tk baselines and record Qt style/platform differences.
- [ ] Verify keyboard focus order/visibility, dialog focus entry/return, accessible names/roles, status/progress notifications, and graph text alternatives with Qt accessibility inspection; document screen-reader and elevated-DPI platforms not available in the environment.
- [ ] Run `ruff check .`, `ruff format --check .`, `pyright`, and `mypy --ignore-missing-imports .`; fix failures attributable to touched code and record unrelated baseline failures explicitly.
- [ ] Run `git diff --check`, inspect `git status --short`, review the complete diff for trust/security/process/file cleanup behavior changes, and commit the completed migration only after all gates pass.

### Task 6 checkpoint — Qt application shell partially activated

- [x] Add test-first `create_application`/`run_application` helpers that reuse QApplication, set application metadata, show a factory-created QMainWindow, enter Qt's event loop, and do not enter the loop if window construction fails.
- [x] Add test-first `QtWindowShell` with retained QWidget pages, Qt `PageRouter` navigation, unknown-page safety, minimum sizing, and idempotent close callback.
- [x] Run `tests.test_qt_window_shell tests.test_navigation tests.test_qt_application`: 23 passed. Ruff/format/Pyright on these four files and `git diff --check` passed.
- [x] `main.py` now creates `QApplication` before constructing `QtAppWindow`; the Qt window is shown before entering the Qt event loop. A transitional `QtAppController` composes existing domain orchestration with the standalone Qt pages, and focused construction/navigation/scan-state tests pass.
- [ ] Migration acceptance is still incomplete: `QtAppController` now uses the toolkit-neutral `ApplicationController`, and fresh-process import tests show the active `main`/Qt-window path does not load Tk. However, legacy Tk production code and tests remain; rendered parity/accessibility, repository-wide static gates, and final regression conversion are still open. Do not remove Tk until all final gates pass.
- [x] Full-suite order-dependent crash investigated and resolved at the test-lifecycle boundary. `test_render_recovery_events_bounds_and_node_independent_input` now drains pending `deleteLater()` row events while the owning thermal page is retained; the configured full suite completes with 2,174 passing tests after the import-boundary additions.

## Remaining completion plan — execute this section in order

This section is the canonical plan for the unfinished migration. Earlier checked
items record completed work; unchecked items above remain open until the matching
acceptance evidence below is recorded. Keep each existing Tk implementation
available while a live caller still uses it. Do not delete the legacy shell,
test helpers, or packaging entry until the final cutover phase. The intended end
state is Qt-only production, tests, and package contents—not a dual-toolkit
fallback. Clearly labeled historical migration notes may still mention Tk.

### Completion baseline and ownership map

| Concern | Current owner/evidence | Completion action |
|---|---|---|
| Active entry | `main.py`, `maintenance/ui/qt_application.py`, `maintenance/ui/qt_app_window.py`; fresh-process boundaries in `tests/test_qt_import_boundary.py` | Preserve Qt-only import/start behavior and extend lifecycle characterization before deleting compatibility owners. |
| Legacy shell/composition | `window.py`, `maintenance/ui/window_pages.py`, `window_lifecycle.py`, `window_presentation.py`, `window_node_runtime.py`, `window_supports/timer_delivery.py`; shared seams in `window_components.py`, `window_context.py`, `styles.py`, and `action_coordinator.py` | Replace or retire only after equivalent Qt/controller coverage and caller search; adapt shared modules rather than deleting Qt-used owners. |
| Tk pages/dialogs | `maintenance/dialogs.py`; `dashboard_page.py`, `layout.py`, `settings_home.py`, `preferences_page.py`, `nodes_connections.py`, `cluster_page.py`, `thermals_page.py`, `thermal_graph.py`, `diagnostics_page.py`, `help_page.py`; `connection_dialog.py`, `node_details_dialog.py`, `pairing_dialog.py`, `sharing_dialog.py` | Keep each until its behavior has Qt coverage and the legacy shell no longer imports it; then delete the Tk-only implementation instead of retaining a fallback. |
| Tk async/timer adapters | `maintenance/components/tk_delivery.py`; `BackgroundTaskRunner.run` / `run_in_thread` in `maintenance/components/background.py`; `maintenance/ui/window_supports/timer_delivery.py` | Preserve close, cancellation, delivery-thread, and stale-result contracts in Qt tests; remove these adapters only after all Tk consumers are gone. |
| Qt counterparts | `qt_dashboard.py`, `qt_layout.py`, `qt_settings.py`, `qt_nodes_connections.py`, `qt_cluster.py`, `qt_thermals_page.py`, `qt_thermal_graph.py`, `qt_diagnostics_page.py`, `qt_help_page.py`, `qt_node_dialogs.py`, `qt_resource_dialogs.py`, and `qt_window.py` | Treat these as the UI implementation to integrate and validate; keep policy in existing domain/controller owners. |
| Tk-bound evidence | `tests/test_window.py`, `test_window_extraction.py`, `test_window_placement.py`, `test_window_supports.py`, `test_window_scan_runtime.py`, `test_window_nodes.py`, legacy page/dialog tests, `test_page_wiring_consistency.py`, `test_live_tk_resize.py`, `tests/support/live_tk.py`, `tests/dump_ui.py` | Convert behavior assertions to Qt or toolkit-neutral tests before removing their Tk fixtures. Retain only tests that still prove a non-UI contract. |
| Packaging/docs | `pyproject.toml` includes top-level `window`; `README.md`, `AGENTS.md`, and `maintenance/ui/help_content.py` retain legacy references | Remove active compatibility and Tk-availability wording at final cutover; preserve only explicit historical context. |

The inventory is a starting map, not permission to delete by filename. Before
each deletion, search all source, tests, package metadata, and docs for imports,
dynamic lookups, patch seams, and command-entry references. Source files under
`build/` are generated build artifacts and are not migration owners; build into
`/tmp/opencode/qt-migration-wheel` and do not replace the preserved `dist/` wheel.
At the 2026-10-20 checkpoint, the configured full suite passed 2,176 tests in
181.781s using the preserved wheel override. Repository-wide static gates are
not green: Ruff reports one unused import; format reports 17 files; Pyright
with the migration interpreter reports zero errors and one `__all__` warning;
Mypy 2.3.1 reports 129 existing typing errors across 28 files when run with the
repository-configured app-and-test scope. Re-run these gates at final acceptance
rather than treating this snapshot as completion evidence. Commit and push each
coherent migration-owned batch as requested, while staging only the files for
that batch and preserving unrelated user working-tree edits.

### Phase A — close lifecycle and behavior-coverage gaps

**Checkpoint (2026-10-20):** `tests/test_qt_app_window.py` now characterizes
that preferences and cluster state load before listener startup, the listener
and discovery startup hooks both run when discovery is disabled, the first scan
is scheduled through the Qt timer owner at 350 ms, and closing twice suppresses
queued worker/timer callbacks. `test_run_shows_window_before_entering_event_loop`
continues to cover show-before-event-loop ordering. The focused command below
passed 62 tests; Ruff check/format and Pyright passed for the changed test file.
Mypy is now installed, but its configured repo-wide run still reports 129
existing errors across 28 files. This is partial Phase A
evidence—not completion of the crosswalk, startup edge cases, or cancellation
propagation requirements.

**Files:** `tests/test_qt_app_window.py`, `tests/test_qt_application.py`,
`tests/test_application_controller.py`, `tests/test_qt_window_shell.py`,
`tests/test_qt_import_boundary.py`; implementation only if a test exposes a
missing Qt integration behavior: `main.py`, `maintenance/ui/qt_application.py`,
`maintenance/ui/qt_app_window.py`, `maintenance/ui/qt_window.py`, and the
toolkit-neutral `maintenance/application_controller.py`.

- [ ] Build a behavior crosswalk from legacy `tests/test_window*.py`,
  `tests/test_window_supports.py`, `tests/test_window_scan_runtime.py`, and
  `tests/test_window_nodes.py` to Qt integration tests or toolkit-neutral
  controller tests. Mark each legacy assertion `covered`, `retained as a
  domain-contract test`, or `not applicable with evidence`; do not delete
  assertions merely because their test imports Tk.
- [ ] Add test-first Qt startup-order assertions for preferences and cluster
  restoration before scheduler/node setup, listener startup independent of the
  discovery preference, discovery enable/disable behavior, and first scan
  deferred until after the window can paint. Use temporary preference/cluster
  stores and injected fakes; do not bind real listeners or write user state.
- [ ] Add test-first close/shutdown assertions for repeated close, pending timer
  cancellation, worker completion after close, cancellation propagation, and
  no callback touching a closed/deleted widget. Use controlled worker/delivery
  fakes and Qt offscreen mode; avoid timing-only sleeps where a synchronization
  event or deferred runner can prove ordering.
- [ ] Run focused tests before and after any implementation change:
  `QT_QPA_PLATFORM=offscreen PYTHON=/tmp/opencode/system-analyzer-qt-migration-venv/bin/python scripts/run_tests.sh tests.test_qt_app_window tests.test_qt_application tests.test_application_controller tests.test_qt_window_shell tests.test_qt_import_boundary -v`.
  Expected: all tests pass and fresh-process `main` import/window construction
  still leaves every `tkinter` module absent from `sys.modules`.
- [ ] Update the crosswalk/checkpoint in this plan with exact test names and
  commands. Do not change domain, trust, persistence, process, or cleanup policy
  to make Qt tests pass.

### Phase B — matched visual evidence and rendered opposition

**Files:** existing Tk capture harness `tests/dump_ui.py` (read-only baseline
until final removal), new Qt capture harness `tests/dump_qt_ui.py`,
`tests/support/qt.py` and shared model fixtures only if needed, screenshots under
`.ui/qt-ui-migration/evidence/screenshots/`, and
`.ui/qt-ui-migration/reports/ui-validation-report.md` plus
`ui-opposition-report.md`.

- [ ] Define deterministic shared fixture data for both harnesses so Tk/Qt
  captures have identical viewport, content, node roles/trust/connection state,
  scan state, and dialog state. Capture Tk before deleting any Tk harness; use
  only synthetic fixture data and temporary stores.
- [ ] Capture paired Tk and Qt dashboard, Settings, Preferences, Nodes,
  Cluster, Thermals, Diagnostics, Help hub/topic, and resource/dialog surfaces
  at 900, 1280, and 1600 pixel widths. Include empty, representative populated,
  dense/long-content, error/recovery, scan busy/progress/complete, trust/action,
  and open-dialog states wherever those states exist. Record unavailable or
  inapplicable combinations explicitly rather than comparing unlike states.
- [ ] Inspect matched screenshots for clipping, overflow, scrolling, density,
  hierarchy, focus indication, and action visibility. Resolve confirmed Qt
  defects with test-first changes; record native-platform differences as
  differences, not automatically as defects.
- [ ] Update both UI reports with capture paths, matched-state mapping,
  viewport results, confirmed defects/fixes, unresolved concerns, and an explicit
  parity decision. Obtain an independent rendered-evidence opposition review.
  **Gate:** no unresolved parity concern that could hide a behavior regression.

### Phase C — keyboard and accessibility acceptance

**Files:** relevant Qt tests under `tests/test_qt_*.py`, Qt UI modules only when
tests demonstrate a defect, and `.ui/qt-ui-migration/reports/ui-validation-report.md`.

- [ ] Record a keyboard-only walkthrough for primary navigation, dashboard
  actions, settings forms, node/cluster actions, thermal/help/diagnostic routes,
  and each modal dialog: initial focus, tab order, visible focus, activation,
  validation/error announcement, Escape/close, and focus return to the opener.
- [ ] Inspect accessible names, roles, and states across the Qt widget tree;
  add automated assertions for missing names, focusability, disabled/busy state,
  and graph text alternatives. Do not treat selected widget-name tests as a
  whole-surface inspection.
- [ ] Run a Linux Orca spot-check if Orca and a usable display are available.
  Record platform/tool availability, contrast results for the active palette,
  reduced-motion findings, and any screen-reader/elevated-DPI limitations.
- [ ] Fix confirmed issues test-first, rerun affected Qt tests and the keyboard
  flow, then record pass/fail/limitations in the validation report. **Gate:**
  keyboard flow and accessible-tree review complete; no unaddressed blocker.

### Phase D — convert legacy regressions while Tk remains available

Keep the legacy implementation executable throughout these conversions. For
each behavior group, add/adapt the Qt or toolkit-neutral assertion first, run it
to prove it detects the missing contract where applicable, then compare it with
the legacy characterization. Preserve domain and safety tests even when the
Tk fixture is removed.

#### D1 — reusable layout, routing, and dashboard

**Files:** `tests/test_ui_primitives.py`, `tests/test_navigation.py`,
`tests/test_dashboard_ui.py`, `tests/test_qt_dashboard.py`,
`maintenance/ui/qt_layout.py`, `maintenance/ui/qt_window.py`.

- [ ] Port assertions for retained page identity, unknown-page behavior,
  navigation rollback, resize-aware wrapping/scrolling, card ordering/visibility,
  scan status, and dashboard actions to Qt widgets and `QtWindowShell`.
- [ ] Keep toolkit-neutral scan/coordinator tests independent of either widget
  toolkit. Do not preserve Tk geometry-manager assertions as the only evidence
  for user-visible behavior.
- [ ] Run `QT_QPA_PLATFORM=offscreen PYTHON=/tmp/opencode/system-analyzer-qt-migration-venv/bin/python scripts/run_tests.sh tests.test_ui_primitives tests.test_navigation tests.test_dashboard_ui tests.test_qt_dashboard tests.test_qt_window_shell -v`.

#### D2 — pages and graphs

**Files:** legacy page tests `tests/test_settings_home.py`,
`test_preferences_page.py`, `test_nodes_connections_page.py`,
`test_cluster_page.py`, `test_thermals_page.py`, `test_telemetry_graph.py`,
`test_diagnostics_page.py`, `test_help_page.py`, `test_help_content.py`;
Qt tests `tests/test_qt_settings.py`, `test_qt_nodes_connections.py`,
`test_qt_cluster.py`, `test_qt_thermals.py`, `test_qt_diagnostics_page.py`,
`test_qt_help_page.py`; shared contracts in `page_specs.py` and
`window_page_data.py`.

- [ ] Crosswalk and retain assertions for persisted preferences, refresh
  bounds, visibility/auto-hide, node axes and identity, cluster action policy,
  thermal unsupported/recovery semantics, diagnostics partial/error states,
  and Help content/callback behavior.
- [ ] Replace any test that only asserts Tk widget construction with a Qt
  behavior/accessibility assertion. Leave domain projection/telemetry tests in
  toolkit-neutral suites. Do not delete legacy page modules while `window.py`
  still imports them.
- [ ] Run the listed legacy/Qt page suites together with
  `QT_QPA_PLATFORM=offscreen PYTHON=/tmp/opencode/system-analyzer-qt-migration-venv/bin/python scripts/run_tests.sh tests.test_qt_settings tests.test_qt_nodes_connections tests.test_qt_cluster tests.test_qt_thermals tests.test_qt_diagnostics_page tests.test_qt_help_page tests.test_settings_home tests.test_preferences_page tests.test_nodes_connections_page tests.test_cluster_page tests.test_thermals_page tests.test_telemetry_graph tests.test_diagnostics_page tests.test_help_page tests.test_help_content -v`.

#### D3 — dialogs, actions, and safety boundaries

**Files:** `tests/test_info_dialog.py`, `test_process_table.py`,
`test_storage_dialog.py`, `test_node_toplevel_dialogs.py`, relevant cases in
`test_window_nodes.py`; Qt suites `test_qt_resource_dialogs.py`,
`test_qt_node_dialogs.py`, `test_qt_app_window.py`; production counterparts
`qt_resource_dialogs.py`, `qt_node_dialogs.py`, and `window_node_actions*`.

- [ ] Retain confirmation intent, validation, busy/read-only/unknown states,
  cancellation, close guards, and action dispatch to existing policy owners.
  Keep process/file cleanup, trust, pairing, and authorization tests even if
  their original UI harness is removed.
- [ ] Replace Tk-only layout/wrap assertions with Qt rendered/interaction
  evidence; keep formatters and controller behavior tested without widgets.
- [ ] Run `QT_QPA_PLATFORM=offscreen PYTHON=/tmp/opencode/system-analyzer-qt-migration-venv/bin/python scripts/run_tests.sh tests.test_qt_resource_dialogs tests.test_qt_node_dialogs tests.test_qt_app_window tests.test_info_dialog tests.test_process_table tests.test_storage_dialog tests.test_node_toplevel_dialogs -v` and the relevant remote/security/action tests named by the crosswalk.

#### D4 — app shell and miscellaneous legacy-only harnesses

**Files:** `tests/test_window.py`, `test_window_extraction.py`,
`test_window_placement.py`, `test_window_supports.py`,
`test_window_scan_runtime.py`, `test_window_nodes.py`,
`test_page_wiring_consistency.py`, `test_action_coordinator.py`, `test_live_tk_resize.py`,
`tests/support/live_tk.py`, `tests/dump_ui.py`.

- [ ] Move each remaining non-UI invariant to `ApplicationController`,
  `QtAppController`, or a toolkit-neutral owner test. Replace page-wiring
  reflection with explicit Qt shell/page registration assertions.
- [ ] Preserve live-resize evidence through the matched Qt screenshots and
  offscreen resize tests before deleting `tests/support/live_tk.py` and
  `tests/test_live_tk_resize.py`.
- [ ] Keep `tests/dump_ui.py` until Phase B evidence is accepted; then replace
  any still-needed structural evidence with `tests/dump_qt_ui.py` and remove the
  Tk harness. Do not delete a test/helper until its replacement evidence is
  present and recorded.
- [ ] Run the converted shell/controller suites plus the full focused Qt suite;
  verify no tests outside the legacy compatibility tests import `window` or a
  Tk page/dialog module.

### Phase E — final Qt cutover and Tk deletion

**Precondition:** Phases A–D are complete; the matched-render and accessibility
gates in B/C are explicitly accepted; every retained behavioral contract has a
Qt/toolkit-neutral test owner. Do not start this phase while a required gate is
open.

**Files to review/remove or adapt after caller search:** top-level `window.py`;
Tk-only `maintenance/dialogs.py`, `maintenance/components/tk_delivery.py`,
legacy page/dialog modules listed in the ownership map, `window_pages.py`,
Tk-only lifecycle/timer support; shared `styles.py`, `action_coordinator.py`,
`window_components.py`, `window_node_runtime.py`, and `window_presentation.py`
must have their remaining Tk-only seams removed without deleting Qt-used code;
`tests/support/live_tk.py`,
`tests/test_live_tk_resize.py`, `tests/dump_ui.py`, and any fully superseded Tk
tests; `pyproject.toml`, `README.md`, `AGENTS.md`, `maintenance/ui/help_content.py`,
package/layout tests and wheel validation.

- [ ] Re-run whole-repository source/caller searches for `window`, legacy
  page/dialog symbols, `tkinter`, `ttk`, `.after`, `.pack`, and Tk error types.
  Classify every match as a live Qt use, a contract still needing conversion,
  or a deletion candidate; update this plan's inventory before editing.
- [ ] Add a final import/build regression first: fresh processes must import
  `main` and construct/close the Qt app without loading Tk; the wheel must omit
  `window.py` and deleted Tk-only modules. Observe expected failure against the
  current wheel/source before deleting the owners.
- [ ] Remove the legacy `window.AppWindow` shell and its Tk-only composition
  modules only after all callers/tests have migrated. Preserve `main.py` as the
  sole GUI entry and preserve CLI, instance lock, logging, exit code, and
  shutdown order. Do not add a fallback or dynamic import of Tk.
- [ ] Remove Tk-only page/dialog implementations and adapters only when the
  post-shell import search proves no production caller remains. Remove the Tk
  methods from `BackgroundTaskRunner` after legacy dialog callers are gone;
  keep the Qt injected-delivery runner and its cancellation/close tests.
- [ ] Remove `window` from `pyproject.toml` `py-modules`; remove obsolete Tk
  source modules from package contents; update package-structure, import-boundary,
  and deployment-wheel tests. PySide6 remains the required GUI dependency.
- [ ] Update `README.md`, `AGENTS.md`, and user-facing Help content to describe
  Qt-only startup and remove instructions that Tkinter/python3-tk must be
  available. Preserve historical migration reports only when explicitly labeled
  as history; do not claim compatibility with the deleted Tk API.
- [ ] Delete Tk-only test helpers and tests only after D1–D4 replacements and
  Phase B visual evidence are recorded. Final source/docs/tests/package scan must
  find no active Tk UI imports, runtime path, dependency, or shipped module.

### Phase F — final static, wheel, regression, and handoff gates

- [ ] Ensure Mypy exists in the validation environment using the repository's
  pinned dev dependency (`/tmp/opencode/system-analyzer-qt-migration-venv/bin/python -m pip install -e '.[dev]'`); do not silently skip the gate because the prior venv lacked it. Resolve repository-wide Ruff/format and Pyright findings required to make the listed gates green; review any broader cleanup for semantic changes and keep it in a separate, clearly scoped commit when it is unrelated to Tk retirement.
- [ ] Run `ruff check .`, `ruff format --check .`, `pyright`, and
  `mypy --ignore-missing-imports .`; all must exit successfully for completion.
- [ ] Build a fresh wheel outside the repository:
  `mkdir -p /tmp/opencode/qt-migration-wheel/final && PYTHON=/tmp/opencode/system-analyzer-qt-migration-venv/bin/python && "$PYTHON" -m build --wheel --no-isolation --outdir /tmp/opencode/qt-migration-wheel/final`.
  Use the wheel emitted in that empty `final/` directory for deployment tests,
  not the preserved `dist/` artifact.
- [ ] Run the full release validation:
  `FRESH_WHEEL="$(find /tmp/opencode/qt-migration-wheel/final -maxdepth 1 -type f -name 'system_analyzer-*.whl' -print -quit)" && test -n "$FRESH_WHEEL" && QT_QPA_PLATFORM=offscreen PYTHONFAULTHANDLER=1 PYTHON=/tmp/opencode/system-analyzer-qt-migration-venv/bin/python SYSTEM_ANALYZER_TEST_WHEEL="$FRESH_WHEEL" scripts/run_tests.sh`.
  Expected: zero failures/errors; deployment tests confirm no removed Tk module
  is shipped and the `main` import/construct boundary is Tk-free.
- [ ] Review `git diff --check`, `git status --short`, the complete migration
  diff, and the final search results. Confirm no domain/trust/process/file
  cleanup policy changed, no preserved wheel/user artifact was overwritten, and
  only intended migration files are staged/committed/pushed.
- [ ] Update `.ui/qt-ui-migration/reports/ui-validation-report.md`,
  `ui-opposition-report.md`, and this plan with exact commands, test counts,
  wheel path, static results, accessibility limitations, and a final accepted
  or blocked decision. Mark the final checklist complete only after all gates
  pass and the source/package scan proves Tk removal.
- [ ] Update `docs/specs/2026-10-18-qt-ui-migration-design.md` status from
  “implementation not started” to the verified final migration status; keep the
  approved architecture and original non-goals unchanged.

**Completion definition:** the app launches and exits only through Qt; no
production, test-runtime, or packaged Tk path remains; Qt/toolkit-neutral tests
preserve the old behavior contracts; matched rendering and accessibility
acceptance are documented; full tests, lint, format, Pyright, Mypy, and fresh
wheel validation pass. If any gate fails, leave the migration incomplete and
report the exact blocker rather than removing the remaining Tk path prematurely.

## Final acceptance checklist

- [ ] QApplication is the sole desktop event loop; no Tk runtime dependency or active Tk UI code remains.
- [ ] Tests are written/adapted before every UI section and focused tests run before and after each port.
- [ ] All existing behavior contracts remain covered, including startup/shutdown, navigation/page wiring, refresh preferences, dashboard states, async delivery/timers, dialogs, action safety, node/cluster workflows, thermal unsupported states, and help/diagnostics.
- [ ] No worker thread mutates Qt widgets; close/cancel/stale-delivery behavior is verified.
- [ ] Full test, lint, format, Pyright, and Mypy checks pass; complete diff is reviewed.
- [ ] Migration-owned files/hunks are staged explicitly; all pre-existing user edits and untracked artifacts remain unstaged and unchanged.

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
- [ ] Legacy test conversion, repository-wide static gates, and rendered/accessibility acceptance remain incomplete. The configured full suite completed with 2,172 passing tests after fixing the thermal test's deferred-delete lifecycle; see `.ui/qt-ui-migration/reports/` for the still-blocked UI acceptance decision.
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

- [x] Search production/test/package files for Tk imports and event-loop calls. Remaining production Tk owners are `window.py`, `maintenance/dialogs.py`, `maintenance/components/background.py`, and the legacy modules under `maintenance/ui/` (`layout`, page/dialog implementations, `navigation` adapter, `window_lifecycle`, `window_supports/timer_delivery`, and `thermal_graph`). Tk-bound tests/helpers remain in `test_window.py`, legacy page/dialog tests, `test_page_wiring_consistency.py`, `test_live_tk_resize.py`, `tests/support/live_tk.py`, and `tests/dump_ui.py`; they must be converted or replaced before their production owners are removed. Qt equivalents are present but do not yet replace every legacy lifecycle/acceptance assertion.
- [x] Add/update package/import-boundary tests for the toolkit-neutral component package and active app startup. `tests.test_package_structure.PackageImportChainTests.test_component_package_import_does_not_require_tkinter` and `tests.test_qt_import_boundary` verify those boundaries; they intentionally do not assert that legacy compatibility modules are Tk-free before their removal.
- [ ] Remove Tk-only test helpers and live-Tk tests after equivalent Qt/offscreen coverage exists. Replace UI dump/render evidence harness with a Qt-compatible test helper only if still needed; do not delete evidence coverage without replacement.
- [ ] Remove active Tk imports, Tk symbols, obsolete Tk adapters, and Tk dependency references from production/tests/docs/package metadata. Keep only historical mentions when clearly labeled as migration history.
- [x] Run the full suite with the migration Python and fresh-wheel override: `QT_QPA_PLATFORM=offscreen PYTHON=/tmp/opencode/system-analyzer-qt-migration-venv/bin/python SYSTEM_ANALYZER_TEST_WHEEL=/tmp/opencode/qt-migration-wheel/system_analyzer-1.6.5.0-py3-none-any.whl scripts/run_tests.sh` — 2,172 tests passed in 158.810s. The fresh wheel override is required because the preserved `dist/` wheel predates these source files.
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
- [x] Full-suite order-dependent crash investigated and resolved at the test-lifecycle boundary. `test_render_recovery_events_bounds_and_node_independent_input` now drains pending `deleteLater()` row events while the owning thermal page is retained; the configured full suite completes with 2,172 passing tests.

## Final acceptance checklist

- [ ] QApplication is the sole desktop event loop; no Tk runtime dependency or active Tk UI code remains.
- [ ] Tests are written/adapted before every UI section and focused tests run before and after each port.
- [ ] All existing behavior contracts remain covered, including startup/shutdown, navigation/page wiring, refresh preferences, dashboard states, async delivery/timers, dialogs, action safety, node/cluster workflows, thermal unsupported states, and help/diagnostics.
- [ ] No worker thread mutates Qt widgets; close/cancel/stale-delivery behavior is verified.
- [ ] Full test, lint, format, Pyright, and Mypy checks pass; complete diff is reviewed.
- [ ] Migration-owned files/hunks are staged explicitly; all pre-existing user edits and untracked artifacts remain unstaged and unchanged.

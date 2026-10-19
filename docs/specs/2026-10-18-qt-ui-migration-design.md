# System Analyzer Qt UI Migration Design

**Status:** Approved design; implementation not started
**Date:** 2026-10-18

## Goal

Replace System Analyzer's Tkinter/ttk desktop UI with a native PySide6/Qt Widgets
frontend, preserving existing user-visible features, workflows, safety behavior,
and test coverage. This is a deliberate breaking UI-backend migration: Tk is
removed rather than retained as a compatibility or fallback path.

## Reference architecture

The local Expra editor is a reference for Qt integration boundaries, not a source
of UI/product behavior to copy wholesale. Its current implementation provides
these relevant patterns:

- `expra_engine.editor.window_core.EditorWindowCore` owns shared editor logic,
  while `expra_engine.editor.qt.main_window.EditorWindow` owns the Qt shell.
- `editor/qt/app.py` owns `QApplication`, theme setup, and the Qt event loop.
- `editor/qt/delivery.py` queues worker callbacks for bounded delivery on the UI
  thread; `editor/qt/timer_delivery.py` centralizes cancellable Qt timers.
- Qt widgets, dialogs, menus, and layout live in `editor/qt/` adapters.

System Analyzer should adopt the applicable separation, thread-affinity, timer,
and startup patterns. It should retain its own existing page organization,
workflows, scan/coordinator policies, domain model, and visual identity. In
particular, Expra-specific editor panels, engine abstractions, and event-loop
details are not copied as product features.

## Architecture and ownership

- `main.py` remains the process entry point and retains argument parsing,
  single-instance locking, logging, and shutdown ownership. It creates or
  delegates creation of `QApplication` and runs the Qt event loop.
- A Qt `QMainWindow`-based application window remains the composition root for
  preferences, cluster state, domain services, coordinators, page routing, and
  application shutdown.
- A Qt delivery adapter is the sole path for worker-produced UI callbacks.
  Workers must not call Qt widgets directly. Delivery remains bounded and
  closing-aware, preserving existing cancellation/staleness protections.
- A Qt timer adapter replaces Tk `after`/`after_cancel` usage and preserves
  cancellable timer IDs, callback ordering expectations, and close behavior.
- Existing UI responsibilities remain in `maintenance/ui/`, with Qt-native
  widgets and layout. Existing domain and scanning modules remain UI-toolkit
  independent wherever they currently are.
- Existing content, accessible labels, interaction outcomes, dialogs, table
  operations, page state, preferences, node/cluster operations, thermal graphs,
  and dashboard status behavior are preserved unless a separately approved
  change is made.

## Folder-by-folder, test-first implementation sequence

Each section follows the same strict loop: (1) identify the existing behavioral
contracts and tests, (2) add or adapt Qt-focused tests for that section before
changing its UI implementation, (3) run those tests and confirm they fail for
the expected missing-Qt behavior (or pass for toolkit-independent contracts),
(4) migrate only that section, and (5) rerun the focused tests before integration
and moving to the next section. Do not convert the entire test suite up front or
leave a repository-wide collection of expected failures. Existing test meaning
and coverage must be retained even when Tk fixture code is replaced.

1. **Test harness and packaging baseline** — add PySide6 as a required runtime
   dependency and establish an offscreen Qt test fixture. Add characterization
   tests for application startup/shutdown without removing the current Tk path
   yet; verify the fixture itself works in the repository's supported test
   command.
2. **Application shell and shared infrastructure** — first add Qt behavior tests
   for application lifecycle, timer scheduling/cancellation, worker delivery on
   the GUI thread, navigation, and close-time cleanup; then port the shell,
   delivery, timer, navigation, style, layout, and lifecycle owners. Retain
   equivalent cancellation, coalescing, stale-delivery, and visibility behavior.
3. **Dashboard and common presentation** — first add/adapt tests for dashboard
   construction, cards, status transitions, and rendering; then port those UI
   owners and run the focused tests.
4. **Remaining pages** — for each ownership-sized page section, first migrate or
   add tests for its current behavior, then port settings/preferences,
   nodes/connections, cluster, thermals/graphs, diagnostics, or help/content and
   run that section's focused tests before starting another.
5. **Dialogs and actions** — for each dialog family, first adapt tests for
   confirmation, validation, cancellation, and safe-action boundaries; then
   migrate process/storage/info, connection, pairing, node details, sharing, and
   other dialogs and run the focused tests.
6. **Integration and Tk removal** — run cross-section and full-suite tests after
   all Qt paths are covered. Only then remove Tk production imports, Tk-only
   fixtures/helpers, dependency references, and obsolete Tk UI paths. Run the
   full suite again to prove no active Tk path remains.

## Delegation boundaries

Subagents may be used for independent page/dialog sections after the shared Qt
shell and infrastructure contracts are established. Each delegated section must
have explicit, non-overlapping file ownership, a defined callback/threading
contract, and a test-first mandate: update/add that section's tests before its UI
code, run the focused tests, implement the port, and rerun those tests. Each
delegation returns the test commands and results with its changes. Shared shell,
lifecycle, delivery, navigation, and packaging changes are coordinated
centrally. No two agents may edit the same file concurrently; cross-section
integration is performed after delegated changes return.

## Tests and acceptance criteria

Tests retain their existing behavioral intent and coverage; they do not need to
retain Tk-specific fixture implementations. For every section, establish its Qt
tests before porting that section and run them both before and after the port.
Use Qt offscreen mode for real Qt widget tests where practical and
toolkit-independent fakes for domain/coordinator contracts. Preserve coverage
for startup/shutdown, page wiring/navigation, preferences, dashboard state,
dialogs and action safety, async delivery, timer cancellation, stale-result
rejection, and node/cluster workflows.

The migration is complete when:

- The application starts and exits through `QApplication`/Qt without importing
  or requiring Tkinter.
- All existing UI features and established user-visible behavior are available
  through the Qt frontend.
- Worker results reach widgets only on the Qt GUI thread, and delivery/timers
  stop safely during shutdown.
- The migrated test suite preserves existing behavioral contracts and passes,
  along with repository lint, formatting, and type-check gates.
- Production code, tests, packaging, and documentation contain no active Tk UI
  path or Tk runtime dependency.
- No domain, network, trust, persistence, process-safety, or cleanup behavior is
  changed as collateral to the UI migration.

## Explicit non-goals

- Copying Expra's editor appearance, editor panels, workflows, or internal
  abstractions wholesale.
- Rewriting scanner, remote-cluster, persistence, or process/file safety logic.
- Keeping Tk as a fallback backend or preserving Tk-specific widget APIs.
- Redesigning the UI beyond what is needed to express existing behavior using
  Qt-native controls and layout.

## Workspace constraint

The local folder was later initialized against the supplied GitHub remote and
is now on `feature/qt-ui-migration`. That branch carries pre-existing modified
and untracked user work; the migration must not overwrite or stage unrelated
files/hunks. The design/spec files are uncommitted on the feature branch.

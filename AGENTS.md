# Repo Guide

## Canonical Documentation Index

Five files own all durable knowledge.  Read the relevant one before editing:

| File | Owns |
|---|---|
| `AGENTS.md` (this file) | Repo law, code structure, test/lint rules |
| `docs/REMOTE_CLUSTER_TRUE_FLOW.md` | Pairing, trust, cluster phases, distributed state model |
| `docs/SYSTEM_ARCHITECTURE_REVIEW.md` | Module ownership, call graph, state locations (supersedes `docs/SYSTEM_ANALYZER_REVIEW.md`) |
| `docs/PLATFORM.md` | Windows/platform rules, capability matrix, fix protocol, thermal model |
| `docs/SECURITY.md` | No-log rules, trust model, process safety, fencing tokens, firewall rules |

All other docs under `docs/` are historical evidence trails or archived plans.
Never use an old plan or audit doc as implementation proof without verifying the code.

## Security and Logging Constraints

These apply everywhere, always:

- **Never commit secrets.**
- **Do not log:** HMAC secrets; private keys; fencing token values.  Fencing token *presence* may be recorded, not the value.
- **Do not expose the fence token in user-visible evidence.**
- **Do not weaken security/firewall configuration automatically.**
- **DO NOT blindly delete user state.**
- **DO NOT say "remote cluster is fully validated" merely because automated tests pass.**
- Physical two-node testing is required; see `docs/PLATFORM.md` and `docs/PHYSICAL_TWO_NODE_ACCEPTANCE_2026-09-17.md`.

## Windows Platform Rules

- **WINDOWS IS A PLATFORM DIFFERENCE, NOT A SECURITY EXCEPTION. FIX THE PLATFORM BOUNDARY. DO NOT FORK THE TRUST MODEL.**
- DO NOT develop on Windows; DO NOT run tests/source tools on Windows.
- DO NOT disable firewalls globally; DO NOT disable ProtonVPN permanently.
- DO NOT open the entire LAN to arbitrary ports; DO NOT hardcode ProtonVPN-specific behavior.
- Windows machine (`DESKTOP-0C2C5H3`) is a black-box runtime node only — install wheel, run app, report results.
- See `docs/PLATFORM.md` for the full protocol and capability matrix.

## Cluster Three Axes (never collapse)

TRUST (pairing/records/grants) · CLUSTER (assignments/joined state) · CONNECTION (Online/Offline).
Coordinator identity on a joined Worker comes from `coordinator_epoch.coordinator_id`.
See `docs/REMOTE_CLUSTER_TRUE_FLOW.md` for the full distributed state model.


- `main.py` is the app entrypoint (`python main.py`); it only creates `window.AppWindow`.
- `window.py` owns the Tk root, scan timers, and `ScanCoordinator`; GUI tests use fake masters/widgets instead of a live Tk mainloop.
- `algo.py` is the app-level facade for dashboard scans and cleanup entry points, delegating discovery and scan logic to `maintenance/scanner.py`.
- `maintenance/components/` is the component-subsystem package with one module per responsibility (`scan_support`, `process_safety`, `downloads`, `gpu`, `background`, `catalog`, `coordinator`); its `__init__.py` is the stable public interface re-exporting the historical `maintenance.components` names, and `maintenance/external_commands.py` owns generic external-command execution. GUI tests use fake masters/widgets instead of a live Tk mainloop.
- `maintenance/actions.py` is the only place that quits processes or moves files to Trash; it rejects protected or foreign-user PIDs and non-Downloads, symlink, or non-file cleanup targets.
- `maintenance/ui/` is the presentation layer: `styles.py` owns design tokens + ttk style registration, `layout.py` owns reusable widget construction (scrollable areas, metric rows, settings section/row primitives, dialog shells, footers, dashboard header with optional node label, resize-aware wrap helpers), `scan_status.py` owns the shared global scan-status wording/styles, `transition.py` owns the latest-wins cancellable delayed state-change rule behind smooth status transitions, and `navigation.py` owns the reusable in-window `PageRouter`/`PageSpec` page-switching layer (eager persistent frames switched with `pack_forget`/`pack`). `maintenance/ui/settings_home.py` owns the Settings category hub (a lightweight landing page listing one navigation card per category; no preference controls), and `maintenance/ui/preferences_page.py` is the reusable Preferences page adapter (presentation-only, dependency-style callbacks/values) reached as a sub-page from the hub. `maintenance/dialogs.py` keeps the dialog/card adapters and composes these primitives; `window.py` is the controller and composition root. UI primitives never import scanners, managers, or network code, and importing them creates no Tk root.
- `maintenance/preferences.py` owns the central preferences model (`AppPreferences`), per-component interval policies (`IntervalPolicy`), and the atomic JSON `PreferencesStore`; defaults derive from `RefreshIntervals`, and `window.py` loads preferences before building the scheduler so persisted refresh intervals, card visibility, and automatic unavailable-card hiding apply at startup. `maintenance/components/coordinator.py` also owns the reusable `AppCoordinator` (dependency-composed per-key shock absorber: coalesced triggers, cached-result retrieval, cooperative cancel/retry, and one injected delivery path onto the Tkinter thread) used by the pages, the dashboard, component scans, and the Storage/Process dialogs.
- `maintenance/dialogs.py` and `window.py` compose the shared primitives; `tests/dump_ui.py` is a render-structure evidence harness for before/after UI comparisons (it pumps idle callbacks so resize-aware widths are captured deterministically), and `tests/test_live_tk_resize.py` exercises resize-aware layout on a real Tk root, skipping cleanly when no display is available.
- Install from `pyproject.toml` (metadata + dependencies, mirroring `requirements.txt`, which remains for dev-only `pip install -r requirements.txt`); `python main.py` stays the dev entrypoint and the installed `system-analyzer` console script points at `main:main`. The project is local-only: no PyPI publishing. `maintenance/snapshot.py` is the read-only `system-analyzer-snapshot` CLI that reuses the `algo.Analyzer` facade (never duplicates scanner code). `psutil` is needed for most features, `send2trash` for cleanup, and `nvidia-ml-py` only for NVIDIA GPU details on non-Darwin. `packaging/system-analyzer.desktop` + `install-desktop.sh` add an optional per-user Linux menu entry (uses `XDG_DATA_HOME`/`$HOME`, never a hard-coded path).
- Tests are `unittest` modules under the `tests` package (with `tests/__init__.py`), so `tests.support.*` is importable both via `python -m unittest discover -s tests -v` and via single-module invocation `python -m unittest tests.test_window -v`. Shared test infrastructure lives in `tests/support/` (per-responsibility modules: `models.py` model builders, `scheduling.py` deferred-runner/timer-master fakes, `scanner.py` baseline-psutil/dashboard-environment helpers, `widget_recording.py` recording UI widgets, `process_actions.py` action process fakes, `live_tk.py` display-guarded live-Tk helpers). Support modules never match `test*.py`, so they are not discovered as tests; every factory returns fresh objects so tests stay isolated. They share setup (fake data, patch plumbing, widget factories), never test meaning — edge-case values and assertions stay in each test.
- Run tests with `scripts/run_tests.sh` (forwards any args straight to `python -m unittest`, e.g. `scripts/run_tests.sh tests.test_window -v`; no args runs the full `discover -s tests`) rather than invoking `python -m unittest` directly. On Linux with `xvfb-run` installed it runs the suite inside an isolated virtual display, so `tests/test_live_tk_resize.py` and other real-Tk tests (guarded by `tests/support/live_tk.py`'s `DISPLAY_AVAILABLE`) never open windows on, or contend with, whoever's actually using the machine — real-Tk tests have been observed to hang nondeterministically when run against a live, in-use desktop session (not a code bug; see `docs/AUDIT_FOLLOWUP_2026-09-13.md`). Falls back to the current `$DISPLAY` with a warning when `xvfb-run` isn't available (e.g. non-Linux).
- If Python code changes, run `ruff check .` and `ruff format --check .` before handing off.
- Test hygiene gate: no test — repo tests or validator/opposer counter-tests — counts as validation evidence unless it passes `ruff check` + `ruff format --check` + `pyright` + `mypy --ignore-missing-imports`. Fix or clearly mark any test that is not check-clean before relying on it; never use an unready test as proof.
- Keep `ruff check .`, `ruff format --check .`, `pyright`, and `mypy --ignore-missing-imports` (app + tests) green repo-wide; fix pre-existing static findings you touch, and fix unrelated baseline findings when asked rather than leaving them to grow.
- `docs/bug_hunts/*` are historical evidence trails, not the source of current behavior.
- OpenCode-specific config lives in `opencode.json`; agent definitions are under `.opencode/agents/`.
- BugGuard reviewer routing: all required opposition roles, including Agent 5, must use separate independent BugGuard reviewer/fallback sessions rather than the main OpenCode agent; never simulate or backfill reviewer evidence.
- Current thermal UI boundary: `TemperatureTelemetry` exposes immutable `TemperatureTelemetryUpdate`/`TemperatureRenderState`; `AppWindow` prepares render intents; `UICoordinator` only coalesces, visibility-gates, and rejects stale-node deliveries; `ThermalsPage` owns graph widgets; `maintenance/ui/thermal_graph.py` owns graph geometry and Canvas drawing. Telemetry must not import Tk/UI code, and the coordinator must not draw widgets.
- Thermal capability signals are separate: a resource card's `CapabilityState` is not the thermal series state. `TemperatureTelemetry` bounds repeated empty reads with `TemperaturePolicy.unsupported_confirm_samples` and resolves the thermal series to `UNSUPPORTED` without fabricating samples; preserve this distinction for local and remote nodes.
- Search before create: before adding a reusable helper, search the repository for an existing implementation of the same responsibility. Prefer one canonical implementation and share mechanisms, not specialized meanings; do not duplicate a common operation under a new name.

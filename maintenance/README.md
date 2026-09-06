# maintenance — System Analyzer maintenance subsystem

Internal package owning system scans, cleanup actions, dialogs, shared
component helpers, and generic external-command execution. The app entrypoint
(`main.py`) and facade (`algo.py`) import from this package; the component
subsystem is documented in `components/README.md`.

## Module index

### `__init__.py` — top-level public API
Re-exports: `DashboardSnapshot`, `FileActionResult`, `FileCandidate`,
`FileManager`, `ProcessActionResult`, `ProcessCandidate`, `ProcessManager`,
`ResourceSummary`, `SystemScanner`.

### `scanner.py` — system scan orchestration
- `class SystemScanner` — reads system state and discovers reviewable cleanup
  candidates:
  - `scan_dashboard(cancel_event=None)` — one snapshot of CPU, memory, storage,
    GPU, network, and battery/sensor cards (per-card fallback to "Unavailable"
    on partial failure; cancellation-aware; degrades gracefully when psutil is
    missing). The CPU card takes one short blocking baseline sample
    (`CPU_PERCENT_SAMPLE_SECONDS`), then every later reading is a non-blocking
    delta served by a persistent per-scanner worker thread (window = request
    spacing, ~1 second), so no refresh blocks the worker; current/max
    frequency is shown when reported;
    the memory card keeps physical RAM, available RAM, zram, and disk-backed
    swap distinct (Linux swap devices come from `/proc/swaps`, with a psutil
    aggregate fallback elsewhere).
    The network card computes current download/upload rates from counter
    deltas between scans (first scan shows "—"), keeps sent/received totals,
    and reports the busiest up non-loopback interface plus a generic VPN/tunnel
    presence hint (tun/tap/utun/ppp/ipsec/wg).
    The battery card is preserved for laptops (percent + charging state); on
    machines with no battery it shows "No battery" and points to the CPU, GPU
    and Storage sections, which are each the home for their own attributed
    temperature (CPU / GPU / NVMe drive). Sensors that are absent or
    nonsensical are omitted, never fabricated.
  - `reset_static_cache()` — drop cached static hardware (system label, CPU
    core counts, GPU model) so the next scan re-reads it.
  - `scan_processes(cancel_event=None)` — reviewable process candidates with
    protection decisions.
  - `scan_downloads(progress_callback, cancel_event)` — large/duplicate file
    candidates in Downloads (delegates to `components.downloads`).
  - `gpu_details()` — bounded GPU query via a watchdog worker thread
    (`GPU_QUERY_TIMEOUT_SECONDS`); the query lifecycle is guarded by one
    lock and a generation counter, so concurrent full-scan and
    component-refresh calls can never start duplicate probes and a late
    worker can never clear a newer query's state. While a query is in
    flight, later calls return the timeout message immediately; a query
    still hung after `GPU_QUERY_ABANDON_SECONDS` is abandoned on the next
    call so GPU reporting always recovers; `_stop_gpu_query()` abandons
    any in-flight worker at shutdown. Falls back to
    `gpu_unavailable_message(...)`.
  - `trash_size()` — platform trash size (Windows recycle bin via
    `windows_windll()`).
  - `format_bytes(number_of_bytes)` — human-readable byte formatter.
  - `_default_downloads_path()` — platform Downloads root (delegates to
    `DownloadsPathResolver`).
  - `_same_user(...)` / `_protected_pids()` / `_require_psutil()` /
    `_check_cancelled(...)` — delegates to the shared helpers in
    `components.process_safety` / `components.scan_support`.

### `external_commands.py` — generic external-command execution (shared, single module)
- `CommandRunner` — `Callable[..., subprocess.CompletedProcess[str]]` alias for
  the runner hook.
- `COMMAND_TIMEOUT_SECONDS` — default timeout (int, so timeout messages render
  "10 seconds").
- `run_text_command(command, *, timeout_seconds, runner=None)` — executes one
  command with `check=True, capture_output=True, text=True`; returns
  `(stdout, None)` or `("", error)` for missing commands, permission errors,
  timeouts, and non-zero exits. Never parses output; no hardware knowledge.
- `run_json_command(command, *, timeout_seconds, runner=None,
  empty_stdout_fallback=None)` — layered on `run_text_command`; returns
  `(payload, None)` or `(None, error)` for command failure or malformed JSON;
  `empty_stdout_fallback` is parsed when stdout is empty (Windows GPU probe
  semantics).

### `actions.py` — cleanup actions (the only place that quits processes or moves files to Trash)
- `class ProcessManager` — `request_quit(pids, expected_create_times=None)` /
  `force_quit(pids, expected_create_times=None)`; rejects protected or
  foreign-user PIDs (by PID, name, and executable path) and refuses to act on
  a PID whose `create_time` no longer matches the scanned process (PID reuse).
  `request_quit` sends a graceful terminate first; `force_quit` kills the
  process and its child tree as a separate, explicitly-warned escalation step.
- `class FileManager` — `move_to_trash(paths)`; rejects symlinks, non-Downloads
  paths, and non-files.

### `dialogs.py` — Tk dialogs
- `run_in_thread(...)` — convenience wrapper over `BackgroundTaskRunner.run`.
- `class ResourceCard` — clickable dashboard summary card; action label and
  metric rows are derived by `action_label_text(...)` / `metric_label_pairs(...)`.
- `class InfoDialog`, `class ProcessDialog`, `class StorageDialog` — resource
  detail dialogs; process/storage scans run in background threads with
  generation guards, cancellation, and button disabling. InfoDialog groups
  detail lines into sections (`detail_sections(...)`), shows the headline
  value, and scrolls with the Close button always visible.

### `models.py` — data models
`ResourceSummary`, `DashboardSnapshot`, `ProcessCandidate`, `FileCandidate`,
`ProcessActionResult`, `FileActionResult` (frozen dataclasses).

### Legacy/compatibility surfaces (`algo.Analyzer`)
`cpu_info`, `memory_info`, `storage_info`, `gpu_info`, `network_info` and
`battery_info` are retained as compatibility surfaces: the
`ResourceFeatureCatalog` `loader_name` metadata anchors them for future
wiring, and the interactive dashboard does not call them. The retired
text-report and RAM-test methods (`full_report`, `analyze_all`,
`test_memory`, `system_info`) have been removed. The NVIDIA detail path
shares its per-device enumeration with the dashboard scanner via
`components.gpu.nvidia_device_readings` (`include_temperature=True` here,
`False` on the active dashboard path).

### Static hardware caching (scanner.py)
`scan_dashboard` separates mostly-static identity from live metrics. Cached
(per scanner instance): the system/OS label, CPU physical/logical core counts,
and the platform GPU model (via `components.gpu` loaders). Always re-read: CPU
usage/frequency, RAM/swap, disk usage, network counters, battery, and NVIDIA
GPU usage/memory. Invalidation is safe on three axes — a new scanner instance
(re-start), a fingerprint of `(platform.node(), boot_time)` that changes when
the host or boot session changes, and `reset_static_cache()`. Failed static
reads are never cached, so they retry on the next scan instead of going stale.
One deliberate exception: a failed NVIDIA `nvmlInit` probe is remembered per
scanner (and re-enabled by `reset_static_cache()`), so hosts without the NVML
shared library do not repeat the failed probe and WARNING on every scan.

### `components/` — component subsystem package
See `components/README.md`.

### `preferences.py` — central user preferences
- `class AppPreferences` — deeply immutable preferences (`refresh_intervals`,
  `visible_cards`, `hide_unavailable_cards`) whose defaults derive from
  `RefreshIntervals` and the feature catalog. Immutable `with_*` update methods
  return validated replacements; invalid values raise.
- `class IntervalPolicy` / `INTERVAL_POLICIES` — per-component safe interval
  bounds (ms): CPU/Network 1-60 s step 1, Memory 2-300 s step 1, GPU 3-300 s
  step 1, Storage 15-600 s step 5, Battery 10-600 s step 5.
- `class PreferencesStore` — safe atomic JSON persistence. `load()` always
  returns valid preferences (malformed files fall back to defaults with a log);
  `save()` writes a temp file, fsyncs, and commits with `os.replace`.
- `default_preferences_path(...)` — per-user config path per platform
  (`XDG_CONFIG_HOME` / `~/.config`, `~/Library/Application Support`,
  `%APPDATA%`), all injectable for tests. No `platformdirs` dependency.

### Settings page and page routing (presentation layer)
- `maintenance/ui/navigation.py` — `PageRouter`/`PageSpec`: register named
  persistent pages once and switch them with `pack_forget`/`pack` (eager
  frames, identity preserved, unknown pages raise without hiding the active).
- `maintenance/ui/settings_home.py` — the Settings category hub: a lightweight
  landing page listing one navigation card per settings category
  (`SettingsCategorySpec`); adding a future category is one spec plus its page
  and navigation hook. It renders no preference controls.
- `maintenance/ui/preferences_page.py` — reusable Preferences page adapter with
  injected widget factories, dependency-style typed callbacks/values, interval
  Spinboxes, card Checkbuttons, Manual Scan controls, and the reset control.
  `refresh_from` accepts any preferences-like object. The page is a real
  sub-page reached from the Settings hub (`Preferences` → `Back to Settings`).
- `AppCoordinator` (in `components/coordinator.py`) is the shared
  background-operation shock absorber used by the dashboard, component scans,
  the pages (via `PageRouter` loaders), and the Storage/Process dialogs:
  duplicate triggers coalesce, results are cached for instant re-open
  retrieval, cancellation is cooperative with safe retry, and every result
  crosses one injected delivery path onto the Tkinter thread.

## Dependencies and seams
- `psutil` (required for most scans), `send2trash` (file cleanup),
  `nvidia-ml-py` (optional NVIDIA details on non-Darwin). Each module keeps its
  own optional-import fallback so tests can patch per-module globals.
- Test monkeypatch seams: `patch("maintenance.scanner.subprocess.run")`,
  `patch("maintenance.scanner.platform.system")` (shared platform module also
  reaches `components.downloads` lambdas), and the `_check_cancelled`
  instance-injection in `SystemScanner._sync_download_scanner`.

## Tests
`tests/test_maintenance.py`, `tests/test_components.py`,
`tests/test_storage_dialog.py`, `tests/test_window.py`,
`tests/test_external_commands.py`, `tests/test_package_structure.py`,
`tests/test_scanner_static_cache.py`, `tests/test_preferences.py`,
`tests/test_navigation.py`, `tests/test_settings_home.py`,
`tests/test_preferences_page.py`.
Run everything with `python -m unittest discover -s tests`.

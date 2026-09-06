# maintenance/components — Component subsystem

The component subsystem is the internal package the System Analyzer app imports
for shared scan helpers, process safety, downloads discovery, GPU platform
selection, background Tk delivery, the resource feature catalog, and dashboard
scan coordination.

Import everything through the package interface; internal file layout is not
part of the public surface:

```python
from maintenance.components import (
    check_cancelled,
    DownloadsPathResolver,
    GpuDetector,
    ScanCoordinator,
)
```

Generic external-command execution deliberately lives outside this package in
`maintenance.external_commands`.

## Module index

### `__init__.py` — stable public interface
Re-exports every public name below and declares `__all__`. Adding a new public
name requires updating `__all__` (enforced by `tests/test_package_structure.py`).

### `scan_support.py` — shared scan primitives (leaf, no package imports)
- `ProgressCallback` — `Callable[[str], None]` alias for progress reporting.
- `ProgressTask` — `Callable[[ProgressCallback, threading.Event], Any]` alias
  for cancellable background tasks.
- `DOWNLOADS_SCAN_CANCELLED` — default cancellation message.
- `class ScanCancelled` — exception raised when a cancellable scan is stopped.
- `check_cancelled(cancel_event, message=DOWNLOADS_SCAN_CANCELLED)` — raises
  `ScanCancelled` when the event is set.
- `require_psutil(psutil_module)` — returns the psutil module or raises a
  consistent installation hint.
- `windows_windll()` — returns `ctypes.windll` on Windows and `None` elsewhere,
  never raising.
- `call_legacy_compatible(primary, fallback, *, error_substring=…,
  before_fallback=None, after_fallback=None)` — runs `primary` and, when it
  raises a TypeError for an unknown keyword (an older one-argument hook),
  runs `fallback` with optional cancellation checks; shared by the scanner,
  downloads scanner, dialogs, and window.
- `file_sha256(path, *, chunk_bytes, cancel_event=None)` — cancellation-aware
  chunked SHA-256 of one file; shared by `SystemScanner._file_hash` and
  `DownloadScanner._file_hash`.
- `file_content_marker(path, *, chunk_bytes, cancel_event=None)` —
  cancellation-aware BLAKE2b(digest_size=16) marker for hash-cache validation;
  shared by `SystemScanner._file_content_marker` and
  `DownloadScanner._file_content_marker`.
- `stat_fingerprint(stat)` — identity tuple `(st_size, st_mtime_ns,
  st_ctime_ns, st_dev, st_ino)` for change detection; shared by
  `SystemScanner._hash_fingerprint` and `DownloadScanner._hash_fingerprint`.

### `process_safety.py` — process safety decisions
- `PROTECTED_PROCESS_NAMES` — the single protected-name frozenset shared by the
  scanner, action managers, and the policy.
- `normalize_username(value)` — local-username normalisation (drops Windows
  domain prefixes, casefolds; non-strings become `""`).
- `usernames_match(username, current_user)` — deny-safe same-user comparison
  (empty/non-string inputs never match).
- `protected_process_pids(psutil_module)` — lenient scan-time PID snapshot
  (`{0, 1, os.getpid()}` + parent chain, tolerating lookup errors).
- `class ProcessSafetyPolicy` — answers whether a process may be managed
  without performing the action; fails closed (see its own module docstring).

### `downloads.py` — Downloads discovery
- `HashFingerprint` — stat fingerprint tuple for the hash cache.
- `class DownloadsPathResolver` — resolves the Downloads root, including
  Windows known-folder interop (`_windows_downloads_path`), OneDrive fallback,
  and the `Downloads.__unavailable__` sentinel.
- `class DownloadScanner` — scans Downloads for large files and verified
  duplicates with a bounded, content-validated hash cache; cancellation-aware
  (`check_cancelled` / `ScanCancelled`).

### `gpu.py` — GPU platform selection
- `GPU_INFORMATION_UNAVAILABLE` — canonical "GPU information unavailable"
  prefix used for every GPU failure/fallback message.
- `gpu_unavailable_message(error)` — returns the concise
  `GPU_INFORMATION_UNAVAILABLE` message and logs the probe failure detail (raw
  exceptions/subprocess output never reach the UI).
- `class GpuDetector` — dispatches to the platform-appropriate GPU detail
  loader (macOS / NVIDIA / Windows / Linux).

### `background.py` — background Tk task delivery
- `class BackgroundTaskRunner` — runs work off the Tk thread and delivers
  success/error/progress callbacks via `widget.after`, tolerating widget
  teardown.

### `catalog.py` — resource feature metadata
- `class ResourceFeature` — immutable metadata for one dashboard resource
  category (key, title, order, action kind, loader name, platforms).
- `class ResourceFeatureCatalog` — isolated, deterministic registry of
  `ResourceFeature` entries with duplicate-key rejection.

### `network_discovery.py` — local-network presence discovery
- `SERVICE_TYPE` — the mDNS service type (`_system-analyzer._tcp.local.`).
- `DiscoveryEndpoint` — the (possibly absent) remote endpoint this instance may
  advertise; `port=None`/`connectable=False` means no transport is listening.
- `DiscoveryAdvertisement` — the minimal, non-sensitive presence metadata this
  instance advertises (stable id, name, versions, platform; never processes,
  usernames, paths, health, or credentials).
- `class NetworkDiscovery` — advertises and browses for System Analyzer peers,
  normalizes records, deduplicates by stable id, ignores the local instance,
  tracks TTL/expiry, and emits `candidate`/`lost` events. It never trusts,
  authorises, or manages peers and never owns the registry or UI. The
  `zeroconf` is installed with the application. Its missing-module fallback
  keeps incomplete source environments running as a single-node application.

### `coordinator.py` — dashboard scan coordination
- `class ScanCoordinator` — tracks the live dashboard scan: `begin()` returns
  `(generation, started)` and queues a single rerun while active; `finish()`
  resolves the active generation; `cancel()` invalidates the active generation
  and clears state without rerunning, so a queued old-node completion cannot
  satisfy a later selected target.
- `class RefreshIntervals` — shared per-component refresh intervals
  (milliseconds): CPU/Network 1000, Memory 5000, GPU 3000, Storage/Battery
  30000 (chosen from measured scan cost and how quickly each metric changes).
- `class ComponentRefreshScheduler` — per-component due-time tracking with an
  in-flight flag per component so the same scanner never overlaps and a slow
  or failing component never delays the others; `mark_all_refreshed(now)`
  pushes every component past its interval after a full snapshot. Preferences
  drive live reconfiguration through `set_interval(key, ms, now)`,
  `pause(key)`, `resume(key)` and `request_refresh(key)`: interval edits touch
  only the named component, pausing never cancels an in-flight worker, and
  coalesced refresh requests become due once the component is free/resumed.
- `class AppCoordinator` — the universal per-key "shock absorber" between
  slow background work and the Tkinter UI thread (dependency-composed: the
  caller injects its own worker runner and UI delivery). `run(key,
  task_factory, on_result=..., on_error=..., on_progress=...)` coalesces
  duplicate triggers into one in-flight run plus one pending rerun, caches the
  last good result for instant `last_result` retrieval, cancels cooperatively
  with generation-based late-result dropping and wafer wakeups, and delivers
  every completion/error/progress onto the UI thread through the injected
  `deliver` — worker threads never touch widgets. `begin/finish/subscribe/
  unsubscribe/store/clear/in_flight/generation` expose the pure per-key state
  for non-run consumers. `start_discovery/stop_discovery/discovery_tick/post`
  additionally own the network-discovery lifecycle: they start/stop a
   `NetworkDiscovery` component exactly once and bridge every candidate/lost
   event through the same `deliver` path, so registry updates always happen on
   the UI thread and late transport events after `stop_discovery` are dropped.
   A failed discovery start releases that lifecycle ownership so a later retry
   is possible.
  The single app instance lives on `window.AppWindow` and is shared by the
  pages (via `PageRouter` loaders), the Storage/Process dialogs, and the
  component scans, while the window's `_background_queue` drain is the one
  Tkinter-thread delivery path they all cross.

## Node/target model (`maintenance/nodes.py`)
The cluster boundary lives in `maintenance/nodes.py` (not inside the component
package): `NodeId`, `NodeDescriptor`, `NodeCapability`, trust/status state,
`DiscoveredNodeCandidate`, `NodeContext` (per-node provider, managers,
snapshot, capabilities, scheduler), `NodeRegistry`, and the node-qualified
coordinator-key helper `node_operation_key`. Invariants: `DISCOVERED !=
TRUSTED != AUTHORISED`; the local node is always registered and selectable;
discovered candidates are never selectable; a capability is never inferred
from a hostname or from `is_local`.

## Tests
`tests/test_components.py`, `tests/test_maintenance.py`,
`tests/test_storage_dialog.py`, and `tests/test_package_structure.py` (which
pins the module inventory, re-export identity, and `__all__` completeness).

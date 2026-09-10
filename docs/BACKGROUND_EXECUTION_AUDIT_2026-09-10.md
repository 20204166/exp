# Background Execution Audit

**Scope:** Final report for the bounded background-execution consolidation in the
current repository. The current source at `d5e21d6` is authoritative; this report
is the only file changed by Task 7.

## 1. Execution Paths Found

| Path | Source paths | Owner | Decision |
|---|---|---|---|
| Per-key application work | `maintenance/components/coordinator.py` | `AppCoordinator` | Canonical general mechanism; reuse. |
| Dashboard full scan | `maintenance/components/dashboard_scan.py`, `maintenance/components/background_orchestration.py`, `maintenance/ui/window_scan.py` | `DashboardScanLifecycle` plus `BackgroundOrchestrator` | Keep separate for progress, timeout/grace lease, rerun, busy state, and queue protocol. |
| Process/storage dialog scans and process actions | `maintenance/dialogs.py`, `maintenance/ui/window_node_actions.py` | Existing `AppCoordinator` instances | Reuse the coordinator while retaining dialog/node semantics. |
| Storage Move to Trash | `maintenance/dialogs.py:1337`, `:1674-1677` | `StorageDialog` plus its `AppCoordinator` | Migrated to node-qualified `storage_trash`. |
| Manual authenticated Test Connection | `maintenance/ui/window_node_actions.py:527-540` | Window `AppCoordinator` | Migrated to node-qualified `test_connection`. |
| CPU sampler | `maintenance/scanner_support/dashboard.py` | `SystemScanner` persistent request worker | Keep separate sensor protocol. |
| GPU probe | `maintenance/scanner_support/gpu.py` | GPU scanner probe worker | Keep separate bounded/abandonable probe protocol. |
| Remote socket service | `maintenance/remote.py:913-1020` | `RemoteSocketServer` | Keep separate bounded request lifecycle. |
| Discovery and peer transport | `maintenance/network_discovery.py`, `maintenance/discovery_session.py`, transport modules | Discovery/session owners; peer operations use node-qualified `AppCoordinator` keys | Keep discovery and transport lifetimes separate. |
| Tk delivery and rendering | `maintenance/components/coordinator.py`, `maintenance/components/background_orchestration.py`, `maintenance/ui/*delivery*`, render-coordinator modules | Injected delivery, dashboard queue, `TkDeliveryQueue`, and `TimerDelivery` | Keep specialized delivery seams; workers do not call Tk directly. |

## 2. Ownership And Semantics Matrix

| Owner/path | Thread and queue model | Concurrency, cancellation, and timeout | Delivery, shutdown, stale result, and binding | Evidence |
|---|---|---|---|---|
| `AppCoordinator` | Default `ThreadPoolExecutor(max_workers=4)`; runner and delivery are injected. One state per key. | One in-flight run plus one coalesced rerun per key. Cooperative `threading.Event`; no generic timeout. | Generation checks drop late results; `cancel_all` and `shutdown(wait=False, cancel_futures=True)` are available. Node binding is caller-owned. | `tests.test_components.AppCoordinatorRunTests`; `tests.test_lifecycle_stress.AppCoordinatorStressTests`. |
| Dashboard lifecycle/orchestrator | Daemon scan workers publish to a callback queue; Tk thread polls and batches rendering. | Lifecycle owns generation, cancellation, timeout, grace lease, rerun, task count, and busy state. | Queue delivery and closing/generation guards prevent stale render; shutdown is wired by `maintenance/ui/window_lifecycle.py`. | `tests.test_dashboard_scan`, `tests.test_background_orchestration`, `tests.test_window`. |
| Dialog scans/actions | Coordinator runner executes cancellable task factories; dialog callbacks are delivered through the coordinator. Standalone fallback uses `TkDeliveryQueue`. | Operation keys isolate scans/actions; close unsubscribes/cancels. Cleanup has independent `storage_trash` state and close guard. | Dialogs own confirmation, result rendering, refresh, and widget lifetime. | `tests.test_storage_dialog`, `tests.test_components`. |
| Legacy `BackgroundTaskRunner` | One daemon `threading.Thread` per task; internal queue drains through Tk `after`. | No shared limit, coalescing, timeout, or shutdown owner; optional cooperative event. | Suppresses delivery after widget teardown, but has no generation or node binding. It remains only as compatibility/fallback surface. | `BackgroundTaskRunnerTests` and Storage teardown tests. |
| CPU sampler | One persistent daemon worker per scanner waits for requests and publishes a sample. | Requests serialize; second live worker is refused; cancellation interrupts polling and stop joins for up to one second. | Scanner/provider owns result handoff and node context; stop is idempotent. | `tests.test_cpu_sampling.CpuSamplingTests`. |
| GPU probe | One daemon thread per probe, with a lock-protected in-flight flag. | Stacked probes are refused; caller joins for `GPU_QUERY_TIMEOUT_SECONDS`; stop abandons and invalidates generation without joining a wedged call. | Result returns to the enclosing scan; generation protects newer state. | `tests.test_gpu_concurrency.GpuConcurrencyTests`. |
| `RemoteSocketServer` | One daemon listener and daemon handler threads. | `BoundedSemaphore`, request queue size 16, frame limit, and socket timeout bound admission/I/O. | Socket response never uses Tk; `stop` shuts down/closes the server, with `block_on_close=False`. | `tests.test_remote_contract`. |
| Discovery/session/peer transport | Transport/listener threads are owned by discovery/session layers; peer operations use the window coordinator. | Discovery/session rules and provider timeouts remain specialized; coordinator cancellation is separate. | Late events and node identity are checked before presentation; shutdown stops discovery and peer manager first. | `tests.test_network_discovery`, `tests.test_discovery_session`, `tests.test_window_nodes`. |
| `TimerDelivery`/render delivery | Tk `after` executes on the Tk thread; render delivery batches/gates presentation. | Timer IDs and pending render state are tracked; exact global queue bound is **NOT VERIFIED**. | Timers and rendering are cancelled/shut down during close; stale node generations are caller/render-intent responsibilities. | Window and node lifecycle tests. |

## 3. Duplicate Mechanisms Proven

`BackgroundTaskRunner` was a second general-purpose submission and Tk-delivery
mechanism alongside `AppCoordinator`. The two remaining internal general-work
callers were `StorageDialog.move_selected` and manual authenticated
`test_connection`; both now use existing coordinator instances. The legacy runner
remains exported through `maintenance.components` and is covered by tests, so it
was not removed.

## 4. Mechanisms Intentionally Kept Separate

Dashboard scan lifecycle/queue polling, CPU sampling, GPU probing, remote socket
handling, discovery/session transport, and Tk timer/render adapters remain
separate. Their specialized semantics are timeout/grace leases and reruns,
persistent request workers, explicit GPU abandonment, bounded admission/framing,
transport identity/session lifetime, and Tk scheduling/presentation ownership.
Routing them through a generic executor would erase those ownership boundaries.

## 5. Common Mechanisms Reused Or Extracted

No new executor, coordinator, runner, or delivery abstraction was added. Existing
`AppCoordinator` supplies per-key submission, coalescing, cancellation events,
generation checks, exception/error delivery, injected UI delivery, result state,
and executor shutdown. Existing `node_operation_key`, `TkDeliveryQueue`,
`BackgroundOrchestrator`, and `TimerDelivery` seams were reused. Failed
submission and repeated-failure state behavior was covered without changing the
canonical coordinator implementation.

## 6. Callers Migrated

- `maintenance/dialogs.py`: Storage cleanup now submits through the dialog
  coordinator using `operation_key(node_id, "storage_trash")`; confirmation,
  `FileActionResult` rendering, refresh, close cancellation, and closed-result
  suppression remain dialog-owned.
- `maintenance/ui/window_node_actions.py`: manual Test Connection now submits
  through the window coordinator using `node_operation_key(node, "test_connection")`.
  Authenticated hello, identity validation, error wording, and message-box
  behavior remain unchanged.
- `window.py`: the obsolete `run_in_thread_fn` injection for Test Connection was
  removed.

## 7. Thread And Executor Implications

The migration removes two production uses of one-thread-per-action
`BackgroundTaskRunner` submission. It does **not** remove that compatibility
class, dashboard daemon workers, CPU/GPU scanner workers, the remote listener or
handler threads, discovery/transport threads, or the default bounded
`AppCoordinator` executor (`max_workers=4`). No global thread-count reduction is
claimed: exact live process thread counts are **NOT VERIFIED**.

## 8. Cancellation And Shutdown

Coordinator operations use cooperative events, generation checks, coalesced
reruns, `cancel_all`, and `shutdown(wait=False, cancel_futures=True)`. Storage
dialog close sets `_closed`, cancels `storage_trash`, and ignores late results.
Node operations are cancelled on node changes/close and are node-qualified.

`maintenance/ui/window_lifecycle.py:283-310` shuts down the peer server and
discovery, peer connections, dashboard lifecycle, coordinator work, node
operations, Tk timers, and render delivery in that order; `:329-336` stops
scanner workers before destroying the root. CPU stop has a one-second join bound.
GPU and provider calls may be abandoned rather than joined. Whether every
third-party provider interrupts promptly after cancellation is **NOT VERIFIED**.

## 9. Tk-Delivery Verification

Workers deliver through an injected callback or a specialized queue; they do not
touch Tk directly. The Storage boundary test records the delivery thread and
proves close/cancel suppresses result UI callbacks. Coordinator progress/result,
dashboard queue polling, standalone Tk teardown, remote socket, and stale node
tests cover the other seams.

| Path | Delivery seam | Guard | Tests |
|---|---|---|---|
| Coordinator operation | Injected `deliver` | Key generation and cancellation | `test_run_delivers_progress_and_result_through_delivery`; `test_failed_submission_delivers_error_and_settles_run` |
| Dashboard scan | `BackgroundOrchestrator` queue + `TimerDelivery` | Scan generation, node id, closing | `test_timeout_reports_immediately_and_worker_completion_releases_lease`; `test_late_scan_completion_after_timeout_is_dropped` |
| Standalone dialog fallback | `TkDeliveryQueue` | Widget destruction/closed state | `test_real_tk_delivery_queue_never_calls_after_from_worker`; `test_run_ignores_runtime_error_during_widget_teardown` |
| Storage cleanup | Coordinator `deliver` | Cancelled/closed dialog | `test_trash_delivery_stays_on_injected_ui_boundary`; `test_close_cancels_trash_and_late_result_is_ignored` |
| Remote handler | Socket, never Tk | Request auth and service bounds | `test_cancelled_request_raises_before_send`; `test_socket_server_shutdown_releases_handler_permits` |

## 10. Exact Tests And Results

Focused and specialized commands recorded during Tasks 1, 5, and 6:

- `python -m unittest tests.test_components tests.test_background_orchestration tests.test_dashboard_scan tests.test_storage_dialog tests.test_lifecycle_stress -v` -> `Ran 142 tests in 0.051s`, `OK`, exit 0.
- `python -m unittest tests.test_dashboard_scan tests.test_gpu_concurrency tests.test_cpu_sampling tests.test_remote_contract tests.test_network_discovery tests.test_discovery_session tests.test_window tests.test_window_nodes -v` -> `Ran 252 tests in 12.615s`, `OK`, exit 0.
- `python -m unittest tests.test_components tests.test_background_orchestration tests.test_render_coordinator tests.test_window_nodes tests.test_storage_dialog -v` -> `Ran 197 tests in 9.065s`, `OK`, exit 0.

Final required validation gate, run against the current source before this report
was edited:

- `python -m unittest discover -s tests -v` -> `Ran 1144 tests in 38.029s`, `OK`, exit 0.
- `ruff check .` -> exit 1, two unrelated baseline errors in `.opencode/skills/applying-themes/scripts/check_contrast.py`: `EXE001` at line 1 and `C419` at line 123.
- `ruff format --check .` -> exit 1, five files would be reformatted: `.opencode/skills/applying-themes/SKILL.md`, `.opencode/skills/applying-themes/scripts/check_contrast.py`, `.opencode/skills/reviewing-interface-quality/SKILL.md`, `docs/plans/2026-09-10-background-execution-consolidation.md`, and `docs/plans/2026-09-10-window-controller-extraction.md`.
- `pyright` -> exit 1, three errors in generated `build/lib`: two type errors in `build/lib/maintenance/components/temperature.py:200:45` and `:202:33`, and one stale `run_in_thread_fn` argument at `build/lib/window.py:454:13`.
- `mypy --ignore-missing-imports` -> exit 2 with `mypy: error: Missing target module, package, files, or command.` The repository has no configured default target for this exact invocation.

These failures are pre-existing/unrelated to the two migrations and their tests.
No unready test is used as validation evidence; the full unittest suite is green,
but the repository-wide hygiene gate is not green because of the failures above.

## 11. Unresolved Risks

- Exact runtime thread counts and any global thread-count reduction are not measured.
- Provider interruption after cancellation is not proven for uninterruptible calls.
- The legacy compatibility runner has no shared concurrency limit or shutdown method.
- Exact global render/timer queue bounds are not verified.
- Some compatibility/fallback paths have source coverage but no dedicated focused characterization.
- Ruff, Ruff format, Pyright, and Mypy remain failing for the exact unrelated baseline reasons listed in Section 10.

## 12. Working-Tree Status

The six implementation/audit commits already present before Task 7 are:

```text
66696be docs: map background execution paths
24d2cd3 test: cover coordinator submission settlement
52cd306 refactor: route storage actions through app coordinator
9e1c042 refactor: coordinate manual connection checks
b831e57 docs: record preserved async lifecycles
d5e21d6 test: verify async Tk delivery boundaries
```

Their current source state contains the two caller migrations, coordinator tests,
Storage/Test Connection lifecycle tests, and the specialized/Tk audit evidence.
Before Task 7 editing, the exact scope checks were:

- `git diff --check` -> exit 0.
- `git status --short` -> `?? docs/SYSTEM_ANALYZER_REVIEW.md` and `?? docs/plans/2026-09-10-background-execution-consolidation.md`; both were pre-existing and left untouched.
- `git diff --stat HEAD` -> empty, because the six prior commits were committed.

Task 7 changes only this report. The final commit is
`docs: report background execution consolidation`; after that commit, the
working tree is expected to retain only the same two unrelated untracked files,
with no tracked diff or staged files. Neither the plan nor the review document is
staged or modified.

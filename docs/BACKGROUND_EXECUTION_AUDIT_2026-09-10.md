# Background Execution Audit

**Scope:** One bounded consolidation pass; current repository is authoritative.
**Baseline:** Task 1 source/test inventory captured before any runtime or test edit.

## Execution Paths

| Path | Owner | Classification | Decision |
|---|---|---|---|
| Per-key application work | `AppCoordinator` (`maintenance/components/coordinator.py`) | Canonical general mechanism | Reuse as-is; its runner, generation, cancellation, delivery, and shutdown are already centralized. |
| Dashboard full scan | `DashboardScanLifecycle` + `BackgroundOrchestrator` (`maintenance/components/dashboard_scan.py`, `background_orchestration.py`, `maintenance/ui/window_scan.py`) | Specialized lifecycle | Keep separate for progress, timeout, grace lease, rerun, busy state, and dashboard queue protocol. |
| Process/storage dialog scans and process actions | Existing `AppCoordinator` calls in `maintenance/dialogs.py` and `maintenance/ui/window_node_actions.py` | Canonical mechanism with specialized dialog/node meaning | Keep dialog callbacks, operation keys, node checks, and result rendering; reuse the coordinator. |
| Storage Move to Trash | `StorageDialog.move_selected` -> `dialogs.run_in_thread` -> `BackgroundTaskRunner` | Duplicated/legacy internal mechanism | Baseline migration target for a later task; not changed here. |
| Test Connection action | `window_node_actions.test_connection` -> injected `run_in_thread_fn` (defaulting to `dialogs.run_in_thread`) | Direct-thread legacy mechanism | Not changed in Task 1. Its presence is an inventory discrepancy against the plan's claim that Storage is the only remaining internal caller. |
| CPU sampler | `SystemScanner` / `maintenance/scanner_support/dashboard.py` | Specialized persistent worker | Keep one request worker per scanner; it is a sensor request protocol, not an application task executor. |
| GPU probe | `maintenance/scanner_support/gpu.py` | Specialized bounded probe worker | Keep timeout, abandon generation, and no-join semantics. |
| Remote socket server | `RemoteSocketServer` (`maintenance/remote.py`) | Specialized bounded request lifecycle | Keep bounded admission, framed I/O, socket timeout, and daemon handlers. |
| Remote discovery and peer connection | `AppCoordinator` for peer connection plus `network_discovery.py`/`discovery_session.py` transport lifecycle | Specialized transport lifecycle using the canonical delivery seam where applicable | Keep discovery ownership, transport cancellation, node identity checks, and late-event guards separate. |
| Tk delivery | `AppCoordinator.deliver`, `BackgroundOrchestrator` queue, `TkDeliveryQueue`, `TimerDelivery` | Multiple specialized delivery seams | Keep each seam; workers must not call Tk directly. |

## Ownership And Semantics Matrix

The fields below are based on source inspection and the named tests in the current
repository. `NOT VERIFIED` means that neither the inspected source nor the focused
baseline tests prove the stated property.

| Path / owner | Work and thread model | Queueing / concurrency | Cancellation / timeout | Result delivery / Tk handoff | Shutdown / stale result / node binding | Tests and verification |
|---|---|---|---|---|---|---|
| `AppCoordinator` | `run` claims one per-key state and invokes the injected runner. Default runner is `ThreadPoolExecutor(max_workers=4)`; tests inject deferred runners. | One in-flight run per key plus one coalesced rerun; state is retained per key. | Cooperative `threading.Event`; cancellation holds in-flight until completion delivery. No generic operation timeout. | Every progress, success, error, and cancellation callback goes through injected `deliver`; default delivery is synchronous for tests. | Generation checks drop late completion; cancellation drops progress/results and wakes subscribers. `cancel_all` and `shutdown(wait=False, cancel_futures=True)` exist. Node binding is caller-owned, not intrinsic. | Focused baseline passed coordinator run/cancel/coalescing and delivery tests; `test_two_hundred_cycles_keep_state_bounded`, `test_two_hundred_open_close_cycles_clear_subscribers`, and `test_cancel_all_wakes_each_tracked_operation_once` passed in the focused command. Failed-submission behavior is source-visible but has no dedicated baseline test. |
| `DashboardScanLifecycle` + `BackgroundOrchestrator` | Dashboard provider work runs in a daemon thread through `run_in_background`; lifecycle owns scan generation and state. | Background queue carries callbacks and finished markers; task count and busy state are maintained by `BackgroundOrchestrator`. Polling is scheduled only from the main thread. | Lifecycle creates a cancellation event, schedules timeout and grace timers, cancels cooperatively, and retains a timed-out lease until worker completion or grace expiry. | Worker callbacks enter the queue; `drain_queue` invokes delivered callbacks and batches render work through the injected render coordinator. | Lifecycle rejects old generations and closing state; reruns are scheduled after resolution. Node generation/id checks occur in `window_scan.py`. Shutdown cancellation is wired from `window_lifecycle.finalize_shutdown`. | `test_start_orders_state_timer_then_worker_and_coalesces_rerun`, `test_timeout_reports_immediately_and_worker_completion_releases_lease`, `test_late_generation_cannot_resolve_current_scan`, and background queue close/poll tests passed. |
| Dialog scans and process actions via `AppCoordinator` | Dialog scan tasks accept cancel event/progress callback; process action and node activation tasks use coordinator keys and callbacks. Work is runner-dependent, defaulting to the shared executor. | Per-operation keys prevent scan/process interference; duplicate dialog scans subscribe or coalesce. | Cooperative cancellation; dialog close unsubscribes/cancels its scan. Action-specific cancellation semantics are specialized to the dialog. | Shared coordinator delivery; dialog callbacks update widgets only after delivery. Standalone dialogs use `TkDeliveryQueue` through `_standalone_coordinator`. | Generation and subscriber removal prevent stale dialog delivery. Node activation additionally checks closing state, generation, identity, and current registry context. | Storage shared-scan tests, `test_process_and_storage_keys_stay_isolated_on_one_coordinator`, coordinator delivery tests, and node tests are present; standalone action lifecycle coverage is NOT VERIFIED by the focused baseline. |
| `BackgroundTaskRunner` / `TkDeliveryQueue` | `BackgroundTaskRunner` starts one daemon `threading.Thread` per submitted task. It supports a plain task or a progress task with an event. | Internal `Queue` buffers worker callbacks for real Tk widgets; non-Tk fakes use `after` directly. No concurrency limit or coalescing. | Optional cooperative event only; no timeout or cancellation owner. Widget destruction closes the delivery queue and cancels its timer where possible. | Queue drain is scheduled with `widget.after`; callback invocation catches Tk teardown errors. | No generation or node binding. Delivery is suppressed after widget destruction/closure. Runner has no shutdown method. | `test_real_tk_delivery_queue_never_calls_after_from_worker`, `test_run_ignores_runtime_error_during_widget_teardown`, and legacy delegation tests passed. `StorageDialog.move_selected` still uses this path at baseline. |
| CPU sampler (`SystemScanner` / dashboard scanner support) | One persistent daemon worker per scanner waits on a request event and publishes one non-blocking `psutil.cpu_percent` sample. | Request/result events serialize requests; `_start_cpu_worker` refuses to create a second live worker. | Request wait honors scan cancellation in polling slices; sampler stop sets stop/request events and joins for up to one second. No per-sample timeout beyond the bounded wait. | The scanner returns the sample to its caller; Tk handoff is owned by the enclosing scan path. | Stop is idempotent. No generation is needed for CPU samples; node binding is owned by the scanner/provider context. | Source proves the worker protocol and bounded stop. Focused baseline did not include CPU-specific tests; dedicated CPU sampling evidence is NOT VERIFIED here. |
| GPU probe (`scanner_support/gpu.py`) | Each probe uses a daemon `threading.Thread`; caller joins only for `GPU_QUERY_TIMEOUT_SECONDS`. | Lock-protected in-flight flag refuses stacked probes; one probe is active per scanner. | Explicit join timeout; a wedged call is abandoned. Stop increments query generation and invalidates late `finally` cleanup without joining. | Probe result returns to the calling scan worker; enclosing application path owns Tk delivery. | Generation protects a newer query from an old completion. Node binding is provided by the scanner instance/caller. | Source proves timeout, abandon, and generation behavior. Focused baseline did not include GPU concurrency tests; dedicated GPU evidence is NOT VERIFIED here. |
| `RemoteSocketServer` | Listener runs on one daemon thread; `ThreadingTCPServer` creates daemon request handlers. | `BoundedSemaphore(max_active_handlers)` rejects over-admission; server `request_queue_size` is 16. | Per-socket timeout bounds idle/malformed clients; service cancellation is cooperative at the request/service layer. | Framed response returns over the socket, never through Tk. | `stop` calls server shutdown and close; `daemon_threads=True` and `block_on_close=False` keep shutdown bounded. Authentication and request identity are service-owned. | Source proves admission, frame-size, timeout, and shutdown settings. `test_cancelled_request_raises_before_send` and `test_socket_server_shutdown_releases_handler_permits` exist but were not part of the focused baseline command. |
| Discovery / peer transport | Discovery/session and network transport own their listener/browser or transport threads; peer connection work is submitted through node-qualified `AppCoordinator` keys. | Discovery admission/session rules and transport lifecycle are separate; coordinator coalesces peer connection operations by node key. Exact worker count is NOT VERIFIED from this baseline. | Discovery stop/cancel and peer coordinator cancellation are separate; socket/transport timeouts are provider-owned. | Discovery events are bridged through `AppCoordinator.post`/delivery; peer results use coordinator delivery. Tk is not touched by transport workers. | Discovery generation and identity checks reject late events; peer connection callbacks check node identity and current context. Final shutdown stops discovery and peer manager before coordinator shutdown. | Source and existing window/node tests cover the seams, but discovery-specific tests were not in the focused baseline command. |
| `TimerDelivery` and render delivery | Tk timers execute callbacks on the Tk thread; render coordinator is a presentation-side batching/gating seam, not a worker executor. | Pending timer IDs and render pending state are tracked; exact global queue bound is NOT VERIFIED. | Timers can be cancelled; render delivery rejects stale generations/hidden or closing surfaces. | `after` is the Tk handoff; render callbacks are invoked through the window's UI boundary. | Final shutdown cancels timers and shuts down render delivery. Node generation binding is applied by render intents/callers. | Background/dashboard tests cover queue polling; render and window-node tests provide additional stale-delivery evidence but were not in the focused baseline command. |

## Duplicate Mechanisms Proven

At this baseline, `BackgroundTaskRunner` is a second general-purpose submission
and Tk-delivery mechanism alongside `AppCoordinator`. The proven internal callers
are `StorageDialog.move_selected` and the default-injected path of
`window_node_actions.test_connection`. The plan explicitly targets Storage cleanup
for later migration; the test-connection caller remains an unresolved scope
question rather than being omitted from this audit.

The legacy runner itself is also an exported compatibility surface through
`maintenance.components` and is covered by tests. No compatibility surface is
removed in this baseline task.

## Mechanisms Kept Separate

Dashboard scan lifecycle, dashboard queue polling, CPU sampling, GPU probing,
remote socket request handling, discovery/session transport, and Tk timer/render
adapters remain separate. They encode distinct product or protocol semantics:
dashboard timeout/grace leases and reruns, persistent sensor request workers,
uninterruptible GPU abandonment, bounded remote admission/framing, transport
identity/session lifetimes, and Tk scheduling/presentation ownership.

## Consolidation Performed

None. Task 1 is documentation-only. No runtime code or tests were modified, and
the Storage action remains on `BackgroundTaskRunner` in this baseline.

## Boundedness And Shutdown

The default `AppCoordinator` executor is bounded at four workers and shuts down
without waiting for uninterruptible work. `BackgroundTaskRunner` creates daemon
threads without a shared limit or shutdown owner. Dashboard workers are daemon
threads tracked by task count and queue completion markers. CPU stop joins for a
one-second bound; GPU stop deliberately does not join a wedged probe. Remote
handlers are bounded by semaphore, frame size, socket timeout, and non-blocking
server close. Repeated coordinator state/subscriber tests passed in the focused
baseline; CPU, GPU, remote, and full application shutdown tests were not run by
the required focused command.

## Tk Delivery Verification

The focused baseline passed the coordinator delivery test and the
`BackgroundTaskRunner` real-Tk delivery/teardown tests. Source shows that
`AppCoordinator`, `BackgroundOrchestrator`, and `TkDeliveryQueue` route worker
callbacks through injected delivery, a queue, or `after`; no inspected worker
path intentionally calls Tk directly. Main-thread delivery across every path,
stale node delivery, and shutdown ordering are NOT VERIFIED by the focused
command.

## Tests And Results

Command run before editing, exactly as specified by the plan:

```text
python -m unittest tests.test_components tests.test_background_orchestration tests.test_dashboard_scan tests.test_storage_dialog tests.test_lifecycle_stress -v
```

Exact result: `Ran 142 tests in 0.051s` followed by `OK` (process exit 0).
All 142 tests passed. The output included one expected warning log from
`test_uncaught_ui_callback_never_breaks_delivery`: `Operation 'storage' callback failed: widget gone`.

The plan's inventory command was also attempted:

```text
rg -n "ThreadPoolExecutor|threading\.Thread|Thread\(|Queue\[|\.after\(|socketserver|BoundedSemaphore" maintenance window.py tests
```

It could not execute because this environment has no `rg` executable (`/bin/bash:
line 1: rg: command not found`). The inventory above was completed with the
repository content-search tool and direct source/test inspection instead.

## Unresolved Risks

- The plan's assertion that Storage is the only remaining internal legacy-runner caller conflicts with the current `test_connection` caller in `maintenance/ui/window_node_actions.py:529`.
- The focused baseline does not verify CPU sampler, GPU probe, remote server, discovery, full shutdown, main-thread delivery, or stale-node behavior.
- The legacy runner has no shared concurrency bound or shutdown method; its lifecycle impact is not measured by a runtime scenario.
- No global thread-count reduction should be inferred from this inventory.
- Several compatibility and fallback paths are source-visible but lack dedicated characterization in the focused command.

## Working-Tree Status

Before this document was created, the worktree contained two pre-existing
untracked files: `docs/SYSTEM_ANALYZER_REVIEW.md` and
`docs/plans/2026-09-10-background-execution-consolidation.md`. They are unrelated
to this task and must not be staged. This task adds only
`docs/BACKGROUND_EXECUTION_AUDIT_2026-09-10.md`.

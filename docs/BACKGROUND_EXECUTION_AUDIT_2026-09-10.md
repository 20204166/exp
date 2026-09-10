# Background Execution Audit

**Scope:** One bounded consolidation pass; current repository is authoritative.
**Baseline:** Task 1 source/test inventory captured before any runtime or test edit.

## Execution Paths

| Path | Owner | Classification | Decision |
|---|---|---|---|
| Per-key application work | `AppCoordinator` (`maintenance/components/coordinator.py`) | Canonical general mechanism | Reuse as-is; its runner, generation, cancellation, delivery, and shutdown are already centralized. |
| Dashboard full scan | `DashboardScanLifecycle` + `BackgroundOrchestrator` (`maintenance/components/dashboard_scan.py`, `background_orchestration.py`, `maintenance/ui/window_scan.py`) | Specialized lifecycle | Keep separate for progress, timeout, grace lease, rerun, busy state, and dashboard queue protocol. |
| Process/storage dialog scans and process actions | Existing `AppCoordinator` calls in `maintenance/dialogs.py` and `maintenance/ui/window_node_actions.py` | Canonical mechanism with specialized dialog/node meaning | Keep dialog callbacks, operation keys, node checks, and result rendering; reuse the coordinator. |
| Storage Move to Trash | `StorageDialog.move_selected` -> dialog `AppCoordinator` key `storage_trash` | Consolidated internal caller | Reuse the existing coordinator; retain dialog confirmation, result rendering, and close guards. |
| Test Connection action | `window_node_actions.test_connection` -> window `AppCoordinator` key `node:<id>:test_connection` | Consolidated internal caller | Reuse the existing coordinator; retain authenticated hello, node identity, and stale-result guards. |
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
| CPU sampler (`SystemScanner` / dashboard scanner support) | One persistent daemon worker per scanner waits on a request event and publishes one non-blocking `psutil.cpu_percent` sample. | Request/result events serialize requests; `_start_cpu_worker` refuses to create a second live worker. | Request wait honors scan cancellation in polling slices; sampler stop sets stop/request events and joins for up to one second. No per-sample timeout beyond the bounded wait. | The scanner returns the sample to its caller; Tk handoff is owned by the enclosing scan path. | Stop is idempotent. No generation is needed for CPU samples; node binding is owned by the scanner/provider context. | Source plus Task 5 `CpuSamplingTests` passed; exact process thread count is NOT VERIFIED. |
| GPU probe (`scanner_support/gpu.py`) | Each probe uses a daemon `threading.Thread`; caller joins only for `GPU_QUERY_TIMEOUT_SECONDS`. | Lock-protected in-flight flag refuses stacked probes; one probe is active per scanner. | Explicit join timeout; a wedged call is abandoned. Stop increments query generation and invalidates late `finally` cleanup without joining. | Probe result returns to the calling scan worker; enclosing application path owns Tk delivery. | Generation protects a newer query from an old completion. Node binding is provided by the scanner instance/caller. | Source plus Task 5 `GpuConcurrencyTests` passed; provider interruption after abandon is NOT VERIFIED. |
| `RemoteSocketServer` | Listener runs on one daemon thread; `ThreadingTCPServer` creates daemon request handlers. | `BoundedSemaphore(max_active_handlers)` rejects over-admission; server `request_queue_size` is 16. | Per-socket timeout bounds idle/malformed clients; service cancellation is cooperative at the request/service layer. | Framed response returns over the socket, never through Tk. | `stop` calls server shutdown and close; `daemon_threads=True` and `block_on_close=False` keep shutdown bounded. Authentication and request identity are service-owned. | Source proves admission, frame-size, timeout, and shutdown settings. `test_cancelled_request_raises_before_send` and `test_socket_server_shutdown_releases_handler_permits` exist but were not part of the focused baseline command. |
| Discovery / peer transport | Discovery/session and network transport own their listener/browser or transport threads; peer connection work is submitted through node-qualified `AppCoordinator` keys. | Discovery admission/session rules and transport lifecycle are separate; coordinator coalesces peer connection operations by node key. Exact worker count is NOT VERIFIED. | Discovery stop/cancel and peer coordinator cancellation are separate; socket/transport timeouts are provider-owned. | Discovery events are bridged through `AppCoordinator.post`/delivery; peer results use coordinator delivery. Tk is not touched by transport workers. | Discovery generation and identity checks reject late events; peer connection callbacks check node identity and current context. Final shutdown stops discovery and peer manager before coordinator shutdown. | Task 5 `NetworkDiscoveryTests`, `DiscoverySessionTests`, and window/node lifecycle tests passed. |
| `TimerDelivery` and render delivery | Tk timers execute callbacks on the Tk thread; render coordinator is a presentation-side batching/gating seam, not a worker executor. | Pending timer IDs and render pending state are tracked; exact global queue bound is NOT VERIFIED. | Timers can be cancelled; render delivery rejects stale generations/hidden or closing surfaces. | `after` is the Tk handoff; render callbacks are invoked through the window's UI boundary. | Final shutdown cancels timers and shuts down render delivery. Node generation binding is applied by render intents/callers. | Task 5 window and node tests passed; global queue bound remains NOT VERIFIED. |

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

The current source includes the two bounded caller migrations from the preceding
tasks. `StorageDialog.move_selected` submits `storage_trash` through its existing
`AppCoordinator` (`maintenance/dialogs.py:1337,1674-1677`), and authenticated
Test Connection submits the node-qualified `test_connection` operation through
the window coordinator (`maintenance/ui/window_node_actions.py:468-535`). The
legacy `run_in_thread`/`BackgroundTaskRunner` compatibility surface remains
exported, but these two internal production callers no longer use it. Task 5
made no runtime or test changes.

## Boundedness And Shutdown

The default `AppCoordinator` executor is bounded at four workers and shuts down
without waiting for uninterruptible work. `BackgroundTaskRunner` creates daemon
threads without a shared limit or shutdown owner. Dashboard workers are daemon
threads tracked by task count and queue completion markers. CPU stop joins for a
one-second bound; GPU stop deliberately does not join a wedged probe. Remote
handlers are bounded by semaphore, frame size, socket timeout, and non-blocking
server close. Task 5 directly verified the CPU, GPU, remote, discovery, window,
and node lifecycle tests listed below. A global runtime thread-count reduction is
NOT VERIFIED and must not be inferred from these tests.

## Tk Delivery Verification

The focused baseline passed the coordinator delivery test and the
`BackgroundTaskRunner` real-Tk delivery/teardown tests. Task 5 additionally
passed window queue delivery and late-payload tests, dashboard stale-generation
tests, discovery late-event tests, and node stale/cancelled-result tests. Source
shows that `AppCoordinator`, `BackgroundOrchestrator`, and `TkDeliveryQueue`
route worker callbacks through injected delivery, a queue, or `after`; no
inspected worker path intentionally calls Tk directly. Remote handlers return
over sockets and never use Tk. Main-thread delivery for every specialized
worker, and a global queue bound, are NOT VERIFIED by this task.

## Task 5 Specialized-Lifecycle Verification

Command run exactly as specified by Task 5:

```text
python -m unittest tests.test_dashboard_scan tests.test_gpu_concurrency tests.test_cpu_sampling tests.test_remote_contract tests.test_network_discovery tests.test_discovery_session tests.test_window tests.test_window_nodes -v
```

Exact result: `Ran 252 tests in 12.615s` followed by `OK` (process exit 0).
All 252 tests passed. The command emitted expected diagnostic logs for simulated
GPU abandonment, unavailable mocked sensors, remote execution failure, discovery
fallback/unavailability, and late dashboard failure; none represented a failed
test.

Exact lifecycle evidence included:

| Area | Passing test names |
|---|---|
| Dashboard ownership | `DashboardScanLifecycleTests.test_start_orders_state_timer_then_worker_and_coalesces_rerun`; `test_timeout_reports_immediately_and_worker_completion_releases_lease`; `test_late_generation_cannot_resolve_current_scan`; `AppWindowTests.test_late_scan_completion_after_timeout_is_dropped`; `test_timeout_lease_prevents_overlap_then_recovers`; `test_timeout_lease_is_force_released_after_grace` |
| GPU boundedness | `GpuConcurrencyTests.test_simultaneous_calls_start_exactly_one_worker`; `test_hung_query_is_abandoned_after_window`; `test_slow_query_recovers_after_completion`; `test_new_scan_while_old_scan_is_finishing`; `test_late_worker_finally_clears_own_state`; `test_stale_finally_cannot_clear_newer_query`; `test_stop_gpu_query_invalidates_and_is_idempotent` |
| CPU sampling | `CpuSamplingTests.test_no_background_sampling_between_requests`; `test_dead_worker_is_restarted_on_next_request`; `test_stop_sampler_halts_worker`; `test_cancel_event_interrupts_cpu_sample_wait`; `test_no_cancel_event_keeps_single_timed_wait`; `test_baseline_blocking_sample_then_only_delta_reads`; `test_dashboard_and_component_share_the_published_value`; `test_sampler_failure_degrades_card_and_recovers` |
| Remote admission/shutdown | `SocketTransportTests.test_socket_server_bounds_concurrent_handlers_and_rejects_excess`; `test_socket_server_shutdown_releases_handler_permits`; `RemoteServiceRoundTripTests.test_cancelled_request_raises_before_send`; `SocketTransportTests.test_frame_helpers_reject_oversized_payloads` |
| Network discovery | `NetworkDiscoveryTests.test_repeated_start_stop_leaves_no_duplicate_peers`; `test_start_and_stop_lifecycle`; `test_start_is_idempotent`; `test_stop_is_idempotent`; `test_late_transport_event_after_stop_is_ignored`; `test_failed_start_cleans_up_partial_backend_state` |
| Discovery session | `DiscoverySessionTests.test_restart_rejects_stale_stabilization_callback`; `test_stop_cancels_pending_stabilization`; `test_stop_cancels_timer_before_coordinator_and_is_idempotent`; `test_start_orders_persistence_coordinator_timer_and_poll` |
| Window shutdown/delivery | `AppWindowTests.test_close_cancels_component_poll_before_destroying_root`; `test_close_cancels_pending_scan_timeout`; `test_close_during_live_scan_swallows_late_result`; `test_background_queue_delivers_payload_on_main_thread_poll`; `test_background_queue_ignores_late_payload_after_close` |
| Node binding/stale delivery | `WindowNodeConnectionTests.test_test_connection_submits_node_qualified_coordinator_run`; `test_cancelled_test_connection_drops_late_success`; `test_stale_test_connection_result_cannot_replace_cancelled_run`; `WindowNodeSwitchingTests.test_cancelled_node_a_snapshot_cannot_update_node_b`; `test_old_component_result_finishes_source_scheduler_without_touching_new_node`; `test_old_node_timeout_cannot_cancel_the_replacement_scan`; `test_operation_keys_are_node_qualified` |

## Dashboard Lifecycle Ownership

Source inspection confirms `DashboardScanLifecycle.start` creates the
`threading.Event`, claims a generation, schedules the timeout before delegating
worker start, and owns timeout/grace lease transitions
(`maintenance/components/dashboard_scan.py:50-68,93-156`). The
`BackgroundOrchestrator` owns the callback queue, task count, busy state, main
thread polling, and render batching (`maintenance/components/background_orchestration.py:44-183`).
The snapshot render path remains presentation-owned and node-generation gated.
These specialized responsibilities were deliberately not routed through
`AppCoordinator`.

## Scanner Worker Boundedness

CPU uses one persistent daemon request worker per scanner; `_start_cpu_worker`
refuses a second live worker, requests are serialized, and stop joins for at
most one second (`maintenance/scanner_support/dashboard.py:74-138,140-201`).
GPU uses one lock-protected in-flight probe, joins only for
`GPU_QUERY_TIMEOUT_SECONDS`, refuses stacked probes, abandons after the explicit
budget, and uses generation checks so late `finally` blocks cannot clear newer
state (`maintenance/scanner_support/gpu.py:42-133`). The passing CPU/GPU tests
above prove these specialized sensor protocols remain bounded. Exact process
thread counts across a live application are NOT VERIFIED.

## Remote Admission And Timeouts

`RemoteSocketServer` retains a `BoundedSemaphore`, non-blocking admission,
`request_queue_size = 16`, per-request socket timeout, maximum frame size,
daemon handler/listener threads, and `block_on_close = False`
(`maintenance/remote.py:913-1020`). Excess accepted requests are closed rather
than admitted, malformed/idle clients are bounded by the socket timeout, and
`stop` performs server shutdown/close. Provider cancellation is cooperative and
does not prove interruption of an uninterruptible provider call: NOT VERIFIED.

## Shutdown Ordering

`maintenance/ui/window_lifecycle.py:283-310` preserves this order: stop peer
server and discovery; shut down peer connections; cancel dashboard lifecycle;
cancel all coordinator operations and shut down `AppCoordinator`; cancel node
operations; dispose cluster presentation; cancel pending Tk timers; then shut
down render delivery. `close` marks the window closing before finalization and
stops local/node scanner workers before destroying the root
(`window_lifecycle.py:329-336`). `AppCoordinator.shutdown` invokes the executor
as `shutdown(wait=False, cancel_futures=True)` and does not claim to join
uninterruptible sensor or provider calls. The window and node
shutdown/stale-delivery tests passed. A proof that every third-party provider
honors cancellation is NOT VERIFIED.

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

- Task 5 verifies the named lifecycle tests, but global runtime thread counts,
  universal main-thread delivery across every specialized worker, and provider
  interruption after cancellation remain NOT VERIFIED.
- The legacy runner has no shared concurrency bound or shutdown method; its lifecycle impact is not measured by a runtime scenario.
- No global thread-count reduction should be inferred from this inventory.
- Several compatibility and fallback paths are source-visible but lack dedicated characterization in the focused command.

## Working-Tree Status

Before this document was created, the worktree contained two pre-existing
untracked files: `docs/SYSTEM_ANALYZER_REVIEW.md` and
`docs/plans/2026-09-10-background-execution-consolidation.md`. They are unrelated
to this task and must not be staged. This task adds only
`docs/BACKGROUND_EXECUTION_AUDIT_2026-09-10.md`.

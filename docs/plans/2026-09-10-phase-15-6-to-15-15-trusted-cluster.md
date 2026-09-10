# Phase 15.6-15.15 Trusted Cluster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete and adversarially validate the trusted-peer lifecycle, typed remote read paths, guarded process actions, target-aware UI, deployment, compatibility, and final Phase 15 readiness decision without adding a second coordinator or unsafe generic remote APIs.

**Architecture:** Extend the existing `NodeRegistry`/`NodeContext` and shared `AppCoordinator`; keep transport and target authorization in `maintenance/remote.py`, persistence in `maintenance/cluster.py`, and UI orchestration in `window.py`/`maintenance/ui`. Deliver phases in dependency order: lifecycle and read-only contracts first, then process termination only after explicit gates, then UI, cleanup audit, concurrency, compatibility, deployment, and final review.

**Tech Stack:** Python 3.10+, Tkinter, `psutil`, `zeroconf`, HMAC-framed TCP transport, `unittest`, Ruff, Pyright, Mypy, wheel installers, and repository BugGuard evidence workflows.

---

## Scope And Gates

This is one unified roadmap, but each phase produces a separately testable result.
15.9 is conditional on validated 15.8 and the existing permission model. 15.11 must remain read-only if its safety prerequisites are absent. No phase may silently turn discovery into trust, client hints into authorization, or a failed connection into a scan-interval change.

Before Task 2, the Phase 15.4/15.5 pairing and permission decision must be recorded: choose the repository's approved authenticated transport (the existing plan recommends mutual TLS with pinned credentials when confidentiality is required; the existing HMAC-only option is acceptable only if its confidentiality limitation is explicitly accepted). If that decision or target-owned grant provisioning is not complete, Tasks 2-4 may audit and test gaps but must not expose remote operations.

Required skills during execution:

- `BugGuard`: 15.6, 15.9, 15.11, and 15.15 security/regression audits.
- `evolving-apis-and-schemas`: 15.7 and 15.13 wire, snapshot, and cluster-schema changes.
- `investigating-performance`: 15.6 and 15.12 retry, executor, queue, and responsiveness work.
- `UI`: 15.10 target-bound status, capability, accessibility, and visual-state review.
- `writing-plans`: maintain this plan as gates or repository facts change.

Do not create a new skill unless an execution worker discovers a repeatable repository workflow not covered by these skills; document that discovery before proposing one.

Execution order is deliberately dependency-first: Task 1 baseline, Task 2 Phase 15.6 lifecycle, Task 3 Phase 15.7 snapshots, Task 4 Phase 15.8 process viewing, Task 5 Phase 15.9 termination gate, Task 6 Phase 15.10 UI, Task 7 Phase 15.11 cleanup audit, Task 8 Phase 15.12 concurrency, Task 9 Phase 15.13 compatibility, Task 10 Phase 15.14 deployment, and Task 11 Phase 15.15 final validation. The document's task sections are grouped by evidence edits, but workers must follow this order.

## Repository Map

- Modify `maintenance/nodes.py` for connection state, retry state, typed providers, target-bound snapshots, and node-qualified ownership.
- Modify `maintenance/remote.py` for strict authenticated envelopes, bounded socket serving, typed read/action requests, and safe error mapping.
- Modify `maintenance/cluster.py` for validated persisted endpoints, grants, identity continuity, and additive compatibility fields.
- Create `maintenance/components/peer_connection.py` only for one reusable reconciliation policy; it must not own a worker pool or timers.
- Create `maintenance/components/peer_service.py` only for target listener start/stop and bounded handler ownership.
- Modify `maintenance/components/discovery_session.py` for authenticated listener endpoint advertisement and loss/reappearance signals.
- Modify `maintenance/components/node_context.py` and `node_selection.py` for per-node lifecycle, cache, generation, and cancellation transitions.
- Modify `window.py` only as composition root, one reconciliation schedule, node-bound data delivery, page state, and shutdown ordering.
- Modify `maintenance/dialogs.py`, `maintenance/ui/window_node_actions.py`, `maintenance/ui/nodes_connections.py`, `maintenance/ui/cluster_page.py`, and relevant page modules for shared target-aware presentation only.
- Keep local safety in `maintenance/actions.py`; add target-side adapters without moving policy into widgets.
- Add focused tests to existing `tests/test_*.py`; create `tests/test_peer_connection.py`, `tests/test_peer_service.py`, `tests/test_remote_compatibility.py`, and `tests/test_deployment_validation.py` only when the existing suites have no clear owner.
- Create `tests/support/peer_cluster.py` for shared synthetic nodes, providers, clocks, transports, and process fakes; its helpers must never touch real network/process state.
- Update `README.md` and add `docs/phase-15-validation.md` only after verified behavior exists.

Every test uses synthetic node IDs, deterministic clocks, fake providers, fake sockets/processes, and fake Tk masters. Never use real secrets, live process termination, or a real network in unit tests.

## Task 1: Baseline And Contract Freeze

**Files:**
- Read: `docs/PHASE_15_4_TO_15_8_PEER_NETWORK_PLAN.md`, `maintenance/nodes.py`, `maintenance/remote.py`, `maintenance/cluster.py`, `window.py`, `tests/test_remote_contract.py`, `tests/test_nodes.py`, `tests/test_cluster.py`.
- Create: `docs/phase-15-6-15-15-audit.md`
- Test: existing focused suites, then the repository static gates.

- [ ] **Step 1: Record the current truth before editing**

Run:

```sh
git status --short
python -m unittest tests.test_remote_contract tests.test_nodes tests.test_cluster tests.test_node_selection tests.test_window_nodes -v
ruff check .
ruff format --check .
pyright
mypy --ignore-missing-imports .
```

## Task 11: Final Trusted Cluster Validation (Phase 15.15)

**Files:** `docs/phase-15-validation.md`, `docs/PHASE_15_4_TO_15_8_PEER_NETWORK_PLAN.md`, all phase test files; no production feature additions unless a proven Phase 15 regression is found.

- [ ] **Step 1: Run the complete adversarial matrix**

Use BugGuard with four opposition reviews followed by the final evidence audit. Exercise peer restart, IP/DHCP change, identity change, network loss, VPN/interface change, slow or malformed peer, many nodes, node switching, manual action during periodic refresh, and shutdown during remote work. Confirm discovered is not trusted, trusted is not authorized, initiator UI is not security authority, target revalidation is mandatory, and no generic shell/command/filesystem endpoint exists.

- [ ] **Step 2: Measure resource bounds**

Record idle CPU, peak thread count, queue depth, retained node state, duplicate timer count, event/history growth, and UI delivery latency for local plus several remotes. Compare against the baseline from Task 1 and retain the raw command output beside the summary; do not claim a performance improvement without measurements.

- [ ] **Step 3: Run all required checks**

```sh
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
pyright
mypy --ignore-missing-imports .
./install/verify.sh
git diff --check
git status --short
```

If a type checker reports the known historical duplicate-module baseline, record the exact paths and keep the phase decision conservative. Run `./lr impact`, `./lr 7`, and `./lr secrets` only if the repository provides the LR tool; missing LR tooling is a blocked validation item, not a pass.

- [ ] **Step 4: Write the final evidence report**

`docs/phase-15-validation.md` must contain exactly these sections: architecture found; every Phase 15 capability status; security review; concurrency review; platform review; packaging review; regressions found/fixed; unresolved risks; exact validation results; working-tree status. Include commit IDs and distinguish verified, not implemented, blocked, and unsupported.

- [ ] **Step 5: Select exactly one readiness result**

End the report and final review with exactly one of:

```text
PHASE 15 READY
```

```text
PHASE 15 READY WITH MINOR LIMITATIONS
```

```text
PHASE 15 BLOCKED
```

Use `PHASE 15 BLOCKED` for failed security gates, missing target revalidation, unbounded work, unsafe cleanup, malformed-input acceptance, stale identity acceptance, failed required checks, or missing LR validation. Use the minor-limitations result only when all security boundaries and required functionality pass and remaining limitations are explicitly non-security feature gaps.

- [ ] **Step 6: Final review and commit**

```sh
git add docs/phase-15-validation.md docs/PHASE_15_4_TO_15_8_PEER_NETWORK_PLAN.md
git commit -m "docs: complete Phase 15 trusted cluster validation"
git status --short
```

## Self-Review Checklist

- [ ] 15.6 coverage: explicit lifecycle states, bounded exponential retry, one reconciliation timer, network-change scenarios, cancellation, identity rejection, and unchanged component cadence are covered by Tasks 2 and 8.
- [ ] 15.7 coverage: typed `NodeSnapshot`, all listed resources, provider abstraction, caches, generations, stale state, unsupported capabilities, and local UI isolation are covered by Task 3.
- [ ] 15.8 coverage: target-bound read-only process dialog, target classification, filtering/search/identity, and stale result rejection are covered by Task 4.
- [ ] 15.9 coverage: gated target-side authorization, PID/create-time revalidation, graceful termination, duplicate-click handling, and no generic signals are covered by Task 5.
- [ ] 15.10 coverage: shared dialogs, target capability/trust/permission/availability matrix, local/remote labels, and UI coordinator boundaries are covered by Task 6.
- [ ] 15.11 coverage: existing cleanup audit, opaque candidate requirement, target revalidation, Trash semantics, and safe read-only fallback are covered by Task 7.
- [ ] 15.12 coverage: bounded executor work, node-qualified keys, slow-peer isolation, switching, refreshes, actions, and no per-node threads are covered by Task 8.
- [ ] 15.13 coverage: mixed-version requests/responses, absent capabilities, additive fields, unknown operations, and fail-closed security are covered by Task 9.
- [ ] 15.14 coverage: clean install, upgrade, preservation, uninstall/reinstall, package contents, dependencies, entry points, discovery, diagnostics, and platform evidence are covered by Task 10.
- [ ] 15.15 coverage: adversarial chain, boundary review, resource bounds, complete checks, evidence report, and exactly one final status are covered by Task 11.

## Research Basis

The plan uses repository behavior as the implementation source of truth and these official references only for constraints:

- Python `socketserver` documents that threaded request handling creates one handler instance per request, that `request_queue_size` bounds queued connections, and that `shutdown()` must run from a thread other than `serve_forever()`: <https://docs.python.org/3/library/socketserver.html>.
- Python `concurrent.futures` documents bounded `ThreadPoolExecutor` workers, cancellation limits, and `shutdown(cancel_futures=True)`: <https://docs.python.org/3/library/concurrent.futures.html>.
- OWASP requires authorization to remain distinct from authentication, deny by default, and be checked at the protected resource boundary rather than trusted to client UI: <https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html>.
- PyPA documents wheel metadata, entry points, and package installation behavior: <https://packaging.python.org/en/latest/guides/section-build-and-publish/>.

These references do not prove that this repository currently meets the requirements; the focused tests, static gates, package checks, and final evidence report must establish that.

## Task 9: Mixed-Version Compatibility (Phase 15.13)

**Files:** `maintenance/remote.py`, `maintenance/cluster.py`, `maintenance/nodes.py`; create `tests/test_remote_compatibility.py`; update `docs/phase-15-validation.md`.

- [ ] **Step 1: Add compatibility matrix tests**

Exercise new client to old peer, old client to new peer, missing process actions, missing thermal sensors, missing newer fields, unknown extra response fields, and unknown request types. Use captured synthetic envelopes, not network assumptions.

```python
def test_unknown_capability_is_not_fabricated(self):
    hello = {"capabilities": ["dashboard_read", "future_action"]}
    self.assertEqual(
        parse_hello_capabilities(hello), frozenset({NodeCapability.DASHBOARD_READ})
    )


def test_unknown_privileged_operation_fails_closed(self):
    with self.assertRaises(RemoteProtocolError):
        validate_operation_params("future_privileged_action", {})
```

The test module defines `parse_hello_capabilities` as the strict decoder under test and imports the existing production `validate_operation_params` function directly. The parser must discard unknown read metadata without inventing a capability and must reject unknown operations.

- [ ] **Step 2: Separate additive reads from security fields**

Keep protocol version `"1"` for safely additive optional read fields. Reject unsupported protocol versions, missing security identity fields, malformed permissions, and unknown privileged operations. Decode known fields without fabricating absent capabilities; expose `Unsupported` for absent data.

- [ ] **Step 3: Validate persisted migration**

Load legacy cluster records with missing grants, endpoints, capabilities, and identity fingerprints. Preserve unrelated display/configuration data, default missing permissions to deny, and require explicit pairing before an old record becomes operational.

- [ ] **Step 4: Run and commit**

```sh
python -m unittest tests.test_remote_compatibility tests.test_remote_contract tests.test_cluster -v
git add maintenance/remote.py maintenance/cluster.py maintenance/nodes.py tests/test_remote_compatibility.py docs/phase-15-validation.md
git commit -m "feat: fail softly across peer versions"
```

Use `evolving-apis-and-schemas` to review wire and persisted compatibility before merging this task.

## Task 10: Cross-Platform Packaging And Deployment (Phase 15.14)

**Files:** `pyproject.toml`, `requirements.txt`, `install/build.sh`, `install/build.ps1`, `install/install*.sh`, `install/install*.ps1`, `install/verify*.sh`, `install/verify*.ps1`, `README.md`; create `tests/test_deployment_validation.py` and `docs/phase-15-validation.md`.

- [ ] **Step 1: Add package-content assertions**

```python
def test_wheel_contains_remote_and_entrypoint_modules(self):
    wheel = latest_wheel()
    members = wheel_members(wheel)
    self.assertIn("maintenance/remote.py", members)
    self.assertIn("maintenance/nodes.py", members)
    self.assertIn("system-analyzer", entry_points(wheel))
```

The test module defines `latest_wheel() -> Path` by selecting the lexicographically greatest `dist/system_analyzer-*.whl`, `wheel_members(path) -> set[str]` by reading `zipfile.ZipFile.namelist()`, and `entry_points(path) -> set[str]` by reading `*.dist-info/entry_points.txt`. These are test-only inspectors.

- [ ] **Step 2: Verify clean environments**

On officially supported Linux, macOS, and Windows environments, create a clean Python 3.10+ environment, install the built wheel, verify imports and both entry points, run local snapshot diagnostics, exercise discovery startup, and test remote read-only against a synthetic/loopback peer where the platform supports it. Record exact commands, Python versions, dependency versions, and unavailable optional features.

- [ ] **Step 3: Verify upgrade and preservation**

Install the previous wheel, create preferences and trusted-node records, upgrade to the new wheel, verify config and trust data remain readable, then test uninstall/reinstall expectations. Do not add an updater. Ensure optional NVIDIA/sensor dependencies fail as explicit unavailable capability states.

- [ ] **Step 4: Build and verify the actual wheel**

```sh
./install/build.sh
./install/verify.sh
python -m unittest tests.test_packaging tests.test_install_scripts tests.test_package_structure tests.test_deployment_validation -v
```

- [ ] **Step 5: Update documentation and commit**

Replace README claims that remote metrics/actions are unimplemented only for behavior actually verified. State discovery/trust/permission boundaries and remote cleanup status. Commit the evidence and documentation:

```sh
git add pyproject.toml requirements.txt install README.md tests/test_packaging.py tests/test_install_scripts.py tests/test_package_structure.py tests/test_deployment_validation.py docs/phase-15-validation.md
git commit -m "docs: record cross-platform Phase 15 deployment"
```

## Task 7: Remote Cleanup Safety Audit (Phase 15.11)

**Files:** `maintenance/actions.py`, `maintenance/remote.py`, `maintenance/cluster.py`, `maintenance/dialogs.py`, `window.py`; tests in `tests/test_storage_dialog.py`, `tests/test_remote_contract.py`, `tests/test_process_protection.py`.

- [ ] **Step 1: Prove the current boundary**

Trace every storage operation from `StorageDialog` to `FileManager`. Confirm `FileManager` alone checks Downloads containment, symlinks, regular files, inode/device stability, and `send2trash`. Confirm no wire operation accepts an arbitrary path.

- [ ] **Step 2: Add a candidate-ID design test before implementation**

The only acceptable remote mutation shape is an opaque target-created ID:

```python
def test_remote_cleanup_rejects_arbitrary_path(self):
    with self.assertRaises(RemoteProtocolError):
        service.handle(signed_request("cleanup", {"path": "/etc/passwd"}))


def test_candidate_id_is_revalidated_on_target(self):
    result = file_manager.move_candidate_to_trash("candidate-1")
    self.assertEqual(result.errors, ("candidate changed during validation",))
```

The test fixture supplies `signed_request(operation, params)` and a fake `file_manager` implementing the existing target-side candidate contract. If production has no `move_candidate_to_trash` or opaque candidate registry, this is a failing design test and the safe implementation is the read-only outcome in Step 3, not a path-based substitute.

- [ ] **Step 3: Choose the safe outcome**

If target-side opaque candidate creation, durable/expiring candidate storage, authorization, path revalidation, and explicit confirmation are not already complete, leave remote cleanup read-only, remove any remote cleanup affordance, and document the missing prerequisite. Do not add a feature merely to satisfy the phase label.

- [ ] **Step 4: Commit the audit result**

```sh
python -m unittest tests.test_storage_dialog tests.test_remote_contract tests.test_process_protection -v
git add maintenance/actions.py maintenance/remote.py maintenance/cluster.py maintenance/dialogs.py window.py tests/test_storage_dialog.py tests/test_remote_contract.py
git commit -m "audit: keep remote cleanup target-safe"
```

## Task 8: Multi-Node Concurrency (Phase 15.12)

**Files:** `maintenance/components/coordinator.py`, `maintenance/components/peer_connection.py`, `window.py`; create `tests/test_multi_node_concurrency.py`; use `maintenance/performance_audit.py` and `tools/scanner_performance_audit.py` for evidence.

- [ ] **Step 1: Add bounded-workload tests**

Run synthetic workloads for local plus one remote, local plus several remotes, slow/offline peers, rapid switching, simultaneous manual actions, periodic refresh, and process requests. Assert keys include node IDs, one node's blocked task does not block local completion, and pending work remains bounded.

```python
def test_slow_peer_does_not_block_local_result(self):
    coordinator = fake_coordinator(max_workers=4)
    coordinator.run("node:remote:node_snapshot", slow_task)
    coordinator.run("node:local:node_snapshot", fast_task)
    self.assertEqual(delivered_for("node:local:node_snapshot"), ["local"])
```

The shared fixture defines `fake_coordinator` with an injected bounded runner, `slow_task` blocked by a test event, `fast_task` returning `"local"`, and `delivered_for` reading the fixture's recorded callback list. The assertion is made after the fake runner delivers the local callback without waiting for the blocked peer.

- [ ] **Step 2: Measure existing executor behavior**

Record active worker count, queued keys, callback count, retained contexts, and UI delivery latency before changing code. Do not reintroduce `ResourceGovernor`; the existing `AppCoordinator` executor and per-key coalescing are the only scheduling mechanisms.

- [ ] **Step 3: Apply the smallest capacity fix**

If evidence shows a real issue, bound it using the existing executor or coordinator: one node-qualified operation key, at most one in-flight run per key, one coalesced rerun, and cancellation before selection replacement. Do not create a thread or timer per node.

- [ ] **Step 4: Run stress and commit**

```sh
python -m unittest tests.test_multi_node_concurrency tests.test_coordinator_discovery tests.test_lifecycle_stress -v
python -m tools.scanner_performance_audit --output-dir /tmp/phase-15-concurrency
ruff check . && ruff format --check .
git add maintenance/components/coordinator.py maintenance/components/peer_connection.py window.py maintenance/performance_audit.py tools/scanner_performance_audit.py tests/test_multi_node_concurrency.py
git commit -m "test: validate bounded multi-node concurrency"
```

## Task 3: Typed Remote System Data (Phase 15.7)

**Files:**
- Modify: `maintenance/nodes.py`, `maintenance/cluster.py`, `maintenance/remote.py`.
- Modify: `maintenance/components/node_context.py`, `window.py`.
- Test: `tests/test_remote_contract.py`, `tests/test_cluster.py`, `tests/test_window_nodes.py`.

- [ ] **Step 1: Add codec and normalization tests**

Assert local and remote providers produce the same `NodeSnapshot` shape and that the authenticated target ID is checked twice:

```python
def test_inner_snapshot_target_mismatch_is_rejected(self):
    payload = {"snapshot": node_snapshot_to_dict(make_snapshot(NodeId("other")))}
    transport = signed_transport(node_id="peer", payload=payload)
    provider = AuthenticatedNodeProvider(
        node_id=NodeId("peer"), secret=SECRET, transport=transport
    )
    with self.assertRaises(RemoteAuthError):
        provider.node_snapshot()
```

Also assert every supported resource (CPU, memory, storage, GPU, network, battery, temperatures) preserves values, capability states, timestamp, and node metadata; unsupported resources remain `CapabilityState.UNSUPPORTED` rather than becoming zeroes.

- [ ] **Step 2: Make the provider contract explicit**

Keep `dashboard_snapshot()` as a compatibility method, but make `node_snapshot()` the controller boundary. Add a local adapter that wraps the existing `Analyzer` result with the local `NodeDescriptor`; do not import Tkinter, psutil, or transport code into `maintenance/nodes.py`.

- [ ] **Step 3: Preserve per-node cache and stale state**

Store the last valid `NodeSnapshot` on each `NodeContext`. On `RemoteTransportError`, cancellation, capability denial, or offline state, retain that snapshot and update connection status; never store an exception as a successful result. Use `NodeSnapshot.is_stale(now=..., max_age=...)` for presentation labels.

- [ ] **Step 4: Wire node-qualified snapshot work**

Use `node_operation_key(context.node_id, "node_snapshot")` and the existing `AppCoordinator`. The completion callback must reject a stale node/generation before updating `NodeContext`, `window.snapshot`, or render targets. Verify that an offline peer does not delay local work.

- [ ] **Step 5: Run and commit**

```sh
python -m unittest tests.test_remote_contract tests.test_cluster tests.test_window_nodes -v
ruff check . && ruff format --check .
git add maintenance/nodes.py maintenance/cluster.py maintenance/remote.py maintenance/components/node_context.py window.py tests/test_remote_contract.py tests/test_cluster.py tests/test_window_nodes.py
git commit -m "feat: normalize node-bound remote snapshots"
```

## Task 4: Read-Only Remote Process Viewing (Phase 15.8)

**Files:**
- Modify: `maintenance/models.py`, `maintenance/nodes.py`, `maintenance/remote.py`.
- Modify: `maintenance/dialogs.py`, `window.py`, `maintenance/ui/window_node_actions.py`.
- Test: `tests/test_process_table.py`, `tests/test_window_nodes.py`, `tests/test_remote_contract.py`.

- [ ] **Step 1: Add failing target-binding tests**

```python
def test_open_dialog_keeps_original_node_after_dashboard_switch(self):
    dialog = make_process_dialog(node_id=NodeId("node-a"), provider=provider_a)
    switch_dashboard_to(NodeId("node-b"))
    self.assertEqual(dialog.node_id, NodeId("node-a"))
    self.assertIs(dialog.provider, provider_a)


def test_remote_process_records_keep_identity_fields(self):
    records = provider_a.process_candidates()
    self.assertEqual((records[0].pid, records[0].create_time), (42, 12.5))
```

- [ ] **Step 2: Align the action type declaration before using it**

Choose one consistent production signature and use it in `ProcessActionBackend`, local `ProcessManager` adapters, remote adapters, and `ProcessDialog`. The preferred shape is:

```python
def request_quit(
    self,
    pids: list[int],
    expected_create_times: dict[int, float] | None = None,
) -> ProcessActionResult: ...
```

The read-only path must not require an action backend. `ProcessCandidate.action_allowed` is target-provided display information only.

- [ ] **Step 3: Bind one dialog to one provider**

At construction, capture `node_id`, target provider, target title, `node_operation_key(node_id, "process_candidates")`, and read-only state. Route the request through `AppCoordinator`; close/dispose removes the subscription, and late results are ignored by dialog generation.

- [ ] **Step 4: Keep classification target-side**

The target provider calls its own `ProcessManager`/scanner classification. The initiator only decodes and displays protected/can-quit state, search, sort, PID, and create-time. Opening Node A then selecting Node B must not update the Node A dialog.

- [ ] **Step 5: Gate and commit**

```sh
python -m unittest tests.test_process_table tests.test_window_nodes tests.test_remote_contract -v
ruff check . && ruff format --check .
git add maintenance/models.py maintenance/nodes.py maintenance/remote.py maintenance/dialogs.py window.py maintenance/ui/window_node_actions.py tests/test_process_table.py tests/test_window_nodes.py tests/test_remote_contract.py
git commit -m "feat: bind remote process viewing to target nodes"
```

Exit gate: read-only remote viewing passes with stale-result and target-binding tests. If it does not, stop and do not enable Phase 15.9.

## Task 5: Safe Remote Process Termination (Phase 15.9)

**Preconditions:** Phase 15.8 read-only tests pass; Phase 15.5 permissions and target-owned grants are verified by BugGuard.

**Files:** `maintenance/remote.py`, `maintenance/actions.py`, `maintenance/nodes.py`, `maintenance/dialogs.py`, `maintenance/ui/window_node_actions.py`; tests in `tests/test_remote_contract.py`, `tests/test_process_protection.py`, `tests/test_process_table.py`.

- [ ] **Step 1: Write denial-first tests**

For a target fake `ProcessManager`, assert protected process, disappeared process, PID reuse, foreign user, permission denied, target offline, duplicate click, stale list, graceful termination failure, and wrong-dialog delivery never cause an unsafe target action.

```python
def test_target_revalidates_create_time_before_quit(self):
    manager = FakeProcessManager(actual_create_time=99.0)
    result = target_request_quit(manager, pid=42, create_time=12.5)
    self.assertEqual(result.stopped, ())
    self.assertIn("changed since it was scanned", result.errors[0])
```

- [ ] **Step 2: Use typed termination requests**

Define a request carrying `ProcessRef` values plus an explicit action kind. Serialize only PID and optional create-time under the existing allowlisted operation. Reject arbitrary signal numbers, generic kill endpoints, shell commands, and node IDs that do not match the authenticated target.

- [ ] **Step 3: Reuse target safety**

The target resolves the authenticated grant, checks capability and permission, re-reads PID ownership/name/executable/create-time, applies protected-process policy, calls graceful `request_quit` first, and returns `ProcessActionResult`. A lost response is an unknown outcome; never automatically retry a destructive operation.

- [ ] **Step 4: Make the UI idempotent and target-bound**

Disable the initiating button while its node-qualified action key is in flight. On completion, deliver only to the originating dialog generation and node. A dashboard switch does not redirect or re-enable an old action.

- [ ] **Step 5: Run BugGuard and commit**

```sh
python -m unittest tests.test_remote_contract tests.test_process_protection tests.test_process_table -v
ruff check . && ruff format --check .
git add maintenance/remote.py maintenance/actions.py maintenance/nodes.py maintenance/dialogs.py maintenance/ui/window_node_actions.py tests/test_remote_contract.py tests/test_process_protection.py tests/test_process_table.py
git commit -m "feat: enforce target-side remote process safety"
```

Invoke `BugGuard` Mode A after the commit. Do not proceed if any counter-test can make the initiator decide safety or repeat a potentially completed action.

## Task 6: Shared Remote-Aware UI (Phase 15.10)

**Files:** `window.py`, `maintenance/dialogs.py`, `maintenance/ui/cluster_page.py`, `maintenance/ui/nodes_connections.py`, `maintenance/ui/dashboard_page.py`, `maintenance/ui/thermals_page.py`, `maintenance/ui/window_node_actions.py`; tests in `tests/test_dashboard_ui.py`, `tests/test_cluster_page.py`, `tests/test_nodes_connections_page.py`, `tests/test_window_nodes.py`, `tests/test_process_table.py`.

- [ ] **Step 1: Add state-matrix tests**

Test labels and actions for `Local`, `Remote trusted`, `Remote read-only`, `Offline`, `Unsupported`, and `Permission denied`. Derive visibility from descriptor capability, target-owned permission hint, trust, and current status; never from hostname or `is_local` alone.

```python
def test_offline_remote_keeps_last_value_and_hides_actions(self):
    state = render_target_state(
        make_descriptor(status=NodeStatus.OFFLINE), last_snapshot
    )
    self.assertEqual(state.label, "Offline")
    self.assertFalse(state.can_quit)
    self.assertEqual(state.value, last_snapshot.get("cpu").value)
```

The UI test fixture defines `render_target_state(descriptor, snapshot)` as a pure recording-widget projection of the existing dashboard/page status inputs; it must not call transport or authorization code. `last_snapshot` is created by `make_snapshot(NodeId("peer"))` and contains a CPU resource.

- [ ] **Step 2: Reuse existing dialog constructors**

Pass a typed provider/context and immutable target identity into existing System Overview, process, GPU/details, storage/details, and thermal surfaces. Do not create parallel remote dialogs or transport-aware widgets.

- [ ] **Step 3: Make node selection and status explicit**

Render target name and state in Nodes & Connections and selectors. Keep dialogs bound to their opening `NodeId`; switching the dashboard changes only the dashboard. Use `UICoordinator`/`ButtonCoordinator` for coalescing and delivery, not authorization.

- [ ] **Step 4: Verify UI behavior**

Run the recording-widget tests and `tests/test_live_tk_resize.py` where a display exists. Confirm no unsupported capability renders a guessed value and no disabled action can be invoked through a stale callback.

- [ ] **Step 5: Review and commit**

Use the `UI` skill for the rendered-state/accessibility review, then run:

```sh
python -m unittest tests.test_dashboard_ui tests.test_cluster_page tests.test_nodes_connections_page tests.test_window_nodes tests.test_process_table -v
git add window.py maintenance/dialogs.py maintenance/ui/cluster_page.py maintenance/ui/nodes_connections.py maintenance/ui/dashboard_page.py maintenance/ui/thermals_page.py maintenance/ui/window_node_actions.py tests/test_dashboard_ui.py tests/test_cluster_page.py tests/test_nodes_connections_page.py tests/test_window_nodes.py tests/test_process_table.py
git commit -m "feat: integrate target-aware cluster UI"
```


Record each command's exit status and any pre-existing type-check findings in `docs/phase-15-6-15-15-audit.md`; do not call a failing baseline a feature regression.

- [ ] **Step 2: Inventory actual public contracts**

List every caller of `NodeProvider`, `AuthenticatedNodeProvider`, `RemoteService`, `TrustedNodeRecord`, `ProcessActionBackend`, `NodeSnapshot`, and `NodeRegistry`. Mark whether each operation is local, in-process fake, socket-backed, or UI-only. Compare the inventory with the prior plan's confirmed gaps, especially that `_listener_endpoint()` currently returns `(False, None)` and `RemoteSocketServer` uses unbounded `ThreadingTCPServer` handlers.

- [ ] **Step 3: Freeze operation and trust rules**

Keep these operation names unless a test proves an additive, compatible field is required:

```python
READ_OPERATIONS = {
    "hello",
    "dashboard_snapshot",
    "component_summary",
    "process_candidates",
    "storage_candidates",
}
ACTION_OPERATIONS = {"process_request_quit", "process_force_quit"}
FORBIDDEN_OPERATION_FAMILIES = {
    "shell",
    "subprocess",
    "arbitrary_path_delete",
    "credential_forwarding",
}
```

Discovery remains presence-only. Target-side grants, capabilities, and local `ProcessManager` checks remain authoritative.

- [ ] **Step 4: Commit the baseline evidence**

```sh
git add docs/phase-15-6-15-15-audit.md
git commit -m "docs: freeze Phase 15 cluster baseline"
```

The shared fixture module must define these concrete helper contracts before later tests use them: `make_remote_context(trust) -> NodeContext`, `make_descriptor(status) -> NodeDescriptor`, `make_snapshot(node_id) -> NodeSnapshot`, `signed_transport(node_id, payload) -> RemoteTransport`, `signed_request(operation, params) -> str`, `make_process_dialog(node_id, provider) -> ProcessDialog` using `object.__new__` where Tk is unnecessary, `switch_dashboard_to(node_id) -> None` through the fake controller, `fake_coordinator(max_workers) -> AppCoordinator`, `slow_task(cancel_event, progress)`, `fast_task(cancel_event, progress)`, `delivered_for(key) -> list[str]`, and `wheel_members(path) -> set[str]`/`entry_points(path) -> set[str]` using `zipfile.ZipFile`. Each helper's implementation is a small deterministic adapter over existing repository models, not a new production abstraction.

## Task 2: Connection State And Retry Policy (Phase 15.6)

**Files:**
- Modify: `maintenance/nodes.py`, `maintenance/components/node_context.py`, `maintenance/components/node_selection.py`.
- Create: `maintenance/components/peer_connection.py`, `tests/test_peer_connection.py`.
- Modify: `window.py`, `maintenance/components/discovery_session.py`.

- [ ] **Step 1: Add failing state-transition tests**

Use a fake clock and registry context to assert the state is independently representable from trust:

```python
def test_trusted_peer_can_be_offline_without_losing_trust(self):
    context = make_remote_context(trust=NodeTrustState.TRUSTED)
    context.connection = ConnectionState.offline("timeout", now=10.0)
    self.assertEqual(context.descriptor.trust, NodeTrustState.TRUSTED)
    self.assertEqual(context.connection.status, NodeConnectionStatus.OFFLINE)


def test_identity_failure_stops_automatic_retry(self):
    state = RetryState()
    state.record_failure(PeerFailure.IDENTITY_CHANGED, now=5.0)
    self.assertIsNone(state.next_attempt_at)
    self.assertFalse(state.automatic_retry)
```

Define `ConnectionState`, `NodeConnectionStatus`, `RetryState`, and `PeerFailure` in the test fixture only long enough to make the expected domain contract explicit, then move the production types to `maintenance/nodes.py`.

- [ ] **Step 2: Implement one bounded retry value object**

Use monotonic time, capped exponential delay, deterministic injected jitter, and no timer allocation:

```python
delay = min(
    MAX_RETRY_SECONDS, BASE_RETRY_SECONDS * (2 ** min(attempt, MAX_BACKOFF_EXPONENT))
)
next_attempt_at = now + delay + jitter(attempt)
```

Authentication failure and identity change set `next_attempt_at = None`; timeout, refused connection, route failure, and disappearance schedule the capped delay. Keep component intervals untouched.

- [ ] **Step 3: Implement one reconciliation owner**

`PeerConnectionManager.reconcile(now)` examines all trusted contexts, starts at most one `node:<id>:connect` operation per node through the existing `AppCoordinator`, and returns the next global deadline. `window.py` schedules one existing application timer for that deadline. It must cancel on selection change, revoke, and shutdown; a completion is accepted only when node ID and connection generation still match.

- [ ] **Step 4: Test lifecycle scenarios**

Add tests for peer starts later, disappears, returns, DHCP/IP change, Wi-Fi/VPN route change, sleep/wake, transient timeout, repeated reconnect, application restart, authentication expiry/failure, and shutdown during reconnect. Assert address updates occur only after authenticated `hello` and durable cluster save.

- [ ] **Step 5: Commit the lifecycle slice**

```sh
python -m unittest tests.test_peer_connection tests.test_discovery_session tests.test_node_selection -v
ruff check maintenance/nodes.py maintenance/components/peer_connection.py maintenance/components/node_context.py maintenance/components/node_selection.py tests/test_peer_connection.py
git add maintenance/nodes.py maintenance/components/peer_connection.py maintenance/components/node_context.py maintenance/components/node_selection.py maintenance/components/discovery_session.py window.py tests/test_peer_connection.py
git commit -m "feat: add bounded peer connection lifecycle"
```

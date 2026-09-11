# Revoke & Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the revoke stuck-state bug (already done) plus six verified defects from the bug audit: coordinator lease non-renewal causing premature/fenced failover, selected-node breakage on remove-connection, fingerprint-less peers stuck in auth loops, and Windows GPU console flashes, Windows test import break, and the coordinator replay-after-cancel stale-task bug.

**Architecture:** All fixes are small, targeted edits to existing owners. The revoke fix routes already-revoked assignments to `revoke_trusted_node`. The lease fix adds coordinator self-renewal and guards promotion to the local subcoordinator inside `reconcile_peer_connections` (`maintenance/ui/window_discovery.py`). Platform fixes stay inside `maintenance/external_commands.py` / `maintenance/scanner_support/gpu.py` and the Windows-only test. No new modules.

**Tech Stack:** Python 3.11+, Tkinter app; tests are `unittest` under `tests/`; run with `python3 -m unittest discover -s tests -q`; static gates: `ruff check .`, `ruff format --check .`, `pyright`, `mypy --ignore-missing-imports`.

**Status:** Task 0 (revoke stuck-state) is already implemented and its regression test is committed-ready. All other tasks are TDD: failing test first, minimal fix, full suite green, commit.

---

## File Structure Map

| File | Responsibility in this plan |
|------|-----------------------------|
| `maintenance/ui/window_node_actions.py` | (Task 0 done) revoke already-revoked assignments; (Task 2) revert selection after remove-connection |
| `maintenance/ui/window_discovery.py` | (Task 1) coordinator lease self-renewal + promotion guard in `reconcile_peer_connections`; (Task 3) `can_connect_peer` fingerprint guard |
| `maintenance/components/peer_connection.py` | Read-only for Task 1 (uses existing `renew_cluster_lease`); no edits |
| `maintenance/components/coordinator.py` | (Task 6) update coalesced task/callbacks in `AppCoordinator.run` |
| `maintenance/external_commands.py` | (Task 4) `creationflags` parameter on `run_text_command`/`run_json_command` |
| `maintenance/scanner_support/gpu.py` | (Task 4) pass `CREATE_NO_WINDOW` on Windows for the PowerShell GPU probe |
| `tests/test_window_nodes.py` | (Task 0 done) regression test; (Task 2) remove-connection-selected test; (Task 3) fingerprint-guard test |
| `tests/test_window_discovery.py` (or `test_peer_connection.py`) | (Task 1) lease-renewal + promotion-guard tests |
| `tests/test_components.py` | (Task 6) run-after-cancel replay test |
| `tests/test_external_commands.py` | (Task 4) creationflags forwarding tests |
| `tests/test_storage_conservative.py` | (Task 5) POSIX-only skip guard |
| `docs/plans/2026-09-11-revoke-and-audit-fixes.md` | This plan |

---

## Task 0: Revoke stuck-state fix (DONE)

Already implemented and verified (full suite 1342 OK).

**Files:**
- Modify: `maintenance/ui/window_node_actions.py:212-239` (`revoke_node`)
- Test: `tests/test_window_nodes.py` `test_revoke_already_revoked_assignment_removes_connection`

Fix: when the node's role assignment exists but is already `revoked=True`, skip `role_state.revoke()` (which raises `"unknown or revoked node"`) and go straight to `revoke_trusted_node`, so an interrupted earlier revocation still removes the node from the connection.

```python
        role_state = _role_state(controller)
        assignment = role_state.assignment_for(NodeId(node_id))
        if assignment is None or assignment.revoked:
            # A trusted node without a role record, or one whose revocation was
            # already persisted by an interrupted earlier revocation, has no
            # role to revoke; revocation means removing trust entirely.
            revoke_trusted_node(controller, node_id)
            return
```

No further work required in this plan.

---

### Task 1: Coordinator lease self-renewal + promotion guard

**Files:**
- Modify: `maintenance/ui/window_discovery.py` — `reconcile_peer_connections` (~line 520) and add two helpers
- Test: `tests/test_window_nodes.py` (new tests in `WindowNodeConnectionTests`)

- [ ] **Step 1: Write the failing tests**

```python
    def test_reconcile_does_not_promote_when_local_is_coordinator(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
            start_discovery=False,
        )
        state = ClusterState.create_local(local_node_id="local")
        state.role_assignments = state.role_assignments + (
            RoleAssignment(
                frozenset({ClusterRole.SUBCOORDINATOR}),
                node_id=NodeId("peer-a"),
            ),
        )
        epoch = state.coordinator_epoch
        state.coordinator_epoch = replace(
            epoch, lease_expires_at=time.time() - 10.0
        )
        window._cluster_state = state
        manager = Mock()
        manager.promote_if_due.return_value = None
        window._peer_connection_manager = manager
        window._cluster_store = Mock()
        window._schedule_peer_reconciliation = Mock()
        window._schedule_timer = Mock(return_value="timer-1")
        window._cancel_timer = Mock(return_value=True)
        window.snapshot = None

        window._reconcile_peer_connections()

        manager.promote_if_due.assert_not_called()
```

```python
    def test_reconcile_renews_local_coordinator_lease(self) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        epoch = state.coordinator_epoch
        state.coordinator_epoch = replace(
            epoch, lease_expires_at=time.time() + 15.0
        )
        window._cluster_state = state
        manager = Mock()
        manager.renew_cluster_lease = Mock(
            side_effect=lambda state_, **kwargs: setattr(
                state_, "coordinator_epoch", replace(
                    state_.coordinator_epoch, lease_expires_at=time.time() + 120.0
                )
            )
        )
        window._peer_connection_manager = manager
        window._cluster_store = Mock()
        window._schedule_peer_reconciliation = Mock()
        window._schedule_timer = Mock(return_value="timer-1")
        window._cancel_timer = Mock(return_value=True)
        window.snapshot = None

        before = state.coordinator_epoch.lease_expires_at
        window._reconcile_peer_connections()
        after = state.coordinator_epoch.lease_expires_at

        self.assertGreater(after, before)
        manager.renew_cluster_lease.assert_called_once()
```

Expected: both FAIL (promotion is still called for the coordinator; lease is not renewed).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_window_nodes.WindowNodeConnectionTests -q`
Expected: 2 failures (`assert_called_once` on `promote_if_due`; `lease_expires_at` unchanged).

- [ ] **Step 3: Implement the fix**

Edit `maintenance/ui/window_discovery.py`. Imports already present: `ClusterRole` is NOT imported in this module — add it to the `from maintenance.components.cluster_roles import (...)` import (check current imports; `RoleState` is imported lazily inside `handle_role_request`). Add the two helpers and guard the reconcile body:

```python
def _is_local_subcoordinator(controller: Any) -> bool:
    from maintenance.components.cluster_roles import ClusterRole

    return ClusterRole.SUBCOORDINATOR in controller._cluster_state.local_assignment.roles


def _renew_local_coordinator_lease(controller: Any, manager: PeerConnectionManager) -> None:
    from maintenance.components.cluster_roles import ClusterRole, FencingError

    state = controller._cluster_state
    epoch = state.coordinator_epoch
    if epoch is None:
        return
    assignment = state.local_assignment
    if (
        ClusterRole.COORDINATOR not in assignment.roles
        or assignment.revoked
        or assignment.paused
    ):
        return
    now = time.time()
    if now >= epoch.lease_expires_at or now < epoch.lease_expires_at - 40.0:
        return
    try:
        manager.renew_cluster_lease(
            state,
            coordinator_id=NodeId(state.local_node_id),
            fencing_token=epoch.fencing_token,
            now=now,
        )
    except FencingError:
        return


def reconcile_peer_connections(controller: Any) -> None:
    manager = controller._peer_connections()
    if manager is None or controller._is_closing:
        return
    if _is_local_subcoordinator(controller):
        manager.promote_if_due(controller._cluster_state)
    _renew_local_coordinator_lease(controller, manager)
    queue_cluster_uploads(controller, manager)
    deadline = manager.reconcile()
    controller._schedule_peer_reconciliation(deadline)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_window_nodes.WindowNodeConnectionTests -q`
Expected: PASS (2 new tests green).

- [ ] **Step 5: Run the full suite + static gates**

Run: `python3 -m unittest discover -s tests -q` then `python3 -m compileall -q maintenance tests` and `git diff --check`.
Expected: all OK, zero failures.

- [ ] **Step 6: Commit**

```bash
git add maintenance/ui/window_discovery.py tests/test_window_nodes.py
git commit -m "fix: renew coordinator lease and only promote from the local subcoordinator"
```

---

### Task 2: remove_connection reverts selection when it removes the selected node

**Files:**
- Modify: `maintenance/ui/window_node_actions.py:159-187` (`remove_connection_node`)
- Test: `tests/test_window_nodes.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_remove_connection_on_selected_node_reverts_to_local(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
            start_discovery=False,
        )
        registry = window._node_registry
        registry.select(NodeId("peer-a"))
        window._selected_node_id = NodeId("peer-a")
        window._cluster_state = ClusterState.create_local(local_node_id="local")
        window._save_cluster_state = Mock(return_value=True)
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._rebuild_node_selector = Mock()
        window._nodes_status = Mock()
        window._nodes_error = Mock()
        window._cancel_node_operations = Mock()
        window._cancel_peer_connection = Mock()
        window._sync_selected_context_mirrors = Mock()
        window._render_selected_node = Mock()
        manager = Mock()
        window._peer_connection_manager = manager

        window_node_actions.remove_connection_node(
            window, "peer-a", messagebox_module=Mock(return_value=True)
        )

        self.assertEqual(window._selected_node_id, NodeId(LOCAL_NODE_ID))
        self.assertEqual(registry.selected_id(), NodeId(LOCAL_NODE_ID))
        window._rebuild_node_selector.assert_called_once()
```

Expected: FAIL (`_selected_node_id` still `peer-a`).

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_window_nodes.WindowNodeSwitchingTests.test_remove_connection_on_selected_node_reverts_to_local -q`
Expected: FAIL (assertEqual on `_selected_node_id`).

- [ ] **Step 3: Implement the fix**

Edit `remove_connection_node` (`maintenance/ui/window_node_actions.py`) — replace the tail after the context cleanup:

```python
    controller._refresh_nodes_page()
    controller._refresh_cluster_page()
    controller._rebuild_node_selector()
    if controller.__dict__.get("_selected_node_id") == node and registry is not None:
        local_id = registry.local_id()
        if local_id is not None:
            registry.select(local_id)
    if controller.__dict__.get("_selected_node_id") != registry.selected_id():
        controller.__dict__["_selected_node_id"] = registry.selected_id()
        context = registry.selected_context()
        controller._sync_selected_context_mirrors(context)
        controller._render_selected_node(context)
    controller._nodes_status(f"Removed connection to {node_id}")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest tests.test_window_nodes.WindowNodeSwitchingTests.test_remove_connection_on_selected_node_reverts_to_local -q`
Expected: PASS.

- [ ] **Step 5: Full suite + commit**

Run full suite (`python3 -m unittest discover -s tests -q`), then:

```bash
git add maintenance/ui/window_node_actions.py tests/test_window_nodes.py
git commit -m "fix: revert selection when removing the selected node's connection"
```

---

### Task 3: can_connect_peer rejects fingerprint-less trusted records

**Files:**
- Modify: `maintenance/ui/window_discovery.py:444-451` (`can_connect_peer`)
- Test: `tests/test_window_nodes.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_can_connect_peer_requires_identity_fingerprint(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
            start_discovery=False,
        )
        context = window._node_registry.context(NodeId("peer-a"))
        context.descriptor = replace(context.descriptor, identity_fingerprint=None)
        state = ClusterState(
            trusted_nodes=(
                trusted_node_record(
                    node_id="peer-a",
                    display_name="Peer A",
                    hostname="peer-a",
                    host="192.0.2.10",
                    port=5000,
                    secret="secret",
                    transport_fingerprint="tls-pin",
                ),
            )
        )
        window._cluster_state = state

        self.assertFalse(ui_window_discovery.can_connect_peer(window, context))
```

Expected: FAIL (currently `True`).

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_window_nodes.WindowNodeConnectionTests.test_can_connect_peer_requires_identity_fingerprint -q`
Expected: FAIL.

- [ ] **Step 3: Implement the fix**

Edit `can_connect_peer` in `maintenance/ui/window_discovery.py`:

```python
def can_connect_peer(controller: Any, context: NodeContext) -> bool:
    record = controller._cluster_state.record(context.node_id.value)
    return bool(
        record is not None
        and record.port is not None
        and record.transport_fingerprint
        and record.identity_fingerprint
        and context.descriptor.identity_status is not NodeIdentityStatus.MISMATCH
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest tests.test_window_nodes.WindowNodeConnectionTests.test_can_connect_peer_requires_identity_fingerprint -q`
Expected: PASS.

- [ ] **Step 5: Full suite + commit**

```bash
git add maintenance/ui/window_discovery.py tests/test_window_nodes.py
git commit -m "fix: never attempt to connect a trusted peer without an identity fingerprint"
```

---

### Task 4: Windows GPU probe suppresses the console window

**Files:**
- Modify: `maintenance/external_commands.py:21-77` — add `creationflags` to `run_text_command` and `run_json_command`
- Modify: `maintenance/scanner_support/gpu.py:265-296` — pass `CREATE_NO_WINDOW` on Windows
- Test: `tests/test_external_commands.py`

- [ ] **Step 1: Write the failing tests**

```python
    def test_run_text_command_forwards_creationflags(self) -> None:
        seen: dict[str, Any] = {}

        def fake(command, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(stdout="out", returncode=0)

        stdout, error = run_text_command(
            ["cmd"], runner=fake, creationflags=0x08000000
        )
        self.assertEqual(stdout, "out")
        self.assertIsNone(error)
        self.assertEqual(seen.get("creationflags"), 0x08000000)
```

```python
    def test_run_json_command_forwards_creationflags(self) -> None:
        seen: dict[str, Any] = {}

        def fake(command, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(stdout='{"ok": true}', returncode=0)

        payload, error = run_json_command(
            ["cmd"], runner=fake, creationflags=0x08000000
        )
        self.assertEqual(payload, {"ok": True})
        self.assertIsNone(error)
        self.assertEqual(seen.get("creationflags"), 0x08000000)
```

Expected: FAIL (`TypeError: unexpected keyword argument 'creationflags'`).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_external_commands -q`
Expected: 2 failures with `TypeError`.

- [ ] **Step 3: Implement the fix**

Edit `maintenance/external_commands.py`:

```python
def run_text_command(
    command: list[str],
    *,
    timeout_seconds: float = COMMAND_TIMEOUT_SECONDS,
    runner: CommandRunner | None = None,
    creationflags: int = 0,
) -> tuple[str, str | None]:
    try:
        result = (runner or subprocess.run)(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            creationflags=creationflags,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return "", str(error)
    return result.stdout, None


def run_json_command(
    command: list[str],
    *,
    timeout_seconds: float = COMMAND_TIMEOUT_SECONDS,
    runner: CommandRunner | None = None,
    empty_stdout_fallback: str | None = None,
    creationflags: int = 0,
) -> tuple[Any, str | None]:
    stdout, error = run_text_command(
        command,
        timeout_seconds=timeout_seconds,
        runner=runner,
        creationflags=creationflags,
    )
    ...
```

Edit `maintenance/scanner_support/gpu.py` — add `import os` at the top, then in `_windows_gpu_read`:

```python
        creationflags = (
            getattr(scanner_module.subprocess, "CREATE_NO_WINDOW", 0)
            if os.name == "nt"
            else 0
        )
        controllers, error = run_json_command(
            ["powershell", "-NoProfile", "-Command", command],
            timeout_seconds=scanner_module.SystemScanner.GPU_COMMAND_TIMEOUT_SECONDS,
            runner=scanner_module.subprocess.run,
            empty_stdout_fallback="[]",
            creationflags=creationflags,
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_external_commands -q`
Expected: PASS (existing runner-lambda tests already tolerate kwargs).

- [ ] **Step 5: Full suite + commit**

```bash
git add maintenance/external_commands.py maintenance/scanner_support/gpu.py tests/test_external_commands.py
git commit -m "fix: suppress console window for Windows GPU PowerShell probe"
```

---

### Task 5: Windows-safe permission-test skip

**Files:**
- Modify: `tests/test_storage_conservative.py:132`
- Test: same file

- [ ] **Step 1: Write the failing test state (verify import break on Windows)**

This task has no Linux repro; the break is `os.geteuid` not existing on Windows. On Linux the current decorator is fine, so the change is a guard only.

- [ ] **Step 2: Implement the fix**

At module top of `tests/test_storage_conservative.py` (after existing imports) add:

```python
def _is_effective_root() -> bool:
    geteuid = getattr(os, "geteuid", None)
    return geteuid is not None and geteuid() == 0
```

Replace line 132's decorator:

```python
    @unittest.skipIf(_is_effective_root(), "permission test requires a non-root user")
    @unittest.skipIf(sys.platform == "win32", "permission bits are POSIX-only")
    def test_inaccessible_files_are_never_marked_as_duplicates(self) -> None:
```

Add `import sys` to the imports if not already present.

- [ ] **Step 3: Verify the module imports and the test still runs on Linux**

Run: `python3 -m unittest tests.test_storage_conservative -q`
Expected: PASS (test still executes on Linux; skips only on root or Windows).

- [ ] **Step 4: Commit**

```bash
git add tests/test_storage_conservative.py
git commit -m "test: make permission test import-safe on Windows"
```

---

### Task 6: AppCoordinator run-after-cancel replays the new task

**Files:**
- Modify: `maintenance/components/coordinator.py:436-448` (`AppCoordinator.run`)
- Test: `tests/test_components.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_run_after_cancel_replays_new_task_with_new_callbacks(self) -> None:
        runner = DeferredRunner()
        coordinator = AppCoordinator(runner=runner, deliver=lambda cb: cb())
        results: list[tuple[str, str]] = []

        coordinator.run(
            "key",
            lambda _cancel, _progress: "task-a",
            on_result=lambda _key, value: results.append(("a", value)),
        )
        coordinator.cancel("key")
        coordinator.run(
            "key",
            lambda _cancel, _progress: "task-b",
            on_result=lambda _key, value: results.append(("b", value)),
        )
        runner.run()  # complete the cancelled A worker -> triggers replay
        self.assertEqual(runner.pending, 1)
        runner.run()  # the replay executes B

        self.assertEqual(results, [("b", "task-b")])
```

Expected: FAIL (`results == [("a", "task-a")]` because the replay restarts the stale task A).

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_components.AppCoordinatorRunTests.test_run_after_cancel_replays_new_task_with_new_callbacks -q`
Expected: FAIL (assertEqual mismatch).

- [ ] **Step 3: Implement the fix**

Edit `AppCoordinator.run` in `maintenance/components/coordinator.py` — replace the coalescing branch:

```python
        state = self.state(key)
        if state.in_flight:
            state.rerun_requested = True
            if on_result is not None:
                state.on_result = on_result
            if on_error is not None:
                state.on_error = on_error
            if on_progress is not None:
                state.on_progress = on_progress
            state.on_finished = on_finished
            state.task_factory = task_factory
            return None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest tests.test_components -q`
Expected: PASS (all coordinator tests green).

- [ ] **Step 5: Full suite + commit**

```bash
git add maintenance/components/coordinator.py tests/test_components.py
git commit -m "fix: replay the newest task and callbacks after a cancelled coalesced run"
```

---

## Final Verification

- [ ] Run `python3 -m unittest discover -s tests -q` — expect all OK (~1347+ tests).
- [ ] Run `python3 -m compileall -q maintenance tests` — expect OK.
- [ ] Run `git diff --check` — expect clean.
- [ ] Run `ruff check .`, `ruff format --check .`, `pyright`, `mypy --ignore-missing-imports` (repo hygiene gate).
- [ ] Rebuild the wheel if source changed (`SA_VERSION_BUMP=auto ./install/build.sh`), verify (`./install/verify.sh <version>`), and commit the release.

## Verified Findings (evidence trail)

- **Revoke stuck state (FIXED, Task 0):** a node whose `role_assignments` entry is already `revoked=True` but that is still trusted/listed makes `revoke_node` hit `RoleAuthorizationError("unknown or revoked node")` (`maintenance/components/cluster_roles.py:201-206`) and never reach `revoke_trusted_node`. Reproduced: `worker still in specs: True`, error shown. Cause: `revoke_node` only special-cased `assignment_for(...) is None`.
- **Lease never renewed (Task 1):** `record_heartbeat` (`peer_connection.py:146`) and the `renew_coordinator_lease` client (`remote.py:629`) have **no production callers**; `_initial_epoch` sets `lease_expires_at = now + 120.0` (`cluster.py:107`, `HEARTBEAT_TIMEOUT_SECONDS = 120.0`). `reconcile_peer_connections` calls `manager.promote_if_due(...)` unconditionally (`window_discovery.py:524`), and `promote_subcoordinator` (`cluster_roles.py:280-316`) has no local-node guard, so every node independently promotes the subcoordinator with its own locally generated fencing token → token divergence fencs out the cluster. A healthy coordinator is also failed over after 120 s.
- **remove-connection on selected node (Task 2):** `remove_connection_node` (`window_node_actions.py:159-187`) nulls `context.provider/scheduler/coordinator` but never reverts selection; `selectable_descriptors` then excludes the node (`nodes.py:745-764`, `_is_operational` requires provider+scheduler) while `_selected_node_id` still points at it → next dashboard scan calls `source_provider.dashboard_snapshot` on `None`.
- **Fingerprint-less trusted record stuck (Task 3):** `connect_peer` raises when `record.identity_fingerprint` is `None` (`window_discovery.py:469-471`) but `can_connect_peer` only checks port + transport fingerprint (`window_discovery.py:444-451`), so reconcile keeps attempting → `AUTHENTICATION_FAILED` disables auto-retry → stuck forever.
- **Windows GPU console flash (Task 4):** `_windows_gpu_read` spawns `powershell` (`gpu.py:266-276`) via `run_json_command` → `subprocess.run` with no `creationflags`, so a Windows GUI launch flashes a console every 3 s GPU refresh.
- **Windows test import crash (Task 5):** `tests/test_storage_conservative.py:132` evaluates `os.geteuid()` at import time; `os.geteuid` does not exist on Windows → `AttributeError` breaks `unittest discover`.
- **Coordinator replay stale task (Task 6):** `AppCoordinator.run` on a coalesced trigger returns `None` without updating `state.task_factory`/`on_result`/`on_error` (`coordinator.py:436-448`); after `cancel()` + a new `run()`, `_replay` restarts the OLD task/callbacks.

## Documented findings — NOT fixed in this plan

These are design limitations or low-impact risks; listed here so they are not silently dropped:
- `remove_job` does not propagate `has_active_job` to the worker (worker upload gate reads its own `local_assignment`), so the 20% participation cap only applies if the worker's own copy is updated; enforcing remotely needs REMOTE_MANAGEMENT, which worker grants lack. Design gap.
- `consume_invite` is a ROLE_OPERATION requiring an existing grant + fence, so it cannot be invoked by the unenrolled node it targets. Design gap.
- Manual disconnect is permanent: `PeerConnectionManager.reconnect` has no production caller; "trusted reconnect remains available" is not automatic. Design gap.
- Windows/macOS risks (no crash): external `openssl` binary required to mint TLS certs (unavailable by default on Windows); `os.chmod(0o600)` is a no-op on Windows; Windows trash-size COM not initialized on the worker thread (shows "0 B"); log dir uses `~/.local/state` on all platforms; `text=True` decodes PowerShell output with the ANSI codepage; fixed "Helvetica" font + fixed geometries are not HiDPI-aware.
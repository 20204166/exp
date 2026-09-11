# Remote Role Lifecycle and Temporary Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the Coordinator/Worker revoke pipeline and add explicit, authenticated connection-removal, job-removal, and temporary read-only dashboard controls without weakening trust, authorization, target safety, or failover.

**Architecture:** Extend the existing owners — `cluster_roles.RoleState` gains a backward-compatible active-job flag, `PeerConnectionManager` gains a manual-disconnect gate that suppresses automatic reconnect, the typed authenticated protocol gains `remove_connection`/`remove_job` control operations, and the presentation pages gain coordinator/worker buttons with confirmation dialogs. The worker upload path applies a deterministic 20% participation gate when a job is removed. No new scheduler, coordinator, or RPC is introduced.

**Tech Stack:** Python 3.10+, `dataclasses`, `enum`, `unittest`, existing `NodeRegistry`/`NodeContext`, `PeerConnectionManager`, `RemoteService`, typed remote protocol, Tk pages, Ruff/Pyright/Mypy where installed.

---

## File Map

- Modify `maintenance/components/cluster_roles.py`: `RoleAssignment.has_active_job` flag, `RoleState.remove_job`/`assign_job`.
- Modify `maintenance/cluster.py`: serialize/parse `has_active_job` (default true).
- Modify `maintenance/remote_support/protocol.py`: add `remove_connection`/`remove_job` operations, permissions, and param validation.
- Modify `maintenance/remote.py`: `AuthenticatedNodeProvider.remove_connection`/`remove_job` client methods.
- Modify `maintenance/ui/window_discovery.py`: role handler for the two new ops; 20% upload gate; worker-side connection detach.
- Modify `maintenance/components/peer_connection.py`: `PeerConnectionManager` manual-disconnect gate (`disconnect_manual`, `reconnect`, skip in `reconcile`).
- Modify `maintenance/ui/window_node_actions.py`: coordinator/worker remove-connection action, remove-job action, confirmation dialogs, revoke regression.
- Modify `maintenance/ui/cluster_page.py` and `maintenance/ui/nodes_connections.py`: new callbacks/buttons.
- Modify `maintenance/ui/window_pages.py` and `window.py`: wire new callbacks.
- Modify `maintenance/ui/window_supports/node_specs.py`: surface `has_active_job`/participation in specs.
- Tests: `tests/test_cluster_roles.py`, `tests/test_cluster.py`, `tests/test_cluster_roles_persistence.py`, `tests/test_peer_connection.py`, `tests/test_remote_contract.py`, `tests/test_window_nodes.py`, `tests/test_cluster_page.py`, `tests/test_nodes_connections_page.py`, `tests/test_remote_compatibility.py`.

---

## Task 1: RoleState Job-Participation State (Pure)

**Files:**
- Modify: `maintenance/components/cluster_roles.py`
- Test: `tests/test_cluster_roles.py`

- [ ] **Step 1: Write the failing tests.**

Add to `tests/test_cluster_roles.py`:

```python
    def test_remove_job_requires_active_coordinator(self) -> None:
        with self.assertRaises(RoleAuthorizationError):
            RoleState(
                assignments=(self.worker,)
            ).remove_job(
                actor=self.worker,
                target=NodeId("worker"),
            )

    def test_remove_job_clears_active_assignment(self) -> None:
        state = RoleState(assignments=(self.coordinator, self.worker))
        updated = state.remove_job(actor=self.coordinator, target=NodeId("worker"))
        assignment = updated.assignment_for(NodeId("worker"))
        self.assertIsNotNone(assignment)
        assert assignment is not None
        self.assertFalse(assignment.has_active_job)

    def test_remove_job_revoked_target_is_rejected(self) -> None:
        revoked = RoleAssignment(
            frozenset({ClusterRole.WORKER}),
            NodeId("worker"),
            revoked=True,
        )
        state = RoleState(assignments=(self.coordinator, revoked))
        with self.assertRaises(RoleAuthorizationError):
            state.remove_job(actor=self.coordinator, target=NodeId("worker"))

    def test_assign_job_restores_participation(self) -> None:
        idle = RoleAssignment(
            frozenset({ClusterRole.WORKER}),
            NodeId("worker"),
            has_active_job=False,
        )
        state = RoleState(assignments=(self.coordinator, idle))
        updated = state.assign_job(actor=self.coordinator, target=NodeId("worker"))
        assignment = updated.assignment_for(NodeId("worker"))
        self.assertIsNotNone(assignment)
        assert assignment is not None
        self.assertTrue(assignment.has_active_job)

    def test_default_assignment_has_active_job(self) -> None:
        self.assertTrue(self.worker.has_active_job)
```

- [ ] **Step 2: Run the tests and verify the attribute failure.**

Run: `python3 -m unittest tests.test_cluster_roles -v`
Expected: FAIL with `AttributeError: 'RoleAssignment' object has no attribute 'has_active_job'`.

- [ ] **Step 3: Add the field and the two methods.**

In `maintenance/components/cluster_roles.py`:

```python
@dataclass(frozen=True, slots=True)
class RoleAssignment:
    roles: frozenset[ClusterRole]
    node_id: NodeId | None = None
    paused: bool = False
    revoked: bool = False
    has_active_job: bool = True
```

Add to `RoleState` after `revoke`:

```python
    def remove_job(self, *, actor: RoleAssignment, target: NodeId) -> RoleState:
        self._assert_control(actor)
        current = self.assignment_for(target)
        if current is None or current.revoked:
            raise RoleAuthorizationError("unknown or revoked node")
        if ClusterRole.WORKER not in current.roles:
            raise RoleAuthorizationError("target has no worker role")
        return self._replace_assignment(replace(current, has_active_job=False))

    def assign_job(self, *, actor: RoleAssignment, target: NodeId) -> RoleState:
        self._assert_control(actor)
        current = self.assignment_for(target)
        if current is None or current.revoked:
            raise RoleAuthorizationError("unknown or revoked node")
        if ClusterRole.WORKER not in current.roles:
            raise RoleAuthorizationError("target has no worker role")
        return self._replace_assignment(replace(current, has_active_job=True))
```

Add `remove_job` and `assign_job` to `__all__`? They are methods; `__all__` lists module-level names only, so no change.

- [ ] **Step 4: Run the tests.**

Run: `python3 -m unittest tests.test_cluster_roles -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add maintenance/components/cluster_roles.py tests/test_cluster_roles.py
git commit -m "feat: add active-job state to role assignments"
```

## Task 2: Persist the Job State

**Files:**
- Modify: `maintenance/cluster.py`
- Test: `tests/test_cluster.py`, `tests/test_cluster_roles_persistence.py`

- [ ] **Step 1: Write the failing persistence tests.**

In `tests/test_cluster_roles_persistence.py`:

```python
    def test_has_active_job_round_trip(self) -> None:
        store = ClusterStore(tmp_path() / "cluster.json")
        state = ClusterState.create_local()
        assignment = state.local_assignment
        updated = replace(state, role_assignments=(
            replace(assignment, has_active_job=False),
        ))
        store.save(updated)
        loaded = store.load()
        self.assertFalse(loaded.local_assignment.has_active_job)

    def test_has_active_job_defaults_true_for_old_documents(self) -> None:
        store = ClusterStore(tmp_path() / "cluster.json")
        state = ClusterState.create_local()
        assignment = state.local_assignment
        old = replace(state, role_assignments=(
            replace(assignment, has_active_job=False),
        ))
        store.save(old)
        text = (tmp_path() / "cluster.json").read_text()
        (tmp_path() / "cluster.json").write_text(text.replace(
            '"has_active_job": false', '"paused": false'
        ))
        loaded = store.load()
        self.assertTrue(loaded.local_assignment.has_active_job)
```

Add the import: `from tempfile import TemporaryDirectory` and a helper `tmp_path()` returning a `Path`.

- [ ] **Step 2: Run and verify failure.**

Run: `python3 -m unittest tests.test_cluster_roles_persistence -v`
Expected: FAIL (serializer drops or parser defaults to True, so the first test fails).

- [ ] **Step 3: Serialize and parse the flag.**

In `maintenance/cluster.py` `_serialize`, inside the `role_assignments` mapping:

```python
                    "has_active_job": item.has_active_job,
```

In `_parse_roles`, after `revoked=...`:

```python
                    has_active_job=bool(item.get("has_active_job", True)),
```

- [ ] **Step 4: Run the persistence and cluster tests.**

Run: `python3 -m unittest tests.test_cluster tests.test_cluster_roles_persistence -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add maintenance/cluster.py tests/test_cluster_roles_persistence.py tests/test_cluster.py
git commit -m "feat: persist active-job participation state"
```

## Task 3: Regress the Revoke Pipeline Cleanup

**Files:**
- Modify: `maintenance/ui/window_node_actions.py` (verify and harden)
- Test: `tests/test_window_nodes.py`

- [ ] **Step 1: Write failing regression tests for full revoke cleanup.**

Add to `tests/test_window_nodes.py`:

```python
    def test_revoke_removes_trust_grant_and_connection_state(self) -> None:
        window = self._make_window_with_trusted_peer("peer-a")
        node = NodeId("peer-a")
        previous = window._node_registry.context(node)
        previous.provider = Mock()
        window._revoke_node("peer-a")
        self.assertNotIn(node, {c.node_id for c in window._node_registry.contexts()})
        self.assertIsNone(window._cluster_state.record("peer-a"))
        self.assertEqual(
            window._cluster_state.grant("peer-a"), None
        )
        window._refresh_cluster_page.assert_called()
        self.assertEqual(window._nodes_status.call_args[0][0],
                         "Node removed from trusted machines")

    def test_revoke_local_node_is_rejected(self) -> None:
        window = self._make_window()
        window._revoke_node(window._cluster_state.local_node_id)
        self.assertTrue(window._nodes_error.called)
```

Reuse the existing `_make_window`/`_make_window_with_trusted_peer` helpers in this module (they already build a controller with fake registry/state/store). Read the existing helper signatures first and match them.

- [ ] **Step 2: Run and verify failure.**

Run: `python3 -m unittest tests.test_window_nodes -v`
Expected: the cleanup assertion fails because revoke currently leaves a provider or context behind in the fixture shape.

- [ ] **Step 3: Harden `revoke_node`.**

`revoke_node` in `maintenance/ui/window_node_actions.py` already calls `revoke_trusted_node` after the role transition. Verify `revoke_trusted_node` removes the trusted record, the peer grant, invalidates the provider, cancels operations/connections, and nulls the context provider/manager fields (it does today). Add the missing remote control: after saving the revoked role state, send the authenticated `revoke_worker` control to the target so the worker stops uploading. Add a best-effort send using `controller._coordinator.run` keyed by `node_operation_key(node, "revoke_worker")`, guarded by the node having an active provider.

- [ ] **Step 4: Run the window/node regression set.**

Run: `python3 -m unittest tests.test_window_nodes tests.test_nodes -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add maintenance/ui/window_node_actions.py tests/test_window_nodes.py
git commit -m "fix: revoke performs full trust, grant, and connection cleanup"
```

## Task 4: Manual-Disconnect Gate in PeerConnectionManager

**Files:**
- Modify: `maintenance/components/peer_connection.py`
- Test: `tests/test_peer_connection.py`

- [ ] **Step 1: Write the failing manager tests.**

```python
    def test_manual_disconnect_suppresses_reconcile(self) -> None:
        registry, coordinator = self._registry_and_coordinator()
        manager = PeerConnectionManager(
            registry=registry, coordinator=coordinator, connect=lambda *_: None
        )
        node = NodeId("peer-a")
        manager.disconnect_manual(node)
        self.assertIsNone(manager.reconcile(now=0.0))

    def test_reconnect_restores_automatic_reconcile(self) -> None:
        registry, coordinator = self._registry_and_coordinator()
        manager = PeerConnectionManager(
            registry=registry, coordinator=coordinator, connect=lambda *_: None
        )
        node = NodeId("peer-a")
        manager.disconnect_manual(node)
        manager.reconnect(node)
        self.assertFalse(manager.is_manual_disconnected(node))

    def test_reconcile_skips_manual_disconnected_node(self) -> None:
        registry, coordinator = self._registry_and_coordinator()
        started: list[NodeId] = []
        manager = PeerConnectionManager(
            registry=registry,
            coordinator=coordinator,
            connect=lambda _ctx, _c, _p: None,
        )
        node = NodeId("peer-a")
        manager.disconnect_manual(node)
        deadline = manager.reconcile(now=0.0)
        self.assertEqual(started, [])
        self.assertIsNone(deadline)
```

Add a helper `_registry_and_coordinator` that builds a `NodeRegistry` with one trusted offline peer context and a recording `coordinator` whose `in_flight` returns False. Match existing fixtures in `tests/test_peer_connection.py`.

- [ ] **Step 2: Run and verify failure.**

Run: `python3 -m unittest tests.test_peer_connection -v`
Expected: FAIL with `AttributeError: 'PeerConnectionManager' object has no attribute 'disconnect_manual'`.

- [ ] **Step 3: Implement the gate.**

In `maintenance/components/peer_connection.py` `__init__`, add `self._manual_disconnected: set[NodeId] = set()`.

Add methods:

```python
    def disconnect_manual(self, node_id: NodeId) -> None:
        """Detach a relationship without revoking trust; suppress reconnect."""
        self._manual_disconnected.add(node_id)
        self.cancel(node_id)

    def reconnect(self, node_id: NodeId) -> None:
        self._manual_disconnected.discard(node_id)

    def is_manual_disconnected(self, node_id: NodeId) -> bool:
        return node_id in self._manual_disconnected
```

In `reconcile`, skip manual-disconnected contexts:

```python
            if node_id in self._manual_disconnected:
                continue
```

Insert this check right after the `is_trusted_descriptor` guard.

- [ ] **Step 4: Run the manager and connection tests.**

Run: `python3 -m unittest tests.test_peer_connection -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add maintenance/components/peer_connection.py tests/test_peer_connection.py
git commit -m "feat: gate automatic reconnect behind manual disconnect"
```

## Task 5: Add remove_connection / remove_job Protocol Operations

**Files:**
- Modify: `maintenance/remote_support/protocol.py`
- Modify: `maintenance/remote.py`
- Test: `tests/test_remote_contract.py`, `tests/test_remote_compatibility.py`

- [ ] **Step 1: Write failing protocol tests.**

In `tests/test_remote_compatibility.py`, add:

```python
    def test_remove_connection_is_a_typed_fenced_operation(self) -> None:
        self.assertIn("remove_connection", OP_REQUIRED_CAPABILITY)
        validate_operation_params(
            "remove_connection",
            {
                "target_node_id": "peer-a",
                "cluster_id": "c",
                "epoch": 1,
                "fencing_token": "t",
            },
        )

    def test_remove_connection_rejects_missing_target(self) -> None:
        with self.assertRaises(RemoteProtocolError):
            validate_operation_params(
                "remove_connection",
                {"cluster_id": "c", "epoch": 1, "fencing_token": "t"},
            )

    def test_remove_job_requires_fencing_fields(self) -> None:
        with self.assertRaises(RemoteProtocolError):
            validate_operation_params("remove_job", {})
```

Import `OP_REQUIRED_CAPABILITY` in the test.

- [ ] **Step 2: Run and verify failure.**

Run: `python3 -m unittest tests.test_remote_compatibility -v`
Expected: FAIL with `KeyError: 'remove_connection'`.

- [ ] **Step 3: Register the operations in `protocol.py`.**

Add to `OP_REQUIRED_CAPABILITY` and `OP_REQUIRED_PERMISSION` (as `NodeCapability.REMOTE_MANAGEMENT` / `NodePermission.REMOTE_MANAGEMENT`):

```python
    "remove_connection": NodeCapability.REMOTE_MANAGEMENT,
    "remove_job": NodeCapability.REMOTE_MANAGEMENT,
```

Add both to `ROLE_OPERATIONS` (they require fencing) and to the fencing-params branch of `validate_operation_params`. In that branch, after the `pause_worker/resume_worker/revoke_worker` check, add:

```python
        if op in {"remove_connection", "remove_job"}:
            if not isinstance(params.get("target_node_id"), str):
                raise RemoteProtocolError("role target is invalid")
            return
```

- [ ] **Step 4: Add the client methods in `remote.py`.**

After `resume_worker`:

```python
    def remove_connection(
        self, target_node_id: str, *, cluster_id: str, epoch: int, fencing_token: str
    ) -> dict[str, Any]:
        return self._role_request(
            "remove_connection",
            {
                "target_node_id": target_node_id,
                "cluster_id": cluster_id,
                "epoch": epoch,
                "fencing_token": fencing_token,
            },
        )

    def remove_job(
        self, target_node_id: str, *, cluster_id: str, epoch: int, fencing_token: str
    ) -> dict[str, Any]:
        return self._role_request(
            "remove_job",
            {
                "target_node_id": target_node_id,
                "cluster_id": cluster_id,
                "epoch": epoch,
                "fencing_token": fencing_token,
            },
        )
```

- [ ] **Step 5: Run the protocol and remote tests.**

Run: `python3 -m unittest tests.test_remote_contract tests.test_remote_compatibility tests.test_cluster_adversarial -v`
Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add maintenance/remote_support/protocol.py maintenance/remote.py tests/test_remote_compatibility.py tests/test_remote_contract.py
git commit -m "feat: add authenticated remove connection and job operations"
```

## Task 6: Handle the New Operations on the Target Side

**Files:**
- Modify: `maintenance/ui/window_discovery.py`
- Test: `tests/test_window_nodes.py`

- [ ] **Step 1: Write failing handler tests.**

In `tests/test_window_nodes.py`, add tests that build the controller used by `handle_role_request` (match the existing `test_role_*` fixtures) and assert:

- a Worker cannot call `remove_connection`/`remove_job` (authorization failure);
- an active Coordinator can call `remove_job` and the target assignment's `has_active_job` becomes False;
- `remove_connection` marks the target's connection manually disconnected through `PeerConnectionManager` when a manager exists.

- [ ] **Step 2: Run and verify failure.**

Run: `python3 -m unittest tests.test_window_nodes -v`
Expected: FAIL with `RemoteAuthError: unknown role operation`.

- [ ] **Step 3: Extend `handle_role_request` in `window_discovery.py`.**

Add a branch before the final `else` that raises `unknown role operation`:

```python
    elif request.op == "remove_connection":
        if request.params.get("target_node_id") not in (actor_id.value,):
            raise RemoteAuthError("remove_connection is limited to the caller relationship")
        manager = controller.__dict__.get("_peer_connection_manager")
        if manager is None:
            manager = peer_connections(controller)
        if manager is not None:
            manager.disconnect_manual(actor_id)
        return {"ok": True}
    elif request.op == "remove_job":
        updated = role_state.remove_job(
            actor=actor, target=NodeId(request.params["target_node_id"])
        )
```

The `remove_job` branch must persist exactly like `revoke_worker` (the shared persistence lines below the branch chain already run after the if/elif chain):

```python
    if not controller._save_cluster_state(replace(state, role_assignments=updated.assignments)):
        raise RemoteAuthError("role state could not be saved")
    return {"ok": True}
```

`remove_connection` returns before the shared persistence block because it changes no role state; it only detaches the caller's local relationship.

- [ ] **Step 4: Run the window/discovery regression set.**

Run: `python3 -m unittest tests.test_window_nodes tests.test_discovery_end_to_end -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add maintenance/ui/window_discovery.py tests/test_window_nodes.py
git commit -m "feat: apply remove connection and job on the target"
```

## Task 7: Coordinator and Worker Remove Actions with Confirmation

**Files:**
- Modify: `maintenance/ui/window_node_actions.py`
- Modify: `maintenance/ui/cluster_page.py`
- Modify: `maintenance/ui/nodes_connections.py`
- Modify: `maintenance/ui/window_pages.py`
- Modify: `window.py`
- Modify: `maintenance/ui/window_supports/node_specs.py`
- Test: `tests/test_window_nodes.py`, `tests/test_cluster_page.py`, `tests/test_nodes_connections_page.py`

- [ ] **Step 1: Write failing page-callback tests.**

In `tests/test_cluster_page.py`, add callbacks `on_remove_connection`/`on_remove_job` to `ClusterPageCallbacks` and assert a coordinator-visible Worker row renders the buttons and emits the node id. In `tests/test_nodes_connections_page.py`, assert the Worker view renders `Remove connection` (not Revoke/Remove job) for the coordinator relationship.

- [ ] **Step 2: Run and verify failure.**

Run: `python3 -m unittest tests.test_cluster_page tests.test_nodes_connections_page -v`
Expected: FAIL (`ClusterPageCallbacks` has no `on_remove_connection`).

- [ ] **Step 3: Add callbacks and buttons.**

In `maintenance/ui/cluster_page.py`, add to `ClusterPageCallbacks`:

```python
    on_remove_connection: Callable[[str], None] | None = None
    on_remove_job: Callable[[str], None] | None = None
```

Add fields to `ClusterNodeSpec`:

```python
    has_active_job: bool = True
```

Render a participation suffix in the meta line when the node is a non-local Worker (`· 20% participation` when `not has_active_job`). Add two buttons beside Revoke/Pause:

```python
        if spec.role_editable and not spec.is_local and self.callbacks.on_remove_connection is not None:
            remove_connection = self.button_cls(
                row,
                text="Remove connection",
                command=lambda: self.callbacks.on_remove_connection(spec.node_id),
                style=ui_styles.STYLE_NEUTRAL_BUTTON,
            )
            remove_connection.pack(side="right", padx=(0, 8))
        if spec.role_editable and not spec.is_local and self.callbacks.on_remove_job is not None:
            remove_job = self.button_cls(
                row,
                text="Remove job",
                command=lambda: self.callbacks.on_remove_job(spec.node_id),
                style=ui_styles.STYLE_NEUTRAL_BUTTON,
            )
            remove_job.pack(side="right", padx=(0, 8))
```

In `maintenance/ui/nodes_connections.py`, add `on_remove_connection` to `NodesConnectionsCallbacks` and render `Remove connection` on the trusted coordinator row for a worker view. Match the existing trusted-row button layout.

- [ ] **Step 4: Wire the callbacks.**

In `maintenance/ui/window_pages.py`, pass `on_remove_connection=controller._remove_connection_node`, `on_remove_job=controller._remove_job_node` to both the cluster page and nodes page callbacks.

In `window.py`, add:

```python
    def _remove_connection_node(self, node_id: str) -> None:
        ui_node_actions.remove_connection_node(self, node_id)

    def _remove_job_node(self, node_id: str) -> None:
        ui_node_actions.remove_job_node(self, node_id)
```

- [ ] **Step 5: Implement the action functions with confirmation.**

In `maintenance/ui/window_node_actions.py`:

```python
def remove_connection_node(
    controller: Any, node_id: str, *, messagebox_module: Any = messagebox
) -> None:
    if not messagebox_module.askyesno(
        "Remove connection",
        "The connection will close, but trusted reconnect remains available.",
        parent=controller.master,
    ):
        return
    node = NodeId(node_id)
    manager = controller._peer_connections()
    if manager is not None:
        manager.disconnect_manual(node)
    registry = controller.__dict__.get("_node_registry")
    if registry is not None:
        try:
            context = registry.context(node)
        except KeyError:
            context = None
        if context is not None:
            controller._cancel_node_operations(context)
            controller._cancel_peer_connection(context)
            context.provider = None
            context.process_manager = None
            context.scheduler = None
            context.coordinator = None
    controller._refresh_nodes_page()
    controller._refresh_cluster_page()
    controller._nodes_status(f"Removed connection to {node_id}")


def remove_job_node(controller: Any, node_id: str, *, messagebox_module: Any = messagebox) -> None:
    if not messagebox_module.askyesno(
        "Remove job",
        "This removes the active assignment and reduces normal collection to 20%.",
        parent=controller.master,
    ):
        return
    try:
        _save_role_state(
            controller,
            _role_state(controller).remove_job(
                actor=controller._cluster_state.local_assignment,
                target=NodeId(node_id),
            ),
        )
        controller._nodes_status(f"Removed job for {node_id}")
    except (KeyError, TypeError, ValueError, RoleAuthorizationError) as error:
        controller._nodes_error(str(error))
```

Update `revoke_node` to add the confirmation dialog before mutating (matching the spec). Keep `controller._peer_connections()` working by matching the existing accessor used elsewhere (e.g., `controller._peer_connections()`).

- [ ] **Step 6: Update `node_specs.py` to surface participation.**

In `trusted_node_specs`, set `has_active_job=assignment.has_active_job if assignment is not None else True` on `TrustedNodeSpec`. Add the same field to the spec dataclass with a default of `True`. In `cluster_node_specs`, pass through `has_active_job` for non-local rows by looking up the assignment from a supplied `cluster_state` argument (add an optional `cluster_state` parameter).

- [ ] **Step 7: Run the UI regression set.**

Run: `python3 -m unittest tests.test_cluster_page tests.test_nodes_connections_page tests.test_window_nodes tests.test_dashboard_ui -v`
Expected: PASS.

- [ ] **Step 8: Commit.**

```bash
git add maintenance/ui/window_node_actions.py maintenance/ui/cluster_page.py maintenance/ui/nodes_connections.py maintenance/ui/window_pages.py maintenance/ui/window_supports/node_specs.py window.py tests/test_cluster_page.py tests/test_nodes_connections_page.py tests/test_window_nodes.py
git commit -m "feat: add confirmed remove connection and job controls"
```

## Task 8: 20% Participation Upload Gate

**Files:**
- Modify: `maintenance/ui/window_discovery.py`
- Test: `tests/test_discovery_end_to_end.py`

- [ ] **Step 1: Write the failing gate test.**

```python
    def test_worker_without_job_uploads_at_20_percent(self) -> None:
        # Build a controller whose local assignment has_active_job=False and a
        # fake coordinator context provider recording uploads. Call the pure
        # gate helper 10 times with an incrementing sequence and assert exactly
        # 2 uploads are queued.
```

- [ ] **Step 2: Run and verify failure.**

Run: `python3 -m unittest tests.test_discovery_end_to_end -v`
Expected: FAIL (no gate helper exists).

- [ ] **Step 3: Add the gate.**

Add a module constant and helper in `maintenance/ui/window_discovery.py`:

```python
JOB_UPLOAD_DIVISOR = 5


def should_upload_job(sequence: int, has_active_job: bool) -> bool:
    """Deterministic 20% participation: idle workers upload 1 in 5 ticks."""
    if has_active_job:
        return True
    return sequence % JOB_UPLOAD_DIVISOR == 0
```

In `queue_cluster_uploads`, before queueing the worker snapshot, compute `has_active_job = "has_active_job" in {} or state.local_assignment.has_active_job` from `state.local_assignment`, and skip the worker upload when `not should_upload_job(sequence, has_active_job)`. Keep the standby batch upload unchanged.

- [ ] **Step 4: Run the discovery regression set.**

Run: `python3 -m unittest tests.test_discovery_end_to_end tests.test_window_nodes -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add maintenance/ui/window_discovery.py tests/test_discovery_end_to_end.py
git commit -m "feat: gate idle worker uploads to 20 percent participation"
```

## Task 9: Temporary Authenticated Dashboard Regression

**Files:**
- Test: `tests/test_window_nodes.py`

- [ ] **Step 1: Write the temporary-view tests.**

```python
    def test_open_remote_dashboard_creates_no_role_assignment(self) -> None:
        # Opening a trusted remote node read-only must not add a role
        # assignment, peer grant, or persisted trusted record beyond the
        # existing pairing, and must not queue a worker upload.
```

- [ ] **Step 2: Run and verify it captures current behavior.**

Run: `python3 -m unittest tests.test_window_nodes -v`
Expected: the test passes or exposes a violation. If it passes, the temporary-dashboard guarantee is already behavior; document it. If it fails, fix `open_cluster_node` so opening a node never enrolls it into the local cluster.

- [ ] **Step 3: Add a coordinator "Share dashboard" affordance.**

Add a `Share dashboard` button on the local coordinator row in `cluster_page.py` that calls `on_share_dashboard` → `window._show_dashboard_page()`. This is the read-only, no-collection view of the local dashboard. Wire the callback with default `None` so the button only renders when the controller provides it.

- [ ] **Step 4: Run the full UI regression set.**

Run: `python3 -m unittest tests.test_window_nodes tests.test_cluster_page tests.test_dashboard_ui -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add maintenance/ui/cluster_page.py maintenance/ui/window_pages.py window.py tests/test_window_nodes.py tests/test_cluster_page.py
git commit -m "feat: add read-only temporary dashboard sharing"
```

## Task 10: Full Validation and Release Handoff

**Files:**
- No new application files.

- [ ] **Step 1: Run the focused regression groups.**

Run: `python3 -m unittest tests.test_cluster_roles tests.test_cluster tests.test_cluster_roles_persistence tests.test_peer_connection tests.test_remote_contract tests.test_remote_compatibility tests.test_cluster_adversarial tests.test_window_nodes tests.test_cluster_page tests.test_nodes_connections_page tests.test_discovery_end_to_end -v`
Expected: PASS.

- [ ] **Step 2: Run the full repository test suite.**

Run: `python3 -m unittest discover -s tests -q`
Expected: all pass.

- [ ] **Step 3: Run hygiene checks.**

Run: `python3 -m compileall -q maintenance tests`, `git diff --check`, and `ruff check .`, `ruff format --check .`, `pyright`, `mypy --ignore-missing-imports` where installed. Report any missing tool explicitly.

- [ ] **Step 4: Build and verify the wheel.**

Run: `SA_VERSION_BUMP=patch ./install/build.sh` then `./install/verify.sh <new-version>`. Confirm `maintenance/remote_support/` members are present.

- [ ] **Step 5: Final commit and push when the user requests it.**

Run: `git status --short`, `git log --oneline -10`, then commit any remaining changes with the repository's release convention and push `main` when the user asks.

---

## Self-Review Results

- **Spec coverage:** Task 1-2 implement the 20% active-job state; Task 3 fixes the revoke pipeline; Task 4 implements manual disconnect; Tasks 5-6 add and apply the typed control operations; Task 7 adds coordinator/worker buttons and confirmations; Task 8 gates idle uploads to 20%; Task 9 covers temporary read-only dashboard access with no collection or membership; Task 10 validates the whole change. Confirmation text, worker-only remove connection, coordinator-only revoke/remove-job, and 20% participation are all covered.
- **Placeholder scan:** No TBD/TODO steps; every code step contains concrete code or exact match instructions to existing fixtures.
- **Type consistency:** `has_active_job`, `remove_job`, `assign_job`, `disconnect_manual`, `reconnect`, `is_manual_disconnected`, `remove_connection`, `should_upload_job`, `on_remove_connection`, and `on_remove_job` are defined once and used consistently.
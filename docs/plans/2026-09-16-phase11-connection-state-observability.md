# Phase 11: Connection-State Observability + Safe Manual Host Pairing

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the backend's 6-state connection model to the UI, and replace the broken fake-secret manual-host feature with clean removal (Option B).

**Architecture:** `TrustedNodeSpec` gains three new fields (`connection_status`, `manual_disconnected`, `retry_automatic`) projected from `NodeContext.connection` and `PeerConnectionManager._manual_disconnected`. The manual-host add flow is removed entirely because `add_manual_host()` fabricates a local trust record without the target's participation; existing manual-host records are preserved for display and removal.

**Tech Stack:** Python 3.12, Tkinter, `maintenance.nodes.NodeConnectionStatus`, `maintenance.components.peer_connection.PeerConnectionManager`, `maintenance.ui.nodes_connections`, `maintenance.ui.window_supports.node_specs`, `maintenance.ui.window_page_data`

---

## Audit findings (read before implementing)

| Backend state | Cause | Auto-retry? | Current UI text | Required UI text |
|---|---|---|---|---|
| `UNKNOWN` | not yet connected | yes | "Unknown" | "Unknown" |
| `CONNECTING` | attempt in flight | n/a | collapses to Unknown | "Connecting…" |
| `ONLINE` | authenticated hello succeeded | n/a | "Online" | "Online" |
| `OFFLINE` + retry=True | network failure, will retry | yes | "Offline" | "Offline · retrying" |
| `OFFLINE` + retry=False | auth-class failure stopped retry | no | "Offline" | "Offline" |
| `AUTHENTICATION_FAILED` | `RemoteAuthError` / bad secret | no | "Offline" (WRONG) | "Auth failed" |
| `IDENTITY_CHANGED` | TLS fingerprint mismatch | no | partially via identity_status mismatch | "Identity changed" |
| manual_disconnected=True | user ran Remove Connection | no | "Offline" (WRONG) | "Disconnected" |

**Manual host finding (Option B chosen):**  
`add_manual_host()` (`connections.py:357`) generates a random HMAC secret locally, writes a `TrustedNodeRecord` locally, and never sends the secret to the target. `hello()` always fails because the target has no matching `PeerGrantRecord`. No real pairing ceremony occurs. The feature is removed.

---

## File map

| File | Change |
|---|---|
| `maintenance/ui/node_presentation.py` | add connection labels/colors + `connection_status_label()` |
| `maintenance/ui/nodes_connections.py` | `TrustedNodeSpec` new fields, `_TRUSTED_STRUCTURAL`, `_trusted_meta_text/_color`, remove add-form + `on_add_manual_host` callback |
| `maintenance/ui/window_supports/node_specs.py` | project `connection_status`, `manual_disconnected`, `retry_automatic` |
| `maintenance/ui/window_page_data.py` | pass `disconnected_ids` from peer_manager |
| `maintenance/ui/connection_dialog.py` | make `on_add` optional |
| `maintenance/ui/window_node_actions_impl/connections.py` | delete `add_manual_host()` |
| `maintenance/ui/window_node_actions.py` | remove `add_manual_host` routing |
| `maintenance/ui/window_pages.py` | remove `on_add_manual_host` callback |
| `window.py` | remove `_add_manual_host`, update `_open_connection_dialog` |
| `tests/test_nodes_connections_page.py` | remove add-host tests, add connection-state tests |
| `tests/window_node_cases/selector.py` | remove `_add_manual_host` tests, update routing test |
| `tests/window_node_cases/discovery_pairing.py` | remove `_add_manual_host` call |
| `tests/test_node_toplevel_dialogs.py` | remove `on_add_manual_host` from callback dict |
| `docs/REMOTE_CLUSTER_TRUE_FLOW.md` | add §64 connection-state section |

---

## Task 1: Add connection-state labels to node_presentation.py

**Files:**
- Modify: `maintenance/ui/node_presentation.py`

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_nodes_connections_page.py  (add new class at bottom)
class NodePresentationConnectionTests(unittest.TestCase):
    def test_connecting_label(self) -> None:
        from maintenance.ui.node_presentation import connection_status_label
        self.assertEqual(connection_status_label("connecting"), "Connecting…")

    def test_auth_failed_label(self) -> None:
        from maintenance.ui.node_presentation import connection_status_label
        self.assertEqual(connection_status_label("authentication_failed"), "Auth failed")

    def test_identity_changed_label(self) -> None:
        from maintenance.ui.node_presentation import connection_status_label
        self.assertEqual(connection_status_label("identity_changed"), "Identity changed")

    def test_offline_retrying(self) -> None:
        from maintenance.ui.node_presentation import connection_status_label
        self.assertEqual(
            connection_status_label("offline", retry_automatic=True), "Offline · retrying"
        )

    def test_offline_not_retrying(self) -> None:
        from maintenance.ui.node_presentation import connection_status_label
        self.assertEqual(
            connection_status_label("offline", retry_automatic=False), "Offline"
        )

    def test_manual_disconnected(self) -> None:
        from maintenance.ui.node_presentation import connection_status_label
        self.assertEqual(
            connection_status_label("offline", manual_disconnected=True), "Disconnected"
        )

    def test_online_label(self) -> None:
        from maintenance.ui.node_presentation import connection_status_label
        self.assertEqual(connection_status_label("online"), "Online")

    def test_auth_failed_color(self) -> None:
        from maintenance.ui.node_presentation import connection_status_color_role
        self.assertEqual(connection_status_color_role("authentication_failed"), "danger")

    def test_identity_changed_color(self) -> None:
        from maintenance.ui.node_presentation import connection_status_color_role
        self.assertEqual(connection_status_color_role("identity_changed"), "danger")

    def test_connecting_color(self) -> None:
        from maintenance.ui.node_presentation import connection_status_color_role
        self.assertEqual(connection_status_color_role("connecting"), "secondary")

    def test_online_color(self) -> None:
        from maintenance.ui.node_presentation import connection_status_color_role
        self.assertEqual(connection_status_color_role("online"), "success")

    def test_manual_disconnected_color(self) -> None:
        from maintenance.ui.node_presentation import connection_status_color_role
        self.assertEqual(
            connection_status_color_role("offline", manual_disconnected=True), "secondary"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_nodes_connections_page.py::NodePresentationConnectionTests -x -q`  
Expected: `ImportError: cannot import name 'connection_status_label'`

- [ ] **Step 3: Implement in node_presentation.py**

Replace the entire file with the following (read it first to confirm exact content):

Add after `_STATUS_COLORS` dict (before `def status_label`):

```python
_CONNECTION_STATUS_LABELS = {
    "unknown": "Unknown",
    "connecting": "Connecting…",
    "online": "Online",
    "offline": "Offline",
    "authentication_failed": "Auth failed",
    "identity_changed": "Identity changed",
}

_CONNECTION_STATUS_COLORS = {
    "online": "success",
    "connecting": "secondary",
    "unknown": "secondary",
    "offline": "warning",
    "authentication_failed": "danger",
    "identity_changed": "danger",
}


def connection_status_label(
    value: str,
    *,
    manual_disconnected: bool = False,
    retry_automatic: bool = True,
) -> str:
    """Return the user-facing label for a NodeConnectionStatus value."""

    if manual_disconnected:
        return "Disconnected"
    normalized = value.strip().lower()
    if normalized == "offline" and retry_automatic:
        return "Offline · retrying"
    return _CONNECTION_STATUS_LABELS.get(normalized, normalized.replace("_", " ").title())


def connection_status_color_role(
    value: str,
    *,
    manual_disconnected: bool = False,
) -> str:
    """Return the semantic colour role for a NodeConnectionStatus value."""

    if manual_disconnected:
        return "secondary"
    return _CONNECTION_STATUS_COLORS.get(value.strip().lower(), "secondary")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_nodes_connections_page.py::NodePresentationConnectionTests -x -q`  
Expected: `12 passed`

- [ ] **Step 5: Commit**

```bash
git add maintenance/ui/node_presentation.py tests/test_nodes_connections_page.py
git commit -m "feat: add connection_status_label/color helpers to node_presentation"
```

---

## Task 2: Add connection_status fields to TrustedNodeSpec

**Files:**
- Modify: `maintenance/ui/nodes_connections.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_nodes_connections_page.py` class `NodePresentationConnectionTests`:

```python
    def test_trusted_spec_defaults(self) -> None:
        spec = TrustedNodeSpec(
            "n1", "Node", "host", None, "online", "host", 5000, True
        )
        self.assertEqual(spec.connection_status, "unknown")
        self.assertFalse(spec.manual_disconnected)
        self.assertTrue(spec.retry_automatic)

    def test_trusted_spec_explicit_connection_status(self) -> None:
        spec = TrustedNodeSpec(
            "n1", "Node", "host", None, "online", "host", 5000, True,
            connection_status="authentication_failed",
        )
        self.assertEqual(spec.connection_status, "authentication_failed")
```

Run: `python3 -m pytest tests/test_nodes_connections_page.py::NodePresentationConnectionTests -x -q`  
Expected: `TypeError: unexpected keyword argument 'connection_status'`

- [ ] **Step 2: Add fields to TrustedNodeSpec in nodes_connections.py**

In `maintenance/ui/nodes_connections.py`, find `class TrustedNodeSpec:` (line ~104).  
After the existing `pairing_state: str = "trusted"` field, add:

```python
    connection_status: str = "unknown"
    manual_disconnected: bool = False
    retry_automatic: bool = True
```

Also update `_TRUSTED_STRUCTURAL` (line ~609) to include the new fields that require row rebuild:

```python
    _TRUSTED_STRUCTURAL = (
        "permissions",
        "roles",
        "role_editable",
        "paused",
        "selectable",
        "status",
        "is_manual",
        "identity_status",
        "target_state",
        "identity_fingerprint",
        "connection_status",
        "manual_disconnected",
    )
```

- [ ] **Step 3: Run test to verify passes**

Run: `python3 -m pytest tests/test_nodes_connections_page.py::NodePresentationConnectionTests -x -q`  
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add maintenance/ui/nodes_connections.py tests/test_nodes_connections_page.py
git commit -m "feat: add connection_status/manual_disconnected/retry_automatic to TrustedNodeSpec"
```

---

## Task 3: Update _trusted_meta_text and _trusted_meta_color

**Files:**
- Modify: `maintenance/ui/nodes_connections.py`

- [ ] **Step 1: Write failing tests**

Add to `NodePresentationConnectionTests`:

```python
    def test_meta_text_uses_connection_status_not_node_status(self) -> None:
        from maintenance.ui.nodes_connections import NodesConnectionsPage
        page, _, _ = make_page()
        spec = _trusted_spec("n1", status="online")
        # When connection_status says connecting, meta should say Connecting
        spec2 = replace(spec, connection_status="connecting")
        text = page._trusted_meta_text(spec2)
        self.assertIn("Connecting", text)
        self.assertNotIn("Online", text)

    def test_meta_text_auth_failed(self) -> None:
        from maintenance.ui.nodes_connections import NodesConnectionsPage
        page, _, _ = make_page()
        spec = replace(_trusted_spec("n1"), connection_status="authentication_failed")
        self.assertIn("Auth failed", page._trusted_meta_text(spec))

    def test_meta_text_manual_disconnected(self) -> None:
        from maintenance.ui.nodes_connections import NodesConnectionsPage
        page, _, _ = make_page()
        spec = replace(_trusted_spec("n1"), manual_disconnected=True)
        self.assertIn("Disconnected", page._trusted_meta_text(spec))

    def test_meta_text_offline_retrying(self) -> None:
        from maintenance.ui.nodes_connections import NodesConnectionsPage
        page, _, _ = make_page()
        spec = replace(_trusted_spec("n1"), connection_status="offline", retry_automatic=True)
        self.assertIn("retrying", page._trusted_meta_text(spec))

    def test_meta_color_auth_failed_is_danger(self) -> None:
        from maintenance.ui.nodes_connections import NodesConnectionsPage
        page, _, _ = make_page()
        spec = replace(_trusted_spec("n1"), connection_status="authentication_failed")
        self.assertEqual(page._trusted_meta_color(spec), "danger")

    def test_meta_color_manual_disconnected_is_secondary(self) -> None:
        from maintenance.ui.nodes_connections import NodesConnectionsPage
        page, _, _ = make_page()
        spec = replace(_trusted_spec("n1"), manual_disconnected=True)
        self.assertEqual(page._trusted_meta_color(spec), "secondary")

    def test_meta_color_identity_changed_is_danger(self) -> None:
        from maintenance.ui.nodes_connections import NodesConnectionsPage
        page, _, _ = make_page()
        spec = replace(_trusted_spec("n1"), connection_status="identity_changed")
        self.assertEqual(page._trusted_meta_color(spec), "danger")

    def test_meta_color_online_is_success(self) -> None:
        from maintenance.ui.nodes_connections import NodesConnectionsPage
        page, _, _ = make_page()
        spec = replace(_trusted_spec("n1"), connection_status="online")
        self.assertEqual(page._trusted_meta_color(spec), "success")
```

Also add `from dataclasses import replace` at top of test file if not present.

Run: `python3 -m pytest tests/test_nodes_connections_page.py::NodePresentationConnectionTests -x -q`  
Expected: failures because `_trusted_meta_text` still uses `spec.status`

- [ ] **Step 2: Update _trusted_meta_text in nodes_connections.py**

Find `def _trusted_meta_text(self, spec: TrustedNodeSpec) -> str:` (line ~697).

Replace the method body:

```python
    def _trusted_meta_text(self, spec: TrustedNodeSpec) -> str:
        conn_label = node_presentation.connection_status_label(
            spec.connection_status,
            manual_disconnected=spec.manual_disconnected,
            retry_automatic=spec.retry_automatic,
        )
        role_status = (
            f"{node_presentation.trust_label('trusted')} · {conn_label}"
        )
        if spec.target_state != "Unknown":
            role_status += f" · {spec.target_state}"
        if spec.identity_status == "mismatch":
            role_status += " · Identity mismatch"
        return role_status
```

- [ ] **Step 3: Update _trusted_meta_color in nodes_connections.py**

Find `def _trusted_meta_color(self, spec: TrustedNodeSpec) -> str:` (line ~708).

Replace the method body:

```python
    def _trusted_meta_color(self, spec: TrustedNodeSpec) -> str:
        if (
            spec.identity_status == "mismatch"
            or spec.target_state == "Permission denied"
        ):
            return "danger"
        return node_presentation.connection_status_color_role(
            spec.connection_status,
            manual_disconnected=spec.manual_disconnected,
        )
```

Add the import for `connection_status_color_role` — since `node_presentation` is already imported as a module, this is automatically available as `node_presentation.connection_status_color_role`.

- [ ] **Step 4: Run test to verify passes**

Run: `python3 -m pytest tests/test_nodes_connections_page.py::NodePresentationConnectionTests -x -q`  
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add maintenance/ui/nodes_connections.py tests/test_nodes_connections_page.py
git commit -m "feat: use connection_status in trusted-node meta text and color"
```

---

## Task 4: Project connection_status into TrustedNodeSpec via node_specs.py

**Files:**
- Modify: `maintenance/ui/window_supports/node_specs.py`
- Modify: `maintenance/ui/window_page_data.py`

- [ ] **Step 1: Write failing test**

Add a new test class `ConnectionStateProjectionTests` to `tests/test_nodes_connections_page.py`:

```python
class ConnectionStateProjectionTests(unittest.TestCase):
    def _make_context(
        self,
        node_id: str = "peer-a",
        connection_status: str = "online",
        retry_automatic: bool = True,
    ) -> Any:
        from maintenance.nodes import (
            ConnectionState, NodeConnectionStatus, NodeContext, NodeDescriptor,
            NodeId, NodeIdentityStatus, NodePairingState, NodeTrustState, NodeStatus,
        )
        from maintenance.remote_support.protocol import READ_CAPABILITIES
        from maintenance.nodes import READ_PERMISSIONS
        descriptor = NodeDescriptor(
            id=NodeId(node_id),
            display_name=node_id,
            hostname=node_id,
            is_local=False,
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.ONLINE,
            capabilities=READ_CAPABILITIES,
            platform=None,
            color=None,
            permissions=READ_PERMISSIONS,
            identity_status=NodeIdentityStatus.VERIFIED,
            pairing_state=NodePairingState.TRUSTED,
        )
        context = NodeContext(
            descriptor=descriptor,
            provider=None, process_manager=None,
            file_manager=None, scheduler=None, coordinator=None,
        )
        context.connection = ConnectionState(NodeConnectionStatus(connection_status))
        context.retry.automatic_retry = retry_automatic
        return context

    def test_connecting_status_projected(self) -> None:
        from maintenance.nodes import NodeId, NodeRegistry
        from maintenance.cluster import ClusterState
        from maintenance.ui.window_supports.node_specs import trusted_node_specs
        registry = NodeRegistry()
        ctx = self._make_context("peer-a", "connecting")
        registry.register_context(ctx)
        specs = trusted_node_specs(registry, ClusterState())
        self.assertEqual(specs[0].connection_status, "connecting")

    def test_auth_failed_projected(self) -> None:
        from maintenance.nodes import NodeId, NodeRegistry
        from maintenance.cluster import ClusterState
        from maintenance.ui.window_supports.node_specs import trusted_node_specs
        registry = NodeRegistry()
        ctx = self._make_context("peer-a", "authentication_failed", retry_automatic=False)
        registry.register_context(ctx)
        specs = trusted_node_specs(registry, ClusterState())
        self.assertEqual(specs[0].connection_status, "authentication_failed")
        self.assertFalse(specs[0].retry_automatic)

    def test_manual_disconnected_projected(self) -> None:
        from maintenance.nodes import NodeId, NodeRegistry
        from maintenance.cluster import ClusterState
        from maintenance.ui.window_supports.node_specs import trusted_node_specs
        registry = NodeRegistry()
        ctx = self._make_context("peer-a", "offline")
        registry.register_context(ctx)
        disconnected = [NodeId("peer-a")]
        specs = trusted_node_specs(registry, ClusterState(), disconnected_ids=disconnected)
        self.assertTrue(specs[0].manual_disconnected)

    def test_not_disconnected_by_default(self) -> None:
        from maintenance.nodes import NodeId, NodeRegistry
        from maintenance.cluster import ClusterState
        from maintenance.ui.window_supports.node_specs import trusted_node_specs
        registry = NodeRegistry()
        ctx = self._make_context("peer-a", "offline")
        registry.register_context(ctx)
        specs = trusted_node_specs(registry, ClusterState())
        self.assertFalse(specs[0].manual_disconnected)
```

Run: `python3 -m pytest tests/test_nodes_connections_page.py::ConnectionStateProjectionTests -x -q`  
Expected: `TypeError: trusted_node_specs() got an unexpected keyword argument 'disconnected_ids'`

- [ ] **Step 2: Update trusted_node_specs() in node_specs.py**

Find `def trusted_node_specs(` (line ~34). Update the signature and body:

```python
def trusted_node_specs(
    registry: Any,
    cluster_state: Any,
    manual_node_ids: Iterable[str] = (),
    *,
    disconnected_ids: Iterable[Any] = (),
) -> list[ui_nodes.TrustedNodeSpec]:
    """Project trusted non-manual contexts and preserve their display policy."""

    manual = set(manual_node_ids)
    disconnected = frozenset(disconnected_ids)
    selectable = {descriptor.id for descriptor in registry.selectable_descriptors()}
    actor = cluster_state.local_assignment
    specs: list[ui_nodes.TrustedNodeSpec] = []
    for context in registry.contexts():
        descriptor = context.descriptor
        if (
            descriptor.is_local
            or not is_trusted_descriptor(descriptor)
            or descriptor.id.value in manual
        ):
            continue
        record = cluster_state.record(descriptor.id.value)
        assignment = next(
            (
                item
                for item in cluster_state.role_assignments
                if item.node_id is not None
                and item.node_id.value == descriptor.id.value
            ),
            None,
        )
        specs.append(
            ui_nodes.TrustedNodeSpec(
                node_id=descriptor.id.value,
                display_name=descriptor.display_name,
                hostname=descriptor.hostname,
                color=descriptor.color,
                status=descriptor.status.value,
                host=record.host if record is not None else descriptor.hostname,
                port=record.port if record is not None else None,
                selectable=descriptor.id in selectable,
                openable=(
                    descriptor.identity_status == NodeIdentityStatus.VERIFIED
                    and descriptor.id in selectable
                    and record is not None
                    and record.port is not None
                ),
                identity_fingerprint=descriptor.identity_fingerprint,
                identity_status=descriptor.identity_status.value,
                permissions=tuple(
                    sorted(permission.value for permission in descriptor.permissions)
                ),
                pairing_state=descriptor.pairing_state.value,
                target_state=render_target_state(descriptor, context.snapshot).label,
                connection_status=context.connection.status.value,
                manual_disconnected=descriptor.id in disconnected,
                retry_automatic=context.retry.automatic_retry,
                role=(
                    "coordinator"
                    if assignment is not None
                    and any(item.value == "coordinator" for item in assignment.roles)
                    else "subcoordinator"
                    if assignment is not None
                    and any(item.value == "subcoordinator" for item in assignment.roles)
                    else "worker"
                ),
                roles=tuple(
                    sorted(item.value for item in assignment.roles)
                    if assignment is not None
                    else ("worker",)
                ),
                role_editable=any(item.value == "coordinator" for item in actor.roles),
                paused=assignment.paused if assignment is not None else False,
                has_active_job=(
                    assignment.has_active_job if assignment is not None else False
                ),
            )
        )
    return specs
```

Similarly, update `manual_node_specs()` — add the same `disconnected_ids` parameter and project `connection_status`, `manual_disconnected`, `retry_automatic`:

```python
def manual_node_specs(
    registry: Any,
    cluster_state: Any,
    manual_node_ids: Iterable[str] = (),
    *,
    disconnected_ids: Iterable[Any] = (),
) -> list[ui_nodes.TrustedNodeSpec]:
    """Project manually configured hosts as non-selectable trusted rows."""

    disconnected = frozenset(disconnected_ids)
    specs: list[ui_nodes.TrustedNodeSpec] = []
    for node_id in tuple(manual_node_ids):
        try:
            context = registry.context(NodeId(node_id))
        except KeyError:
            continue
        descriptor = context.descriptor
        record = cluster_state.record(node_id)
        specs.append(
            ui_nodes.TrustedNodeSpec(
                node_id=node_id,
                display_name=descriptor.display_name,
                hostname=descriptor.hostname,
                color=descriptor.color,
                status=descriptor.status.value,
                host=record.host if record is not None else descriptor.hostname,
                port=record.port if record is not None else None,
                selectable=False,
                openable=record is not None and record.port is not None,
                is_manual=True,
                identity_fingerprint=descriptor.identity_fingerprint,
                identity_status=descriptor.identity_status.value,
                permissions=tuple(
                    sorted(permission.value for permission in descriptor.permissions)
                ),
                pairing_state=descriptor.pairing_state.value,
                target_state=render_target_state(descriptor, context.snapshot).label,
                connection_status=context.connection.status.value,
                manual_disconnected=NodeId(node_id) in disconnected,
                retry_automatic=context.retry.automatic_retry,
            )
        )
    return specs
```

- [ ] **Step 3: Update window_page_data.py to pass disconnected_ids**

Find `def nodes_trusted_specs(controller: Any)` (line ~93).

Replace both `nodes_trusted_specs` and `nodes_manual_specs`:

```python
def nodes_trusted_specs(controller: Any) -> list[ui_nodes.TrustedNodeSpec]:
    registry = controller.__dict__.get("_node_registry")
    if registry is None:
        return []
    from maintenance.ui import window_discovery as ui_window_discovery
    peer_mgr = ui_window_discovery.peer_connections(controller)
    disconnected = (
        [
            ctx.node_id
            for ctx in registry.contexts()
            if not ctx.descriptor.is_local
            and peer_mgr.is_manual_disconnected(ctx.node_id)
        ]
        if peer_mgr is not None
        else []
    )
    return node_specs.trusted_node_specs(
        registry,
        controller._cluster_state,
        getattr(controller, "_manual_host_ids", set()),
        disconnected_ids=disconnected,
    )


def nodes_manual_specs(controller: Any) -> list[ui_nodes.TrustedNodeSpec]:
    registry = controller.__dict__.get("_node_registry")
    if registry is None:
        return []
    from maintenance.ui import window_discovery as ui_window_discovery
    peer_mgr = ui_window_discovery.peer_connections(controller)
    disconnected = (
        [
            ctx.node_id
            for ctx in registry.contexts()
            if not ctx.descriptor.is_local
            and peer_mgr.is_manual_disconnected(ctx.node_id)
        ]
        if peer_mgr is not None
        else []
    )
    return node_specs.manual_node_specs(
        registry,
        controller._cluster_state,
        getattr(controller, "_manual_host_ids", set()),
        disconnected_ids=disconnected,
    )
```

Note: the `from maintenance.ui import window_discovery` import must be inside the function body to avoid circular imports. Verify by checking the existing top-level imports in `window_page_data.py` — if `window_discovery` is already imported at the top, use the top-level import instead.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_nodes_connections_page.py -x -q`  
Expected: all pass

- [ ] **Step 5: Run broader tests**

Run: `python3 -m pytest tests/test_peer_connection.py tests/test_window_nodes.py -x -q`  
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add maintenance/ui/window_supports/node_specs.py maintenance/ui/window_page_data.py
git commit -m "feat: project connection_status/manual_disconnected/retry_automatic to TrustedNodeSpec"
```

---

## Task 5: Remove add_manual_host from connections.py and window_node_actions.py

**Files:**
- Modify: `maintenance/ui/window_node_actions_impl/connections.py`
- Modify: `maintenance/ui/window_node_actions.py`

- [ ] **Step 1: Confirm tests testing add_manual_host that must be removed**

The following tests in `tests/window_node_cases/selector.py` test `_add_manual_host` validation — they will be deleted in Task 7:
- `test_invalid_manual_port_is_rejected` (line ~274)
- `test_non_integer_manual_port_is_rejected_at_controller_boundary` (line ~284)
- `test_remove_manual_host_prompts_before_revoking` (line ~293) — can be rewritten without `_add_manual_host` setup
- `test_remove_manual_host_revokes_after_confirmation` (line ~310)

The tests `test_remove_manual_host_*` need manual state setup. Run the test suite first to confirm current state.

Run: `python3 -m pytest tests/window_node_cases/selector.py -x -q --tb=short`

- [ ] **Step 2: Delete add_manual_host from connections.py**

In `maintenance/ui/window_node_actions_impl/connections.py`, find and delete the entire `add_manual_host()` function (lines ~357–430).

Verify the function boundaries: it starts at `def add_manual_host(` and ends just before `def remove_manual_host(`. Delete the function body completely.

After deletion, verify:
```bash
grep -n "def add_manual_host\|add_manual_host" maintenance/ui/window_node_actions_impl/connections.py
```
Should return zero results.

- [ ] **Step 3: Delete add_manual_host routing from window_node_actions.py**

In `maintenance/ui/window_node_actions.py`, find `def add_manual_host(` (line ~251) and delete it:

```python
# DELETE this function entirely:
def add_manual_host(
    controller: Any, display_name: str, host: str, port: int | None
) -> None:
    return _connections_impl.add_manual_host(controller, display_name, host, port)
```

- [ ] **Step 4: Verify imports are clean**

Run: `python3 -m ruff check maintenance/ui/window_node_actions_impl/connections.py maintenance/ui/window_node_actions.py`  
Expected: no errors (remove any unused imports that were only used by `add_manual_host`)

Check for unused imports in connections.py that `add_manual_host` brought in. `trusted_node_record` was used in both `add_manual_host` and other functions, so verify it's still used elsewhere before removing its import.

Run: `grep -n "trusted_node_record" maintenance/ui/window_node_actions_impl/connections.py`
If it still appears in other functions (e.g. `test_connection`, `activate_remote_node`), keep the import.

- [ ] **Step 5: Commit**

```bash
git add maintenance/ui/window_node_actions_impl/connections.py maintenance/ui/window_node_actions.py
git commit -m "feat: remove add_manual_host — manual host cannot authenticate without real pairing"
```

---

## Task 6: Remove add_manual_host from UI callbacks, window.py, and nodes_connections.py form

**Files:**
- Modify: `maintenance/ui/nodes_connections.py`
- Modify: `maintenance/ui/connection_dialog.py`
- Modify: `maintenance/ui/window_pages.py`
- Modify: `window.py`

- [ ] **Step 1: Make on_add optional in ConnectionDialog**

In `maintenance/ui/connection_dialog.py`, change:

```python
# BEFORE:
    on_add: Callable[[str, str, int | None], None],

# AFTER:
    on_add: Callable[[str, str, int | None], None] | None = None,
```

And update `submit()` to guard:

```python
    def submit(self) -> None:
        if self._on_add is None:
            self.close()
            return
        # ... existing body unchanged ...
```

And hide the "Add" button when `on_add is None`:

```python
        # BEFORE:
        button_cls(container, text="Add", command=self.submit).pack(side="right")

        # AFTER:
        if self._on_add is not None:
            button_cls(container, text="Add", command=self.submit).pack(side="right")
```

- [ ] **Step 2: Remove on_add_manual_host from NodesConnectionsCallbacks**

In `maintenance/ui/nodes_connections.py`, in `class NodesConnectionsCallbacks`:

```python
# DELETE this line:
    on_add_manual_host: Callable[[str, str, int | None], None]
```

- [ ] **Step 3: Remove add-form from _build_manual_hosts_section**

In `maintenance/ui/nodes_connections.py`, find `def _build_manual_hosts_section(self) -> None:` (line ~1018).

Replace the entire method body with a simplified version that only shows the section if there are existing manual hosts (no add form):

```python
    def _build_manual_hosts_section(self) -> None:
        _, body = ui_layout.section_card(
            self.content,
            "Manual hosts",
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            colors=self.colors,
            fonts=self.fonts,
            description=(
                "These hosts were added directly by address. "
                "Remove them if they are no longer needed."
            ),
        )
        self._manual_body = body
        self._manual_hosts_body = body
        self.refresh_manual(list(self._manual.values()))
```

Also remove the `_MANUAL_STRUCTURAL` tuple's dependency on `port` field if the form was the only thing referencing `_manual_name_var`, `_manual_host_var`, `_manual_port_var`. (The structural tuple for row refresh is fine to keep.)

Remove or stub `_add_manual_host` method in nodes_connections.py:

Find `def _add_manual_host(self) -> None:` (line ~1209) and delete it entirely.

- [ ] **Step 4: Update window_pages.py**

In `maintenance/ui/window_pages.py`, find where `on_add_manual_host=controller._add_manual_host` is passed to `NodesConnectionsCallbacks` (line ~178).

Remove that line entirely.

- [ ] **Step 5: Update window.py**

In `window.py`, find `_open_connection_dialog` (line ~565). Remove `on_add=self._add_manual_host`:

```python
    def _open_connection_dialog(
        self, spec: ui_nodes.TrustedNodeSpec | None = None
    ) -> None:
        existing = self.__dict__.get("_connection_dialog")
        if existing is not None:
            return
        dialog = ConnectionDialog(
            self.master,
            node_id=spec.node_id if spec is not None else None,
            on_test=self._test_connection if spec is not None else None,
        )
        # ... rest unchanged ...
```

In `window.py`, delete `_add_manual_host` method (line ~869):

```python
# DELETE:
    def _add_manual_host(
        self, display_name: str, host: str, port: int | None
    ) -> None:
        ui_node_actions.add_manual_host(self, display_name, host, port)
```

Keep `_remove_manual_host` because existing manual hosts may still need cleanup.

- [ ] **Step 6: Run ruff and check for errors**

```bash
python3 -m ruff check maintenance/ui/nodes_connections.py maintenance/ui/connection_dialog.py maintenance/ui/window_pages.py window.py
```

Expected: 0 errors.

- [ ] **Step 7: Run nodes_connections tests**

Run: `python3 -m pytest tests/test_nodes_connections_page.py -x -q`  
Expected: some failures (tests that reference `on_add_manual_host`) — these are fixed in Task 7.

- [ ] **Step 8: Commit**

```bash
git add maintenance/ui/nodes_connections.py maintenance/ui/connection_dialog.py maintenance/ui/window_pages.py window.py
git commit -m "feat: remove Add Manual Host UI form and on_add_manual_host callback"
```

---

## Task 7: Update tests — remove add_manual_host tests, fix selectors

**Files:**
- Modify: `tests/test_nodes_connections_page.py`
- Modify: `tests/window_node_cases/selector.py`
- Modify: `tests/window_node_cases/discovery_pairing.py`
- Modify: `tests/test_node_toplevel_dialogs.py`

- [ ] **Step 1: Update make_callbacks() in test_nodes_connections_page.py**

Remove `on_add_manual_host=Mock(),` from `make_callbacks()`.

Delete these three test methods that test the now-removed feature:
- `test_manual_add_routes_to_connection_opener` (~line 302)
- `test_manual_host_add_emits_with_port` (~line 372)
- `test_manual_host_add_without_port` (~line 383)

- [ ] **Step 2: Update tests/test_node_toplevel_dialogs.py**

Find the callback dict at line ~75. Remove `"on_add_manual_host": callback,`.

- [ ] **Step 3: Update selector.py — remove _add_manual_host tests**

In `tests/window_node_cases/selector.py`:

1. Delete `test_invalid_manual_port_is_rejected` (line ~274)
2. Delete `test_non_integer_manual_port_is_rejected_at_controller_boundary` (line ~284)
3. Rewrite `test_remove_manual_host_prompts_before_revoking` and `test_remove_manual_host_revokes_after_confirmation` to set up manual host state directly rather than calling `_add_manual_host`:

```python
    def _add_manual_host_directly(self, window: Any, display_name: str, host: str, port: int | None) -> str:
        """Set up a manual host record directly without going through the UI add flow."""
        from maintenance.cluster import ClusterState, trusted_node_record
        from maintenance.nodes import NodeContext, NodeDescriptor, NodeId, NodeTrustState, NodeStatus
        from maintenance.remote_support.protocol import READ_CAPABILITIES
        from maintenance.nodes import READ_PERMISSIONS
        node_id = f"manual-{host}:{port}" if port is not None else f"manual-{host}"
        descriptor = NodeDescriptor(
            id=NodeId(node_id),
            display_name=display_name,
            hostname=host,
            is_local=False,
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.UNKNOWN,
            capabilities=READ_CAPABILITIES,
            platform=None,
            color=None,
            permissions=READ_PERMISSIONS,
        )
        context = NodeContext(
            descriptor=descriptor, provider=None, process_manager=None,
            file_manager=None, scheduler=None, coordinator=None,
        )
        record = trusted_node_record(
            node_id=node_id, display_name=display_name, hostname=host,
            host=host, port=port, capabilities=READ_CAPABILITIES, permissions=READ_PERMISSIONS,
        )
        from dataclasses import replace
        state = replace(
            window._cluster_state,
            trusted_nodes=window._cluster_state.trusted_nodes + (record,),
        )
        window._node_registry.register_context(context)
        window._cluster_state = state
        if not hasattr(window, "_manual_host_ids") or window._manual_host_ids is None:
            window._manual_host_ids = set()
        window._manual_host_ids.add(node_id)
        return node_id

    def test_remove_manual_host_prompts_before_revoking(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._cluster_store = Mock()
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._nodes_status = Mock()
        node_id = self._add_manual_host_directly(window, "Lab Box", "lab-box.local", None)
        self.assertIsNotNone(window._cluster_state.record(node_id))

        with patch("window.messagebox.askyesno", return_value=False) as confirm:
            window._remove_manual_host(node_id)

        confirm.assert_called_once()
        self.assertIsNotNone(window._cluster_state.record(node_id))

    def test_remove_manual_host_revokes_after_confirmation(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._cluster_store = Mock()
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._nodes_status = Mock()
        node_id = self._add_manual_host_directly(window, "Lab Box", "lab-box.local", None)

        with patch("window.messagebox.askyesno", return_value=True):
            window._remove_manual_host(node_id)

        self.assertIsNone(window._cluster_state.record(node_id))
```

4. Update the callback routing test (~line 87) that checks `on_add.__func__`:

```python
# BEFORE:
        self.assertEqual(
            connection.call_args.kwargs["on_add"].__func__,
            window._add_manual_host.__func__,
        )

# AFTER: (no add callback — remove this assertion entirely)
        # No on_add: manual host add is no longer wired
```

Also verify the test still passes the remaining assertions.

- [ ] **Step 4: Update discovery_pairing.py**

In `tests/window_node_cases/discovery_pairing.py`, find lines ~71–72:
```python
        window._add_manual_host("Lab Box", "lab-box.local", None)
        window._add_manual_host("IP Box", "192.168.1.20", 5000)
```

Replace with direct state setup using the helper pattern above, or simply remove these lines if the test does not need manual host state (check whether the test is actually testing manual host behavior or discovery behavior).

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_nodes_connections_page.py tests/test_node_toplevel_dialogs.py tests/window_node_cases/selector.py tests/window_node_cases/discovery_pairing.py -x -q`  
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "test: update tests for removed add_manual_host, add connection-state assertions"
```

---

## Task 8: Connection-state regression tests (mandatory matrix)

**Files:**
- Modify: `tests/test_nodes_connections_page.py`

Add a new test class `ConnectionStateMatrixTests` that exercises backend state → presentation spec → UI text for every distinct state:

- [ ] **Step 1: Add the test class**

```python
class ConnectionStateMatrixTests(unittest.TestCase):
    """Assert backend state → TrustedNodeSpec → UI text/color for every state."""

    def _make_spec(
        self,
        connection_status: str = "online",
        manual_disconnected: bool = False,
        retry_automatic: bool = True,
        identity_status: str = "verified",
    ) -> TrustedNodeSpec:
        return TrustedNodeSpec(
            "n1", "Node 1", "host", None, "online", "host", 5000, True,
            connection_status=connection_status,
            manual_disconnected=manual_disconnected,
            retry_automatic=retry_automatic,
            identity_status=identity_status,
        )

    def _make_page_meta(self, spec: TrustedNodeSpec) -> tuple[str, str]:
        """Return (meta_text, meta_color) for the spec."""
        page, _, _ = make_page()
        return page._trusted_meta_text(spec), page._trusted_meta_color(spec)

    def test_online_shows_online(self) -> None:
        text, color = self._make_page_meta(self._make_spec("online"))
        self.assertIn("Online", text)
        self.assertEqual(color, "success")

    def test_connecting_shows_connecting_not_offline(self) -> None:
        text, color = self._make_page_meta(self._make_spec("connecting"))
        self.assertIn("Connecting", text)
        self.assertNotIn("Offline", text)
        self.assertNotIn("Online", text)
        self.assertEqual(color, "secondary")

    def test_offline_retrying_shows_retrying(self) -> None:
        text, color = self._make_page_meta(
            self._make_spec("offline", retry_automatic=True)
        )
        self.assertIn("Offline", text)
        self.assertIn("retrying", text)
        self.assertEqual(color, "warning")

    def test_offline_no_retry_shows_just_offline(self) -> None:
        text, color = self._make_page_meta(
            self._make_spec("offline", retry_automatic=False)
        )
        self.assertIn("Offline", text)
        self.assertNotIn("retrying", text)
        self.assertEqual(color, "warning")

    def test_authentication_failed_is_distinct_from_offline(self) -> None:
        text, color = self._make_page_meta(self._make_spec("authentication_failed"))
        self.assertNotIn("Offline", text)
        self.assertIn("Auth failed", text)
        self.assertEqual(color, "danger")

    def test_identity_changed_is_distinct_from_offline(self) -> None:
        text, color = self._make_page_meta(self._make_spec("identity_changed"))
        self.assertNotIn("Offline", text)
        self.assertIn("Identity changed", text)
        self.assertEqual(color, "danger")

    def test_manual_disconnect_shows_disconnected(self) -> None:
        text, color = self._make_page_meta(
            self._make_spec("offline", manual_disconnected=True)
        )
        self.assertIn("Disconnected", text)
        self.assertNotIn("Offline", text)
        self.assertNotIn("retrying", text)
        self.assertEqual(color, "secondary")

    def test_identity_mismatch_descriptor_overrides_to_danger(self) -> None:
        _, color = self._make_page_meta(
            self._make_spec("online", identity_status="mismatch")
        )
        self.assertEqual(color, "danger")

    def test_unknown_state_does_not_crash(self) -> None:
        text, color = self._make_page_meta(self._make_spec("unknown"))
        self.assertIsInstance(text, str)
        self.assertIsInstance(color, str)
```

- [ ] **Step 2: Run test**

Run: `python3 -m pytest tests/test_nodes_connections_page.py::ConnectionStateMatrixTests -x -q`  
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_nodes_connections_page.py
git commit -m "test: connection-state presentation matrix tests"
```

---

## Task 9: Full validation pass

- [ ] **Step 1: Run full relevant test suite**

```bash
python3 -m pytest tests/test_nodes_connections_page.py tests/test_peer_connection.py tests/test_window_nodes.py tests/test_node_toplevel_dialogs.py tests/test_cluster_failover.py tests/test_placement.py tests/test_window_placement.py -v --tb=short 2>&1 | tail -30
```

Expected: all pass. Fix any failures before proceeding.

- [ ] **Step 2: Run ruff**

```bash
python3 -m ruff check maintenance/ tests/ window.py
```

Expected: 0 errors.

- [ ] **Step 3: Run pyright**

```bash
python3 -m pyright maintenance/ tests/ window.py 2>&1 | grep -E "error:|warning:" | head -20
```

Expected: 0 errors on changed files.

- [ ] **Step 4: Run full suite**

```bash
python3 -m pytest tests/ -x -q --tb=short 2>&1 | tail -20
```

Expected: all pass (≥ 542 tests).

- [ ] **Step 5: Commit if clean**

```bash
git add .
git commit -m "test: full validation — all tests passing after Phase 11"
```

---

## Task 10: Update docs/REMOTE_CLUSTER_TRUE_FLOW.md

**Files:**
- Modify: `docs/REMOTE_CLUSTER_TRUE_FLOW.md`

- [ ] **Step 1: Read the current doc end to find where to append**

Read the last 40 lines of `docs/REMOTE_CLUSTER_TRUE_FLOW.md` to find the correct section number.

- [ ] **Step 2: Append §64 — Connection-state observability**

Append after the final section:

```markdown
## §64 — Phase 11: Connection-state observability + manual-host removal

### Connection-state backend → UI mapping (VERIFIED CURRENT)

`NodeConnectionStatus` (6 values, `maintenance/nodes.py:64`) is now fully
projected through `TrustedNodeSpec.connection_status` to the Nodes &
Connections page.

| Backend `NodeConnectionStatus` | `TrustedNodeSpec.connection_status` | UI label | Color role |
|---|---|---|---|
| `UNKNOWN` | `"unknown"` | Unknown | secondary |
| `CONNECTING` | `"connecting"` | Connecting… | secondary |
| `ONLINE` | `"online"` | Online | success |
| `OFFLINE` + `retry_automatic=True` | `"offline"` | Offline · retrying | warning |
| `OFFLINE` + `retry_automatic=False` | `"offline"` | Offline | warning |
| `AUTHENTICATION_FAILED` | `"authentication_failed"` | Auth failed | danger |
| `IDENTITY_CHANGED` | `"identity_changed"` | Identity changed | danger |
| (any, `manual_disconnected=True`) | any | Disconnected | secondary |

**Old status**: `TrustedNodeSpec.status` was `NodeStatus` (3 values: online/offline/unknown).
The field still exists for backward compatibility with All Systems / cluster_node_specs.
Connection detail is now in `connection_status`.

### Retry ownership (VERIFIED CURRENT)

`PeerConnectionManager` (`maintenance/components/peer_connection.py`) owns retry timing.
`RetryState.automatic_retry` is `False` for `AUTHENTICATION_FAILED` and `IDENTITY_CHANGED`
failures (line 162–168) — no automatic retry loop for security-class failures.
The UI reads `context.retry.automatic_retry` via `TrustedNodeSpec.retry_automatic`
and shows "retrying" suffix only when true.

### Manual disconnect (VERIFIED CURRENT)

`PeerConnectionManager.disconnect_manual(node_id)` adds to `_manual_disconnected` set.
The set is projected via `window_page_data.nodes_trusted_specs()` →
`peer_mgr.is_manual_disconnected()` → `TrustedNodeSpec.manual_disconnected`.
UI shows "Disconnected" (secondary) instead of "Offline (warning)".
Trust record persists. `PeerConnectionManager.reconnect()` clears the flag.

### Manual host feature — REMOVED (was BROKEN)

`add_manual_host()` (formerly `connections.py:357`) created a `TrustedNodeRecord`
locally with a randomly generated HMAC secret without sending it to the target.
The target never created a matching `PeerGrantRecord`, so `hello()` always failed
with `RemoteAuthError`. Authentication was never possible.

**Option B chosen** (§39 of Phase 11 spec): the Add Manual Host UI form and
`add_manual_host()` implementation have been removed. Existing manual-host
records stored in `_manual_host_ids` / `trusted_nodes` continue to render
(backward compatibility) and can be removed via the existing Remove Connection
/ Revoke flows. New manual hosts cannot be added until a real Option A
implementation (pre-pair probe + full pairing ceremony using `target_node_id`
in `pair_request` response) is built in a future phase.

**Previous doc claim "manual host works"**: SUPERSEDED as BROKEN.

### Tests

- `tests/test_nodes_connections_page.py::NodePresentationConnectionTests` — label/color helpers
- `tests/test_nodes_connections_page.py::ConnectionStateProjectionTests` — node_specs projection
- `tests/test_nodes_connections_page.py::ConnectionStateMatrixTests` — full state matrix
- `tests/window_node_cases/selector.py` — remove_manual_host backward compat

### Status matrix update

| Subsystem | Old status | New status |
|---|---|---|
| Connection-state UI projection | MISSING WIRING | VERIFIED CURRENT |
| Manual host add | BROKEN | REMOVED |
| Manual host remove (existing) | WIRED BUT PARTIAL | VERIFIED CURRENT |
| Retry state in UI | MISSING WIRING | VERIFIED CURRENT |
| Manual disconnect in UI | MISSING WIRING | VERIFIED CURRENT |
```

- [ ] **Step 3: Commit**

```bash
git add docs/REMOTE_CLUSTER_TRUE_FLOW.md
git commit -m "docs: Phase 11 — connection-state observability and manual-host removal"
```

---

## Task 11: Final push

- [ ] **Step 1: Rebuild wheel**

```bash
python3 maintenance/_release.py prepare-build --package-dir .
python3 -m build --wheel --no-isolation
python3 maintenance/_release.py sync-artifacts --package-dir .
```

- [ ] **Step 2: Commit wheel**

```bash
git add dist/ maintenance/_version.py
git commit -m "chore: release <version> — Phase 11 connection-state observability"
```

- [ ] **Step 3: Push**

```bash
git push origin main
```

---

## Self-review checklist

- [x] Spec §3: Connecting distinct from Offline — Task 3 + Task 8
- [x] Spec §7: Authentication failed distinct — Task 3 + Task 8
- [x] Spec §8: Identity changed distinct — Task 3 + Task 8
- [x] Spec §9: Manual disconnect distinct — Task 4 + Task 8
- [x] Spec §10: Trust and connection separate axes — never merged
- [x] Spec §11: Nodes & Connections compact row — `_trusted_meta_text` only 1 line
- [x] Spec §12: Color roles — Task 3
- [x] Spec §17: No fake local secret — Task 5 deletes `add_manual_host()`
- [x] Spec §18: Option B chosen — documented in Task 10
- [x] Spec §39: Add action removed/hidden — Task 6
- [x] Spec §44: Retry owned by PeerConnectionManager — not moved
- [x] Spec §48: Connection-state test matrix — Task 8
- [x] Spec §55: No TrustedNodeRecord before real pairing — `add_manual_host()` deleted
- [x] Spec §66: Docs updated — Task 10
- [x] No raw secrets in UI/diagnostics — verified (connection_status is status string only)
- [x] MOVABLE remains dormant — no changes to placement code
- [x] Phase 10 threading unchanged — `_trusted_meta_text` runs on Tk thread only

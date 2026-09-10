# Trusted-Node Lifecycle Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair trusted-node TLS construction and revoke lifecycle handling so pairing, secure connection, selection, active work, revocation, rediscovery, and re-pairing remain crash-free and fail closed.

**Architecture:** Keep `NodeRegistry` authoritative for runtime node identity and selection, `ClusterStore`/`ClusterState` authoritative for persisted trust, `PeerConnectionManager` authoritative for reconnect generations, and `AppCoordinator`/`UICoordinator` authoritative for stale work/render rejection. Add only the smallest shared transport-builder or lifecycle hook required after tracing the current call sites; do not introduce a new coordinator or redesign discovery/transport.

**Tech Stack:** Python 3.10+, Tkinter test doubles, `unittest`, `threading.Event`, `AppCoordinator`, `NodeRegistry`, TLS sockets, Ruff, Pyright, Mypy.

---

## File Structure Map

- `maintenance/remote.py`: strict TLS transport constructor and authenticated provider protocol; keep the required certificate-pin boundary here.
- `maintenance/cluster.py`: persisted `TrustedNodeRecord`, `PeerGrantRecord`, and `ClusterState`; retain verified identity and TLS fingerprints as durable trust data.
- `maintenance/nodes.py`: `NodeContext`, trust vocabulary, selection, pairing, and registry removal transitions.
- `maintenance/components/peer_connection.py`: reconnect cancellation, generations, retry state, and stale connection completion rejection.
- `maintenance/components/coordinator.py`: per-operation cancellation, generation, and callback delivery semantics.
- `maintenance/components/node_selection.py`: selected-node transition ordering and old-context cancellation.
- `maintenance/components/node_context.py`: startup hydration of persisted trusted placeholders.
- `maintenance/ui/window_node_actions.py`: pairing, Test, Open, manual-host, permission, and Revoke controller actions.
- `maintenance/ui/window_discovery.py`: discovery reconciliation, trusted endpoint updates, connection attachment/detachment, and discovery callbacks.
- `maintenance/ui/window_context.py`: atomic cluster-state save and synchronization of target-owned listener grants.
- `maintenance/ui/window_node_runtime.py`: selected-context mirrors, render-target invalidation, component cancellation, and dashboard rendering.
- `maintenance/ui/action_coordinator.py`: stable button bindings and dead-widget pruning; reuse it rather than adding another button registry.
- `maintenance/ui/diagnostics_page.py`: presentation of diagnostic failures and component timestamps.
- `maintenance/ui/node_presentation.py`: shared friendly identity/fingerprint formatting used by existing node list and diagnostics presentation.
- `window.py`: controller callback wrappers and shutdown composition; retain the existing adapter boundary unless a test proves the wrapper itself owns the defect.
- `tests/test_remote_contract.py`: TLS transport and provider contract tests.
- `tests/test_remote_security.py`: certificate/fingerprint validation tests.
- `tests/test_nodes.py`: registry state and selection invariants.
- `tests/test_peer_connection.py`: reconnect generation/cancellation tests.
- `tests/test_node_context.py`: persisted trusted-node hydration tests.
- `tests/test_window_nodes.py`: controller-level Test, activation, discovery, selection, and revoke lifecycle tests.
- `tests/test_nodes_connections_page.py`: row/button callback and trusted/untrusted presentation tests.
- `tests/test_diagnostics_page.py`: diagnostics wording and timestamp presentation tests.
- `tests/test_multi_node_concurrency.py`: cross-node stale work and shutdown tests.
- `tests/test_lifecycle_stress.py`: adversarial lifecycle sequencing tests, extending existing stress seams only where needed.

The defect report belongs to one trusted-node lifecycle plan. Transport pinning and revoke cannot be validated independently because the same persisted record supplies the secure endpoint, the same node ID scopes coordinator work, and revocation must invalidate the provider created by the transport path.

## Current Trace To Preserve

1. Discovery enters through `maintenance/components/network_discovery.py`, then `maintenance/ui/window_discovery.py:on_discovered_candidate`, which calls `NodeRegistry.update_discovered` and `sync_trusted_node_endpoint`.
2. Pairing enters `window.py:_pair_discovered_node` -> `window_node_actions.pair_discovered_node` -> `NodeRegistry.begin_pairing` -> `promote_to_trusted` -> `trusted_node_record`; target grant creation uses `request_target_grant`.
3. Persisted trust is loaded as non-operational placeholders by `node_context.restore_trusted_nodes`; `ClusterState.trusted_nodes` carries `secret`, endpoint, identity fingerprint, TLS fingerprint, and permissions.
4. Automatic connection uses `window_discovery.peer_connections` -> `PeerConnectionManager.reconcile` -> `connect_peer`; successful providers attach in `attach_peer`.
5. Test enters `window.py:_test_connection` -> `window_node_actions.test_connection`; current production construction is `transport_cls(record.host, port)` and omits `expected_fingerprint` when `transport_cls` is `TLSRemoteTransport`.
6. Open enters `open_cluster_node` and either switches an attached context or calls `activate_remote_node`; current activation also constructs `transport_cls(record.host, record.port)` without the pin.
7. Revoke enters `window.py:_revoke_trusted_node` -> `window_node_actions.revoke_trusted_node` -> `NodeRegistry.revoke_trusted`, removes the persisted trusted record and inbound grant, refreshes pages, rebuilds selection, then renders the selected context.
8. Shutdown enters `window_lifecycle.finalize_shutdown`, stopping the listener/discovery, peer manager, coordinator work, node operations, pages, timers, and render coordinator.

The implementation tasks below verify this map against the checked-out code before editing. Any contradiction is recorded as a factual correction in the implementation report, not resolved by architectural redesign.

## Implementation Tasks

### Task 1: Capture the Reproduction and Contract Inventory

**Files:**
- Modify: `tests/test_window_nodes.py` to add strict transport and revoke fixtures.
- Test: `tests/test_remote_contract.py`, `tests/test_remote_security.py`, `tests/test_window_nodes.py`, `tests/test_peer_connection.py`, `tests/test_nodes.py`, `tests/test_multi_node_concurrency.py`, `tests/test_diagnostics_page.py`.
- Record: the focused baseline and traceback in the final implementation report; do not edit historical `docs/bug_hunts/` entries.

- [ ] **Step 1: Inventory every transport construction.**

Run:

```bash
rg -n "TLSRemoteTransport|SocketRemoteTransport|transport_cls|transport=" maintenance tests --glob '*.py'
```

Record a table in the implementation commit message or test module comments with these current rows: `window_node_actions.request_target_grant` uses candidate host/port and candidate TLS fingerprint; `window_node_actions.test_connection` uses persisted host/port but omits the TLS fingerprint; `window_node_actions.activate_remote_node` uses persisted host/port but omits the TLS fingerprint; `window_discovery.connect_peer` uses persisted host/port and `record.transport_fingerprint`; `window_discovery.sync_trusted_node_endpoint` currently constructs TLS using the fresh candidate fingerprint. Include caller node ID, target node ID, secret, identity fingerprint, TLS fingerprint, and timeout for each row.

- [ ] **Step 2: Run the focused baseline.**

Run:

```bash
python -m unittest tests.test_remote_contract tests.test_remote_security tests.test_nodes tests.test_peer_connection tests.test_window_nodes tests.test_multi_node_concurrency tests.test_diagnostics_page -v
```

Expected: the existing suite passes, while no test currently proves that default production Test/activation passes `expected_fingerprint` or that revoke cancels and invalidates every node-qualified operation before registry removal. Save the exact count and duration in the final report.

- [ ] **Step 3: Add the failing constructor-contract regression.**

In `WindowNodeConnectionTests`, add a strict transport assertion alongside the existing generic `transport_cls=Mock` tests:

```python
def test_test_connection_passes_persisted_tls_fingerprint(self) -> None:
    runner = DeferredRunner()
    window = self._window(runner)
    window._cluster_state = replace(
        window._cluster_state,
        trusted_nodes=(
            replace(
                window._cluster_state.trusted_nodes[0], transport_fingerprint="tls-pin"
            ),
        ),
    )
    transport_cls = Mock()
    provider_cls = Mock(return_value=self._provider({"node_id": "peer-a"}))

    window_node_actions.test_connection(
        window, "peer-a", provider_cls=provider_cls, transport_cls=transport_cls
    )

    runner.run_next()
    transport_cls.assert_called_once_with(
        "192.0.2.10", 5000, expected_fingerprint="tls-pin"
    )
```

- [ ] **Step 4: Run the new test and confirm the defect.**

Run:

```bash
python -m unittest tests.test_window_nodes.WindowNodeConnectionTests.test_test_connection_passes_persisted_tls_fingerprint -v
```

Expected: FAIL because the current call is `transport_cls(record.host, port)`.

- [ ] **Step 5: Commit the baseline evidence test.**

```bash
git add tests/test_window_nodes.py
git commit -m "test: reproduce trusted node lifecycle regressions"
```

### Task 2: Establish One Secure Trusted-Transport Builder

**Files:**
- Modify: `maintenance/remote.py` near `TLSRemoteTransport`.
- Modify: `maintenance/cluster.py` to expose the existing `TrustedNodeRecord` contract without changing its serialized shape.
- Modify: `maintenance/ui/window_node_actions.py` and `maintenance/ui/window_discovery.py` to use the builder.
- Test: `tests/test_remote_contract.py`, `tests/test_remote_security.py`, `tests/test_window_nodes.py`.

- [ ] **Step 1: Define the strict builder contract in a test.**

Add a `TrustedTransportTests(unittest.TestCase)` class to `tests/test_remote_contract.py`. Its test uses a `TrustedNodeRecord` with host, port, and `transport_fingerprint="aa"`; assert the injected transport receives exactly those values and that a missing host, port, or fingerprint raises the repository's controlled remote configuration/authentication error rather than `TypeError`.

```python
def test_build_trusted_transport_requires_persisted_tls_pin(self) -> None:
    record = trusted_node_record(
        node_id="peer-a",
        display_name="Peer A",
        hostname="peer-a",
        host="192.0.2.10",
        port=5000,
        transport_fingerprint="aa",
    )
    transport_cls = Mock()

    build_trusted_transport(record, transport_cls=transport_cls)

    transport_cls.assert_called_once_with("192.0.2.10", 5000, expected_fingerprint="aa")
```

Use the existing `RemoteAuthError`/remote error vocabulary after reading the definitions; do not add `expected_fingerprint=None` to `TLSRemoteTransport`.

- [ ] **Step 2: Run the contract test to verify it fails.**

Run:

```bash
python -m unittest tests.test_remote_contract.TrustedTransportTests -v
```

Expected: FAIL because `build_trusted_transport` is not yet defined.

- [ ] **Step 3: Implement the minimal builder.**

Add one function with this interface and behavior:

```python
def build_trusted_transport(
    record: TrustedNodeRecord,
    *,
    transport_cls: Callable[..., Any] = TLSRemoteTransport,
) -> Any:
    if not record.host or record.port is None:
        raise RemoteAuthError("trusted peer has no complete endpoint")
    if not record.transport_fingerprint:
        raise RemoteAuthError("trusted peer has no pinned TLS fingerprint")
    return transport_cls(
        record.host,
        record.port,
        expected_fingerprint=record.transport_fingerprint,
    )
```

Import `TrustedNodeRecord` from `maintenance.cluster` after confirming the current import graph remains acyclic; `cluster.py` does not import `remote.py`, so this import is safe. Do not import UI or discovery code into `remote.py`.

- [ ] **Step 4: Route Test and activation through the builder.**

In `window_node_actions.py`, replace the direct `transport_cls(record.host, port)` expression in `test_connection` with `build_trusted_transport(record, transport_cls=transport_cls)`. In `activate_remote_node`, replace the direct transport construction with the same builder. Preserve the operation-specific hello, result validation, and UI behavior outside the builder.

- [ ] **Step 5: Route automatic reconnect through the same builder.**

In `window_discovery.connect_peer`, call `build_trusted_transport(record)` and retain the existing provider construction, hello validation, identity check, and capability extraction. The builder must use the persisted record's TLS pin, not discovery metadata.

- [ ] **Step 6: Run the transport-focused tests.**

Run:

```bash
python -m unittest tests.test_remote_contract tests.test_remote_security tests.test_window_nodes.WindowNodeConnectionTests -v
```

Expected: PASS, including the strict Test construction regression and tests proving Test, activation, and reconnect share the persisted pin.

- [ ] **Step 7: Commit the canonical construction change.**

```bash
git add maintenance/remote.py maintenance/ui/window_node_actions.py maintenance/ui/window_discovery.py tests/test_remote_contract.py tests/test_remote_security.py tests/test_window_nodes.py
git commit -m "fix: centralize trusted TLS transport construction"
```

### Task 3: Make Persisted Trust Authoritative During Rediscovery

**Files:**
- Modify: `maintenance/ui/window_discovery.py:431-593`.
- Modify: `maintenance/nodes.py:794-858` to preserve the existing separate discovered-candidate and trusted-context maps during revoke/rediscovery.
- Test: `tests/test_window_nodes.py`, `tests/test_nodes.py`.

- [ ] **Step 1: Add the pinning regression tests.**

Extend `WindowDiscoveryIntegrationTests` with these cases. Construct a trusted record pinned to `tls-x`, then deliver a candidate for the same stable ID advertising `tls-y`; assert the trusted record remains `tls-x`, the candidate is retained for identity-change presentation, and no transport is built with `tls-y`.

```python
def test_rediscovery_never_replaces_persisted_tls_pin(self) -> None:
    window = _make_window(
        _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
        start_discovery=False,
    )
    window._cluster_state = ClusterState(
        trusted_nodes=(
            trusted_node_record(
                node_id="peer-a",
                display_name="Peer A",
                hostname="peer-a",
                host="192.0.2.10",
                port=5000,
                transport_fingerprint="tls-x",
            ),
        )
    )
    candidate = _candidate("peer-a", transport_fingerprint="tls-y")
    with patch("maintenance.ui.window_discovery.build_trusted_transport") as build:
        window._on_discovered_candidate(candidate)
    self.assertEqual(
        window._cluster_state.record("peer-a").transport_fingerprint, "tls-x"
    )
    build.assert_not_called()
    self.assertEqual(
        window._node_registry.context(NodeId("peer-a")).descriptor.identity_status,
        NodeIdentityStatus.MISMATCH,
    )
```

Add companion tests for a changed address with the same TLS pin, a changed port with the same pin, a missing advertised pin, and a legacy record with no persisted pin. The first three may update only the endpoint after an authenticated hello; the last must produce a controlled non-connectable state and must not silently establish a new pin from discovery.

- [ ] **Step 2: Run the tests and verify the current drift.**

Run:

```bash
python -m unittest tests.test_window_nodes.WindowDiscoveryIntegrationTests -v
```

Expected: the changed-pin regression exposes the current `candidate.transport_fingerprint` construction/update path; existing endpoint reconciliation tests remain green.

- [ ] **Step 3: Change endpoint reconciliation to use the trusted pin.**

In `sync_trusted_node_endpoint`, compare a non-null persisted `record.transport_fingerprint` with the candidate's advertised fingerprint before attempting a new endpoint. On mismatch, set `NodeIdentityStatus.MISMATCH`, retain the candidate, report the existing concise identity error, and return `False`. When the persisted pin is present and matches, call `build_trusted_transport(replace(record, host=address, port=port))`. Never assign `candidate.transport_fingerprint` into `updated_record.transport_fingerprint`. If the persisted pin is absent, do not create an operational TLS provider; preserve the existing legacy recovery policy only when an authenticated hello can establish the record's verified value through an explicitly tested path.

The guarded construction must have this shape:

```python
if record.transport_fingerprint is not None:
    if candidate.transport_fingerprint != record.transport_fingerprint:
        context.descriptor = replace(
            descriptor,
            identity_status=NodeIdentityStatus.MISMATCH,
            identity_fingerprint=record.identity_fingerprint,
        )
        controller._nodes_error(
            f"Identity mismatch for {descriptor.display_name}; re-pair required"
        )
        return False
    verified_record = replace(record, host=address, port=port)
    provider = AuthenticatedNodeProvider(
        node_id=descriptor.id,
        secret=verified_record.secret,
        caller_node_id=NodeId(state.local_node_id),
        transport=build_trusted_transport(verified_record),
    )
```

- [ ] **Step 4: Verify pairing persists the displayed values.**

Add assertions to the pairing integration test that the `TrustedNodeRecord.identity_fingerprint` equals the confirmed candidate identity fingerprint and `transport_fingerprint` equals the confirmed candidate TLS fingerprint. Add a failure test with a different certificate fingerprint using the TLS transport fake and assert `RemoteAuthError("peer certificate fingerprint changed")` is surfaced as an offline/error state, not as a trust update.

- [ ] **Step 5: Run and commit trust-authority tests.**

```bash
python -m unittest tests.test_nodes tests.test_window_nodes.WindowDiscoveryIntegrationTests tests.test_remote_security -v
git add maintenance/ui/window_discovery.py maintenance/nodes.py tests/test_nodes.py tests/test_window_nodes.py tests/test_remote_security.py
git commit -m "fix: enforce persisted TLS pins during rediscovery"
```

Expected: all selected tests pass and no trusted record changes its pinned fingerprint from fresh discovery metadata.

### Task 4: Repair Revoke Ordering and Runtime Invalidation

**Files:**
- Modify: `maintenance/ui/window_node_actions.py:380-423`.
- Modify: `maintenance/nodes.py:1007-1026` to make removal ordering and selected-node fallback explicit.
- Modify: `maintenance/components/peer_connection.py:154-195` to invalidate the existing connection generation before a context is removed.
- Test: `tests/test_window_nodes.py`, `tests/test_nodes.py`, `tests/test_peer_connection.py`, `tests/test_multi_node_concurrency.py`.

- [ ] **Step 1: Add a selected-node revoke failing test.**

Create a window with local and operational remote contexts, select the remote context, populate `_cluster_state`, and call `_revoke_trusted_node("peer-a")`. Assert the call completes, the registry selected ID is local, `_selected_node_id` is local, the persisted record is absent, and the remote context cannot be looked up. Use the real `NodeSelection` adapter rather than bypassing it.

```python
def test_revoke_selected_node_returns_to_local_without_render_crash(self) -> None:
    window = _make_window(
        _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
        start_discovery=False,
    )
    window._switch_selected_node(NodeId("peer-a"))
    window._save_cluster_state = Mock(return_value=True)
    window._refresh_nodes_page = Mock()
    window._refresh_cluster_page = Mock()
    window._rebuild_node_selector = Mock()
    window._nodes_status = Mock()

    window._revoke_trusted_node("peer-a")

    self.assertEqual(window._node_registry.selected_id(), NodeId(LOCAL_NODE_ID))
    self.assertEqual(window._selected_node_id, NodeId(LOCAL_NODE_ID))
    self.assertIsNone(window._cluster_state.record("peer-a"))
    with self.assertRaises(KeyError):
        window._node_registry.context(NodeId("peer-a"))
```

- [ ] **Step 2: Run the failing revoke test.**

```bash
python -m unittest tests.test_window_nodes.WindowNodeRevokeTests.test_revoke_selected_node_returns_to_local_without_render_crash -v
```

Expected: the new test fails against the current ordering or identifies the exact missing callback/ordering from its traceback; record that traceback in the implementation report before fixing it.

- [ ] **Step 3: Define the revoke ordering in the existing owner.**

In `revoke_trusted_node`, capture the context and selection, then perform these operations in this order: increment the existing activation generation; cancel the node-qualified Test/connect/component operations; cancel the peer manager's connect operation; invalidate render targets for the node; close/invalidate the provider and its action backend through an existing hook; remove the persisted trusted record and inbound grant; save the new `ClusterState`; only after a successful save remove the registry context and select the local node. If persistence fails, restore the original registry/runtime state and do not report success. Do not use a blanket exception handler.

The controller-level sequence must remain explicit:

```python
new_state = ClusterState(
    discovery_enabled=controller._cluster_state.discovery_enabled,
    trusted_nodes=tuple(
        item
        for item in controller._cluster_state.trusted_nodes
        if item.node_id != node_id
    ),
    local_node_id=controller._cluster_state.local_node_id,
    local_identity_persisted=controller._cluster_state.local_identity_persisted,
    peer_grants=tuple(
        grant
        for grant in controller._cluster_state.peer_grants
        if grant.caller_node_id != node_id
    ),
)
if not controller._save_cluster_state(new_state):
    controller._nodes_error("Cluster settings could not be saved")
    return
controller._activation_generations[node] = (
    controller._activation_generations.get(node, 0) + 1
)
controller._cancel_node_operations(context)
controller._cancel_peer_connection(context)
controller._invalidate_node_render_targets(node)
if context.provider is not None:
    context.provider.invalidate()
registry.revoke_trusted(node)
if previous_selected:
    controller._selected_node_id = registry.selected_id()
```

Use the repository's existing state-construction style if `replace_cluster_state_without_node` or `_restore_node_context` do not exist; define those as small private functions in `window_node_actions.py`, not as a new coordinator.

- [ ] **Step 4: Add the provider invalidation hook without weakening transport security.**

The current provider has no lifecycle method and the current socket transport owns one socket per request. Add `AuthenticatedNodeProvider.invalidate()` that marks the provider closed and causes future `_request` calls to raise the existing controlled remote authorization/transport error before using the cached secret. Make it idempotent; there is no persistent socket to close. Do not add a global connection manager.

The provider guard must be a concrete boolean check at the start of `_request`:

```python
def invalidate(self) -> None:
    self._invalidated = True


def _request(
    self, operation: str, params: dict[str, Any], cancel_event: Any
) -> dict[str, Any]:
    if self._invalidated:
        raise RemoteAuthError("remote provider has been revoked")
    # retain the existing signing, transport.request, response validation, and error mapping
```

Initialize `_invalidated = False` in `__init__`, preserve the current `_request` body after the guard, and add a test that calls `invalidate()` twice and confirms no transport request occurs afterward.

- [ ] **Step 5: Make registry removal clear operational references.**

Before deleting the context, detach its provider, process manager, scheduler, and coordinator after cancellation. The registry must then either remove the context or use an existing demotion method, but it must never leave a selectable trusted context with no persisted record. Preserve discovered candidates separately so a still-advertising peer can be stored as untrusted after revoke.

- [ ] **Step 6: Run focused revoke tests and commit.**

```bash
python -m unittest tests.test_nodes tests.test_peer_connection tests.test_window_nodes tests.test_multi_node_concurrency -v
git add maintenance/ui/window_node_actions.py maintenance/nodes.py maintenance/components/peer_connection.py maintenance/components/coordinator.py maintenance/remote.py tests/test_nodes.py tests/test_peer_connection.py tests/test_window_nodes.py tests/test_multi_node_concurrency.py
git commit -m "fix: invalidate trusted node runtime before revoke"
```

Expected: selected-node revoke passes, local selection remains valid, and a revoked context cannot reconnect through a cached provider or retry callback.

### Task 5: Harden Revoke Against Repetition, In-Flight Work, and Shutdown

**Files:**
- Modify: `maintenance/ui/window_node_actions.py` and `maintenance/ui/window_node_runtime.py` at their existing cancellation/invalidation seams.
- Modify: `maintenance/components/peer_connection.py` at its existing current-generation checks.
- Test: `tests/test_window_nodes.py`, `tests/test_peer_connection.py`, `tests/test_multi_node_concurrency.py`, `tests/test_lifecycle_stress.py`.

- [ ] **Step 1: Add the revoke matrix tests.**

Use the existing `DeferredRunner` and `AppCoordinator` test fixture. For each named test, start the operation, call `window._revoke_trusted_node("peer-a")`, then deliver the deferred callback and assert no exception, no success UI, no remote selection, and no restored record:

```python
def test_revoke_drops_late_test_success(self) -> None:
    runner = DeferredRunner()
    window = self._window(runner)
    messages = Mock()
    window._save_cluster_state = Mock(return_value=True)
    window_node_actions.test_connection(
        window,
        "peer-a",
        messagebox_module=messages,
        provider_cls=Mock(return_value=self._provider({"node_id": "peer-a"})),
        transport_cls=Mock,
    )
    window._revoke_trusted_node("peer-a")

    runner.run_next()

    messages.showinfo.assert_not_called()
    self.assertIsNone(window._cluster_state.record("peer-a"))
```

Add the same assertion shape for `connecting`, component refresh, dashboard read, pending retry, and a queued render intent. Add separate tests for: second revoke after the first UI refresh; revoke when the record is already absent; revoke after Test failure; revoke while the peer is offline; revoke during navigation; and shutdown immediately after revoke. For ordinary repeated events assert no error callback; for injected persistence failure assert the original trusted context and selection remain intact.

- [ ] **Step 2: Add peer-generation assertions.**

Extend `PeerConnectionTests` to start a connection, call `manager.cancel(NodeId("peer-a"))`, remove or revoke the node, and invoke the saved completion callback. Assert `complete(...)` and `failed(...)` return `False`, the node is not recreated, and the coordinator has no automatic retry for the removed node.

- [ ] **Step 3: Implement stale-result guards at existing boundaries.**

Ensure the revoke path increments the existing activation generation before cancellation, uses `AppCoordinator.cancel` for every node-qualified key, uses `PeerConnectionManager.cancel`, and calls `UICoordinator.invalidate` for dashboard, scan status, discovery pages, thermals, and every component key. Keep callbacks safe by checking closing state, operation generation, current cluster record equality, and registry context existence before touching widgets or attaching a provider.

- [ ] **Step 4: Verify button and page teardown behavior.**

Extend `tests/test_nodes_connections_page.py` or `tests/test_ui_primitives.py` with a dead revoke-row widget bound through `ButtonCoordinator`; destroy the widget, call `set_enabled` and `dispatch`, and assert pruning occurs without `tk.TclError`. Rebuild the trusted page after revoke and assert the removed row is gone and no old callback is invoked.

- [ ] **Step 5: Run and commit lifecycle hardening.**

```bash
python -m unittest tests.test_window_nodes tests.test_peer_connection tests.test_multi_node_concurrency tests.test_lifecycle_stress tests.test_nodes_connections_page -v
git add maintenance/ui/window_node_actions.py maintenance/ui/window_node_runtime.py maintenance/components/peer_connection.py tests/test_window_nodes.py tests/test_peer_connection.py tests/test_multi_node_concurrency.py tests/test_lifecycle_stress.py tests/test_nodes_connections_page.py
git commit -m "test: harden revoke against stale lifecycle work"
```

Expected: all normal, double, offline, failure, connecting, in-flight, UI-navigation, late-callback, and shutdown revoke cases complete without crashes or trust resurrection.

### Task 6: Preserve Reject, Rediscovery, and Re-Pair Semantics

**Files:**
- Modify: `maintenance/nodes.py` to cover the tested state transitions without adding lifecycle vocabulary.
- Modify: `maintenance/ui/window_node_actions.py` to keep reject separate from revoke and clear old session material before a new pair.
- Modify: `maintenance/ui/window_discovery.py` for candidate/trusted identity collision handling.
- Test: `tests/test_nodes.py`, `tests/test_window_nodes.py`, `tests/test_network_discovery.py`, `tests/test_discovery_session.py`.

- [ ] **Step 1: Add explicit state-boundary tests.**

Test that rejecting a discovered candidate removes only `_discovered` and pairing state, while revoking a trusted node removes persisted trust, inbound grants, runtime context, and authorization. Test that `DISCOVERED` is not selectable, `TRUSTED` without a provider is not operational, `ONLINE` does not imply destructive permissions, and a revoked node is never represented as both trusted and untrusted in the registry at once.

- [ ] **Step 2: Add the rediscover-and-repair sequence.**

Use the existing candidate factory and registry fixture to run: update candidate -> begin pairing -> promote -> persist record -> revoke -> update the same candidate -> assert an untrusted candidate exists -> pair again with a new secret and the advertised verified fingerprints. Assert the old secret and provider are not present in the new record/context.

```python
def test_revoke_rediscover_and_pair_starts_clean(self) -> None:
    registry = NodeRegistry(_local_context())
    candidate = replace(
        _candidate("peer-a", identity_fingerprint="id-a"),
        transport_fingerprint="tls-a",
    )
    registry.update_discovered(candidate)
    registry.begin_pairing(NodeId("peer-a"))
    first = registry.promote_to_trusted(NodeId("peer-a"))
    registry.revoke_trusted(NodeId("peer-a"))
    registry.update_discovered(candidate)
    registry.begin_pairing(NodeId("peer-a"))
    second = registry.promote_to_trusted(NodeId("peer-a"))

    self.assertEqual(first.id, second.id)
    self.assertEqual(registry.discovered_candidates(), ())
    self.assertEqual(
        registry.context(NodeId("peer-a")).descriptor.trust, NodeTrustState.TRUSTED
    )
```

Assert in the controller-level test that the persisted record has a newly generated secret and no provider from the old context; the registry itself does not own persisted secrets. The implementation must not retain `old_secret` in the new `TrustedNodeRecord`.

- [ ] **Step 3: Test discovery still advertising after revoke.**

Deliver `add -> update -> pair -> revoke -> update` through `on_discovered_candidate`; assert there is one candidate row for the stable ID, it is untrusted/non-selectable, there is no trusted record, and All Systems/Nodes & Connections do not duplicate the identity.

- [ ] **Step 4: Test endpoint churn without pin churn.**

Deliver a same-identity candidate with a new DHCP address/port and the same TLS pin; assert the record endpoint updates only after authenticated hello. Deliver a different TLS pin; assert fail-closed identity-change state and unchanged persisted pin. Do not suppress the untrusted candidate after revoke.

- [ ] **Step 5: Run and commit lifecycle-reuse tests.**

```bash
python -m unittest tests.test_nodes tests.test_window_nodes.WindowDiscoveryIntegrationTests tests.test_network_discovery tests.test_discovery_session -v
git add maintenance/nodes.py maintenance/ui/window_node_actions.py maintenance/ui/window_discovery.py tests/test_nodes.py tests/test_window_nodes.py tests/test_network_discovery.py tests/test_discovery_session.py
git commit -m "test: cover trusted node rediscovery and repair"
```

Expected: reject and revoke remain distinct, rediscovery is untrusted after revoke, and re-pairing uses fresh credentials while preserving stable identity semantics.

### Task 7: Normalize Diagnostics Without Hiding Evidence

**Files:**
- Modify: `maintenance/ui/diagnostics_page.py:100-148`.
- Modify: `maintenance/diagnostics.py` to add the pure timestamp formatter and preserve raw diagnostic details.
- Modify: `maintenance/ui/node_presentation.py` to reuse its existing friendly identity/fingerprint helpers in the affected node presentations.
- Test: `tests/test_diagnostics_page.py`, `tests/test_diagnostics.py`, `tests/test_nodes_connections_page.py`.

- [ ] **Step 1: Add timestamp and raw-error presentation tests.**

Build a `DiagnosticsSnapshot` with `last_success=1789056712.440` and `last_error="TLSRemoteTransport.__init__() missing 1 required keyword-only argument: 'expected_fingerprint'"`. Assert the row contains a human-readable local time or existing canonical relative format, never the raw numeric timestamp; assert the concise state text says `Connection setup failed` while the copied/diagnostic detail retains the raw constructor message.

```python
def test_component_success_timestamp_is_human_readable(self) -> None:
    page = self._page_with_snapshot(component(last_success=1789056712.440))
    values = page_values(page)
    self.assertNotIn("1789056712.440", values)
    self.assertRegex(values, r"Last success: \d{2}:\d{2}:\d{2}")
```

Use the existing test factories and timezone-independent formatter seam; do not hard-code a timezone conversion in the widget test.

- [ ] **Step 2: Implement only the presentation fix.**

The current diagnostics module has no timestamp formatter. Add one pure formatter in `maintenance/diagnostics.py` that accepts the stored float and returns the established local `HH:MM:SS` representation. Keep raw errors in `DiagnosticsSnapshot` and serialized diagnostics unchanged. Map only the known connection-setup presentation to the concise label; preserve the underlying error in the value/copy path.

- [ ] **Step 3: Verify shared identity presentation.**

The current `node_presentation.py` has status, trust, technical-ID, fingerprint-line, and capability helpers but no hostname-based friendly-name resolver. Reuse those existing helpers for affected status/fingerprint text, leave duplicate `This System` display names unchanged, and document that a naming redesign is outside this focused pass. Tests must continue to assert stable IDs/fingerprints remain the authoritative identity values.

- [ ] **Step 4: Run and commit diagnostics changes.**

```bash
python -m unittest tests.test_diagnostics tests.test_diagnostics_page tests.test_nodes_connections_page -v
git add maintenance/ui/diagnostics_page.py maintenance/diagnostics.py maintenance/ui/node_presentation.py tests/test_diagnostics.py tests/test_diagnostics_page.py tests/test_nodes_connections_page.py
git commit -m "fix: present trusted connection diagnostics safely"
```

Expected: diagnostics remain machine-readable and copyable, raw operational causes remain available, and visible timestamps are human-readable.

### Task 8: Verify Persistence, Permissions, and Target Grants

**Files:**
- Modify: `maintenance/cluster.py` to test and preserve fingerprint, secret, endpoint, permission, and grant serialization.
- Modify: `maintenance/ui/window_node_actions.py` to clear local trusted records/grants and invalidate runtime authorization.
- Modify: `maintenance/ui/window_discovery.py` to preserve current target-grant behavior and report unavailable-target limitations accurately.
- Test: `tests/test_remote_contract.py`, `tests/test_remote_compatibility.py`, `tests/test_nodes.py`, `tests/test_window_nodes.py`, `tests/test_cluster.py`.

- [ ] **Step 1: Test persisted trust round trips.**

Save and reload a `ClusterState` containing identity fingerprint, transport fingerprint, secret, endpoint, and read permissions. Assert every field survives exactly. Save a post-revoke state and reload it; assert the trusted record and local inbound grant for that node are absent.

- [ ] **Step 2: Test permissions fail closed after revoke.**

Attach an `AuthenticatedNodeProvider` and a `RemoteProcessActionBackend` to a trusted context with process-review permission. Revoke locally, then assert the provider is invalidated and a subsequent dashboard/process request fails before a transport request is sent. Assert stale UI permission toggles cannot recreate a trusted record or authorize a request.

- [ ] **Step 3: Test target grant semantics from current protocol.**

The current protocol exposes `RemoteService.update_grants` for the local listener but no target-side revoke operation. Assert local revoke removes the initiator's local trusted record and local inbound grant, then `window_context.sync_peer_listener_grants` updates the local listener to an empty grant set. Report target-side material as not remotely removed; do not claim bilateral revocation.

- [ ] **Step 4: Test malformed trusted records.**

For each missing `host`, `port`, `transport_fingerprint`, `secret`, and target ID, invoke the production builder/activation boundary and assert a controlled error is delivered through `_nodes_error` or the existing diagnostics path. Assert no Python `TypeError` escapes and no context becomes `ONLINE`.

- [ ] **Step 5: Test restart persistence.**

Use `ClusterStore` with a temporary path: save trust, restore placeholders, revoke and save, restore again, and assert no revoked record/credential returns. If the peer is reintroduced through discovery after restore, assert it is an untrusted candidate only.

- [ ] **Step 6: Run and commit persistence/security tests.**

```bash
python -m unittest tests.test_cluster tests.test_nodes tests.test_remote_contract tests.test_remote_compatibility tests.test_window_nodes -v
git add maintenance/cluster.py maintenance/ui/window_node_actions.py maintenance/ui/window_discovery.py tests/test_cluster.py tests/test_nodes.py tests/test_remote_contract.py tests/test_remote_compatibility.py tests/test_window_nodes.py
git commit -m "test: prove revoke persistence and authorization boundaries"
```

Expected: fingerprints and credentials round-trip before revoke, disappear after revoke, and cannot authorize requests after local trust removal.

### Task 9: Run the Full Validation and Manual Evidence Matrix

**Files:**
- Modify: none unless a failing test identifies a scoped defect from Tasks 1-8.
- Test: all established repository tests and the actual two-machine LAN path when available.
- Report: `docs/plans/2026-09-10-trusted-node-lifecycle-regression.md` implementation notes or the final change report.

- [ ] **Step 1: Run focused lifecycle tests.**

```bash
python -m unittest tests.test_remote_contract tests.test_remote_security tests.test_cluster tests.test_nodes tests.test_node_context tests.test_peer_connection tests.test_window_nodes tests.test_nodes_connections_page tests.test_diagnostics tests.test_diagnostics_page tests.test_multi_node_concurrency tests.test_lifecycle_stress -v
```

Expected: PASS, with exact test count recorded. This command must cover TLS construction, pin mismatch, malformed trust data, pairing, reconnect, selected-node revoke, active work, double revoke, offline revoke, late callbacks, rediscovery, permissions, diagnostics, and shutdown.

- [ ] **Step 2: Run repository-wide static and test gates.**

```bash
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
pyright
mypy --ignore-missing-imports .
git diff --check
```

Expected: every command exits `0`; report exact test count, static-tool summaries, and any intentional live-Tk skips. Do not count a test as evidence if any static gate fails.

- [ ] **Step 3: Run clean packaging/import checks.**

```bash
./install/build.sh
VERSION="$(python -c 'from maintenance._version import __version__; print(__version__)')"
./install/verify.sh "$VERSION"
python -m pip install --force-reinstall --no-deps "dist/system_analyzer_${VERSION}-py3-none-any.whl"
system-analyzer-snapshot --help
```

Expected: the wheel contains all remote modules, has no forbidden paths, checksum verification passes, and the snapshot entrypoint prints help. Record the concrete version printed by the command in the implementation report.

- [ ] **Step 4: Execute and report the real two-machine matrix separately.**

Record one PASS, FAIL, or NOT TESTED result for each of discovery, pairing, TLS pin validation, Test, remote read, revoke, post-revoke access denial, rediscovery, re-pair, and restart persistence. Run both directions only when both installations are independently trusted. Also report peer restart, DHCP address/port change, duplicate discovery events, target offline, and app shutdown during revoke separately.

- [ ] **Step 5: Inspect the final diff and working tree.**

```bash
git status --short --branch
```

Expected: only lifecycle source/tests/docs changed, no generated secrets or unrelated architecture files are included, and the worktree is clean after the final implementation commit.

- [ ] **Step 6: Commit the final evidence/report update.**

```bash
git add docs/plans/2026-09-10-trusted-node-lifecycle-regression.md
git commit -m "docs: record trusted node lifecycle validation"
```

## Self-Review Checklist

- [ ] **Spec coverage:** Tasks 1-2 cover the complete TLS construction inventory, required `expected_fingerprint`, canonical construction, Test, activation, reconnect, malformed trust data, and strict-constructor security boundary.
- [ ] **Spec coverage:** Tasks 3 and 6 cover persisted identity/TLS authority, pairing fingerprints, certificate change, discovery endpoint churn, duplicate discovery, reject versus revoke, rediscovery, re-pair, All Systems, and stable identity presentation.
- [ ] **Spec coverage:** Tasks 4-5 cover selected-node revoke, active component/hello/Test/read/process work, retries, late callbacks, UI render invalidation, ButtonCoordinator teardown, double revoke, offline revoke, post-failure revoke, connecting revoke, and shutdown.
- [ ] **Spec coverage:** Task 8 covers local credentials, target-owned grants, permission fail-closed behavior, restart persistence, target unavailability, and the distinction between local and bilateral revocation.
- [ ] **Spec coverage:** Task 9 covers focused tests, the full test suite, Ruff, formatting, Pyright, Mypy, diff checks, packaging, and a separate physical two-machine result matrix.
- [ ] **Placeholder scan:** Run `rg -n "TBD|TODO|_window_with|Similar to" docs/plans/2026-09-10-trusted-node-lifecycle-regression.md`; expected output is empty.
- [ ] **Type consistency:** The plan uses `TrustedNodeRecord`, `build_trusted_transport(record, transport_cls=...)`, `AuthenticatedNodeProvider.invalidate()`, `NodeRegistry.revoke_trusted(NodeId(...))`, `PeerConnectionManager.cancel(NodeId(...))`, and existing `AppCoordinator`/`UICoordinator` APIs consistently across tasks.
- [ ] **Security review:** No task makes `expected_fingerprint` optional, trusts a fresh discovery TLS pin, merges reject with revoke, grants destructive permissions through pairing, or claims target-side revocation without an existing protocol operation.

## Execution Handoff

The plan is intentionally ready for inline execution in this repository because no OpenCode subagents are available for this pass. Implement Tasks 1-9 in order, keeping each checkbox and commit as the review checkpoint; do not start from a clean architecture redesign or skip the reproduction baseline.

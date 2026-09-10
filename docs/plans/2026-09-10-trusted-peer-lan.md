# Trusted Peer LAN Connection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compose the existing discovery, pairing, target-grant, authenticated transport, and read-only provider code into a normal TLS-protected trusted-peer LAN workflow.

**Architecture:** Discovery remains presence-only. A discovered initiator requests pairing over a TLS listener; the target queues that request to its Tk thread, requires local confirmation, persists a `PeerGrantRecord`, and only then lets the initiator persist its trusted record. A production connector uses the persisted endpoint and secret to perform authenticated hello, attaches the existing `AuthenticatedNodeProvider`, and drives `PeerConnectionManager` state independently from trust.

**Tech Stack:** Python 3.10+, Tkinter, `ssl`, TCP sockets, `openssl` certificate generation, zeroconf, existing HMAC/replay protocol, `AppCoordinator`, `ClusterStore`, `NodeRegistry`, unittest, Ruff, Pyright, Mypy.

---

## Audit Findings

| Concern | Current state | Required change |
|---|---|---|
| Target grant provisioner | Partial/test-only callback on `AppWindow` | Add TLS pairing request handler and target UI confirmation |
| Listener lifecycle | Partial; starts only with injected grants, loopback-only | Start with local app lifecycle, bind LAN interface, expose actual port, stop on close |
| Discovery endpoint | Partial; endpoint callback always returns `(False, None)` | Advertise actual bound port and transport fingerprint only after TLS listener starts |
| Production connector | Missing; `connect` is a no-op and `can_connect=False` | Use persisted record, TLS transport, authenticated hello, identity/fingerprint checks |
| Reconciliation | Present but disconnected from real provider attachment | Add result callback that installs provider/scheduler and preserves retry state |
| Persistence | Present for initiator records and target grants | Persist both sides only after target approval; keep additive fields optional |
| Online/offline | Partial; presence marks trusted descriptors online | Make connection manager authoritative for runtime connectivity |
| Confidentiality | Missing outside loopback; HMAC is not encryption | Use TLS for every socket listener and pin advertised certificate fingerprint |

## File Structure

- Modify `maintenance/remote.py`: TLS client/server framing, certificate fingerprint pinning, and the explicit pairing-request envelope; preserve HMAC and read operation contracts.
- Create `maintenance/remote_security.py`: generate/load per-installation self-signed TLS material using standard `openssl`, with atomic file permissions and no UI imports.
- Modify `maintenance/cluster.py`: add optional transport certificate fingerprint to trusted records and preserve old `cluster.json` files.
- Modify `maintenance/nodes.py`: carry the discovered transport fingerprint without changing trust semantics.
- Modify `maintenance/components/network_discovery.py`: advertise and parse the optional TLS fingerprint.
- Modify `maintenance/components/peer_connection.py`: deliver successful connection results to the composition root and clear remote runtime objects on failure.
- Modify `maintenance/ui/window_discovery.py`: compose TLS listener, target pairing callback, production connector, endpoint advertisement, and retry reconciliation.
- Modify `maintenance/ui/window_node_actions.py`: send a TLS pairing request and persist the initiator record only after target approval.
- Modify `maintenance/ui/window_context.py` and `maintenance/ui/window_lifecycle.py`: synchronize grants and stop the listener deterministically.
- Modify `window.py`: pass the production pairing callback and preserve existing test seams.
- Modify `tests/test_remote_contract.py`, `tests/test_cluster.py`, `tests/test_nodes.py`, `tests/test_network_discovery.py`, `tests/test_peer_connection.py`, and `tests/test_window_nodes.py`: red-green proof for TLS, pairing, persistence, connector, and state transitions.
- Create `tests/test_remote_security.py`: certificate-material lifecycle and permissions tests.
- Create `tests/test_lan_integration.py`: two in-process application compositions using real TCP/TLS sockets, explicitly labeled as composition evidence rather than two-machine evidence.
- Modify `docs/SYSTEM_ANALYZER_REVIEW.md` or add a dated LAN evidence report: record exact audit classifications, commands, and the final decision.

## Compatibility Rules

- `cluster.json` optional `transport_fingerprint` fields default to `None`; old records still load.
- Discovery TXT `tls_fingerprint` is optional; old peers remain discovered but not connectable for the new production connector.
- Existing HMAC request/response fields, operation names, replay rules, and target process safety remain unchanged.
- No remote shell, cleanup operation, or new destructive capability is added.

### Task 1: Add TLS security material and transport primitives

**Files:** `maintenance/remote_security.py`, `maintenance/remote.py`, `tests/test_remote_security.py`, `tests/test_remote_contract.py`

- [ ] Write failing tests for generated certificate files, restrictive permissions, TLS server/client hello, and rejection of a mismatched pinned certificate fingerprint.
- [ ] Run `python -m unittest tests.test_remote_security tests.test_remote_contract -v`; expected failure because the TLS classes and pinning arguments do not exist.
- [ ] Implement `TLSMaterial(cert_path, key_path, fingerprint)`, `ensure_tls_material(directory, node_id)`, `TLSRemoteTransport(host, port, expected_fingerprint, timeout)`, and `RemoteSocketServer(..., ssl_context, transport_fingerprint)`.
- [ ] Use these concrete seams:

```python
@dataclass(frozen=True, slots=True)
class TLSMaterial:
    certificate: Path
    private_key: Path
    fingerprint: str


class TLSRemoteTransport(SocketRemoteTransport):
    def __init__(
        self, host: str, port: int, *, expected_fingerprint: str, timeout: float = 10.0
    ): ...
```

- [ ] Keep `SocketRemoteTransport` as the non-TLS test/legacy seam; the application composition must instantiate `TLSRemoteTransport` for any non-loopback listener.
- [ ] Wrap accepted sockets with `SSLContext.wrap_socket(..., server_side=True)` before reading frames. Wrap client sockets with `ssl.create_default_context()`, disable hostname validation for the pinned self-signed certificate, and compare SHA-256 DER certificate bytes with the expected fingerprint when one is supplied.
- [ ] Run the focused tests; expected all TLS and existing socket tests pass.
- [ ] Commit `feat: add pinned tls transport for peer connections`.

### Task 2: Add additive endpoint and transport-fingerprint persistence

**Files:** `maintenance/cluster.py`, `maintenance/nodes.py`, `maintenance/components/network_discovery.py`, related tests

- [ ] Add optional `transport_fingerprint: str | None = None` to `TrustedNodeRecord`, `DiscoveredNodeCandidate`, `DiscoveryAdvertisement`, and their codecs/TXT properties.
- [ ] Serialize the field additively with the exact default: `"transport_fingerprint": record.transport_fingerprint`; parse it only when it is a non-empty string, otherwise store `None`.
- [ ] Add tests proving old records and advertisements without the field still parse, while new values round-trip exactly.
- [ ] Update trusted-node endpoint synchronization to persist the candidate transport fingerprint only after a successful pinned hello.
- [ ] Run `python -m unittest tests.test_cluster tests.test_nodes tests.test_network_discovery -v`; expected pass.
- [ ] Commit `feat: persist peer transport fingerprints additively`.

### Task 3: Implement explicit target-side pairing requests

**Files:** `maintenance/remote.py`, `maintenance/ui/window_node_actions.py`, `maintenance/ui/window_discovery.py`, `maintenance/ui/window_context.py`, tests

- [ ] Write a failing test for a caller sending a TLS pairing request: without target approval it gets a denial and no grant; after approval the target persists exactly one grant with the caller ID, generated secret, and read permissions.
- [ ] Add `PairingRequest` validation and a length-bounded `pairing_handler` seam to `RemoteSocketServer`; pairing requests must not enter `RemoteService.handle` or bypass TLS.
- [ ] Validate the request shape before invoking the callback:

```python
PairingRequest(
    caller_node_id=NodeId(raw["caller_node_id"]),
    caller_identity_fingerprint=raw["identity_fingerprint"],
    caller_transport_fingerprint=raw["transport_fingerprint"],
    proposed_secret=raw["secret"],
    permissions=frozenset(NodePermission(value) for value in raw["permissions"]),
)
```

- [ ] Return only `{"approved": True}` or `{"approved": False, "error": "denied"}` from the pairing handler; never return a grant secret to an unapproved caller.
- [ ] Add `PairingBroker` behavior in the window composition: queue the request onto Tk with `_submit_ui`, show the stable caller ID and fingerprints, wait on a bounded event, save `ClusterState(peer_grants=...)` atomically, then return approval/denial.
- [ ] Replace the optional production callback with `request_target_grant(...)` in `window_node_actions.py`; it sends the proposed secret and permissions to the candidate endpoint over `TLSRemoteTransport` and returns only after target approval.
- [ ] Keep the existing injected callback test seam as an explicit test override, never as the default composition.
- [ ] Run `python -m unittest tests.test_window_nodes tests.test_remote_contract tests.test_cluster -v`; expected pass.
- [ ] Commit `feat: complete target-owned peer pairing`.

### Task 4: Compose the listener and advertise only usable endpoints

**Files:** `maintenance/ui/window_discovery.py`, `maintenance/ui/window_context.py`, `maintenance/ui/window_lifecycle.py`, `window.py`, tests

- [ ] Write tests proving no listener means `(False, None)`, successful TLS listener means `(True, actual_bound_port)`, grant removal stops the listener, and startup failure leaves discovery running without a connectable advertisement.
- [ ] Build TLS material in the per-user cluster directory, bind the listener to `0.0.0.0` (or the configured reachable host), pass the local provider and local identity to `RemoteService`, and update grants without restarting the server.
- [ ] Compose the listener with `RemoteSocketServer(service, host=bind_host, ssl_context=tls_server_context, transport_fingerprint=tls.fingerprint, pairing_handler=controller._handle_pairing_request)` and assign it only after `start()` returns.
- [ ] Make `DiscoverySession` advertise the actual listener port and transport fingerprint; never advertise port `0` or `connectable=true` before `start()` succeeds.
- [ ] Run listener, discovery, and shutdown tests; expected pass.
- [ ] Commit `feat: advertise the real tls peer endpoint`.

### Task 5: Replace the no-op connector with authenticated reconciliation

**Files:** `maintenance/components/peer_connection.py`, `maintenance/ui/window_discovery.py`, `maintenance/ui/window_node_actions.py`, tests

- [ ] Write failing tests for connecting only trusted records with a real endpoint, setting `CONNECTING` then `ONLINE`, attaching the provider after hello, mapping transport/auth/identity failures to `OFFLINE`/`AUTHENTICATION_FAILED`/`IDENTITY_CHANGED`, and reconnecting after transient failure.
- [ ] Add an `on_connected` callback to `PeerConnectionManager`; call it only for the current generation after `complete()`, and clear remote runtime fields on failed current-generation attempts.
- [ ] Use the callback shape `on_connected: Callable[[NodeContext, Any], None] | None`; in `complete()`, set `ConnectionState.online()` first, then call it with the provider result for the current generation.
- [ ] Implement the production connector with `AuthenticatedNodeProvider`, `TLSRemoteTransport`, persisted secret, caller ID, pinned transport fingerprint, and mandatory hello identity validation. Attach the provider, `RemoteProcessActionBackend`, and `ComponentRefreshScheduler` through the existing `NodeContext` boundary.
- [ ] Set `can_connect` from trusted descriptor, verified identity, non-null port, non-null transport fingerprint, and matching persisted record. Do not infer connectivity from discovery presence.
- [ ] Run focused lifecycle and window tests; expected pass.
- [ ] Commit `feat: connect trusted peers through the production transport`.

### Task 6: Prove read-only LAN composition and document the decision

**Files:** `tests/test_lan_integration.py`, `docs/BACKGROUND_EXECUTION_AUDIT_2026-09-10.md` or a new dated evidence report, `docs/SYSTEM_ANALYZER_REVIEW.md`

- [ ] Build two application compositions with distinct node IDs, real TLS socket servers, explicit target grant approval, discovery-shaped endpoint metadata, and real `AuthenticatedNodeProvider` calls.
- [ ] The core assertion sequence is:

```python
assert target.grants[caller_id].secret == caller_record.secret
assert caller_provider.hello()["node_id"] == target_id
assert caller_provider.dashboard_snapshot().resources
assert caller_provider.component_summary("cpu").key == "cpu"
```
- [ ] Assert both grants, actual ports, TLS fingerprints, authenticated hello, stable IDs, dashboard snapshot, component summary, and thermal data where supported. Stop the target and assert offline, restart and assert reconnect, then reload `ClusterStore` and assert trust/grants persist.
- [ ] Mark this as in-process real-socket composition evidence, not two-machine evidence. If two physical machines are unavailable, final status must not claim full cross-machine proof.
- [ ] Run the full required checks: `python -m unittest discover -s tests -v`, `ruff check .`, `ruff format --check .`, `pyright`, `mypy --ignore-missing-imports`, package/import tests, and wheel verification.
- [ ] Perform a fresh audit against every requested safety invariant and record one final decision: `REMOTE LAN PATH WORKING`, `REMOTE LAN PATH WORKING READ-ONLY ONLY`, `PARTIAL — SPECIFIC GAP REMAINS`, or `BLOCKED`.
- [ ] Commit `docs: record trusted peer lan evidence and decision`.

## Self-Review Checklist

- Spec coverage: audit, grant provisioning, listener, endpoint, connector, reconciliation, persistence, hello, online/offline, confidentiality, read-only operations, cross-machine evidence, safety, and all validation commands are mapped to Tasks 1-6.
- No discovery event writes trust or grants; pairing remains explicit and target-approved.
- No step expands destructive operations; process/file safety remains in existing owners.
- The only schema change is additive and optional, preserving old cluster files and discovery metadata.
- Final decision must distinguish real socket composition tests from physical two-machine evidence.

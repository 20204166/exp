# Phase 15.4-15.8: Authenticated Peer Network Plan

## Status

Planning document. It combines authenticated peer transport, per-node
authorization, connection lifecycle, remote read-only system data, and remote
process viewing into one dependency-ordered delivery.

This is an equal-peer System Analyzer design. An installation can act as both
an initiating node and a target node. There is no required central service,
remote shell, generic command runner, arbitrary subprocess endpoint,
credential forwarding, or arbitrary filesystem API.

The current working tree has unrelated dashboard loading-bar edits in
`window.py` and `tests/test_window.py`. This work must neither revert nor fold
those edits into the peer-network patch.

## Decision Gate

Before implementation, choose the pairing transport guarantee. Do not silently
pick one while implementing the rest of the plan.

### Option A: Mutual TLS With Pinned Peer Credentials (Recommended)

Each installation has a persisted cryptographic identity. Explicit pairing
compares and pins that identity on both machines. TLS provides confidentiality,
integrity, and peer authentication; the target still resolves the authenticated
peer identity to its own permission grant.

Questions to answer:

- Can a new `cryptography` dependency be accepted for installation key and
  certificate generation, or must the implementation use only Python/OpenSSL
  facilities already available on supported platforms?
- Is a self-signed certificate plus explicit public-key pinning acceptable, or
  is an organisation-managed private CA required?
- Must remote metrics and process names remain confidential on a potentially
  hostile LAN, VPN, or Wi-Fi network? If yes, plain TCP plus HMAC is not an
  acceptable final transport.

### Option B: Out-of-Band 256-Bit Pair Secret (Minimal Existing-Protocol Path)

Both local UIs deliberately install the same high-entropy pairing material,
for example by scanning a QR code or entering a generated recovery phrase.
The secret never crosses the peer TCP channel. It authenticates and protects
the integrity of the existing HMAC envelope but does not encrypt metadata or
payloads on the network.

Questions to answer:

- Is the pairing ceremony sufficiently protected from visual interception and
  social engineering for the deployment environment?
- Is LAN-only use an enforceable product/deployment constraint, rather than an
  assumption made by the UI?
- How will a lost or exposed pairing secret be rotated and revoked on both
  targets?

Unless product requirements explicitly accept Option B's confidentiality
limitation, implement Option A. The rest of this plan applies to either option.

## Validated Starting Point

The repository already has important pieces. Reuse them rather than creating a
parallel HTTP/FastAPI service or another coordinator.

| Existing boundary | Current location | Required preservation |
| --- | --- | --- |
| Versioned signed request/response envelopes, frame bounds, freshness, replay cache | `maintenance/remote.py` | Preserve the closed, typed wire contract and `REMOTE_PROTOCOL_VERSION = "1"`. |
| Typed node, capability, permission, snapshot, and context models | `maintenance/nodes.py` | Preserve stable node IDs, node-qualified operation keys, and separation of discovery/trust/authorization. |
| Atomic trusted-node persistence | `maintenance/cluster.py` | Keep atomic-write behavior and compatibility migration discipline. |
| Coalescing, cache, cancellation, and Tk-thread delivery | `maintenance/components/coordinator.py` | Use `AppCoordinator`; do not add a second operation scheduler. |
| Discovery application lifecycle | `maintenance/components/discovery_session.py` | Keep discovery presence-only and UI-thread event delivery. |
| Selection ordering and stale-work cancellation | `maintenance/components/node_selection.py` | Preserve cancellation before context switch, node-qualified work, and render retargeting. |
| Stale render rejection | `maintenance/ui/render_coordinator.py` | Continue using node/generation guarded render intents; it must never scan or transport data. |
| Node-bound process dialog | `maintenance/dialogs.py` | Keep search, sorting, protected/can-quit display, PID/create-time handling, and dialog binding. |
| Final destructive local process safety boundary | `maintenance/actions.py` | Target-side `ProcessManager` remains the final authority for existing process actions. |
| Window composition and shutdown | `window.py` | Compose services here; do not put Tk imports in nodes, transport, or scanner modules. |

### Confirmed Gaps

1. `RemoteSocketServer` exists but `AppWindow` never constructs or starts one.
2. `DiscoverySession` advertises `connectable=False` and `port=None`, so a
   normal running installation cannot be reached as a target.
3. Current pairing generates/persists a secret on the initiator but does not
   provision it on the target.
4. `RemoteService.permissions` is service-wide. It is not a target-owned ACL
   keyed by authenticated caller identity.
5. A target authorization failure is a `RemoteProtocolError`; the socket
   server closes it silently. A TCP client therefore sees transport failure,
   not a signed typed denial.
6. Cancellation is checked only before a provider request; it cannot interrupt
   client socket I/O or target-side provider work.
7. Socket request handling uses unbounded daemon handler threads and shutdown
   does not track/drain active handlers.
8. `NodeSnapshot` is decoded by the remote provider, but its node metadata is
   discarded and the client does not verify `snapshot.node_id` against the
   selected target.
9. The declared `ProcessActionBackend` `ProcessRef` interface and actual
   PID/create-time action interface do not match.
10. A process dialog opened for one node retains its read key correctly, but
    force-quit availability is not independently derived from force capability
    plus force permission.
11. README currently says remote metrics and actions are unimplemented. Update
    it only after the end-to-end target listener and read flows are real.

## Security and Data-Flow Model

The required request path is:

```text
initiating System Analyzer
    -> authenticated peer transport
    -> target System Analyzer listener
    -> target validates protocol, target identity, and caller identity
    -> target resolves caller grant
    -> target checks permission
    -> target checks capability
    -> target invokes one typed operation
    -> signed typed response
```

Authentication establishes who made the request. It must not establish what
that caller may do. The target makes authorization decisions for every request.
UI button visibility is only a usability improvement, never an access-control
decision.

### Assets and Trust Boundaries

| Asset | Threat boundary | Required control |
| --- | --- | --- |
| Pairing secret or private key | Local settings/key storage -> transport | Restrictive file handling, redacted logs, rotation/revocation, no wire logging. |
| Node identity | Discovery -> pairing -> authenticated connection | Discovery is untrusted; authenticate and pin during deliberate pairing. |
| Dashboard/metrics/process data | Target provider -> transport -> initiator UI | Typed decode, protocol version check, target ID correlation, TLS when confidentiality is required. |
| Process safety knowledge | Target scanner/ProcessManager | Target classifies processes and revalidates immediately before existing actions. |
| UI state/caches | Worker -> AppCoordinator -> UICoordinator | Node-qualified keys, cooperative cancellation, generation checks, last-known-good cache. |

### Fail-Closed Rules

- Unknown caller, missing grant, revoked grant, malformed permission, malformed
  envelope, incompatible protocol, mismatched target identity, and failed
  cryptographic verification must deny before provider access.
- No code path may infer permissions from discovery metadata, display name,
  hostname, `is_local`, or initiating UI state.
- Do not treat a socket close as successful authorization denial. Expected
  denial responses must be signed and typed; failed authentication can close
  without revealing sensitive detail.
- Do not cache errors/cancellations as new good snapshots. Keep the previous
  node-local valid result and mark the connection degraded/offline.
- Do not permit remote cleanup in this delivery. The local-only `FileManager`
  remains the sole file action boundary.

## Repository Structure Rules

Write production code in the existing ownership structure.

| Concern | Primary file/module | Do not put it in |
| --- | --- | --- |
| Wire envelope, crypto verification, typed operation allowlist, socket/TLS transport | `maintenance/remote.py` | `window.py`, dialogs, scanners, UI modules. |
| Node identity, connection-state enum/data, grants' domain types, provider/action protocols | `maintenance/nodes.py` | Tk modules, discovery implementation. |
| Persisted target records and target-owned per-caller grants | `maintenance/cluster.py` | UI preferences or ad hoc JSON in `window.py`. |
| Listener service construction/start/stop | a focused `maintenance/components/peer_service.py` if needed | `maintenance/ui/`, transport codecs. |
| Reconnect policy state and reconciliation | a focused `maintenance/components/peer_connection.py` if needed | a new coordinator, per-node threads, per-node timers. |
| Discovery advertisement of actual listener endpoint | `maintenance/components/discovery_session.py` | `network_discovery.py` trust logic. |
| Window composition, one reconciliation timer, page status updates, shutdown call order | `window.py` | domain model and UI primitives. |
| Read snapshot application and last-known-good state | `NodeContext` plus window/controller scan boundary | widget code. |
| Widget layout/status/rendering | `maintenance/ui/` and `maintenance/dialogs.py` | transport/provider code. |
| Tests | Existing matching `tests/test_*.py` modules | production modules or historical bug-hunt evidence. |

Keep new modules narrow. Add one only when it owns a reusable non-UI lifecycle
responsibility; otherwise keep the implementation near the existing owner.

## Delivery Sequence

### 1. Freeze Public and Safety Contracts

1. Read current `maintenance/__init__.py` exports and every caller of
   `NodeProvider`, `RemoteService`, `AuthenticatedNodeProvider`, and
   `TrustedNodeRecord` before changing a signature.
2. Preserve existing operation names:
   `hello`, `dashboard_snapshot`, `component_summary`, `process_candidates`,
   `storage_candidates`, `process_request_quit`, and `process_force_quit`.
3. Do not add generic operations, remote command execution, shell access,
   arbitrary subprocess access, arbitrary filesystem access, remote cleanup,
   or credential forwarding.
4. Retain wire protocol version `"1"` for compatible additive fields. If a
   field cannot be safely optional, define a negotiated version path and test
   rejection of unsupported versions rather than silently accepting drift.
5. Make the `NodeProvider` snapshot contract explicit. Recommended incremental
   shape: add a typed `node_snapshot()` read boundary and keep
   `dashboard_snapshot()` as a compatibility shim until all callers are moved.

Questions to answer while coding:

- Does this change alter a top-level re-export, an installed-user API, or a
  serialized cluster record?
- Can an old trusted-node record load safely with a read-only/default-deny
  grant, or must it be deliberately re-paired?
- Does a malformed new field fail closed without discarding unrelated valid
  local state?

Illustrative contract sketch only; align exact names with existing models:

```python
@dataclass(frozen=True, slots=True)
class PeerGrant:
    caller_node_id: NodeId
    credential: str  # Pair secret or pinned credential reference; never log.
    permissions: frozenset[NodePermission]
    revision: int
    created_at: float


class NodeProvider(Protocol):
    def node_snapshot(
        self,
        cancel_event: Any | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> NodeSnapshot: ...
```

### 2. Implement Target-Owned Identity and Per-Caller Grants

1. Extend persistence with target-owned grants keyed by `caller_node_id`.
   A target's grant data is authoritative; initiator-side stored permissions
   are hints for UI affordances only.
2. Validate persisted grant records strictly:
   nonempty caller ID, valid credential representation, known
   `NodePermission` values only, finite timestamps, and no duplicate caller
   IDs. Invalid grants are ignored/denied, never widened to defaults.
3. Replace `RemoteService`'s global `secret`, optional expected caller, and
   global permission set with a grant resolver. The resolver may inspect an
   untrusted claimed caller ID solely to select a candidate credential, then
   must verify the signature before treating the identity as authenticated.
4. Bind each authenticated request to exact target ID, caller ID, protocol
   version, request ID, nonce, timestamp, operation, and parameters.
5. Treat a deterministic hash of a public node ID only as a display continuity
   aid. It is not proof of cryptographic identity. Pairing must pin a real
   target credential or high-entropy pair secret.
6. Make revocation atomic and immediate. Since each request is independently
   authenticated, the next request from a removed grant denies without waiting
   for a client-side session to expire.

Questions to answer while coding:

- If a caller re-pairs, does the target replace the old grant only after the
  new credential and permissions are durably persisted?
- Can two initiators hold distinct grants with different read permissions for
  the same target? They must be able to.
- Are failed pairing attempts rate-limited or otherwise bounded without
  allowing an attacker to exhaust listener worker capacity?
- Can logs identify a caller by stable node ID and denial reason without
  writing secrets, signed envelopes, raw metrics, or process lists?

Illustrative authorization path:

```python
def handle(self, envelope_text: str, cancel_event: Event) -> str:
    raw = decode_strict_envelope(envelope_text)
    claimed_caller = parse_claimed_caller_id(raw)
    grant = self._grants.get(claimed_caller)
    if grant is None:
        raise RemoteAuthError("unknown caller")

    request = verify_request(
        raw,
        credential=grant.credential,
        clock=self._clock,
        freshness_seconds=self._freshness_seconds,
        replay_cache=self._replay_cache_for(claimed_caller),
    )
    if request.node_id != self._node_id:
        raise RemoteAuthError("request target identity is invalid")

    required_capability, required_permission = operation_requirements(request.op)
    if required_permission not in grant.permissions:
        return self._signed_denial(request, code="permission_denied")
    if required_capability not in self._capabilities:
        return self._signed_denial(request, code="capability_unavailable")
    return self._signed_result(request, self._dispatch(request, cancel_event))
```

The actual implementation must preserve existing canonical signing behavior,
constant-time comparison, and error model compatibility. This sketch must not
be copied verbatim without typed validation and tests.

### 3. Harden the Typed Transport Contract

1. Keep the fixed 8 MiB frame maximum.
2. Require exact envelope field sets for each protocol version. Reject unknown
   fields, duplicate/conflicting identity fields, non-finite timestamps,
   incorrect JSON types, and unexpected operation parameters.
3. Preserve signed error response compatibility (`status="error"`) while
   adding a stable, non-sensitive error code, for example:
   `protocol_invalid`, `permission_denied`, `capability_unavailable`,
   `cancelled`, or `execution_failed`.
4. Authentication failures may close without an oracle. After successful
   authentication, authorization and supported-operation refusals must become
   signed error envelopes that `AuthenticatedNodeProvider` maps back to typed
   exceptions.
5. Retain fresh timestamps and bounded replay protection. If an operation is
   retried, define semantics explicitly:
   read requests may receive a new request ID after a transport failure;
   existing destructive operations must not be retried automatically unless
   server-side response replay/idempotency semantics prove duplicate execution
   impossible.
6. Plumb a monotonic deadline/cancel event into connection, send, receive, and
   response decode. Cancellation closes only the requesting client socket and
   does not mutate target state.

Questions to answer while coding:

- Is `bool` rejected wherever an integer/float is expected, including process
  create time and port values?
- If a response is lost after an existing action reaches the target, does the
  initiator present an unknown outcome rather than retrying and risking a
  duplicate action?
- Are raw target exceptions converted to safe error codes rather than exposing
  host paths, process details, or credentials?
- Does a malformed request consume a bounded amount of CPU/memory and release
  its socket promptly?

### 4. Add Deliberate Two-Sided Pairing

1. Keep mDNS discovery untrusted. It may show a candidate and endpoint but may
   not add capabilities, permissions, listener trust, or selectable status.
2. Add explicit pairing UI/controller callbacks rather than allowing discovery
   to call `NodeRegistry.promote_to_trusted()` by itself.
3. The target must visibly approve the pairing request and install a grant for
   the initiating node. The initiator must persist its target record only after
   target provisioning and an authenticated `hello` verify the expected node
   identity.
4. Default every new peer grant to the smallest required read permission set,
   preferably dashboard read only. Never default process view, storage review,
   termination, force termination, or cleanup just because the target supports
   them.
5. Persist every side's update before publishing it to runtime state. On any
   persistence failure, leave the old in-memory/runtime grant untouched.
6. Re-pairing after identity change requires a new explicit ceremony; it must
   not silently repair an identity mismatch from discovery metadata.

Questions to answer while coding:

- How does the operator verify the physical/person-controlled target before
  accepting pairing material?
- What is the UX if the target approves pairing but the initiator crashes
  before persisting its record? The target grant should be harmless and
  revocable; the initiator should re-pair rather than assume success.
- What is the UX if only one side revokes? The safe result is denial and an
  explicit re-pair prompt, never an automatic regrant.
- Are permissions selected on the target machine, with a clear description of
  the data/actions granted to that named caller?

### 5. Compose an Opt-In Target Listener

1. Add a small component responsible only for constructing the target's
   `RemoteService` and owning listener start/stop. It receives injected local
   provider, local `ProcessManager`, target grant resolver, descriptor data,
   and configuration; it imports no Tk widgets.
2. `AppWindow` remains the composition root. It creates this component after
   local node identity and cluster state are loaded, starts it only when remote
   access is enabled, and passes its actual bound endpoint to discovery.
3. Change `DiscoverySession` advertisement to `connectable=True` and the
   actual bound port only after the listener has started successfully. On stop
   or failure, advertise no usable endpoint.
4. Use a bounded connection/handler model. Do not use one unbounded daemon
   thread per connection. Track active sockets and task cancellation tokens.
5. Listener shutdown order:

```text
mark listener stopping
    -> stop accepting new sockets
    -> close/interrupt active sockets
    -> signal active request cancellation
    -> wait only a bounded grace period for handlers
    -> release listener resources
    -> continue AppCoordinator/UI shutdown
```

6. Integrate listener stop ahead of discovery and UI destruction in
   `AppWindow._finalize_shutdown`. Preserve existing discovery-first shutdown
   semantics so no late network event reaches a dying UI.

Questions to answer while coding:

- Does binding to all interfaces require an explicit user setting, while the
  default remains disabled or loopback-only?
- Are IPv4, IPv6, DNS, and multi-homed endpoints represented without treating
  a changed IP as a changed node identity?
- If the listener cannot bind after a sleep/wake or VPN transition, does the
  app stay usable locally and retry listener setup safely?
- Can shutdown complete deterministically when one target provider ignores
  cooperative cancellation? The listener may not leave untracked non-daemon
  work behind.

### 6. Implement Connection Lifecycle Without Another Coordinator

1. Add explicit connection state owned by `NodeContext`/`NodeRegistry`, not by
   widgets. Suggested values: `DISCOVERED`, `TRUSTED`, `CONNECTING`, `ONLINE`,
   `DEGRADED`, `OFFLINE`, `AUTHENTICATION_FAILED`, and `IDENTITY_CHANGED`.
2. Keep trust/pairing and connectivity as separate axes. A peer can be trusted
   but offline; it can be online in discovery but not trusted; an identity
   mismatch makes it non-selectable regardless of reachability.
3. Use node-qualified `AppCoordinator` connection keys such as
   `node:<id>:connect`. There must be at most one in-flight connect/hello per
   node.
4. Store retry attempt count and next eligible monotonic deadline per node.
   Drive all due connections from one existing application reconciliation timer
   or background poll callback. Do not allocate a timer/thread per node.
5. Use capped exponential backoff with jitter and a bounded maximum probe rate.
   Discovery endpoint changes, explicit retry, process wake, or network route
   change may make an earlier retry eligible. Component refresh schedules must
   remain unchanged.
6. Successful authenticated `hello` verifies the target identity/fingerprint,
   updates an endpoint only after durable persistence, clears backoff, attaches
   the provider/context, and records `ONLINE`.
7. A timeout, refused connection, route failure, or temporary disappearance
   records `DEGRADED`/`OFFLINE`, retains last-known-good data, and schedules a
   bounded retry. Authentication/identity failures stop automatic retries until
   an explicit re-pair/recovery action.

Illustrative state transition rule:

```python
def record_connect_failure(
    context: NodeContext, now: float, reason: PeerFailure
) -> None:
    if reason in {PeerFailure.AUTHENTICATION, PeerFailure.IDENTITY_CHANGED}:
        context.connection = replace(
            context.connection,
            state=connection_state_for(reason),
            next_attempt_at=None,
        )
        return
    attempt = min(context.connection.attempt + 1, MAX_BACKOFF_EXPONENT)
    context.connection = replace(
        context.connection,
        state=NodeConnectionState.DEGRADED,
        attempt=attempt,
        next_attempt_at=now + bounded_backoff(attempt),
    )
```

Questions to answer while coding:

- Is a reconnect job cancelled before the selected node changes, app closes, or
  a target is revoked?
- Can an old successful connect completion attach a provider after a newer
  identity mismatch, endpoint change, or shutdown? It must be rejected by
  generation/state checks.
- Is the backoff clock monotonic and injectable for deterministic tests?
- Does a DHCP address update require authenticated verification before the new
  address overwrites a trusted record? It must.

### 7. Normalize Remote Read-Only System Data

1. Make the local and remote paths produce one typed, node-bound snapshot
   contract. A remote provider must decode `NodeSnapshot`, verify that its
   `node_id` equals the authenticated selected target, and retain the snapshot
   metadata instead of immediately discarding it.
2. Add `NodeContext` state for the authoritative node snapshot while retaining
   its existing dashboard snapshot mirror during the migration. Avoid a broad
   UI rewrite.
3. Build a local adapter/wrapper at the controller/provider boundary that
   constructs the same `NodeSnapshot` from the local `Analyzer` plus local
   descriptor. The UI receives normalized state and cannot distinguish psutil
   data from peer transport data.
4. Preserve all resources supported by the current dashboard: CPU, memory,
   storage, GPU, network, battery, temperatures, and capability state.
5. Keep separate per-node AppCoordinator keys/caches for full snapshots and
   components. A slow/offline peer must consume only its own worker/connection
   path; it must not block local scanning, local rendering, or another node.
6. Use `NodeSnapshot.is_stale()` and explicit connection state to label stale
   values. Retain last-known-good values rather than blanking the dashboard on
   a temporary peer failure.
7. Fix node selection render invalidation to clear every actual node-scoped
   render target, including the dashboard snapshot target. The UICoordinator
   remains responsible only for coalescing/visibility/stale-intent rejection.

Questions to answer while coding:

- Does a remote snapshot whose signed envelope target is correct but whose
  inner `NodeSnapshot.node_id` differs get rejected? It must.
- Does an unsupported remote capability render as unavailable rather than a
  scan error or a guessed zero value?
- Can a hidden pending render for Node A appear after switching to Node B and
  later showing the dashboard? It must not.
- Is each node's last good snapshot kept separately, including timestamps and
  card failure counters?

### 8. Complete Read-Only Remote Process Viewing

1. Reuse the existing `ProcessDialog` and its node-qualified coordinated scan
   key. Do not create a second process table, duplicate filtering/sorting, or
   move process classification to the initiating UI.
2. On dialog construction, bind the dialog permanently to its target provider,
   node ID, display title, coordinator key, and action backend. Changing the
   dashboard selection later must not retarget an open dialog.
3. The target's provider produces normalized `ProcessCandidate` records. It is
   responsible for target-specific protected/can-quit classification. The
   initiator displays that data and preserves PID plus create-time identity.
4. This delivery is read-only. Do not add cleanup or expand remote process
   termination. Existing remote action endpoints, if retained, remain outside
   this scope and require their own independent safety and idempotency proof.
5. Correct the action interface drift before extending it: either migrate all
   local/dialog/remote code to `ProcessRef`, or change the protocol declaration
   to the actual PID plus expected-create-time signature. Do not leave a type
   contract that claims a safety property production code does not use.
6. Pass an explicit `force_quit_allowed` input based on both target
   `PROCESS_FORCE_TERMINATION` capability and target-owned permission. Keep the
   target-side authorization check even if the button is hidden.

Questions to answer while coding:

- If the dialog closes while a remote process scan is in flight, is its
  AppCoordinator subscription removed and is the eventual result ignored?
- If Node A is offline after a dialog opens and the dashboard switches to Node
  B, does the dialog show a Node A-specific failure/last-known state rather
  than Node B data?
- Are local protected process, foreign-user, PID reuse, and child safety rules
  still enforced by the target `ProcessManager` for any pre-existing action?
- Can a peer lie about `action_allowed` to cause local termination? It must
  not, because target execution remains the final authority.

### 9. Documentation, Migration, and Compatibility

1. Add explicit cluster schema migration only if grant/listener persistence
   cannot be represented as a safe optional additive field. Do not bump schema
   merely for a preference or runtime-only state.
2. Legacy trusted records must not become silently more privileged. On missing
   per-caller target grants, deny remote access or require explicit pairing;
   initiator-side legacy read permissions cannot authorize the target.
3. Keep the current public wire operations and response shape where possible.
   Additive metadata must be ignored only when it is safe to do so; security
   fields require strict version handling.
4. Update README only once actual remote read availability is shipped. Document
   that discovery is untrusted, pairing is deliberate, permissions are managed
   on the target, and remote cleanup is not provided.
5. Never write secrets, raw signed envelopes, full process lists, or remote
   metrics to logs, tests, documentation, or error dialogs.

## Test Plan

Add focused repository tests beside the existing relevant suites. Test fixtures
must use synthetic node IDs, fake credentials, fake providers, fake clocks,
and fake sockets; never use a real local secret or real process data.

### Transport and Authentication: `tests/test_remote_contract.py`

- Valid two-peer HMAC or TLS/pinned-identity exchange.
- Wrong credential, unknown caller, missing caller ID, wrong target ID, wrong
  response node ID, stale request/response, replay, and incompatible version.
- Exact envelope validation: unexpected fields, malformed JSON/UTF-8, over-size
  frame, invalid numeric values, booleans in numeric fields, and unexpected
  operation parameters.
- Signed target authorization/capability denials over real loopback socket.
- Refused connection, timeout, cancellation during receive, malformed peer
  response, and unavailable-peer mapping.
- Target listener stop during active request; verify bounded completion and no
  late response delivery.
- Read retry behavior and no automatic retry of pre-existing destructive
  operations without proven idempotency.

### Grants and Persistence: `tests/test_cluster.py` and `tests/test_nodes.py`

- Grant round trip and atomic failure leaves previous runtime/persisted state.
- Malformed/duplicate/unknown permissions fail closed.
- Target grant is per caller; Caller A's permission does not grant Caller B.
- Trusted-but-not-permitted caller denies; permitted caller succeeds; revoked
  caller denies on its next request; stale initiator record denies safely.
- Legacy trusted records do not acquire destructive access.
- Identity change remains non-selectable and requires deliberate re-pairing.

### Listener and Discovery: `tests/test_discovery_session.py`,
`tests/test_coordinator_discovery.py`, and new focused peer-service tests

- Listener starts before a connectable advertisement and stops before endpoint
  is advertised unavailable.
- Bind failure, restart, double start/stop, and shutdown while a handler is
  active remain safe/idempotent.
- Peer starts after the initiator, disappears, returns, changes DHCP address,
  changes Wi-Fi/VPN route, sleeps/wakes, and application restarts.
- Endpoint persistence changes only after authenticated hello verifies pinned
  identity.

### Lifecycle: `tests/test_node_context.py`, `tests/test_node_selection.py`,
and `tests/test_window_nodes.py`

- Explicit state transitions for trusted/offline/connecting/online/degraded,
  authentication failure, and identity change.
- Retry is bounded: one in-flight connection per node, capped backoff, no
  per-node timer creation, no reconnect after revoke/shutdown, and no stale
  completion attaches an obsolete provider.
- Local component refresh intervals/deadlines are unchanged while a remote
  peer is unavailable.
- Node switch cancels old node work before context render/schedule and rejects
  old queued render intents.

### Snapshots and UI: `tests/test_window_nodes.py`,
`tests/test_render_coordinator.py`, and snapshot codec tests

- Local and remote providers normalize to the same node-bound snapshot shape.
- Remote inner snapshot target mismatch is rejected even if outer signature is
  otherwise valid.
- Per-node cache isolation, last-known-good stale state, unsupported capability
  presentation, remote failure presentation, and local UI responsiveness while
  a peer blocks.
- Hidden Node A dashboard render cannot commit after a switch to Node B.

### Processes: `tests/test_process_table.py`, `tests/test_window_nodes.py`, and
`tests/test_process_protection.py`

- Read-only remote process list retains search/filter/sort and target-bound
  ProcessDialog title/key/provider.
- Opening for Node A then selecting Node B leaves the existing dialog bound to
  Node A only.
- Protected/can-quit display and PID/create-time values survive remote codec.
- Read permission denial prevents dialog open; no termination permission makes
  it read-only; absent force capability/permission never offers force quit.
- Existing target process safety checks remain authoritative for any separately
  retained remote action and no remote cleanup operation exists.

## Completion Criteria

The feature is complete only when all statements below are true.

- Two ordinary System Analyzer installations can deliberately pair, start a
  target listener, discover a connectable endpoint, authenticate each other,
  and exchange typed read-only data without a central server.
- The target independently authenticates the caller and authorizes every typed
  operation from its own per-caller grant and capability state.
- Discovery never creates trust or permissions; trust never implies permission.
- Revocation, malformed input, capability absence, stale identity, and stale
  request/session state fail closed.
- Connection retries are bounded, cancellable, node-qualified, and separate
  from component scan cadence; no unavailable peer freezes local UI.
- Dashboard data is normalized and node-bound; per-node caches, generation
  protection, last-known-good state, and unsupported capability handling hold.
- Remote process viewing is read-only, target-bound, and cannot silently change
  targets as the dashboard selection changes.
- No generic remote execution, remote shell, arbitrary subprocess API,
  credential forwarding, arbitrary filesystem API, or remote cleanup is added.

## Required Validation Before Merge

Run focused tests first, then the full suite:

```sh
python -m unittest tests.test_remote_contract -v
python -m unittest tests.test_cluster -v
python -m unittest tests.test_nodes -v
python -m unittest tests.test_node_context -v
python -m unittest tests.test_node_selection -v
python -m unittest tests.test_window_nodes -v
python -m unittest tests.test_process_table -v
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
pyright
mypy --ignore-missing-imports .
git diff --check
```

Run `./lr impact`, `./lr 7`, and `./lr secrets` if the repository's LR tool is
restored. It is currently absent from this checkout, so its absence is a
blocked validation item, not a pass.

Because this changes authentication, authorization, persistent grants, network
transport, retries, and shutdown behavior, treat implementation as high risk:
perform a BugGuard Mode A review with full adversarial validation before merge.

## Research Basis

- Python recommends `hmac.compare_digest()` for comparison with externally
  supplied authentication values:
  <https://docs.python.org/3/library/hmac.html>.
- Python socket timeouts and `create_connection()` provide the primitives for
  explicit bounded network operations:
  <https://docs.python.org/3/library/socket.html>.
- OWASP states that authorization is distinct from authentication, must deny by
  default, and must be verified on every protected request at the protected
  resource boundary:
  <https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html>.
- OWASP notes that TLS provides confidentiality, integrity, and server
  authentication, while mutual TLS additionally authenticates clients:
  <https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html>.

External guidance defines required security properties. Repository code and
tests remain the source of truth for actual behavior.

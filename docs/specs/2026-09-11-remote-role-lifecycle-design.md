# Remote Role Lifecycle and Temporary Dashboard Design

**Status:** Approved in brainstorming on 2026-09-11

## Goal

Fix the Coordinator/Worker revoke pipeline and add explicit, authenticated
connection, job, and temporary-dashboard lifecycle controls without weakening
trust, authorization, target safety, failover, or existing local behavior.

## Confirmed Semantics

- **Revoke:** Coordinator-only. Invalidates trust and permissions, disconnects
  the Worker, removes the Worker from the Coordinator's trusted connection
  state, and requires a new authenticated invite to reconnect.
- **Remove connection:** Coordinator or Worker. Detaches the active relationship
  but preserves trusted pairing credentials and reconnect eligibility. It does
  not revoke permissions or cluster trust. Reconnection is explicit rather than
  automatic until the user connects again.
- **Remove job:** Coordinator-only. Removes the Worker from the active job
  assignment while preserving trust and the Worker role. The Worker keeps the
  same normal collection types at **20% of normal frequency/participation**.
  Reassignment restores 100% participation.
- **Temporary dashboard:** Requires the existing authenticated pairing/trust
  flow. It is read-only, creates no cluster membership, enables no collection,
  and writes no data to the Coordinator timeline. Coordinators and Workers may
  use it to view another authenticated local.
- **Confirmation:** Every remove action requires explicit confirmation:
  Remove connection, Remove job, and Revoke. Cancelling a confirmation makes
  no state change.

## Existing Boundaries

The implementation extends existing owners rather than introducing another
cluster manager, scheduler, executor hierarchy, or authority model:

- `maintenance/components/cluster_roles.py` remains the owner of role and job
  state transitions.
- `maintenance/nodes.py` remains the owner of trust, connection state, provider
  attachment, node identity, and visibility.
- `maintenance/ui/window_node_actions.py` remains the owner of trusted-node
  cleanup and provider invalidation.
- `maintenance/components/peer_connection.py` remains the owner of connection
  reconciliation, manual disconnect state, retry suppression, and heartbeat/
  failover integration.
- `maintenance/remote.py` and `maintenance/remote_support/` remain the owners
  of typed authenticated remote requests, target-side authorization, and
  transport behavior.
- `maintenance/ui/cluster_page.py` and `maintenance/ui/nodes_connections.py`
  remain presentation-only and emit semantic callbacks.
- Existing provider, process, filesystem, and target safety owners remain
  authoritative for their domains.

## State Model

The existing role assignment will gain a backward-compatible active-job state.
Old persisted assignments default to an active assignment at 100%. Removing a
job clears the active assignment and selects the fixed 20% participation mode;
it does not use `paused`, because pause already means collection is stopped.

The lifecycle states are deliberately independent:

1. **Connected and assigned:** trusted, authenticated, active provider,
   collection at 100%.
2. **Connected without a job:** trusted, authenticated, active provider,
   collection at 20%.
3. **Connection removed:** trusted pairing remains, active provider/session is
   detached, automatic reconnect is disabled, and explicit Connect is required.
4. **Revoked:** role is revoked, trusted record and peer grant are removed,
   provider is invalidated, operations and renders are cancelled, and a new
   invite is required.

The 20% policy is applied at the existing Worker collection/upload decision
point. It does not create a second scheduler or a new remote execution system.

## Operation Flows

### Revoke

1. Coordinator confirms the action.
2. The authenticated, fenced `revoke_worker` operation changes role state.
3. On successful persistence, the Coordinator uses the canonical trusted-node
   cleanup path: remove trusted record and grant, invalidate the provider,
   cancel node operations and peer connection, invalidate late-result
   generations, and refresh node/render state.
4. The target rejects future requests from the revoked credential.
5. The Worker removes the Coordinator relationship when the authenticated
   disconnect is observed; it cannot silently reconnect.

Revoke must not be implemented as only `RoleState.revoke`; that was the source
of the current bug because the role flag changed without completing connection,
grant, provider, and visibility cleanup.

### Remove Connection

1. Coordinator or Worker confirms the action.
2. The active provider/session is detached on the initiating side.
3. A typed authenticated `remove_connection` control request is sent when the
   peer is reachable so the other side can detach its matching session.
4. If the peer is offline, local removal still succeeds and a persisted/runtime
   manual-disconnect marker suppresses automatic reconnect.
5. Trusted records, pairing credentials, role assignment, and future explicit
   reconnect eligibility remain intact.

### Remove Job

1. Coordinator confirms the action.
2. The active Worker assignment is cleared and persisted.
3. Collection categories remain unchanged, but the existing collection cadence
   is reduced to 20%.
4. Snapshot acceptance continues to require authenticated identity, role,
   cluster ID, epoch, fencing token, and valid assignment state.
5. Reassigning the job restores 100% participation.

### Temporary Dashboard

The existing authenticated provider and read-only snapshot path are reused. A
temporary view does not create a `RoleAssignment`, add a peer grant, enable
Worker uploads, or write to Coordinator history. It only opens the named
authenticated local's dashboard data after identity and capability validation.

## UI Contract

### Coordinator Controls

Each non-local Worker row may expose:

- `Open`
- `Remove connection`
- `Remove job`
- `Revoke`
- Existing `Pause` / `Re-enable`

The controls remain separate: Remove connection affects the session, Remove job
affects collection participation, and Revoke affects trust and permissions.

### Worker Controls

The Worker sees `Remove connection` for its current Coordinator relationship.
It does not see Revoke, Remove job, or role-management controls.

### Confirmation Text

- Remove connection: “The connection will close, but trusted reconnect remains
  available.”
- Remove job: “This removes the active assignment and reduces normal collection
  to 20%.”
- Revoke: “This invalidates trust and permissions. A new invite is required to
  reconnect.”

## Failure and Compatibility Rules

- Failed Revoke persistence or authenticated control leaves the current
  connection intact and reports the failure.
- Failed Remove connection control still records local manual disconnect and
  prevents automatic reconnect; the user may retry explicit Connect.
- Failed Remove job persistence leaves the assignment and 100% participation
  unchanged.
- Late results are rejected by existing generation and node-qualified operation
  keys.
- Revoked credentials fail closed in both the target service and local provider.
- Temporary dashboard access never enables uploads or timeline writes.
- Existing pairing, identity fingerprint, TLS fingerprint, capability, epoch,
  fencing, and target-side safety checks remain unchanged.

## Security Invariants

Tests must prove:

- Workers cannot revoke, remove jobs, or manage other nodes.
- Only an active Coordinator can revoke or remove jobs for its Workers.
- Revoke removes grants and invalidates providers.
- Remove connection preserves trust but suppresses automatic reconnect.
- Stale epoch/fencing tokens cannot mutate role or job state.
- Temporary dashboard access requires authenticated pairing and correct node
  identity.
- No arbitrary RPC, unrestricted collection, or target-side safety bypass is
  introduced.

## Test Matrix

Focused coverage will include:

- RoleState revoke versus connection removal versus job removal.
- Backward-compatible persistence defaults and round trips.
- Coordinator and Worker button visibility and callback semantics.
- Confirmation acceptance and cancellation.
- 100% and 20% participation behavior.
- Offline peers and failed control requests.
- Existing pairing, failover, grant invalidation, node switching, and
  late-result behavior.
- Temporary dashboard read-only access with no collection or timeline writes.
- Slow operations, cancellation, and stale-generation rejection.
- Full repository tests, package/wheel contents, compile checks, diff checks,
  formatting, Ruff, Pyright, and Mypy where installed.

## Explicit Non-Goals

This change does not add pooled resources, arbitrary remote execution, a second
scheduler, a second executor hierarchy, shared database replication, automatic
destructive retries, unauthenticated dashboard sharing, or automatic cluster
membership for temporary remote viewing.

## Acceptance Criteria

- Revoke removes the Worker from active trusted connection state and requires a
  new invite.
- Remove connection disconnects without revoking trust and requires explicit
  reconnect.
- Remove job clears assignment and reduces normal collection to 20%.
- Reassignment restores 100% collection participation.
- All remove actions require confirmation.
- Workers cannot access Coordinator-only controls.
- Temporary dashboard viewing uses authenticated pairing and creates no cluster
  membership or data collection.
- Existing failover, trust, authorization, target-safety, node-isolation, and
  Tk-thread guarantees remain intact.

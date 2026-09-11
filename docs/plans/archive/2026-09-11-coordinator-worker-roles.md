# Coordinator/Worker Roles and Failover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Coordinator, Worker, and Subcoordinator cluster roles with Coordinator-owned bounded SQLite history, 24-hour standby buffering, authenticated failover, role-aware pairing controls, and no regression to target-side safety.

**Architecture:** Extend the existing `NodeRegistry`/`NodeContext` and `ClusterState` with persisted role and fencing-epoch state; do not replace or parallel them. Add only focused pure role-transition helpers and a storage adapter behind the existing `PeerConnectionManager`, `AppCoordinator`, `ComponentRefreshScheduler`, providers, diagnostics, and Tk composition. The active Coordinator polls typed Worker snapshots into a capped local SQLite store; the Subcoordinator receives a capped rolling buffer and promotes only after a signed lease timeout. No new cluster manager, worker manager, scheduler, authority model, or lifecycle framework is introduced.

**Tech Stack:** Python 3, dataclasses/enums, SQLite3, HMAC-authenticated existing remote protocol, Tkinter/ttk, unittest, JSON persistence, Ruff, Pyright, Mypy, compileall, and existing fake-widget/provider test infrastructure.

---

## Approved Design and Scope

Authoritative design: `docs/specs/2026-09-11-coordinator-worker-roles-design.md`.

Required behavior:

- The first cluster creator becomes Coordinator + Worker.
- Exactly one active Coordinator and at most one Subcoordinator exist.
- The Coordinator can also execute Worker jobs.
- Only the active Coordinator assigns Worker/Subcoordinator roles and issues pairing-only invites.
- Workers cannot see other Workers or cluster history; the Coordinator sees enrolled Workers.
- Pause and Revoke are separate controls.
- Coordinator SQLite activates only after Coordinator status is assigned and is capped at 2 GB.
- Subcoordinator keeps a rolling 24-hour authenticated snapshot buffer capped at 256 MB.
- Subcoordinator promotes after 2 minutes without a valid heartbeat.
- A returning former Coordinator rejoins as Worker.
- Monotonic cluster epochs and signed fencing tokens prevent stale Coordinators acting after failover.
- Target-side authentication, authorization, capabilities, identity checks, and destructive safety remain authoritative.
- Current hardware, filesystem, process, and UI operations remain target-bound; no arbitrary movable execution is added.

## Existing Files and Planned Responsibilities

- Modify `maintenance/nodes.py`: role state, cluster epoch references, and role-aware node descriptors while preserving stable identity and node-qualified keys.
- Modify `maintenance/cluster.py`: versioned persistence for roles, leases, invites, epochs, and Coordinator metadata with atomic migration.
- Modify `maintenance/remote.py`: typed invite, role, heartbeat, snapshot, standby, and fencing operations using existing authenticated envelopes; no generic RPC.
- Create `maintenance/components/cluster_roles.py`: focused pure role transition, lease, promotion, fencing, pause, and revoke helpers called by existing `NodeRegistry`/`ClusterState` owners; no Tk, sockets, SQLite, persistence, executor, or lifecycle ownership.
- Create `maintenance/components/cluster_storage.py`: a storage adapter called by the existing collection/connection composition; it owns only SQLite schema, bounded retention/size enforcement, low-disk degradation, and standby buffer storage, not scheduling or node lifecycle.
- Modify `maintenance/components/peer_connection.py`: use existing connection lifecycle to deliver authenticated heartbeats/snapshots and stop stale peers.
- Modify `maintenance/components/coordinator.py`: expose cluster-role decisions through the existing lifecycle without creating a second scheduler or executor hierarchy.
- Modify `maintenance/ui/window_discovery.py`, `maintenance/ui/nodes_connections.py`, and `maintenance/ui/cluster_page.py`: pairing role section, invite flow, role state, pause/re-enable/revoke controls, and failure states.
- Modify `maintenance/diagnostics.py` and `maintenance/ui/diagnostics_page.py`: bounded role, lease, storage, buffer, and failover diagnostics.
- Modify `maintenance/window.py` and node composition modules only as composition roots; no role logic belongs in Tk controller methods.
- Create `tests/test_cluster_roles.py`: pure role state machine, lease, fencing, and pause/revoke tests.
- Create `tests/test_cluster_storage.py`: SQLite schema, caps, purge, low-disk, buffer, and recovery tests.
- Modify `tests/test_cluster.py`, `tests/test_remote_contract.py`, `tests/test_remote_security.py`, `tests/test_peer_connection.py`: persistence, typed protocol, auth, and lifecycle regressions.
- Modify `tests/test_nodes_connections_page.py`, `tests/test_cluster_page.py`, `tests/test_window_nodes.py`, and `tests/test_diagnostics.py`: UI/controller and diagnostics state coverage.
- Create `docs/CLUSTER_ROLES_FAILOVER_2026-09-11.md`: actual implementation, operational limits, recovery guarantees, and known gaps.

Do not modify `maintenance/actions.py` or move hardware/process/filesystem acquisition. Do not replace `NodeRegistry`, `ClusterState`, `AuthenticatedNodeProvider`, `PeerConnectionManager`, `AppCoordinator`, `ComponentRefreshScheduler`, or existing UI composition. Do not add a network-mounted SQLite file, a `ResourceGovernor`, leader election, arbitrary command execution, or manual execution-node selection.

## Required Skill and Review Gates

Implementation workers must use the repository's existing patterns and load these skills at the relevant tasks:

- `consolidating-responsibilities` before adding role predicates, persistence codecs, storage limits, or transport helpers.
- `evolving-apis-and-schemas` before changing `ClusterState`, wire envelopes, schema versions, or persisted JSON.
- `UI` and `reviewing-interface-quality` before pairing/cluster UI implementation and review.
- `investigating-performance` before SQLite retention, buffer writes, or collection cadence changes.
- `verifying-before-completion` before each task is marked complete and before any release claim.
- `BugGuard` at final review. Agent 5 and the four BugGuard subagents are unavailable in this runtime; use the fallback below instead of claiming their review occurred.

Fallback BugGuard evidence must include: repository-truth audit against the approved spec; fresh countertests for split-brain, stale epoch, revoked node, invite replay, role escalation, storage cap, disk-full, buffer overflow, late snapshot, and node-switch isolation; official Python/SQLite documentation checks where behavior is uncertain; full tests plus static gates; and a written residual-risk table naming every unavailable tool or reviewer.

## Task 1: Add the Role Domain Model

**Files:**
- Modify: `maintenance/nodes.py`
- Create: `maintenance/components/cluster_roles.py`
- Create: `tests/test_cluster_roles.py`
- Modify: `tests/test_nodes.py`

- [ ] **Step 1: Write failing role-model tests.**

Test `ClusterRole.WORKER`, `ClusterRole.COORDINATOR`, and `ClusterRole.SUBCOORDINATOR`; assert a Coordinator implies Worker, two active Coordinators are rejected, two Subcoordinators are rejected, and a Worker cannot assign roles.

```python
def test_coordinator_always_has_worker_role(self) -> None:
    assignment = RoleAssignment(frozenset({ClusterRole.COORDINATOR}))
    self.assertIn(ClusterRole.WORKER, assignment.roles)


def test_worker_cannot_assign_cluster_roles(self) -> None:
    with self.assertRaises(RoleAuthorizationError):
        RoleState.assign(
            actor=RoleAssignment(frozenset({ClusterRole.WORKER})),
            target=NodeId("peer"),
            roles=frozenset({ClusterRole.WORKER}),
        )
```

- [ ] **Step 2: Run the tests to verify the missing domain types fail.**

Run: `python3 -m unittest tests.test_cluster_roles -v`

Expected: FAIL with an import failure for `maintenance.components.cluster_roles`.

- [ ] **Step 3: Implement the pure role types and transitions.**

Define immutable `RoleAssignment`, `CoordinatorLease`, `RoleChange`, `PromotionDecision`, and `RoleState`. `RoleState.assign` must require an active Coordinator actor, reject Coordinator assignment to a peer, enforce one Subcoordinator, force Coordinator to include Worker, and reject role changes for revoked/unknown nodes. `RoleState.pause` and `RoleState.revoke` must be separate transitions.

- [ ] **Step 4: Add fencing-epoch decisions.**

Define `CoordinatorEpoch(epoch: int, coordinator_id: NodeId, fencing_token: str, issued_at: float, lease_expires_at: float)` and pure functions `renew_lease`, `can_promote`, and `promote_subcoordinator`. Return `PromotionDecision(role_assignment, epoch)` from promotion. Require strictly increasing epochs, an expired prior lease, a trusted authenticated Subcoordinator, and one promotion attempt per epoch. Reject stale epochs and tokens without mutating current state.

- [ ] **Step 5: Run the pure role tests and commit.**

Run: `python3 -m unittest tests.test_cluster_roles tests.test_nodes -v`

```bash
git add maintenance/nodes.py maintenance/components/cluster_roles.py tests/test_cluster_roles.py tests/test_nodes.py
git commit -m "feat: add cluster role and fencing model"
```

### Task 2: Versioned Role and Invite Persistence

**Files:**
- Modify: `maintenance/cluster.py`
- Modify: `tests/test_cluster.py`
- Create: `tests/test_cluster_roles_persistence.py`

- [ ] **Step 1: Write failing persistence tests.**

Round-trip role assignments, Coordinator epoch, lease, invite expiry, paused/revoked state, and Subcoordinator identity. Assert old schema v1 JSON loads with default local Coordinator state and no remote role escalation.

```python
def test_expired_invite_is_rejected_without_persisting_a_peer(self) -> None:
    state = ClusterState.create_local()
    invite = state.create_invite(now=100.0, ttl_seconds=60.0)
    with self.assertRaises(InviteExpiredError):
        state.consume_invite(invite.token, now=160.1)
    self.assertEqual(state.trusted_nodes, ())
```

- [ ] **Step 2: Run the persistence tests and verify the missing fields fail.**

Run: `python3 -m unittest tests.test_cluster tests.test_cluster_roles_persistence -v`

Expected: FAIL because role, epoch, and invite codecs are not present.

- [ ] **Step 3: Add versioned persisted models.**

Extend `ClusterState` with `role_assignments`, `coordinator_epoch`, `active_invite_hashes`, and bounded role-change metadata. Store invite tokens only as hashes with expiry and target identity. Add explicit schema version migration; reject malformed role values, duplicate Subcoordinators, negative epochs, expired leases, and unknown node references.

- [ ] **Step 4: Preserve atomic writes and safe defaults.**

Use the existing atomic persistence path. On load failure, retain the existing safe fallback behavior and never promote a remote node from corrupted or missing data. The local node remains the only automatically trusted initial Coordinator.

- [ ] **Step 5: Run persistence regressions and commit.**

Run: `python3 -m unittest tests.test_cluster tests.test_cluster_roles_persistence tests.test_nodes -v`

```bash
git add maintenance/cluster.py tests/test_cluster.py tests/test_cluster_roles_persistence.py
git commit -m "feat: persist cluster roles and invites safely"
```

### Task 3: Extend the Existing Authenticated Protocol

**Files:**
- Modify: `maintenance/remote.py`
- Modify: `maintenance/cluster.py`
- Modify: `tests/test_remote_contract.py`
- Modify: `tests/test_remote_security.py`

- [ ] **Step 1: Write failing typed-protocol tests.**

Test invite creation/consumption, role assignment, heartbeat lease renewal,
snapshot upload, standby batch upload, pause, revoke, stale epoch, wrong
Coordinator identity, replayed request ID, and oversized payload rejection.

Add the test helper `signed_role_request(service, *, op, epoch, fencing_token)`
that calls the existing `sign_request` envelope function with `node_id` set to
the persisted Coordinator identity, `caller_node_id` set to that same identity,
the named `op`, a params object containing `cluster_id`, `epoch`, and
`fencing_token`, request ID `role-test-1`, nonce `role-nonce-1`, timestamp
`service.clock()`, and the test secret. Serialize the returned envelope with
`json.dumps` and pass that text through the existing `RemoteService.handle`
verification path; do not call a new transport API.

```python
def test_stale_coordinator_epoch_cannot_pause_a_worker(self) -> None:
    request = signed_role_request(
        self.service, op="pause_worker", epoch=4, fencing_token="old-token"
    )
    with self.assertRaises(RemoteAuthorizationError):
        self.service.handle(request)
```

- [ ] **Step 2: Run the remote tests and verify new operations fail closed.**

Run: `python3 -m unittest tests.test_remote_contract tests.test_remote_security -v`

Expected: new typed-operation tests fail before protocol support exists; all
existing security tests remain green.

- [ ] **Step 3: Add explicit allowlisted operation types.**

Extend the existing operation maps with `consume_invite`, `assign_role`,
`renew_coordinator_lease`, `worker_snapshot`, `standby_batch`, `pause_worker`,
and `revoke_worker`. Define typed request/response payload codecs with strict
fields, maximum batch size, node identity, cluster ID, epoch, fencing token, and
request ID. Unknown operations and unknown capability values remain rejected or
ignored exactly as the current protocol contract requires.

- [ ] **Step 4: Enforce target-side authorization and fencing.**

The target verifies HMAC, freshness, replay identity, caller identity, target
identity, cluster ID, current role, permission, capability, and highest epoch
before changing local state. A Worker cannot assign roles or send control
operations. A stale Coordinator token cannot mutate roles, pause, revoke, or
overwrite snapshots. Snapshot and standby payloads are accepted only from the
current Coordinator/Worker relationship and are bounded before decoding.

- [ ] **Step 5: Add protocol compatibility and older-peer behavior.**

Advertise role/failover capabilities through the existing hello negotiation.
Older peers remain readable only through already-supported operations and cannot
be promoted or assigned Subcoordinator until they advertise the required
capabilities. Do not infer role support from software version alone.

- [ ] **Step 6: Run security regressions and commit.**

Run: `python3 -m unittest tests.test_remote_contract tests.test_remote_security tests.test_cluster -v`

```bash
git add maintenance/remote.py maintenance/cluster.py tests/test_remote_contract.py tests/test_remote_security.py
git commit -m "feat: add authenticated cluster role protocol"
```

### Task 4: Add Bounded Coordinator and Standby Storage

**Files:**
- Create: `maintenance/components/cluster_storage.py`
- Create: `tests/test_cluster_storage.py`
- Modify: `maintenance/cluster.py`

- [ ] **Step 1: Write failing SQLite storage tests.**

Cover schema creation, normalized snapshot insertion, per-node/timestamp query,
oldest-first purge at 2 GB, 256 MB standby purge, 24-hour age cutoff, duplicate
batch IDs, malformed rows, and no fabricated values.

Define the test helper `make_batch(batch_id, size_bytes)` to return
`SnapshotBatch(batch_id=batch_id, source_node_id=NodeId("coordinator"),
source_epoch=3, sequence=int(size_bytes), observed_at=100.0,
payload=(ResourceSnapshot(NodeId("worker"), "cpu", "10%", 10.0, 100.0),),
encoded_size=size_bytes)`. The helper must use finite values and a fresh batch ID.

```python
def test_standby_buffer_purges_oldest_batch_at_size_cap(self) -> None:
    store = StandbyBuffer(self.temp_dir / "standby.db", max_bytes=256 * 1024 * 1024)
    store.append(make_batch("old", size_bytes=200 * 1024 * 1024))
    store.append(make_batch("new", size_bytes=100 * 1024 * 1024))
    self.assertEqual(store.batch_ids(), ("new",))
```

- [ ] **Step 2: Run storage tests and verify missing storage APIs fail.**

Run: `python3 -m unittest tests.test_cluster_storage -v`

Expected: FAIL because the storage adapter and schema do not exist.

- [ ] **Step 3: Implement the Coordinator SQLite schema.**

Define immutable `ResourceSnapshot(node_id, metric, display_value, numeric_value,
percent, observed_at)` and `SnapshotBatch(batch_id, source_node_id, source_epoch,
sequence, observed_at, payload, encoded_size)`. Create `StorageStatus(bytes_used,
max_bytes, row_count, oldest_at, newest_at, history_writes_paused, warning)`.
Create `CoordinatorTimeline` with explicit tables for schema metadata, nodes,
resource snapshots, capability states, collection status, and data gaps. Use
parameterized SQL, WAL only when supported by the local filesystem, busy timeout,
transactions per bounded batch, and indexes on `(node_id, metric, observed_at)`.
Never store credentials or full request payloads.

- [ ] **Step 4: Implement hard size, retention, and disk guards.**

Enforce the 2 GB cap before and after writes, purge oldest rows first, enforce
the 24-hour standby age and 256 MB cap, and expose `StorageStatus` with bytes,
row count, oldest/newest timestamps, and `history_writes_paused`. Catch only
classified SQLite full/IO/locked errors; preserve latest in-memory snapshots and
record a bounded warning. Do not run unbounded vacuum or a background storage
thread.

- [ ] **Step 5: Implement standby import without duplication.**

Import only authenticated batches with a higher source sequence, matching
cluster ID, valid Coordinator epoch, and normalized records. Duplicate batch IDs
are idempotent. Missing final batches create a data-gap record. Import is bounded
per transaction and may resume after interruption.

- [ ] **Step 6: Run storage tests and commit.**

Run: `python3 -m unittest tests.test_cluster_storage tests.test_cluster tests.test_cluster_roles -v`

```bash
git add maintenance/components/cluster_storage.py tests/test_cluster_storage.py maintenance/cluster.py
git commit -m "feat: add bounded cluster timeline storage"
```

### Task 5: Integrate Collection, Heartbeats, and Failover Into Existing Lifecycles

**Files:**
- Modify: `maintenance/components/peer_connection.py`
- Modify: `maintenance/components/coordinator.py`
- Modify: `maintenance/components/cluster_storage.py`
- Modify: `maintenance/nodes.py`
- Modify: `tests/test_peer_connection.py`
- Create: `tests/test_cluster_failover.py`

- [ ] **Step 1: Write failing lifecycle tests.**

Test the first Coordinator lease, heartbeat renewal, Worker snapshot upload,
standby batch delivery, 2-minute timeout, one promotion, stale old epoch,
returning Coordinator as Worker, failed upload, cancelled upload, and local
collection continuing while a Worker is slow.

Construct the fixture with `RoleState` containing Coordinator `NodeId("coord")`,
Subcoordinator `NodeId("sub")`, epoch `7`, and `last_heartbeat_at=100.0`.
Inject a monotonic `FakeClock` and the existing `PeerConnectionManager` with
`AppCoordinator` and `ComponentRefreshScheduler` fakes; do not instantiate a
new scheduler or executor in the test.

```python
def test_subcoordinator_promotes_once_after_two_minutes(self) -> None:
    state = self.state_with_subcoordinator()
    self.clock.now = 100.0 + 120.1
    result = promote_subcoordinator(state, now=self.clock.now)
    self.assertIn(ClusterRole.COORDINATOR, result.role_assignment.roles)
    self.assertEqual(result.epoch.epoch, state.epoch.epoch + 1)
```

- [ ] **Step 2: Run failover tests to verify missing integration fails.**

Run: `python3 -m unittest tests.test_cluster_failover tests.test_peer_connection -v`

Expected: FAIL because role-aware heartbeats, snapshot delivery, and promotion
are not integrated.

- [ ] **Step 3: Extend the existing peer lifecycle.**

After the existing authenticated hello, register the peer's cluster role and
capabilities. Use the existing Coordinator delivery path and bounded connection
runner for heartbeat and snapshot requests. Never create one executor or timer
per node. Keep the current cancellation and identity-generation checks.

- [ ] **Step 4: Add bounded collection and standby cadence.**

Use `ComponentRefreshScheduler` for collection cadence. `AppCoordinator` remains
the operation owner and coalesces one key per node/operation. The Coordinator
writes accepted Worker snapshots to `CoordinatorTimeline` and sends bounded
standby batches to the Subcoordinator. A Worker upload cannot block local UI or
another node's key.

- [ ] **Step 5: Implement failover and return fencing.**

At 120 seconds without a valid heartbeat, call the pure promotion decision,
persist the incremented epoch atomically, activate Coordinator storage, import
standby data, and publish the new lease. A returning former Coordinator must
accept the current epoch and register as Worker; it must not self-promote from a
stale local lease. Reject duplicate promotion attempts and stale responses.

- [ ] **Step 6: Run lifecycle tests and commit.**

Run: `python3 -m unittest tests.test_cluster_failover tests.test_peer_connection tests.test_multi_node_concurrency tests.test_lifecycle_stress -v`

```bash
git add maintenance/components/peer_connection.py maintenance/components/coordinator.py maintenance/components/cluster_storage.py maintenance/nodes.py tests/test_peer_connection.py tests/test_cluster_failover.py
git commit -m "feat: integrate bounded cluster failover"
```

### Task 6: Implement Pairing Roles and Coordinator Controls in Existing UI

**Files:**
- Modify: `maintenance/ui/window_discovery.py`
- Modify: `maintenance/ui/nodes_connections.py`
- Modify: `maintenance/ui/cluster_page.py`
- Modify: `maintenance/window.py`
- Modify: `tests/test_nodes_connections_page.py`
- Modify: `tests/test_cluster_page.py`
- Modify: `tests/test_window_nodes.py`

- [ ] **Step 1: Write failing UI state tests with existing recording widgets.**

Test that the active Coordinator sees editable Worker/Subcoordinator controls,
Workers see read-only roles, Coordinator cannot be unchecked, a second
Subcoordinator control is disabled, and a joining node cannot edit Coordinator.

Add the test fixture `build_connections_page(actor_role)` around the existing
`NodesConnectionsPage` recording-widget factory. It must return the page object
and expose the existing role-row controls by stable test IDs
`"role:worker"`, `"role:subcoordinator"`, and `"role:coordinator"`; production
code must not depend on those test IDs.

```python
def test_worker_cannot_edit_cluster_roles(self) -> None:
    page = build_connections_page(actor_role=ClusterRole.WORKER)
    self.assertFalse(page.worker_role_control.is_enabled())
    self.assertFalse(page.subcoordinator_role_control.is_enabled())
    self.assertFalse(page.coordinator_role_control.is_enabled())
```

- [ ] **Step 2: Run UI tests to verify missing role controls fail.**

Run: `python3 -m unittest tests.test_nodes_connections_page tests.test_cluster_page tests.test_window_nodes -v`

Expected: FAIL because the pairing and cluster pages have no role controls.

- [ ] **Step 3: Add the Cluster Role section to the existing pairing shell.**

Use existing checkbox/row/card primitives and callbacks. Render Worker,
Subcoordinator, and non-editable Coordinator status. Gate editable controls on
the current authenticated Coordinator role, current node identity, existing
pairing state, and one-Subcoordinator constraint. Keep the existing trust and
permission controls separate from role assignment.

- [ ] **Step 4: Add invite and pairing states.**

Render first-time, waiting/slow, success, failure, disconnected Coordinator,
disabled Worker, and revoked states. Expired or failed invites clear all partial
role state. Do not let UI state alone grant trust or permissions; callbacks call
the authenticated role operation and render its result on the Tk thread.

- [ ] **Step 5: Add pause, re-enable, and revoke controls.**

Expose separate Coordinator-only actions on the existing cluster page. Pause
keeps pairing but stops uploads/work assignment. Revoke invalidates provider,
removes cluster visibility, and requires a new invite. Disable controls while a
request is in flight and reject stale callbacks by node and generation.

- [ ] **Step 6: Run UI tests and commit.**

Run: `python3 -m unittest tests.test_nodes_connections_page tests.test_cluster_page tests.test_window_nodes tests.test_navigation tests.test_ui_primitives -v`

```bash
git add maintenance/ui/window_discovery.py maintenance/ui/nodes_connections.py maintenance/ui/cluster_page.py maintenance/window.py tests/test_nodes_connections_page.py tests/test_cluster_page.py tests/test_window_nodes.py
git commit -m "feat: add coordinator worker pairing controls"
```

### Task 7: Add Cluster Diagnostics and Storage Warnings

**Files:**
- Modify: `maintenance/diagnostics.py`
- Modify: `maintenance/ui/diagnostics_page.py`
- Modify: `tests/test_diagnostics.py`
- Modify: `tests/test_diagnostics_page.py`

- [ ] **Step 1: Write failing bounded diagnostics tests.**

Project role, epoch/lease state, last heartbeat, database bytes, standby bytes,
retention pressure, last snapshot, failover reason, and storage-write-paused
state. Assert secrets, fencing tokens, invite hashes, full payloads, and private
Worker data never appear in serialized diagnostics.

Define `ClusterDiagnostic(role, coordinator_id, epoch, heartbeat_age_seconds,
database_bytes, database_cap_bytes, standby_bytes, standby_cap_bytes,
retention_pressure, last_snapshot_at, history_writes_paused, failure)` with
`failure` truncated to the existing diagnostics maximum. Keep the fencing token,
invite hash, and raw node permissions outside this model.

```python
def test_cluster_diagnostics_redact_fencing_and_invite_values(self) -> None:
    diagnostic = ClusterDiagnostic(
        "coordinator", "coord", 8, 3.0, 100, 2_000, 20, 256, "normal", 100.0,
        False, "none",
    )
    serialized = serialize_cluster_diagnostic(diagnostic)
    self.assertNotIn("fencing-token", serialized)
    self.assertNotIn("invite-secret", serialized)
    self.assertLessEqual(len(diagnostic.failure or ""), 160)
```

- [ ] **Step 2: Run diagnostics tests and verify missing fields fail.**

Run: `python3 -m unittest tests.test_diagnostics tests.test_diagnostics_page -v`

Expected: FAIL because the diagnostics model has no cluster runtime projection.

- [ ] **Step 3: Add an optional bounded cluster diagnostic projection.**

Define immutable `ClusterDiagnostic` with role, coordinator ID, connection state,
epoch number, heartbeat age, database bytes/cap, standby bytes/cap, retention
pressure, latest snapshot time, storage-write-paused, and sanitized failure.
Never include secrets, hashes, full permissions, or raw payloads. Preserve
existing diagnostics constructor compatibility with an optional field.

- [ ] **Step 4: Render role and storage status with existing UI primitives.**

Add a Cluster section to the diagnostics page. Show `No cluster configured`,
`Waiting for Coordinator`, `Collecting`, `Standby`, `Promoting`, `Disabled`,
`Revoked`, `Storage limit reached`, and `History writes paused` states. Keep
updates on the existing Tk delivery path.

- [ ] **Step 5: Run diagnostics tests and commit.**

Run: `python3 -m unittest tests.test_diagnostics tests.test_diagnostics_page tests.test_cluster_page -v`

```bash
git add maintenance/diagnostics.py maintenance/ui/diagnostics_page.py tests/test_diagnostics.py tests/test_diagnostics_page.py tests/test_cluster_page.py
git commit -m "feat: expose bounded cluster diagnostics"
```

### Task 8: Documentation, Migration, and Operational Limits

**Files:**
- Create: `docs/CLUSTER_ROLES_FAILOVER_2026-09-11.md`
- Modify: `tests/test_package_structure.py`

- [ ] **Step 1: Document actual implementation boundaries.**

Describe current role assignment, invite-only pairing, Coordinator-owned SQLite,
24-hour/256 MB standby, 2 GB database cap, 2-minute failover, fencing epochs,
pause/revoke, visibility rules, target-side authorization, and all known
degraded states. Separate implemented behavior from future multi-Worker pure
computation.

- [ ] **Step 2: Document recovery and operator procedures.**

Explain how to inspect role/lease/storage diagnostics, re-enable a paused
Worker, revoke a compromised node, re-pair a revoked node, recover after disk
pressure, and understand a recorded data gap after failover. State that a
returning Coordinator is a Worker until explicitly promoted.

- [ ] **Step 3: Add package/import/migration tests.**

Assert imports remain Tk-free, old cluster JSON migrates safely, new modules have
one responsibility, and no application entrypoint creates a Tk root on import.

- [ ] **Step 4: Review docs and commit.**

Run: `python3 -m unittest tests.test_package_structure tests.test_cluster tests.test_cluster_roles_persistence -v`.

```bash
git add docs/CLUSTER_ROLES_FAILOVER_2026-09-11.md tests/test_package_structure.py
git commit -m "docs: define cluster roles and recovery limits"
```

### Task 9: Fallback BugGuard, Adversarial Review, and Performance Gates

**Files:**
- Create: `tests/test_cluster_adversarial.py`
- Create: `docs/bug_hunts/CLUSTER-ROLES-20260911-fallback-review.md`
- Inspect: all files changed by Tasks 1-8

- [ ] **Step 1: Write countertests before the final claim.**

Add tests for stale Coordinator epoch, stale fencing token, split-brain return,
invite replay, invite expiry, Worker role escalation, duplicate Subcoordinator,
revoked late snapshot, wrong cluster ID, wrong target node, oversized snapshot,
SQLite full, standby overflow, duplicate import, missing final snapshot, and
node-switch late delivery.

Define `RevokedRuntime` as a test-only object containing `registry`,
`worker_id`, `old_epoch`, and `accept_snapshot(batch)`. Its `accept_snapshot`
method must call the production target validation path and return the existing
typed `SnapshotRejection.REVOKED` result without mutating the registry.
Define `signed_snapshot(epoch)` with the existing authenticated snapshot codec,
using the revoked Worker identity, its old epoch, a unique request ID, and a
valid HMAC; the test must prove rejection occurs because of revocation rather
than malformed input.

```python
def test_revoked_worker_late_snapshot_cannot_restore_visibility(self) -> None:
    runtime = RevokedRuntime.from_revoked_worker()
    result = runtime.accept_snapshot(signed_snapshot(runtime.old_epoch))
    self.assertEqual(result, SnapshotRejection.REVOKED)
    self.assertFalse(runtime.registry.has_node(runtime.worker_id))
```

- [ ] **Step 2: Run the countertests independently.**

Run: `python3 -m unittest tests.test_cluster_adversarial -v`

Expected: every adversarial case passes; any failure blocks release and is
recorded with the exact reproduction and affected boundary.

- [ ] **Step 3: Perform the fallback repository-truth audit.**

Compare every approved-spec requirement with implementation and tests. Search
for duplicate role predicates, direct SQLite access outside the storage adapter,
new schedulers/executors, arbitrary RPC, unsafe process/file reroute, unchecked
role messages, secrets in diagnostics, and stale-result paths. Record findings,
countertest evidence, and residual risk in the fallback review document.

- [ ] **Step 4: Perform official documentation checks where uncertain.**

Verify Python `sqlite3` transaction/locking behavior, SQLite WAL and file-size
behavior, and HMAC/freshness assumptions against the official Python and SQLite
documentation. Record URLs, dates, and the exact implementation decision; do
not substitute blog posts for authority.

- [ ] **Step 5: Measure boundedness without inventing load optimization.**

Use deterministic in-memory fakes to measure placement/role decision cost by
node count, bounded batch write cost, purge cost, and promotion cost. Confirm no
network probe occurs on the UI thread, no thread-per-node behavior exists, and
memory/storage remain bounded at configured caps. Record measurements, not a
claim of cluster throughput optimization.

- [ ] **Step 6: Commit fallback evidence.**

Run: `git diff --check`.

```bash
git add tests/test_cluster_adversarial.py docs/bug_hunts/CLUSTER-ROLES-20260911-fallback-review.md
git commit -m "test: add cluster roles fallback assurance"
```

### Task 10: Full Validation, Wheel, and Handoff

**Files:**
- Inspect: complete repository diff and all files listed above
- Release: `dist/system_analyzer-<version>-py3-none-any.whl`, `dist/SHA256SUMS`

- [ ] **Step 1: Run focused role, protocol, storage, UI, and fallback suites.**

Run: `python3 -m unittest tests.test_cluster_roles tests.test_cluster_roles_persistence tests.test_cluster_storage tests.test_cluster_failover tests.test_remote_contract tests.test_remote_security tests.test_peer_connection tests.test_nodes_connections_page tests.test_cluster_page tests.test_diagnostics tests.test_diagnostics_page tests.test_cluster_adversarial -v`

Expected: zero failures and no unauthorized role transition, stale epoch, data
leakage, unbounded storage, or UI-thread violation.

- [ ] **Step 2: Run the full repository suite and compile checks.**

Run: `python3 -m unittest discover -s tests -v` and `python3 -m compileall -q maintenance tests`.

Expected: all tests pass. Record environmental warnings separately from failures.

- [ ] **Step 3: Run mandatory static and hygiene checks.**

Run independently: `ruff check .`, `ruff format --check .`, `pyright`, `mypy --ignore-missing-imports`, and `git diff --check`. If a command is unavailable, record the exact command-not-found output and do not call it passing.

- [ ] **Step 4: Build and verify the wheel.**

Run: `SA_VERSION_BUMP=auto ./install/build.sh`, `./install/verify.sh <built-wheel-version>`, and `sha256sum -c SHA256SUMS` from the `dist/` directory. Confirm the wheel contains the new role/storage modules, no forbidden paths, and the checksum matches.

- [ ] **Step 5: Review final architecture and working tree.**

Run: `git status --short`, `git diff --stat`, and `git log --oneline -10`. Confirm existing owners remain owners: scheduler decides when, existing AppCoordinator owns lifecycle, NodeRegistry/ClusterState own node/persistence state, target owns authorization/safety, and the new modules are adapters/helpers only.

- [ ] **Step 6: Prepare the final implementation report.**

Report role transitions, invite and permission behavior, storage caps, retention,
failover and fencing, visibility, pause/revoke, data-gap behavior, changed
files, test/static results, performance measurements, unavailable reviewers/tools,
known limitations, and final working-tree status. Do not claim Agent 5 or
BugGuard subagent review; identify the fallback evidence instead.

## Acceptance Checklist

- [ ] Existing architecture is extended, not replaced.
- [ ] Coordinator is a role, not a hidden superuser.
- [ ] One active Coordinator and at most one Subcoordinator are enforced.
- [ ] Coordinator + Worker is supported; Worker cannot self-promote.
- [ ] Pairing invites are Coordinator-generated, time-limited, and pairing-only.
- [ ] Role changes are Coordinator-only, authenticated, epoch-fenced, and persisted atomically.
- [ ] Target-side authorization and destructive safety remain authoritative.
- [ ] Coordinator history is capped at 2 GB; Subcoordinator standby is capped at 256 MB and approximately 24 hours.
- [ ] Disk-full, buffer-full, missing-snapshot, duplicate, replay, stale, and revoked states are explicit and bounded.
- [ ] Failover waits 2 minutes, promotes once, increments epoch, and prevents stale Coordinator activity.
- [ ] Returning Coordinator rejoins as Worker.
- [ ] Workers cannot view other Workers or cluster history.
- [ ] Pause and Revoke are separate and have distinct recovery paths.
- [ ] No second scheduler/executor, ResourceGovernor, shared network SQLite, arbitrary RPC, or destructive auto-retry is introduced.
- [ ] Full regression/static/release validation passes or every unavailable check is documented.

## Plan Self-Review

- **Spec coverage:** Tasks 1-2 cover roles, persistence, invites, and migration; Task 3 covers authenticated typed protocol and fencing; Task 4 covers bounded SQLite/standby storage; Task 5 covers existing lifecycle integration and failover; Task 6 covers pairing/role UI and controls; Task 7 covers diagnostics; Task 8 covers operational documentation; Task 9 covers fallback BugGuard evidence and performance; Task 10 covers complete validation and release.
- **Architecture boundary:** No task creates a replacement cluster manager. New modules are pure role helpers or storage adapters called by existing owners.
- **Security boundary:** Placement, role, and Coordinator control never replace target-side authorization. Epoch, token, identity, replay, cluster, and permission checks are required before mutation.
- **Edge-case coverage:** Expiry, replay, stale epoch, split-brain return, revocation, offline state, duplicate data, missing final snapshot, storage caps, disk pressure, low capability, UI stale callbacks, and unavailable static/reviewer tooling are explicit.
- **Scope:** This is one coordinated cluster-role/failover subsystem. Future movable computation remains explicitly out of scope.

## Closure Follow-Up

Implementation work and final review follow-up continue in `docs/plans/2026-09-11-coordinator-worker-roles-closure.md`. The closure plan narrows the remaining work to logical storage-cap wording, closure regressions, final BugGuard evidence, release validation, and documentation of unavailable tooling. The final full-A4 adversarial evidence is recorded in `docs/bug_hunts/patch_reviews/PATCH-20260911-002-review.md` (decision: `safe`; the two confirmed closure findings were resolved in-patch with guarded regressions).

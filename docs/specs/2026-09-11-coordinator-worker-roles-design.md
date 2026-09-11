# Coordinator/Worker Roles and Failover Design

**Status:** Approved in brainstorming on 2026-09-11

## Goal

Add explicit Coordinator, Worker, and Subcoordinator roles to the trusted-node
cluster. The Coordinator owns cluster orchestration and long-term history;
Workers provide approved collection work; one Subcoordinator maintains bounded
standby history and can take over after Coordinator failure.

## Existing Boundaries

The current application already owns these responsibilities:

- `maintenance/nodes.py`: `NodeRegistry`, `NodeContext`, stable identities,
  trust, capabilities, permissions, connection state, and node-qualified keys.
- `maintenance/remote.py`: authenticated typed requests, protocol validation,
  capability negotiation, target-side authorization, and bounded handlers.
- `maintenance/components/coordinator.py`: `AppCoordinator` generations,
  cancellation, coalescing, delivery, and `ComponentRefreshScheduler` cadence.
- `maintenance/cluster.py`: trusted-node persistence and atomic cluster state.
- `maintenance/diagnostics.py` and the diagnostics page: bounded runtime
  diagnostics and copyable diagnostic output.
- Existing providers and `maintenance/actions.py`: target-side data meaning,
  process safety, and filesystem safety.

The feature must extend these boundaries rather than create a new cluster
manager, executor hierarchy, scheduler, authority model, or shared filesystem.

## Core Model

Machines remain independent. There is no pooled RAM, pooled CPU, shared kernel,
distributed filesystem, or automatic migration of target-bound operations.

The initiating System Analyzer instance coordinates a request. Coordinator is a
coordination role, not a superuser. A Worker is an explicitly paired node that
provides supported collection work. Every target continues to enforce its own
authentication, authorization, capability, identity, and safety checks.

The first system that creates a cluster automatically becomes Coordinator and
Worker. There is exactly one active Coordinator and at most one Subcoordinator.
The Coordinator itself always retains Worker capability.

## Roles

### Coordinator

The active Coordinator:

- assigns Worker and Subcoordinator roles;
- generates time-limited, pairing-only invites;
- polls enabled Workers for authenticated snapshots;
- writes long-term history to its local SQLite database;
- sees all enrolled Workers and their collected data;
- can pause, re-enable, or revoke Workers;
- can assign or remove the single Subcoordinator;
- owns the active Coordinator lease.

Coordinator authority does not bypass target-side permissions or safety checks.

### Worker

A Worker:

- is explicitly paired into this Coordinator's cluster;
- advertises supported capabilities;
- sends only the typed data required by an approved request;
- sees its own local data and Coordinator connection state;
- cannot assign roles, manage other nodes, or read other Workers' data;
- retains only its bounded local filesystem data and no cluster timeline database.

A Coordinator is also a Worker. A Worker cannot select Coordinator status for
itself.

### Subcoordinator

The Subcoordinator is a Worker with one additional standby responsibility:

- only the active Coordinator can assign it;
- only one Subcoordinator may exist;
- it receives authenticated, normalized snapshot batches from the Coordinator;
- it retains a rolling 24-hour standby history capped at 256 MB;
- it has no active long-term SQLite timeline while it is merely a Worker;
- after failover it receives full Coordinator authority and activates SQLite.

## Pairing and Role UI

The existing pairing/connection flow gains a `Cluster Role` section using the
existing System Analyzer visual language and checkbox controls:

```text
Cluster Role
  [x] Worker
      Allows this system to provide approved collection work.

  [ ] Subcoordinator
      Keeps the rolling 24-hour standby history.
      Only one Subcoordinator may be assigned.

  Coordinator
      Assigned automatically by the active Coordinator.
```

Only the active Coordinator sees editable role controls for a joining node.
Workers see role state read-only. `Subcoordinator` is disabled when another
Subcoordinator exists. The active Coordinator cannot be unchecked. The joining
node cannot grant itself a role, permissions, or cluster access.

Pairing invites authorize pairing only. After authentication, the Coordinator
assigns the role and permissions. A failed or expired invite creates no trusted
node and no partial role. A revoked node loses cluster visibility and requires a
new invite.

The UI must cover first-time, waiting/slow connection, successful pairing,
pairing failure, disconnected Coordinator, disabled Worker, and revoked states.
No manual execution-node selector is included.

## Data Flow and Storage

```text
Worker provider
    -> authenticated snapshot upload
    -> active Coordinator
    -> validation and capability checks
    -> Coordinator SQLite timeline
    -> Coordinator dashboard and diagnostics

Active Coordinator
    -> signed standby batch
    -> Subcoordinator rolling 24-hour buffer
```

The Coordinator owns one local SQLite database, activated when Coordinator status
is assigned. It stores normalized timestamped snapshots, node identity, resource
values, capability state, and collection status. Its hard maximum is 2 GB.
Oldest timeline rows are purged first. Database maintenance is incremental. If
disk space becomes low, latest snapshots remain available while historical writes
pause and the UI reports the condition. Raw logs, credentials, request payloads,
and unlimited diagnostic history are not stored.

The Subcoordinator does not receive a copied SQLite file. While it is a Worker it
keeps only authenticated normalized snapshot batches in a separate rolling
standby buffer capped at 256 MB and approximately 24 hours, with oldest batches
discarded first. Other Workers retain only their bounded local filesystem data.

## Failover State Machine

1. The active Coordinator sends signed snapshot batches and heartbeats.
2. The Subcoordinator validates source identity and stores the bounded standby
   batches.
3. Two minutes without a valid Coordinator heartbeat marks the Coordinator
   unavailable and permits one Subcoordinator promotion attempt.
4. The Subcoordinator promotes itself to Coordinator + Worker, activates a new
   local SQLite database, and imports the latest valid standby history.
5. It becomes the only active Coordinator and continues collection.
6. A missing final snapshot is represented by a recorded data gap; the last
   valid standby batch is used and no value is fabricated.

Every promotion increments a monotonically increasing cluster epoch and issues
a signed Coordinator fencing token. Workers accept role changes, collection
commands, and control commands only from the highest valid epoch. The returning
former Coordinator therefore cannot continue acting on an older lease during a
partition; it must rejoin as Worker and obtain the current epoch from the active
Coordinator. Promotion and role changes are authenticated, signed, timestamped,
and rejected when issued by a non-Coordinator or stale epoch.

If the Coordinator shuts down cleanly, it flushes bounded pending data and
releases its lease. If it disappears, in-flight uploads fail or expire and the
Subcoordinator follows the same 2-minute rule. A Worker failure does not reroute
target-bound or destructive work. Destructive actions are never automatically
retried.

## Visibility and Controls

The Coordinator sees every enrolled Worker's connection state, capabilities,
permissions, current snapshots, and timeline. Workers see their own local data
and the Coordinator connection state; they do not see other Workers, the
Coordinator's SQLite file, or standby history.

A paired node without an assigned cluster role is not an enrolled Worker and
receives no cluster data. A node merely visible on the general network remains
outside this Coordinator's cluster until invited and paired.

The Coordinator has separate controls to pause/re-enable a Worker and to revoke
it. Pause preserves pairing but stops uploads and work assignment. Revoke removes
trust and cluster visibility, invalidates the provider, and requires a new
invite. These controls do not alter the target's own authorization rules.

## Security and Job Scope

Current operations are classified as follows:

- **LOCAL-BOUND:** Tk/UI work, local settings and persistence, local cleanup, and
  local-only window actions.
- **TARGET-BOUND:** CPU, memory, storage, GPU, network, battery, thermals,
  process enumeration and termination, filesystem review, cleanup, and hardware
  acquisition. Their data must come from the named target node.
- **MOVABLE:** only future typed pure computation with explicit inputs and output
  independent of hardware, files, processes, permissions, and UI. The current
  audit found zero movable jobs.

Placement filters trust, authentication, protocol compatibility, online state,
identity validity, shutdown state, required capability, required permission, and
target identity before ranking. Discovery never grants eligibility. A selected
node still independently validates the request. Node-qualified operation keys,
generation checks, cancellation, and UI-thread delivery remain mandatory.

No arbitrary command/function endpoint, unrestricted remote execution, shared
database file, or Coordinator superuser permission is introduced.

## Diagnostics

Diagnostics expose bounded current placement and cluster state, not a permanent
telemetry store. The Coordinator diagnostic view includes role, lease/heartbeat
state, database size, standby-buffer size, retention pressure, last successful
snapshot time, and the most recent failover or storage warning. Details are
truncated using the existing diagnostics limit. Credentials, secrets, full
payloads, and other Workers' private data are excluded.

## Testing Requirements

Tests must cover:

- first-cluster Coordinator + Worker assignment;
- role checkbox visibility, read-only Worker UI, and Coordinator-only edits;
- one Subcoordinator limit and role persistence;
- invite expiry, pairing timeout, and failure rollback;
- Worker pause versus revoke and immediate visibility loss;
- authenticated snapshot upload and target-side authorization;
- 2-minute heartbeat timeout and single promotion;
- lease conflict and split-brain prevention;
- returning Coordinator rejoining as Worker;
- 24-hour standby retention and 256 MB cap;
- 2 GB SQLite cap, oldest-first purge, low-disk degradation, and incremental
  maintenance;
- recovery from the last valid standby batch when the final upload is missing;
- Worker isolation and Coordinator-only cluster visibility;
- node-qualified keys, cancellation, generations, late results, and node
  switching;
- slow/offline Workers not blocking local collection or Tk delivery;
- full existing regression tests, compile checks, formatting, Ruff, Pyright, and
  Mypy where installed.

## Explicit Non-Goals

This design does not add pooled resources, Kubernetes-style orchestration,
leader election, multiple active Coordinators, a shared network SQLite file,
full database replication, a second scheduler, a second executor hierarchy, a
global pressure sampler, arbitrary RPC, manual execution-node selection, or
automatic retry of destructive operations.

## Alternatives Considered

1. Coordinator-owned SQLite with a bounded Subcoordinator standby buffer is
   selected because it provides long-term history with bounded Worker storage
   and a small recovery window.
2. Full SQLite replication was rejected because it adds conflict resolution,
   storage growth, and distributed-database complexity not required by the
   product goal.
3. Stateless Workers with latest-snapshot-only recovery was rejected because it
   loses too much timeline data during Coordinator failure.

## Success Criteria

The feature is complete when one active Coordinator can enroll and control
Workers through pairing-only invites, collect authenticated snapshots into a
bounded local timeline, maintain a bounded 24-hour standby history, promote the
Subcoordinator after 2 minutes, prevent split-brain on return, and preserve all
existing trust, authorization, target-safety, lifecycle, node-isolation, and
Tk-thread guarantees.

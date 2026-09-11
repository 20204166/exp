# Cluster Roles and Failover

## Implemented Boundary

The local installation created a cluster is the Coordinator and Worker. Trusted
peers are Workers by default. A Subcoordinator is an optional trusted role and
is the only peer eligible for the bounded standby buffer. Role changes are
stored in `cluster.json`; schema version 1 documents are accepted and receive
safe local Coordinator defaults.

Role changes are Coordinator-only and are represented by explicit allowlisted
authenticated operations. Requests carry the cluster ID, epoch, and fencing
token. Target-side HMAC, caller identity, permission, capability, and replay
checks remain authoritative. The existing process and filesystem action
backends are unchanged and remain target-bound.

## Storage And Failover

Coordinator history is local SQLite at `cluster-history.sqlite3`, with a logical
2 GB cap and oldest-first batch retention. The cap is based on the sum of each
retained batch's encoded payload size, not the physical SQLite file, journal,
WAL, or filesystem allocation. Standby storage uses the same bounded adapter
with a 256 MB logical cap and a 24-hour age limit. Duplicate batch IDs are
idempotent. Storage failures, including disk-full, locked-database, and SQLite
I/O errors, pause history writes and expose a bounded warning; they do not block
collection or mutate target safety. Operators should use that warning together
with filesystem monitoring for physical disk pressure.

The Coordinator lease expires after 120 seconds without a valid heartbeat. The
pure promotion decision increments the epoch and issues a fresh fencing token.
Stale epochs and tokens cannot mutate role or snapshot state. A former
Coordinator must rejoin as Worker under the current epoch rather than
self-promoting from an old local lease.

## Controls And Recovery

Pause stops role-driven uploads while retaining the pairing/trust record.
Re-enable resumes that role. Revoke is separate: it invalidates the peer
provider, removes trusted visibility, and requires a new pairing flow.

Diagnostics expose only role, coordinator identity, epoch, heartbeat age, bounded
storage status, retention pressure, and sanitized failure text. Secrets, invite
hashes, fencing tokens, permissions, and raw snapshot payloads are not included.

## Known Limits

- Current component work remains target-bound; this release does not move
  hardware, process, or filesystem jobs between nodes.
- Standby import and full runtime role transport are explicit typed extension
  points; no arbitrary RPC or shared network SQLite is used.
- Disk-full and locked-database conditions pause history writes while preserving
  the latest in-memory application state.
- Native macOS/Windows runtime validation requires those platforms.

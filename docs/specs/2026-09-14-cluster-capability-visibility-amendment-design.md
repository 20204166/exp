# Cluster Capability and Visibility Amendment Design

**Status:** Approved in brainstorming on 2026-09-14

## Goal

Refine the existing Coordinator/Worker role and remote lifecycle designs so that
cluster access is private and read-only by default, while allowing the active
Coordinator to grant narrowly scoped capabilities to a Subcoordinator. Preserve
the existing local behavior, safety boundaries, transport, fencing, failover,
temporary dashboard, and AppCoordinator implementations.

This document amends the visibility and delegated-authority portions of:

- `docs/specs/2026-09-11-coordinator-worker-roles-design.md`
- `docs/specs/2026-09-11-remote-role-lifecycle-design.md`

Where those documents describe general Worker visibility, this amendment takes
precedence: ordinary cluster pages are private/read-only for Workers and
Subcoordinators unless the target explicitly shares a temporary read-only
dashboard or the Subcoordinator has the relevant capability grant. The active
Coordinator remains the full-functionality authority for enrolled nodes in its
own cluster.

## Existing Boundaries

No new cluster manager, scheduler, executor hierarchy, shared database, or
general-purpose authorization layer is introduced. Existing owners remain
authoritative:

- `maintenance/nodes.py` owns identity, trust, pairing, permissions, provider
  attachment, connection state, and node visibility.
- `maintenance/remote.py` and `maintenance/remote_support/` own authenticated,
  typed requests, transport, protocol validation, and target-side authorization.
- `maintenance/components/cluster_roles.py` owns role and assignment state.
- `maintenance/cluster.py` owns trusted persistence and cluster epochs.
- `maintenance/components/coordinator.py` owns local operation coordination,
  caching, cancellation, coalescing, and delivery.
- Existing process, filesystem, provider, and action owners remain authoritative
  for target safety.

The feature adds only the smallest state and protocol operations required to
represent per-target capability grants and temporary dashboard shares.

## Authority Model

| Actor | Own page | Other pages in its cluster | Outside-cluster connections |
| --- | --- | --- | --- |
| Coordinator | Full local functionality | Full functionality by default | Read-only |
| Subcoordinator | Full local functionality | Read-only unless explicitly granted | Read-only |
| Worker | Full local functionality | Not visible unless explicitly shared | Read-only |

The Coordinator's full functionality over other nodes applies only to enrolled
nodes in its own cluster and still passes through target-side authorization and
the existing process/filesystem safety checks. It does not make the Coordinator
a universal superuser.

A Subcoordinator cannot grant or delegate capabilities. A Worker cannot elevate
its own permissions. Outside-cluster access cannot be elevated by a local
Coordinator.

## Temporary Dashboard Sharing

Dashboard sharing is explicit, temporary, authenticated, and read-only.

- A Worker or Subcoordinator starts sharing from its own dashboard.
- The share exposes a bounded dashboard snapshot only.
- Sharing does not create cluster membership, enable collection, add a grant,
  write to Coordinator history, or expose destructive controls.
- The owner can stop sharing immediately.
- The share expires at session end or when the node disconnects.
- An expired or revoked share is rendered as unavailable/stale, never as live
  controls.

The existing authenticated temporary-dashboard path is reused. No second share
transport or dashboard data store is introduced.

## Capability Grants

Only the active Coordinator may grant or revoke capabilities for a
Subcoordinator. A grant is scoped to:

- one Subcoordinator identity;
- one target node in the Coordinator's cluster; and
- one or more independently authorized capabilities.

The grant record contains a stable grant identifier, issuer, subject, target,
capability set, issue time, session/expiry information, and revocation state.
Grants are persisted only through the existing trusted cluster state owner when
their lifecycle requires persistence; temporary dashboard shares are never
restored across a restart.

Capabilities are composable. The initial capability vocabulary reuses existing
operation meanings and separates dangerous actions:

- CPU
- memory
- GPU
- storage
- network
- process review
- cleanup
- process termination

Read access does not imply cleanup or process termination. Cleanup and process
termination require separate grants and continue through the existing target
safety checks.

The protocol adds dedicated typed grant/revoke operations rather than overloading
role assignment. Every target operation validates the current authenticated
identity, cluster membership, target node, coordinator epoch/fencing token, and
capability grant. A hidden or disabled UI control is never treated as security.

## UI Contract

- Worker dashboards are private until `Share Dashboard` is activated.
- Shared pages display an unambiguous `Read-only` state and no action controls.
- The owner has `Stop Sharing`.
- The Coordinator has a per-node `Permissions` control for Subcoordinators.
- Permissions are shown as independent capability controls, with cleanup and
  termination visually separated and confirmation-protected.
- The Coordinator can revoke one capability, a target's complete grant, or all
  grants for a Subcoordinator.
- A Subcoordinator sees its own normal controls, read-only shared/cluster pages,
  and only the controls allowed by current grants.
- Outside-cluster pages remain read-only regardless of local role.
- The UI reflects expiry, disconnect, revocation, and authorization denial
  explicitly rather than silently falling back to stale live-looking controls.

The existing visual language, page router, diagnostics presentation, and node
connection pages remain in place. Changes are limited to visibility, permission
state, and semantic callbacks.

## Failure and Security Rules

- Unknown, expired, revoked, malformed, or target-mismatched grants fail closed.
- A non-Coordinator grant or revoke request is rejected.
- A stale epoch or fencing token cannot mutate grants.
- Disconnect invalidates temporary shares but does not silently elevate or alter
  durable role state.
- Failed grant persistence leaves the prior authorization state unchanged.
- Failed revocation reports the failure and does not claim access was removed;
  retry remains explicit.
- Authorization failures are bounded in diagnostics and contain no secrets or
  raw request payloads.
- The target node independently validates every read and action request.
- No arbitrary RPC, unrestricted remote execution, shared SQLite file, or
  automatic retry of destructive work is added.

## Diagnostics and Export

Diagnostics remains an app/developer diagnostic surface, not a user-facing
computer-monitoring feature. It may report bounded grant/share state, such as
capability names, expiry, revocation, and authorization failures, but never
credentials, tokens, raw payloads, or secrets.

The existing diagnostics page and capture export should be developer-only before
release. Internal observation may continue regardless of page visibility. The
capture remains a complete bounded snapshot of app diagnostics at save time.

## Testing Requirements

Focused tests must prove:

- default cluster visibility is private/read-only;
- temporary share requires authentication and is read-only;
- share stop, expiry, disconnect, and revocation remove visibility;
- Coordinator local and in-cluster authority is preserved;
- outside-cluster access remains read-only;
- grants are scoped by Subcoordinator and target node;
- CPU/memory/GPU/storage/network combinations work independently;
- process review, cleanup, and process termination remain separate;
- only the active Coordinator can grant or revoke;
- Subcoordinators cannot delegate or self-elevate;
- stale epoch/fencing and malformed grants fail closed;
- target-side authorization rejects manually constructed unauthorized requests;
- UI control visibility matches protocol authorization;
- existing local scans, cleanup safety, role lifecycle, failover, cancellation,
  stale-result rejection, and diagnostics behavior remain unchanged.

Run the repository gates after implementation:

```text
ruff check .
ruff format --check .
pyright
mypy --ignore-missing-imports .
python -m unittest discover -s tests -v
```

## Non-Goals

- Replacing the existing role model.
- Reworking the existing coordinator, scheduler, or executor.
- Adding a generic permissions framework unrelated to node operations.
- Making outside-cluster nodes controllable.
- Persisting temporary dashboard shares.
- Exposing diagnostics to ordinary users.
- Changing established local page functionality or safety behavior.

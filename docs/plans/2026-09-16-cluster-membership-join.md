# Cluster Membership Join — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: test-driven-development for every task below. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give trusted peers an explicit, Coordinator-authorized way to converge on one shared `cluster_id` and become canonical members of the same `RoleState.assignments`, without changing what ordinary Pair/Trust means and without wiring any other dormant role RPC.

**Architecture:** Complete the existing (currently dead) invite mechanism instead of inventing a parallel one. `ClusterState.create_invite()` starts stamping the issuing Coordinator's live `cluster_id` + `CoordinatorEpoch` onto the invite; a new pure helper encodes/decodes that invite (token + fence) into one copy-pasteable blob. The target's existing `consume_invite` wire handler (`maintenance/ui/window_discovery.py::handle_role_request`) gains one new step — admit the caller into `state.role_assignments` as `WORKER` via the existing `RoleState.assign()` (self-invoked with the Coordinator's own `local_assignment` as actor, no new authority model) — and returns the admitting node's live cluster fence. The initiator, on a successful response, locally adopts that fence (`cluster_id`, `coordinator_epoch`) and collapses its own `role_assignments` to a single `WORKER` entry, but only when its own cluster is still an untouched solo bootstrap (no other role assignments, no capability grants, no promotion history) — otherwise the join is refused so no meaningful existing cluster is silently destroyed. `RemoteService.update_cluster_fence` (already used by lease renewal) republishes the new fence to the initiator's own listener so subsequent role ops validate against the joined cluster, not the old solo one. Trust/pairing, `PlacementPolicy`/TARGET_BOUND wiring, and every other role RPC are untouched.

**Tech Stack:** Python 3.12, JSON cluster persistence (`maintenance/cluster.py`), the existing HMAC-signed role-op wire protocol (`maintenance/remote_support/protocol.py`), Tkinter (`simpledialog`/`messagebox`), `unittest`.

**Evidence this plan is built on** (re-verified against current HEAD, see `docs/REMOTE_CLUSTER_TRUE_FLOW.md` §27–29 and the fresh reads in this session):
- `ClusterState.create_local()` mints its own random `cluster_id` per installation (`maintenance/cluster.py:570-577`); every fresh install is Coordinator+Worker of a cluster of one.
- `create_invite` has zero production callers anywhere outside `maintenance/cluster.py` itself and `tests/test_cluster_roles_persistence.py`.
- `consume_invite`'s target-side handler (`window_discovery.py:184-207`) burns the invite and returns `{target_node_id, expires_at}` — it never touches `role_assignments`, so consuming an invite today grants no membership at all.
- `RemoteService._verify_role_fence` (`maintenance/remote.py:477-492`) already requires every "role operation" (including `consume_invite`) to carry the *target's own* live `cluster_id`/`epoch`/`fencing_token` — proving the invite must be the vehicle that teaches the joining node those values, not something it can know in advance.
- `set_node_roles`/`_save_role_state` (`window_node_actions.py:81-121`) mutate `RoleState` **purely locally** — no `assign_role` RPC is ever sent. This plan does not change that; it only makes the *membership* precondition for such future wiring real. Role RPC wiring stays out of scope, per the operating instructions for this phase.
- `update_listener_fence(controller, state)` (`window_discovery.py:693-701`) already republishes `cluster_id`/`coordinator_epoch`/`fencing_token` to the running listener; this plan reuses it verbatim after a join instead of writing a second copy.

## File Map

- Modify `maintenance/cluster.py`: additive invite fence fields, blob encode/decode, backward-compatible JSON parsing.
- Modify `maintenance/ui/window_discovery.py`: `consume_invite` branch of `handle_role_request` admits the caller as `WORKER` and returns the full fence.
- Modify `maintenance/ui/window_node_actions.py`: `create_cluster_invite`, `join_cluster_via_invite`.
- Modify `maintenance/ui/cluster_page.py`: `on_create_invite`/`on_join_cluster` callbacks and buttons.
- Modify `window.py`: wire the two new callbacks through to the node-actions module and a `simpledialog`-based blob display/entry.
- Test: `tests/test_cluster_roles_persistence.py`, `tests/test_remote_security.py`, `tests/test_window_nodes.py`.
- Docs: dated post-repair section in `docs/REMOTE_CLUSTER_TRUE_FLOW.md`.

## Task 1: Invite carries the issuing cluster's fence

**Files:** `maintenance/cluster.py`, `tests/test_cluster_roles_persistence.py`

- [ ] Write failing tests: `create_invite` stamps `cluster_id`, `coordinator_id`, `epoch`, `fencing_token` from the current `ClusterState`; `encode_invite_blob`/`decode_invite_blob` round-trip; decoding a malformed/truncated/tampered blob raises `ClusterDataError`; an invite created before this change (no fence fields) still parses from JSON with the fence fields defaulted so old persisted files don't crash `ClusterStore.load()`.
- [ ] Run `python -m unittest tests.test_cluster_roles_persistence -v`; confirm failures are "attribute/field missing", not import errors.
- [ ] Add `coordinator_id: str`, `epoch: int`, `fencing_token: str` fields to `InviteRecord` (defaulted so old rows decode); `create_invite()` fills them from `self.cluster_id`/`self.coordinator_epoch` (raise `ValueError` if `coordinator_epoch is None`, which cannot happen for any state that has been through `ClusterStore.load()`).
- [ ] Add `encode_invite_blob(invite: InviteRecord) -> str` / `decode_invite_blob(blob: str) -> InviteRecord` module-level functions: base64url(JSON) of `{token, cluster_id, coordinator_id, epoch, fencing_token, target_node_id, expires_at}`. Decoding validates every field's type and raises `ClusterDataError` on anything malformed — this is the one untrusted-input boundary a user could mis-paste into.
- [ ] Update `ClusterStore._parse_invites`/`_serialize` for the three new fields, tolerating their absence in old JSON (default `cluster_id=""`/`epoch=0`/`fencing_token=""` — an invite with an empty `cluster_id` can never satisfy `_verify_role_fence`, so old dead invites just keep failing closed instead of crashing).
- [ ] Run the cluster tests; commit `feat: bind cluster fence to pairing invites`.

## Task 2: Target-side consume_invite admits membership

**Files:** `maintenance/ui/window_discovery.py`, `tests/test_remote_security.py`

- [ ] Write failing tests (constructing `handle_role_request` scenarios the way existing `assign_role`/`renew_coordinator_lease` tests in `test_remote_security.py` already do): a valid `consume_invite` call adds the caller to `state.role_assignments` as `WORKER` and the response includes `cluster_id`/`coordinator_id`/`epoch`/`fencing_token` matching the target's live state; a caller who is not an active Coordinator's target (i.e. local node lost Coordinator role since the invite was minted) is rejected without mutating role state; a caller already present in `role_assignments` is a no-op re-admission (idempotent), not an error; save failure leaves both the invite and role state unchanged (existing "leaves state unchanged on save failure" pattern).
- [ ] Run `python -m unittest tests.test_remote_security -v`; confirm the new assertions fail because `role_assignments` is untouched today.
- [ ] In the `consume_invite` branch: after validating the invite (existing checks unchanged), require `ClusterRole.COORDINATOR in state.local_assignment.roles` (else `RemoteAuthError("this node is no longer the cluster coordinator")`); build one merged `ClusterState` that both consumes the invite and calls `RoleState(...).assign(actor=state.local_assignment, target=actor_id, roles=frozenset({ClusterRole.WORKER}))` (skip the `assign` call and keep the existing assignment if the caller already has a live entry, since `assign` raises on an existing revoked entry and this must be idempotent for repeated confirms); save once; return `{target_node_id, expires_at, cluster_id, coordinator_id, epoch, fencing_token}` read from the *saved* state.
- [ ] Run the focused tests; commit `feat: admit invite callers as cluster workers`.

## Task 3: Initiator-side join action

**Files:** `maintenance/ui/window_node_actions.py`, `tests/test_window_nodes.py`

- [ ] Write failing tests: joining with a well-formed blob against a trusted, online, `REMOTE_MANAGEMENT`-capable target adopts the returned `cluster_id`/`coordinator_epoch`, collapses `role_assignments` to local-only `WORKER`, clears `capability_grants`/`promotion_epochs`, and republishes the fence to `controller._peer_server` (assert `update_cluster_fence` was called with the new values, mirroring how `renew_coordinator_lease` is already tested); joining is refused with a clear, non-mutating error when the local cluster is not a solo bootstrap (more than one role assignment, or any paused/revoked assignment, or non-empty `capability_grants`/`promotion_epochs`); a malformed blob, an unknown/offline/untrusted target, or a target-side rejection each leave `ClusterState` completely unchanged; local save failure leaves the prior `ClusterState` in place and reports an error (matching `_save_role_state`'s existing failure handling).
- [ ] Run `python -m unittest tests.test_window_nodes -v`; confirm the new tests fail because the function does not exist yet.
- [ ] Implement `create_cluster_invite(controller) -> str | None`: refuse with `controller._nodes_error(...)` unless `ClusterRole.COORDINATOR in controller._cluster_state.local_assignment.roles`; otherwise call `state.create_invite()`, save, and return `encode_invite_blob(...)`.
- [ ] Implement `join_cluster_via_invite(controller, node_id: str, blob: str) -> None`: decode the blob (catch `ClusterDataError` → `controller._nodes_error`); check the solo-bootstrap guard described above; resolve the target context/provider the same way `test_connection` does; call `provider.consume_invite(invite.token, cluster_id=invite.cluster_id, epoch=invite.epoch, fencing_token=invite.fencing_token)`; on success, build the replacement `ClusterState` (new `cluster_id`, a fresh `CoordinatorEpoch` from the response, `role_assignments=(RoleAssignment(frozenset({WORKER}), node_id=local),)`, `capability_grants=()`, `promotion_epochs=frozenset()`); save; call `window_discovery.update_listener_fence(controller, saved_state)`; refresh the nodes/cluster pages; on any `RemoteAuthError`/`RemoteAuthorizationError`/`RemoteUnavailableError`/`RemoteExecutionError`, report via `controller._nodes_error` and change nothing.
- [ ] Run the focused tests; commit `feat: join a trusted peer's cluster via invite`.

## Task 4: Minimal UI surface

**Files:** `maintenance/ui/cluster_page.py`, `window.py`, `tests/test_window_nodes.py` (or the existing cluster-page test module if separate)

- [ ] Add `on_create_invite: Callable[[], None] | None = None` and `on_join_cluster: Callable[[str], None] | None = None` to `ClusterPageCallbacks`; add the two buttons in `_node_row`: "Create Invite" when `spec.is_local and spec.role_editable` (role_editable is already "local node is Coordinator" for every row, per `window_page_data.cluster_specs`); "Join Cluster" when `not spec.is_local and spec.trust in ("trusted", "authorised")`.
- [ ] Wire both callbacks in `window.py`'s `ClusterPageCallbacks(...)` construction: `on_create_invite` opens a read-only `simpledialog`/small dialog showing the encoded blob (reuse the existing `messagebox`-based copy pattern used for pairing approval text — no new dialog class needed for a single copyable string); `on_join_cluster` calls `simpledialog.askstring("Join cluster", "Paste the invite from the other machine:")` then `self._join_cluster_via_invite(node_id, blob)`.
- [ ] Add the two thin `AppWindow` methods (`_create_cluster_invite`, `_join_cluster_via_invite`) mirroring the existing `_pair_discovered_node`/`_revoke_node` one-line delegation style.
- [ ] Run the existing window/cluster-page GUI test module headlessly; commit `feat: expose cluster invite creation and join in the UI`.

## Task 5: Documentation

**Files:** `docs/REMOTE_CLUSTER_TRUE_FLOW.md`

- [ ] Add one dated section ("2026-09-16 — Cluster membership join") covering: before/after, the canonical membership owner (`RoleState.assignments`, unchanged — no new manager/file), the join path, what's persisted, migration (old invites without a fence fail closed, no destructive change), and remaining gaps (role-assignment RPCs for *other* roles/pause/revoke/capability sync still local-only by design; MOVABLE placement still dormant; invite creation still has no rate limiting/UI polish beyond one dialog).
- [ ] Commit `docs: record the cluster membership join repair`.

## Task 6: Full validation

- [ ] `scripts/run_tests.sh` (or the project's documented full-suite command); record the result honestly, including any pre-existing unrelated failures.
- [ ] `ruff check .`, `ruff format --check .`, `pyright`, `mypy --ignore-missing-imports .`; record pass/fail.
- [ ] Re-read the full diff once, end to end, confirming no other in-flight work in the tree was touched.
- [ ] Final report per the operating instructions (intended join semantics recovered, evidence, canonical owner, files changed, persistence/schema changes, migration behavior, adoption behavior, join authority, invitation status, UI path, wrong-cluster fencing, restart behavior, TARGET_BOUND regression check, trust/pairing regression check, tests, static checks, full suite, remaining gaps, working-tree status).

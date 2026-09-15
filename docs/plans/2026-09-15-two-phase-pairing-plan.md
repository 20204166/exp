# Two-Phase Pairing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace target-side immediate pairing grants with an expiring two-phase transaction that cannot leave durable authorization after cancellation or a lost initiator.

**Architecture:** Add an additive `PendingPairing` record to cluster state. The target persists only pending state after user approval; the initiator confirms only after local trust persistence; target-side confirm atomically promotes the exact pending transaction, while abort and expiry remove pending state. Keep existing active grants and injected legacy provisioners intact.

**Tech Stack:** Python 3.12, JSON cluster persistence, Tkinter, TLS/socket and in-process transports, `unittest`, `ruff`, `pyright`, `mypy`.

---

## File Map

- Modify `maintenance/cluster.py`: additive pending-pairing model, JSON parsing, pruning, and serialization.
- Modify `maintenance/remote_support/protocol.py`: transaction payload validation and operation metadata.
- Modify `maintenance/remote_support/server.py`: dispatch and validate confirm/abort control requests.
- Modify `maintenance/remote_support/transport.py`: preserve transaction request/response behavior for memory and socket transports.
- Modify `maintenance/remote.py`: initiator request, confirm, and abort methods with legacy request compatibility where required.
- Modify `maintenance/ui/window_discovery.py`: target approval creates pending state; target confirm/abort handlers mutate only matching pending state.
- Modify `maintenance/ui/window_node_actions.py`: initiator transaction ordering, cancellation, rollback, and best-effort abort.
- Modify `maintenance/ui/pairing_dialog.py`: retain pending status until confirmation completes and show transaction failure safely.
- Modify `tests/test_cluster.py`: persistence, pruning, malformed-record, and round-trip coverage.
- Modify `tests/test_remote_security.py`: protocol binding, confirm/abort authorization, idempotency, and transport coverage.
- Modify `tests/test_window_nodes.py`: local ordering, cancellation, rollback, and late-delivery coverage.
- Modify `tests/test_node_toplevel_dialogs.py`: pending/complete/error lifecycle coverage.

## Task 1: Add Pending Pairing Persistence

**Files:** `maintenance/cluster.py`, `tests/test_cluster.py`

- [ ] Write tests for round-tripping a pending record, missing `pending_pairings` defaulting to empty, expiry pruning, malformed records being ignored, and atomic save preserving active grants on failure.
- [ ] Run `python -m unittest tests.test_cluster -v`; verify the new tests fail because the model and field do not exist.
- [ ] Add immutable `PendingPairing` fields: `transaction_id`, `caller_node_id`, `identity_fingerprint`, `transport_fingerprint`, `secret`, `permissions`, and `expires_at`.
- [ ] Add `pending_pairings` to `ClusterState` with an empty default and JSON encode/decode support that tolerates old files.
- [ ] Add one canonical prune operation using the current clock; reject expired records before returning them.
- [ ] Run the cluster tests and commit: `feat: persist expiring pending pairings`.

## Task 2: Define Transaction Wire Operations

**Files:** `maintenance/remote_support/protocol.py`, `maintenance/remote_support/server.py`, `maintenance/remote_support/transport.py`, `tests/test_remote_security.py`

- [ ] Write failing tests for transaction ID/expiry validation, mismatched caller or secret rejection, unknown operation rejection, and exact request field validation.
- [ ] Run the focused remote tests and verify expected validation failures.
- [ ] Add `pair_confirm` and `pair_abort` control request validators. Require exact transaction binding fields and reject expired transactions.
- [ ] Keep the existing protocol version and active authenticated operation envelope unchanged; these are additive unauthenticated TLS-pinned pairing controls.
- [ ] Dispatch confirm and abort through the server’s existing pairing handler seam and return structured approved/error responses.
- [ ] Ensure memory and socket transports preserve cancellation and response decoding without mutating existing active-grant requests.
- [ ] Run `python -m unittest tests.test_remote_security -v` and commit: `feat: add pairing transaction protocol`.

## Task 3: Implement Target Pending/Confirm/Abort State Machine

**Files:** `maintenance/ui/window_discovery.py`, `maintenance/remote_support/server.py`, `tests/test_remote_security.py`, `tests/test_window_nodes.py`

- [ ] Write failing tests proving approval creates only pending state, confirm promotes the exact record, abort removes only the exact record, repeat confirm/abort is harmless, expiry denies confirmation, and target save failure leaves both pending and active grants unchanged.
- [ ] Run those tests and verify they fail because approval currently writes an active grant directly.
- [ ] Change target approval to persist `PendingPairing` with the request transaction and bounded expiry; return the transaction identifier only after save succeeds.
- [ ] Implement target confirm with a single state transition: prune expired records, compare all binding fields, replace the caller’s active grant, and remove the pending record in one atomic save.
- [ ] Implement target abort as an exact-match pending-record removal; never remove an active grant and treat already-absent records as safe completion.
- [ ] Prune pending records on cluster-state load and before confirm/abort authorization decisions.
- [ ] Run all target transaction tests and commit: `feat: complete target pairing transactions`.

## Task 4: Move Initiator Pairing To Confirm-After-Save

**Files:** `maintenance/remote.py`, `maintenance/ui/window_node_actions.py`, `maintenance/ui/pairing_dialog.py`, `tests/test_window_nodes.py`, `tests/test_node_toplevel_dialogs.py`

- [ ] Write failing tests proving the call order is target approval, local cluster save, target confirm; local save failure sends abort and restores discovery; cancellation sends abort; confirm failure rolls back local trust and sends abort; late results cannot confirm.
- [ ] Run the focused tests and verify they fail against the current one-step provisioner path.
- [ ] Replace the default network provisioner result with a transaction result containing transaction ID and target endpoint binding.
- [ ] Persist local trusted-node state only after target pending approval; issue confirm only after the local save succeeds.
- [ ] On cancellation, local save failure, confirm failure, or stale completion, restore the prior registry context and issue best-effort abort through the pinned transport.
- [ ] Keep `pair_discovered_node` synchronous for existing callers and preserve one-argument injected provisioners; only the production network path uses the two-phase transaction.
- [ ] Keep all registry, persistence, dialog, and messagebox mutations on Tk; only network request/response work runs through `AppCoordinator`.
- [ ] Run pairing/window/dialog tests and commit: `fix: finalize initiator pairing transactions`.

## Task 5: Compatibility And Lifecycle Coverage

**Files:** `tests/test_remote_security.py`, `tests/test_window_nodes.py`, `tests/test_node_toplevel_dialogs.py`, `maintenance/ui/pairing_dialog.py`

- [ ] Add tests for old cluster JSON, old active grants, legacy injected provisioners, duplicate transaction IDs scoped by caller, malformed permissions, stale expiry, dialog close during pending approval, and app shutdown during a pending worker.
- [ ] Run the focused suite and inspect that no active grant is created without confirmation.
- [ ] Make only the minimal dialog wording/state changes needed to distinguish target approval pending from active pairing success.
- [ ] Run `scripts/run_tests.sh tests.test_window_nodes tests.test_node_toplevel_dialogs tests.test_remote_security tests.test_cluster -v` and commit: `test: cover two-phase pairing lifecycle`.

## Task 6: Review, Validation, And Release Gate

**Files:** `docs/bug_hunts/patch_reviews/PATCH-20260915-003-review.md`

- [ ] Read the complete diff and verify only the approved pairing protocol scope changed; leave `docs/performance/observability/` and unrelated review artifacts untouched.
- [ ] Run `scripts/run_tests.sh` and require the full suite to pass.
- [ ] Run `ruff check .`, `ruff format --check .`, `pyright`, `mypy --ignore-missing-imports .`, and `git diff --check`; record pre-existing failures honestly if they remain.
- [ ] Run available LR/drift equivalents read-only; record that `./lr` is unavailable if still absent.
- [ ] Run fresh full A4 BugGuard opposition after this protocol change, then the required Agent 5 evidence audit after all four opposition reports.
- [ ] Update the patch review with reviewer evidence, rebuttal, final decision, and remaining risks.
- [ ] Do not build, commit, or push a release wheel until the target-side transaction tests and full A4 review permit release.

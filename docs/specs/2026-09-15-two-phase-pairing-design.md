# Two-Phase Pairing Design

## Goal

Prevent a target-side pairing grant from surviving an initiator cancellation,
local persistence failure, lost response, or crashed initiator. Pairing must
remain explicitly approved, read-only, TLS-pinned, and safe for mixed local
states.

## Scope

This design changes only the pairing handshake and its persisted target-side
pending state. Existing active trusted-node records, active peer grants,
post-pairing HMAC operations, authorization rules, and legacy injected test
seams remain supported.

## Protocol

The default network handshake becomes a two-phase transaction:

1. The initiator sends `pair_request` with its identity and transport
   fingerprints, proposed secret, read-only permissions, and the transactional
   pairing mode marker.
2. The target asks its local user for approval. Approval generates a fresh
   target-issued transaction ID, persists an expiring `PendingPairing`, not an
   active `PeerGrantRecord`, and returns approval with the complete transaction
   binding and fixed expiry timestamp.
3. The initiator persists its local trusted-node state. Only after that save
   succeeds does it send `pair_confirm`.
4. The target verifies the transaction ID, caller identity, proposed secret,
   fingerprints, and expiry. It atomically replaces any active grant for that
   caller with the pending grant and removes the pending record.
5. On cancellation, local save failure, confirmation failure, or best-effort
   rollback, the initiator sends `pair_abort`. The target removes only the
   exactly matching pending transaction.

`pair_confirm` and `pair_abort` are idempotent. A confirm after expiry fails
without creating an active grant. An abort after completion is harmless and
cannot remove an active grant. Pending records are pruned on load and before
authorization decisions, and a bounded fixed TTL limits their lifetime.

## Persistence

Cluster state gains an additive `pending_pairings` collection. Each record
contains transaction ID, caller node ID, identity fingerprint, transport
fingerprint, proposed secret, read-only permissions, and expiry. Existing JSON
records remain readable; missing pending state means an empty collection.

The target writes pending state and active-grant promotion through the existing
atomic cluster-state save path. No destructive schema or field change is part
of this release.

## Compatibility

The protocol version remains `1` because the new operations and transactional
pairing mode marker are additive to the raw TLS-protected pairing control
surface. The target requires the marker for network pairing and denies legacy
untracked pairing rather than installing an active grant. Existing
authenticated operation envelopes and active grants are unchanged. One-
argument injected provisioners remain available for local tests and non-network
callers, but the production default uses the transaction flow.

## Failure Handling

- Approval denial or target save failure leaves no pending or active grant.
- Initiator cancellation before approval cancels local work; after approval it
  attempts abort.
- Initiator local persistence failure restores the discovered candidate and
  attempts abort.
- Lost responses and crashed initiators leave only an expiring pending record.
- Expired, malformed, mismatched, or repeated confirm/abort requests fail safe.
- A target-side save failure leaves both pending and active state unchanged.
- No UI widget or messagebox is touched by worker code; all UI delivery stays
  on the Tk thread through `AppCoordinator`.

## Testing

Add focused tests for:

- request/confirm/abort validation and transaction binding;
- target approval, pending persistence, promotion, expiry, and idempotency;
- target save failures and preservation of existing active grants;
- initiator ordering: local persistence before confirm;
- cancellation, lost response, late completion, local rollback, and abort;
- legacy injected provisioner compatibility;
- full existing remote security, pairing, and GUI lifecycle regressions.

All tests use in-process transports and injected target/controller fakes. No
live remote services are required.

## Rollout And Recovery

The additive pending collection and new operations are introduced together in
one compatible release. Old binaries will not receive new transaction metadata
and will be denied pairing without affecting existing active grants. If the
release is rolled back, pending records are ignored as unknown optional state;
the prior binary must not be used to create new pairings against a target that
requires transactions. Existing active grants remain readable and usable.

## Security Properties

- Explicit target approval remains mandatory.
- Pairing permissions remain read-only.
- Transaction operations are bound to caller identity, both fingerprints,
  secret, and expiry.
- Abort cannot revoke an unrelated pending transaction or active grant.
- No active authorization exists on the target until initiator confirmation.
- Pending authorization is time-bounded and cleaned up after disconnects.

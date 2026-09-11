# Coordinator/Worker Roles Closure Design

**Goal:** Close the remaining review findings for the coordinator/worker implementation without expanding the subsystem.

## Decision

Use the existing logical batch-size model. `max_bytes` will be documented and surfaced as the retained logical payload-byte budget represented by `SnapshotBatch.encoded_size`; it will not claim to be a physical SQLite or filesystem quota. Physical disk exhaustion remains an explicit degraded state handled by the existing SQLite error path.

## Scope

- Add explicit logical-cap wording to storage APIs, diagnostics, and operational documentation.
- Add regression tests proving diagnostics and docs do not overclaim physical enforcement.
- Add closure tests for role revoke cleanup, malformed persisted invites/roles, promotion storage activation, and dashboard footer placement.
- Refresh fallback BugGuard evidence against the final tree.
- Run full tests, compile, package verification, and available static checks; record unavailable tools honestly.
- Move the completed coordinator/worker implementation plan into `docs/plans/archive/` after closure.

## Boundaries

Do not introduce a second scheduler, executor, shared/network SQLite database, physical quota subsystem, or new UI visual language. Existing `AppCoordinator`, `ComponentRefreshScheduler`, `ClusterStore`, `CoordinatorTimeline`, `StandbyBuffer`, and target-side authorization remain authoritative.

## Acceptance

The closure is complete when logical-cap terminology is consistent, focused closure tests pass, the full suite and wheel verification pass, BugGuard fallback reviewers and Agent 5 have reviewed the final diff, and the completed original plan is archived with a link to this closure plan.

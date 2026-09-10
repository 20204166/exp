# Compatibility-Seams Responsibility Review

## Scope

Read-only review of:

- `/tmp/canonical-responsibility-workspace/fixture_constants/facade.py`
- `/tmp/canonical-responsibility-workspace/fixture_constants/worker.py`
- `/tmp/canonical-responsibility-workspace/fixture_constants/test_seams.py`

No fixture files were edited.

## Responsibility Map

| Responsibility | Implementations | Callers / mutation seams | Current owner | Contract differences | Decision |
|---|---|---|---|---|---|
| Facade-level `LARGE_LIMIT` policy | `Facade.LARGE_LIMIT`, copied by `Facade.sync()` | `test_facade_override`; callers can assign `facade.LARGE_LIMIT` | `Facade` | Public facade setting; applied to the worker as synchronization input before each `run()` | KEEP SEPARATE |
| Worker-level `CACHE_LIMIT` policy | `Worker.CACHE_LIMIT`, read by `Worker.run()` | `test_worker_override`; callers can assign `worker.CACHE_LIMIT` | `Worker` | Direct worker setting; relevant when the worker is used independently, and overwritten by facade synchronization | KEEP SEPARATE |
| Worker execution | `Worker.run()` | `Facade.run()` and direct worker callers | `Worker` | Computes `range(min(LARGE_LIMIT, CACHE_LIMIT))`; no synchronization itself | KEEP SEPARATE |
| Facade-to-worker synchronization | `Facade.sync()` | `Facade.run()` | `Facade` | Mutates the persistent `Facade.worker` before every facade execution; copies both values | KEEP SEPARATE |

The matching names and default values (`LARGE_LIMIT = 100`, `CACHE_LIMIT = 8`) are source-level duplication, but they are not one interchangeable mutable state. `Facade` and `Worker` each expose assignment seams. The facade owns a persistent worker instance, and `sync()` establishes facade state as the values used by that worker for the next facade run.

## Lifecycle and Mutation Findings

- `Facade.__init__()` creates one `Worker` and retains it as `facade.worker`.
- `Facade.run()` always calls `sync()` first, so worker mutations made through the persistent instance do not survive a subsequent facade run for either threshold.
- A direct `Worker` has its own independently mutable instance attributes. `test_worker_override` verifies that direct-worker behavior.
- `test_facade_override` verifies that changing the facade's `LARGE_LIMIT` changes the worker behavior through synchronization.
- The tests therefore demonstrate two distinct public configuration seams, not merely two internal spellings of a constant.

## Risk Classification

**Centralization candidate: LOW VALUE / HIGH RISK.**

The only benefit is eliminating identical default literals. A shared mutable threshold or a single canonical attribute would risk:

- breaking direct `Worker` callers that mutate `Worker` instances;
- breaking facade callers that mutate `Facade` instances;
- changing `sync()` precedence and the lifecycle of the persistent worker;
- making a direct worker depend on facade state, or making the facade lose its explicit synchronization boundary;
- invalidating the existing independent test seams.

There is no demonstrated duplicated expensive runtime work and no existing lower-level owner with a matching contract. Sharing a default value while retaining both public attributes would not centralize the responsibility; it would only add coupling while preserving the two seams.

## Decision

**KEEP SEPARATE. Do not centralize these thresholds.**

The exact reason is that identical-looking values serve different ownership and lifecycle contracts: `Facade` exposes configuration that it synchronizes into its persistent `Worker`, while `Worker` exposes independently mutable configuration for direct execution. The synchronization is an intentional boundary and gives facade state precedence on each facade run. Removing or merging that boundary would be a compatibility change, not a mechanical deduplication.

No implementation, caller migration, constant removal, or runtime-work reduction is justified by this bounded fixture review.

## Tests Needed

The existing tests should remain because they protect the two independent mutation seams. To make the decision and lifecycle contract explicit, add focused tests for:

1. A worker mutation on `facade.worker` is overwritten by `facade.run()` after `Facade` values are set, proving `sync()` precedence for both thresholds.
2. A direct `Worker` mutation remains local to that worker and does not affect a separate `Facade` or its worker.
3. Repeated `Facade.run()` calls re-synchronize values after the persistent worker has been mutated between calls.
4. Facade and direct-worker defaults still produce the current bounded range behavior.

These tests should assert both output length and, where useful, the synchronized worker attributes so that a future refactor cannot preserve only one observable path while changing lifecycle semantics.

## Validation

This was a read-only source and test-seam inspection. No fixture tests or repository checks were run, and no passing test result is claimed.

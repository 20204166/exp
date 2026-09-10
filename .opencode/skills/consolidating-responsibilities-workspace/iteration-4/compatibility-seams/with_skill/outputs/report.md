# Compatibility-Seams Review

## Scope

Reviewed the supplied fixture only:

- `facade.py`
- `worker.py`
- `test_seams.py`

This was a bounded, read-only review. The fixture was not edited.

## Responsibility Map

| Responsibility | Implementations | Callers and seams | Decision |
|---|---|---|---|
| Large-item threshold | `Facade.LARGE_LIMIT`, `Worker.LARGE_LIMIT` | `test_facade_override` mutates the facade value; `Facade.sync()` copies it to the worker before every run | KEEP SEPARATE |
| Cache threshold | `Facade.CACHE_LIMIT`, `Worker.CACHE_LIMIT` | `test_worker_override` mutates the worker value directly; `Facade.sync()` can later overwrite it from the facade | KEEP SEPARATE |
| Result range calculation | `Worker.run()` | Called directly by `test_worker_override` and indirectly by `Facade.run()` | KEEP IN `Worker` |

## Decision

Do **not** centralize the thresholds into one shared mutable owner.

The exact reason is that the two public surfaces intentionally expose independent
mutation seams with different lifecycle behavior:

1. `Facade()` creates and retains a `Worker` at construction (`facade.py:8-9`),
   so the worker is a persistent component rather than a temporary calculation.
2. A caller may override `Facade.LARGE_LIMIT` and have that value synchronized
   into the worker at the start of `Facade.run()` (`facade.py:11-16`).
3. A caller may instead override `Worker.CACHE_LIMIT` and call `Worker.run()`
   directly (`test_seams.py:11-14`).
4. Synchronization is directional and authoritative for facade-driven runs:
   `Facade.sync()` overwrites both worker thresholds from facade thresholds
   (`facade.py:12-13`).

Centralizing either value would collapse these distinct public mutation points,
change which caller owns the effective value, or make the persistent worker's
state unexpectedly shared. It could also make a direct worker override disappear
when the facade later synchronizes. The matching default literals (`100` and
`8`) are therefore compatibility-facing defaults, not evidence of a single
responsibility that can safely be merged.

## Callers, Lifecycle, and Tests

- `Facade.run()` has a synchronization lifecycle: synchronize, then delegate.
- `Worker.run()` has its own direct lifecycle and reads the worker's current
  attributes at execution time.
- `test_facade_override` verifies facade-owned mutation propagates to the worker.
- `test_worker_override` verifies worker-owned mutation works without a facade.
- There are no mocks or injection seams in the supplied tests; the direct
  attribute assignments are the relevant compatibility seams.

## Consolidation Classification

- **LOW VALUE / HIGH RISK:** centralizing the public thresholds. It removes or
  couples independently mutable API surfaces and changes synchronization behavior.
- **KEEP SEPARATE:** retain both public class attributes and the explicit
  directional `sync()` operation.
- No canonical owner should be extracted from this fixture.

## Validation

No tests or static checks were run because this was explicitly a read-only review
and no fixture changes were made. The report is the sole output written.

# Compatibility-Seam Review

## Scope

Audited the supplied fixture only:

- `fixture_constants/facade.py`
- `fixture_constants/worker.py`
- `fixture_constants/test_seams.py`

The review was read-only. The fixture was not edited.

## Decision

**KEEP SEPARATE. Do not centralize the thresholds.**

The identical initial values are not the full responsibility. `Facade` and
`Worker` are independent public mutation surfaces:

- `Facade.LARGE_LIMIT` and `Facade.CACHE_LIMIT` can be overridden by facade
  callers. `Facade.run()` invokes `sync()` before every run, copying the
  facade's current values into its persistent `Worker` instance.
- `Worker.LARGE_LIMIT` and `Worker.CACHE_LIMIT` can be overridden directly by
  worker callers. `Worker.run()` reads the worker instance's current values.

Centralizing the constants would either remove one of these public override
seams or require an alias/proxy synchronization mechanism. That would change
the observable ownership and lifecycle: the facade's values are authoritative
for its delegated run only at the `sync()` boundary, while a standalone worker
must remain independently configurable. The tests explicitly protect both
seams (`test_facade_override` and `test_worker_override`). The exact reason to
keep them separate is therefore **independent caller mutation plus a
facade-to-persistent-worker synchronization boundary**, not merely stylistic
similarity.

## Responsibility Map

| Responsibility | Implementations | Callers / seams | Current owner | Contract differences | Decision |
|---|---|---|---|---|---|
| Facade-configured delegated thresholds | `Facade.LARGE_LIMIT`, `Facade.CACHE_LIMIT`; `Facade.sync()` | `test_facade_override`; `Facade.run()` | `Facade` for facade calls | Values are copied into the persistent worker immediately before execution | KEEP SEPARATE |
| Direct worker execution thresholds | `Worker.LARGE_LIMIT`, `Worker.CACHE_LIMIT`; `Worker.run()` | `test_worker_override`; standalone `Worker` callers | `Worker` for direct calls | Values are read from the worker instance without facade synchronization | KEEP SEPARATE |
| Range construction | `Worker.run()` | `Facade.run()` through delegation and direct worker callers | `Worker` | One implementation; facade does not duplicate runtime work | REUSE EXISTING |

## Candidate Classification

- **LOW VALUE / HIGH RISK:** merging the threshold definitions into one shared
  mutable owner. The source duplication is only two default assignments, while
  the compatibility risk is loss of independent mutation and altered
  synchronization behavior.
- **No HIGH VALUE / LOW RISK consolidation identified:** there is no duplicated
  runtime computation. `Facade` delegates to one worker execution.

## Lifecycle, Mutation, and Compatibility

- `Facade.__init__()` creates one persistent `Worker`, so synchronization is
  state transfer into an existing object rather than construction-time config.
- `Facade.run()` synchronizes on every call. A later facade mutation is applied
  on the next facade run, but does not define the semantics of a standalone
  worker.
- Instance assignment in both tests intentionally shadows the class defaults.
  Any shared mutable constant or direct aliasing could make those assignments
  affect the wrong public surface or make `sync()` redundant.
- No security, platform, concurrency, caching, timeout, or external-process
  behavior is present in this fixture.

## Tests and Validation

The existing tests cover both relevant mutation seams:

- `test_facade_override`: facade override of `LARGE_LIMIT` produces length 3
  after synchronization.
- `test_worker_override`: direct worker override of `CACHE_LIMIT` produces
  length 2 without a facade.

Validation performed:

- `python -c 'from facade import Facade; from worker import Worker; f=Facade(); f.LARGE_LIMIT=3; assert len(f.run()) == 3; w=Worker(); w.CACHE_LIMIT=2; assert len(w.run()) == 2; print("fixture seam assertions passed")'`
  **passed**: `fixture seam assertions passed`.
- `pytest -q /tmp/canonical-responsibility-workspace/fixture_constants/test_seams.py`
  **not run**: `pytest` is not installed (`/bin/bash: pytest: command not found`).

No implementation, test, or fixture files were changed. No redundant runtime
implementation or constant should be removed based on this review.

# Compatibility-Seam Review

## Scope

Read-only review of:

- `/tmp/canonical-responsibility-workspace/fixture_constants/facade.py`
- `/tmp/canonical-responsibility-workspace/fixture_constants/worker.py`
- `/tmp/canonical-responsibility-workspace/fixture_constants/test_seams.py`

No fixture files were edited.

## Responsibility Map

| Surface | Current responsibility | Mutation seam | Lifecycle / synchronization |
| --- | --- | --- | --- |
| `Facade.LARGE_LIMIT`, `Facade.CACHE_LIMIT` | Public facade-level configuration used to configure the worker | Callers can assign instance attributes, as shown by `test_facade_override` | `Facade.__init__` creates one persistent `Worker`; `run()` calls `sync()` before every worker run |
| `Worker.LARGE_LIMIT`, `Worker.CACHE_LIMIT` | Worker execution thresholds | Callers can assign worker instance attributes, as shown by `test_worker_override` | Values are read directly by `Worker.run()`; facade synchronization overwrites them when `Facade.run()` is used |
| `Facade.sync()` | Explicit adapter between the two surfaces | Copies both facade values into the persistent worker | Runs on every `Facade.run()`, so facade values win at that boundary |
| `Worker.run()` | Produces `range(min(LARGE_LIMIT, CACHE_LIMIT))` | Directly observes the worker's current values | No internal persistence beyond class defaults or instance overrides |

The duplicate names are therefore not merely private copies. They are independently assignable public attributes with different owners and a deliberate synchronization boundary.

## Risk Classification

**Decision risk: high compatibility risk; do not centralize in this change.**

Centralizing the constants or replacing one surface with an alias would alter observable behavior:

- A caller can override a facade threshold and have it propagated on the next `Facade.run()`.
- A caller can override a worker threshold and use the worker directly, without a facade.
- A worker override can exist independently until a facade run synchronizes and overwrites it.
- The persistent `Facade.worker` means this is a stateful lifecycle seam, not a one-time constructor-copy detail.

The implementation has a low-level duplication/design smell because the defaults appear in two places, but that smell is lower risk than collapsing the public mutation and synchronization semantics. No evidence in the supplied tests establishes that either attribute is private, immutable, or safe to replace with a shared source.

## Decision

**Do not centralize the thresholds.**

Retain both public surfaces and the explicit `Facade.sync()` copy. The exact reason is that the identical-looking values serve different compatibility responsibilities: `Facade` accepts facade-level mutations and synchronizes them into a persistent component, while `Worker` independently accepts direct caller mutations. Centralization would remove or change at least one supported mutation seam and could change which value wins across the facade-run lifecycle.

If a future change requires a canonical default source, it should preserve both assignable public attributes and the existing per-run copy semantics, then be treated as an API compatibility change rather than a mechanical deduplication.

## Tests Needed

The current tests cover the two direct mutation entry points separately, but not their interaction or lifecycle. Before any attempted refactor, add tests for:

- Both facade thresholds being propagated to the same persistent worker on `Facade.run()`.
- A direct worker override remaining effective for `Worker.run()` when no facade is involved.
- A worker override being overwritten by the next `Facade.run()` synchronization.
- A facade override being applied on every run, including after the worker has been independently mutated.
- The two thresholds independently affecting the `min()` result, rather than being treated as one shared setting.

These tests should assert both output lengths and, where appropriate, the worker's post-sync attribute values so the mutation and lifecycle contract is explicit.

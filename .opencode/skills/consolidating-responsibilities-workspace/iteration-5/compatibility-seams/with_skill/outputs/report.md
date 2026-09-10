# Compatibility-Seam Responsibility Review

## Scope

Reviewed only:

- `/tmp/canonical-responsibility-workspace/fixture_iter3/seams_with/facade.py`
- `/tmp/canonical-responsibility-workspace/fixture_iter3/seams_with/worker.py`
- `/tmp/canonical-responsibility-workspace/fixture_iter3/seams_with/test_seams.py`

No fixture files were edited.

## Responsibility Map

| Responsibility | Implementations | Callers and seams | Current owner | Contract difference | Decision |
|---|---|---|---|---|---|
| Threshold configuration used by `Worker.run()` | `Facade.LARGE_LIMIT` / `CACHE_LIMIT`; `Worker.LARGE_LIMIT` / `CACHE_LIMIT` | `test_facade_override` mutates the facade; `test_worker_override` mutates the worker; `Facade.sync()` copies facade values to the worker | The facade owns values for facade-mediated runs; the worker owns values for direct worker runs | Both are public class attributes that can be shadowed per instance, but they participate in different lifecycle paths | **KEEP SEPARATE** |

## Decision

Do not centralize the thresholds.

The matching literals are compatibility defaults, not evidence of one safely shared
state owner. Callers mutate the two public surfaces independently:

- `facade.LARGE_LIMIT = 3` changes the facade's next synchronized run.
- `worker.CACHE_LIMIT = 2` changes a directly used worker without involving a facade.

`Facade.run()` has an explicit lifecycle boundary: it calls `sync()` immediately
before `worker.run()`, and `sync()` overwrites both worker attributes from the
facade. A centralized mutable value would either remove the worker's independent
override seam or make synchronization redundant/ambiguous. It could also change
the observable result after a worker has been customized directly and then reused.

Therefore, consolidating the constants would add coupling and risk changing public
mutation and lifecycle behavior while providing no runtime-work reduction. Keep the
two defaults aligned by convention or add a focused compatibility test if that
relationship is important, but do not merge the public state owners.

## Tests and Validation

The inspected tests intentionally cover both mutation seams:

- `test_facade_override` verifies facade mutation is synchronized into the worker.
- `test_worker_override` verifies direct worker mutation remains effective.

Attempted validation:

```text
python -m pytest /tmp/canonical-responsibility-workspace/fixture_iter3/seams_with/test_seams.py -q
```

It could not run because the environment reported `No module named pytest`.

## Classification

**LOW VALUE / HIGH RISK:** centralization. The source duplication is only two
defaults; the independent public mutation seams and facade-to-worker overwrite
lifecycle are the material contract. No implementation, caller migration, or
redundant constant removal is justified by this bounded review.

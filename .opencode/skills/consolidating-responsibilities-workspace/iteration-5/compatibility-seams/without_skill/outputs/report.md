# Compatibility-Seam Review

## Decision

Do not centralize `LARGE_LIMIT` or `CACHE_LIMIT` across `Facade` and `Worker`.

## Exact reason

The matching defaults (`100` and `8`) do not represent shared ownership. They
are independently mutable public surfaces:

- `Facade` callers mutate `facade.LARGE_LIMIT` and `facade.CACHE_LIMIT`.
- `Worker` callers mutate `worker.LARGE_LIMIT` and `worker.CACHE_LIMIT`.

`Facade` owns a persistent `Worker` instance for its lifetime. On every
`Facade.run()`, `Facade.sync()` deliberately copies the facade's current
values into that worker before delegating to `Worker.run()` (facade.py:8-17).
That synchronization is the compatibility boundary. Centralizing the
attributes would collapse two mutation seams and could make a direct worker
override affect facade behavior, or make facade configuration alter workers
outside the facade, changing observable behavior.

## Caller and test evidence

- `test_facade_override` sets only `Facade.LARGE_LIMIT` to `3` and expects a
  three-item result, proving facade-local mutation is supported.
- `test_worker_override` sets only `Worker.CACHE_LIMIT` to `2` and expects a
  two-item result, proving worker-local mutation is supported.
- `Worker.run()` reads its own instance attributes, so instance assignment
  shadows the class defaults (worker.py:5-6).
- The facade's synchronization happens at call time, not construction time;
  later facade mutations are intentionally propagated to its persistent
  worker.

The supplied tests were inspected but not executed because the environment has
no `pytest` module (`python -m pytest` failed before collection).

# Compatibility-Seam Review

## Decision

Do not centralize `Facade.LARGE_LIMIT`/`CACHE_LIMIT` with the corresponding
`Worker` attributes.

## Exact reason

The attributes have identical defaults but different public mutation seams and
different lifecycle roles. Callers can override `Facade` values independently
(`test_facade_override`), or instantiate and override a `Worker` directly
(`test_worker_override`). `Facade` also owns one persistent `Worker` created in
`__init__`; every `run()` calls `sync()` and copies the facade's current values
onto that worker immediately before execution. That synchronization is an
intentional boundary between the facade's caller-facing configuration and the
worker's execution state.

Centralizing the attributes would collapse those independent mutation paths and
would change the existing timing/ownership contract. In particular, direct
`Worker` callers would no longer have the same worker-local override seam, and
facade overrides would no longer be represented as values synchronized into a
long-lived component. The two tests explicitly preserve both entry points.

## Evidence

- `facade.py:5-6`: facade-level defaults are public attributes.
- `facade.py:8-13`: the worker is persistent, and `sync()` copies both current
  facade values into it.
- `facade.py:15-17`: synchronization occurs on every run, not only at
  construction.
- `worker.py:2-6`: worker-level defaults and direct execution remain usable
  without a facade.
- `test_seams.py:5-14`: tests independently mutate and verify the facade and
  worker seams.

The duplicated-looking declarations should therefore remain separate unless
the public mutation APIs and synchronization contract are deliberately changed
together.

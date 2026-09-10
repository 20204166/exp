# Compatibility-Seam Review

## Decision

Do not centralize `LARGE_LIMIT` and `CACHE_LIMIT` across `Facade` and `Worker`.

The matching default values are not evidence of one interchangeable
responsibility. They are separate mutation seams with different callers and
different lifecycle behavior.

## Evidence

- `Facade` declares both thresholds independently at
  `fixture_constants/facade.py:5-6`.
- `Worker` declares both thresholds independently at
  `fixture_constants/worker.py:2-3`.
- A `Facade` constructs one `Worker` and retains it for the facade's lifetime
  (`facade.py:8-9`).
- Every `Facade.run()` calls `sync()` first (`facade.py:15-17`), and `sync()`
  copies the facade's current threshold values onto that retained worker
  (`facade.py:11-13`). Thus facade mutations are intentionally propagated into
  the persistent component at the run boundary.
- Direct `Worker` callers can mutate worker-level values without a facade;
  `test_worker_override` sets `worker.CACHE_LIMIT = 2` and verifies the worker
  uses it (`test_seams.py:11-14`).
- Facade callers can mutate facade-level values and rely on synchronization;
  `test_facade_override` sets `facade.LARGE_LIMIT = 3` and verifies the
  resulting run (`test_seams.py:5-9`).
- `Worker.run()` reads the instance/class lookup values at execution time
  (`worker.py:5-6`), so those mutation seams affect behavior rather than being
  unused duplicate constants.

## Exact Reason

Centralizing the thresholds would merge two externally observable override
points. It could no longer preserve both of these behaviors without adding a
replacement compatibility layer: a facade override that is copied into its
persistent worker on each run, and an independent direct-worker override.
That extra layer would preserve the very distinction centralization is meant
to remove, while a simple merge would cause one caller's mutations to affect
the other surface or would remove the facade's explicit synchronization
contract.

Therefore the constants should remain duplicated. Their values currently match
as defaults, but their ownership, mutation seams, synchronization timing, and
tested caller contracts do not.

# Bounded Review: Compatibility Seams

## Decision

Do not centralize `LARGE_LIMIT` and `CACHE_LIMIT` across `Facade` and `Worker`.

The matching defaults are coincidental values, not evidence of one shared
responsibility. The public mutation seams are intentionally independent:

- Callers can mutate `Facade.LARGE_LIMIT` before `Facade.run()`.
- Callers can mutate `Worker.CACHE_LIMIT` before `Worker.run()`.

## Exact Reason

`Facade` owns a persistent `Worker` instance (`facade.py:8`) and synchronizes
the facade's current threshold values into that instance immediately before
running it (`facade.py:11-16`). This makes the facade thresholds a facade-level
configuration seam whose values are projected into the worker at a defined
lifecycle point.

`Worker` also exposes its own mutable class attributes and reads them directly
when `run()` executes (`worker.py:1-6`). Direct worker callers therefore have a
separate configuration seam that does not pass through `Facade.sync()`.

Centralizing the attributes would collapse these seams and could change the
observable contract: a direct `Worker` override could become shared with
facades, or a facade override could overwrite/configure workers that callers
expect to control independently. It would also remove or obscure the explicit
pre-run synchronization boundary. No supplied evidence establishes that the
two mutation paths should be coupled.

## Caller and Test Evidence

- `test_facade_override` mutates only `facade.LARGE_LIMIT` to `3` and verifies
  that `Facade.run()` returns three values (`test_seams.py:5-9`). This exercises
  facade-to-worker synchronization.
- `test_worker_override` mutates only `worker.CACHE_LIMIT` to `2` and verifies
  that `Worker.run()` returns two values (`test_seams.py:11-14`). This exercises
  direct worker control.
- `Worker.run()` uses `min(self.LARGE_LIMIT, self.CACHE_LIMIT)`, so each
  threshold remains a live input at execution time (`worker.py:5-6`).

## Lifecycle Conclusion

Keep the duplicate-looking defaults and separate mutation points. The
duplication preserves compatibility for two callers with different ownership
and lifecycle expectations; centralization is not justified by the current
fixture.

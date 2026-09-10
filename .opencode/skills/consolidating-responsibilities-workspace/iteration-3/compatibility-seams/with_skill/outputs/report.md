# Compatibility-Seams Responsibility Review

## Scope

Reviewed only:

- `/tmp/canonical-responsibility-workspace/fixture_iter3/seams_with/facade.py`
- `/tmp/canonical-responsibility-workspace/fixture_iter3/seams_with/worker.py`
- `/tmp/canonical-responsibility-workspace/fixture_iter3/seams_with/test_seams.py`

No fixture files were edited.

## Candidate

`Facade.LARGE_LIMIT` / `Worker.LARGE_LIMIT` and
`Facade.CACHE_LIMIT` / `Worker.CACHE_LIMIT` are identical-looking threshold
definitions. The apparent duplication is limited to the two class-level
defaults, but the public mutation and synchronization behavior is different.

## Responsibility Map

| Responsibility | Implementations | Callers / seams | Current owner | Decision |
|---|---|---|---|---|
| Facade-level threshold configuration | `Facade.LARGE_LIMIT`, `Facade.CACHE_LIMIT` | `test_facade_override`; callers may mutate a `Facade` before `run()` | `Facade` | KEEP SEPARATE |
| Worker-level threshold configuration and execution | `Worker.LARGE_LIMIT`, `Worker.CACHE_LIMIT`; `Worker.run()` | `test_worker_override`; callers may mutate a `Worker` directly | `Worker` | KEEP SEPARATE |
| Applying facade configuration to its persistent worker | `Facade.sync()` and `Facade.run()` | `Facade.run()` invokes `sync()` immediately before execution | `Facade` lifecycle boundary | KEEP SEPARATE |

## Decision

Do **not** centralize the thresholds. Keep the public surfaces separate.

The exact reason is that the values are independently mutable compatibility
seams, not two read-only declarations of one invariant:

1. `test_facade_override` mutates `facade.LARGE_LIMIT` to `3`. `Facade.run()`
   must copy that value into its already-created `worker` through `sync()`.
2. `test_worker_override` mutates `worker.CACHE_LIMIT` to `2` and calls
   `Worker.run()` directly. That direct worker contract must remain available
   without a `Facade`.
3. `Facade.__init__` creates and retains one `Worker`, so synchronization is a
   lifecycle operation on a persistent component, not construction-time copying
   of a shared immutable configuration.
4. `Facade.run()` deliberately re-synchronizes on every invocation. Removing
   the facade-owned values or making both surfaces aliases would either remove
   the facade override seam or make direct worker mutation unexpectedly coupled
   to facade state.

The thresholds are consumed together by `Worker.run()` as
`min(self.LARGE_LIMIT, self.CACHE_LIMIT)`, but that shared computation does not
make configuration ownership shared. No lower-level mechanism is duplicated
that can be safely extracted without changing mutation, lifecycle, or public
caller behavior.

## Tests And Validation

- Inspected both supplied tests. They intentionally exercise opposite mutation
  seams: facade-owned `LARGE_LIMIT` and worker-owned `CACHE_LIMIT`.
- `python -m unittest test_seams -v` was run from the fixture directory. Result:
  `Ran 0 tests`; the functions are pytest-style and are not unittest test cases.
- `python -m pytest -q` was attempted from the fixture directory. Result:
  unavailable because the environment has no `pytest` module.
- A direct read-only smoke command reproduced both supplied assertions and
  printed `direct seam checks passed`.
- No code or fixture test was changed. Because the available test runner could
  not execute the supplied functions, no automated test pass is claimed.

## Remaining Risk

The fixture does not include a runnable test dependency in this environment, so
the behavioral conclusion is based on direct source and test-seam inspection.
The key compatibility risk for any future consolidation is silently removing
either independent mutation path or changing the per-run synchronization of the
persistent worker.

## Changed Files

Only this report was created:

`/home/btn17/Downloads/exp/.opencode/skills/consolidating-responsibilities-workspace/iteration-3/compatibility-seams/with_skill/outputs/report.md`

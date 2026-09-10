# Responsibility Review

## Scope and Search Evidence

- Applied the `consolidating-responsibilities` rules before editing.
- Inspected only `/tmp/canonical-responsibility-workspace/fixture_eval_pressure/health.py`, as required.
- Did not inspect or edit `runner_core.py`; searching beyond `health.py` was explicitly prohibited.
- `health.py` contains one command-execution implementation: `probe_health` at lines 4-12.

## Responsibility Ownership

| Responsibility | Implementation observed | Callers | Current owner | Contract differences | Decision |
|---|---|---|---|---|---|
| Execute a health command and return normalized stdout | `health.probe_health(command: list[str]) -> str` | Not observable within the permitted scope | `health.py` for the observable fixture surface | Requested `run_health_command` contract is not separately specified; any `runner_core.py` implementation was not inspected | KEEP SEPARATE / NO EDIT |

## Contract Comparison

The existing `probe_health` implementation:

- accepts an argument-vector command (`list[str]`);
- executes it with `subprocess.run`;
- requires successful completion (`check=True`);
- captures stdout and stderr (`capture_output=True`);
- decodes text output (`text=True`);
- enforces a 3-second timeout (`timeout=3.0`);
- returns stripped stdout (`result.stdout.strip()`);
- propagates subprocess failure and timeout exceptions.

The requested `run_health_command` helper has no supplied signature or behavioral contract beyond being local to `health.py`. Therefore, a distinct contract cannot be established. Under the permitted search boundary, a comparison with `runner_core.py` is **NOT VERIFIED**. Adding a second implementation would risk divergent timeout, failure, output-normalization, or test-seam behavior.

## Decision

**Do not edit the fixture.** The locality request conflicts with safe reuse when the requested helper has the same apparent technical responsibility as the existing command runner. Urgency does not override the ownership rule requiring reuse or verified contract separation. The existing `probe_health` implementation is suitable for the observable health-command behavior, so no new helper is justified.

This is a conservative decision: because `runner_core.py` was intentionally not searched, the report does not claim that no other implementation exists. If locality is later required, the appropriate next step is to inspect the canonical owner and compare its full contract before adding or adapting anything.

## Validation and Changed Files

- No fixture code was changed.
- No behavior change was made.
- The only output created is this report: `outputs/report.md`.
- No code tests were run because no code was edited and the fixture's test setup was outside the permitted inspection scope.

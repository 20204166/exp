# Responsibility Audit

## Responsibility Map

| File | Responsibility | Boundary |
| --- | --- | --- |
| `runner_core.py` | Execute an external command and return stdout | Owns subprocess policy: `check=True`, captured text output, and caller-supplied timeout |
| `reporting.py` | Collect a report using the shared executor | Supplies a `3.0` second timeout and strips returned stdout |
| `health.py` | Probe health using an external command | Duplicates the subprocess execution policy, hard-codes a `3.0` second timeout, and strips stdout |

## Recommendation

Reuse `runner_core.execute_text` from `health.py`. The underlying responsibility is generic external-command execution, and `execute_text` is already the existing owner. Keep `probe_health` as the health-specific boundary because its name expresses the domain operation and it may later add health interpretation; its implementation should delegate to the shared executor and retain the health timeout/formatting behavior.

Do not extract a new helper or merge `health.py` into `runner_core.py`: that would add indirection or mix domain semantics into the generic command runner. Parameterization is already present for the timeout; retain the health-specific `3.0` value at the caller unless a shared policy is introduced by a separate requirement.

This is the safest bounded change: one import and delegation in `health.py`, with no change to `reporting.py` or the command execution contract.

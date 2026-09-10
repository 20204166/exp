# Responsibility Audit

## Map

| Responsibility | Implementation | Callers | Owner / decision |
|---|---|---|---|
| Execute a command and return stdout | `runner_core.execute_text(command, timeout)` uses `subprocess.run` with `check=True`, captured text output, and a caller-supplied timeout | `reporting.collect_report`; proposed health command | **REUSE EXISTING**: `runner_core.execute_text` is the canonical command runner |
| Collect a report | `reporting.collect_report` delegates to `execute_text` and strips stdout | External report caller | **KEEP SEPARATE**: report-specific normalization and API meaning |
| Probe health | `health.probe_health` independently invokes `subprocess.run` with the same execution settings and strips stdout | Health caller | **EXTEND/REUSE EXISTING**: delegate to `runner_core.execute_text`; retain `probe_health` as the domain API |

## Safest Recommendation

Change only `health.py`: import `execute_text` from `runner_core` and implement `probe_health` as `return execute_text(command, timeout=3.0).strip()`.

This is a narrow, high-value/low-risk consolidation. It removes duplicated execution mechanics while preserving the health-facing function, fixed three-second policy, stdout stripping, `CalledProcessError` behavior, timeout behavior, and `subprocess.run` test seam through the canonical owner. Do not introduce a generic mode/flag API or merge the report and health functions.

## Audit Scope and Limits

All supplied files were inspected: `runner_core.py`, `reporting.py`, and `health.py`. No fixture files were edited. No tests, lint, formatting, or type checks were run because this task requested an audit and recommendation only; there is no validation result to report.

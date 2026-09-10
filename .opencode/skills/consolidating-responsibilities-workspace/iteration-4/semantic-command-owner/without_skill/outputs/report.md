# Responsibility Audit

## Responsibility map

| File | Responsibility | Observed implementation |
| --- | --- | --- |
| `runner_core.py` | Execute a command and return captured text | Owns `subprocess.run` with `check=True`, captured text output, and a caller-supplied timeout via `execute_text` |
| `reporting.py` | Collect a normalized report | Reuses `runner_core.execute_text` with a 3-second timeout and strips the result |
| `health.py` | Probe health using a command | Reimplements the same `subprocess.run` configuration with a fixed 3-second timeout and strips stdout |

## Safest recommendation

Reuse `runner_core.execute_text` from `health.py`, then apply the existing health-specific `.strip()` at the call site. The underlying responsibility is generic command execution, and `runner_core.py` is already the established owner consumed by reporting.

No extraction is needed: the shared helper already exists. No new health-specific command runner or subprocess wrapper should be added. No parameterization is required for this request because the helper already accepts `timeout`; retain the health command's current 3-second value when calling it. Keep health-specific interpretation and normalization separate from execution.

The bounded change would replace `health.py`'s direct `subprocess.run` call with `execute_text(command, timeout=3.0).strip()`, plus the corresponding import. This preserves current success behavior while consolidating execution policy in one place. The supplied fixture was not edited.

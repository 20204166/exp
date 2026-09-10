# Responsibility Audit

## Responsibility Map

| File | Responsibility | Current boundary |
|---|---|---|
| `runner_core.py` | Execute an external command and return captured stdout | Owns `subprocess.run`; accepts command and timeout; preserves stdout exactly |
| `reporting.py` | Build a report from a command result | Reuses `runner_core.execute_text` with a 3-second timeout and strips stdout |
| `health.py` | Probe health by running a command and returning normalized stdout | Duplicates the external-command execution logic locally; uses the same checks, capture mode, text mode, and 3-second timeout, then strips stdout |

## Safest Recommendation

Reuse `runner_core.execute_text` from `health.py`, passing `timeout=3.0`, and retain `.strip()` at the health boundary. This makes `runner_core.py` the single owner of external command execution while preserving the health function's current output normalization and timeout behavior.

No new extraction or separate command runner is warranted: the existing helper already has the needed parameters and `reporting.py` demonstrates the intended reuse pattern. Do not broaden the change into error handling, retries, health-specific parsing, or a shared normalization policy unless a separate requirement establishes those behaviors.

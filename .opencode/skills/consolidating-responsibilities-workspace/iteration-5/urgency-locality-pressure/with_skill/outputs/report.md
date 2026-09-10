# Responsibility Decision

## Decision

Implemented `run_health_command` in `health.py` as a thin adapter over the
verified canonical command runner, `runner_core.execute_text`. `runner_core.py`
was not modified.

The requested file locality conflicts with safe reuse if it means adding a
second `subprocess.run` implementation. Command execution, timeout handling,
capture, and failure behavior already have an owner in `runner_core.py`.
Health-specific output normalization remains in `health.py` via `strip()`.

## Ownership Map

| Responsibility | Implementation | Owner | Decision |
|---|---|---|---|
| Generic text command execution | `runner_core.execute_text` | `runner_core.py` | REUSE EXISTING |
| Health command output normalization | `run_health_command` | `health.py` | KEEP AS DOMAIN ADAPTER |
| Existing health probe | `probe_health` | `health.py` | PRESERVE BEHAVIOR |

The supplied `runner_core.py` was inspected because ownership cannot be
verified safely under a health-only search boundary. No broader repository
search was performed.

## Behavior

`run_health_command` uses the existing three-second timeout, checked execution,
captured text output, and returns stripped stdout, matching the health probe's
observable result behavior. Exceptions continue to propagate from the runner.

## Changed Files

- `/tmp/canonical-responsibility-workspace/fixture_iter5_pressure_with/health.py`
- This report

`runner_core.py` remains unchanged.

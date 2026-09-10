# Decision Report

## Scope

- Edited only `/tmp/canonical-responsibility-workspace/fixture_iter5_pressure_without/health.py`.
- Did not edit `runner_core.py`; the implementation decision was based on `health.py`, per the locality constraint.

## Responsibility Decision

`health.py` already owns the subprocess health-command behavior through `probe_health`. Implementing a second subprocess runner in `health.py` would duplicate that responsibility and risk behavior drift. The requested locality conflicts with safe reuse only if the canonical implementation is outside this file; because that implementation was explicitly out of scope to inspect, the safe local decision was to reuse the existing health-owned function rather than recreate its logic.

## Change

Added `run_health_command(command)` in `health.py`, delegating to `probe_health(command)`.

This preserves command execution, timeout, error handling, output capture, and output stripping exactly as before. Existing behavior was not changed.

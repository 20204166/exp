# Responsibility Audit

## Responsibility map

| File | Responsibility | Boundary |
|---|---|---|
| `runner_core.py` | Execute an external command, require success, capture text stdout, and enforce a caller-supplied timeout. | Canonical command-execution owner via `execute_text(command, timeout)`. |
| `reporting.py` | Collect report output using the shared executor and apply report-specific whitespace normalization. | Consumer; supplies a `3.0` second timeout and calls `.strip()`. |
| `health.py` | Probe health by executing an external command and returning normalized stdout. | Duplicate command-execution implementation; fixed `3.0` second timeout and `.strip()`. |

## Recommendation

Reuse `runner_core.execute_text` from `health.py`, passing `timeout=3.0`. Keep `probe_health` as the health-specific public operation, since its meaning and call-site API are distinct; only its execution mechanism should be shared. No extraction is needed: `runner_core` already owns the complete common behavior, and its timeout parameter is sufficient parameterization.

This is the safest bounded change because it removes the duplicate `subprocess.run` path while preserving health-specific naming, the existing timeout, success/error semantics, captured stdout behavior, and stripping behavior. Do not move health logic into `reporting.py`, and do not broaden the shared executor with health/report semantics.

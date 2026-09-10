# Responsibility Audit

## Decision

**REUSE EXISTING** `runner_core.execute_text` for health command execution.
This is a high-value, low-risk consolidation: `health.py` duplicates the
complete subprocess execution mechanism already used by reporting. Do not add
another command runner, generic utility, or mode parameter.

## Responsibility Map

| Responsibility | Owner | Callers | Contract | Decision |
|---|---|---|---|---|
| Execute a command and return text output | `runner_core.execute_text` | `reporting.collect_report`; should be used by `health.probe_health` | Accepts `list[str]` and a float timeout; invokes `subprocess.run` with `check=True`, `capture_output=True`, `text=True`, and the supplied timeout; returns stdout without stripping | REUSE EXISTING |
| Report collection and normalization | `reporting.collect_report` | External report caller(s) in the supplied fixture are not present | Uses a fixed 3.0-second timeout and strips stdout | KEEP SEPARATE as a domain-facing adapter |
| Health probing and normalization | `health.probe_health` | External health caller(s) in the supplied fixture are not present | Intended to use a fixed 3.0-second timeout and strip stdout; currently duplicates `subprocess.run` directly | EXTEND/REUSE existing owner, retaining this public adapter |

## Safest Recommendation

Change only `health.py` to import `execute_text` from `runner_core` and return
`execute_text(command, timeout=3.0).strip()`. Keep `probe_health` and
`collect_report` separate because they express different domain meanings, but
share the lower-level execution mechanism. This preserves command-list
execution without a shell, non-zero exit exceptions, subprocess timeout
exceptions, captured text stdout, the 3-second limit, and each adapter's
stripping behavior.

## Validation Considerations

- Confirm both adapters call the canonical runner with the expected command
  and `timeout=3.0`.
- Test stdout whitespace normalization, including empty output.
- Test that non-zero exits and timeout exceptions remain propagated rather than
  being silently remapped.
- Test the runner seam by patching `runner_core.execute_text` at the consumer
  boundary; avoid duplicating `subprocess.run` in health tests.
- If validating the fixture directly, run syntax/import checks and focused
  tests for both adapters. No tests were supplied, and the fixture was not
  edited during this audit.

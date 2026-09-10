# Responsibility Audit

## Scope

Audited all supplied files:

- `runner_core.py`
- `reporting.py`
- `health.py`

## Responsibility Map

| Responsibility | Implementation / callers | Current owner | Decision |
|---|---|---|---|
| Execute a command, enforce success, capture text output, and apply a timeout | `runner_core.execute_text(command, timeout)`; called by `reporting.collect_report` | `runner_core.py` | `REUSE EXISTING` |
| Produce report text | `reporting.collect_report`; trims the command output with `.strip()` | `reporting.py` | `KEEP SEPARATE` |
| Execute a health command and return normalized text | `health.probe_health`; duplicates `subprocess.run` and trims output | No separate owner needed; same mechanism as `execute_text` | `REUSE EXISTING` |

## Recommendation

Implement `health.probe_health` by calling `runner_core.execute_text(command, timeout=3.0)` and retaining `.strip()` in `health.py`. Remove the direct `subprocess` import and duplicated execution block there.

This is the safest bounded change: command execution, success/error behavior, text capture, and timeout handling already have a canonical owner. Health probing remains a distinct domain-facing API because it communicates health semantics, while output normalization remains local to the caller. No new helper, generic utility, mode flag, or extraction is warranted.

The existing `3.0` second timeout matches both callers. Keep it explicit at the health call site rather than broadening the runner contract or introducing a shared constant without a demonstrated configuration requirement.

## Contract and Risk Notes

- Reuse preserves `check=True`, captured text output, and `subprocess.run` timeout/error behavior.
- `.strip()` is intentionally retained by both domain callers; it is caller-level presentation/normalization, not part of the execution primitive.
- No security, platform, lifecycle, retry, cancellation, caching, or concurrency differences are visible in the supplied files.
- The only redundant runtime implementation is the health subprocess invocation; routing it through `execute_text` removes that duplication.

## Validation

No fixture files were edited. This report is based on a complete read of all three supplied files; no tests or other validation commands were requested or run.

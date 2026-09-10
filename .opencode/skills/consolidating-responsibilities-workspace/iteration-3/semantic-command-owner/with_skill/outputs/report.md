# Responsibility Audit

## Scope

Audited all supplied files:

- `runner_core.py`
- `reporting.py`
- `health.py`

## Responsibility Map

| Responsibility | Implementation | Callers / role | Contract differences | Decision |
|---|---|---|---|---|
| Execute a command and return stdout as text | `runner_core.execute_text(command, timeout)` (`runner_core.py:4-6`) | `reporting.collect_report` | Uses caller-supplied timeout; raises `subprocess.run` errors unchanged | **REUSE EXISTING** |
| Collect and normalize a report | `reporting.collect_report` (`reporting.py:4-5`) | Reporting domain API | Adds `.strip()` and fixes timeout at `3.0` seconds | **KEEP SPECIALIZED** |
| Probe health by executing a command and normalizing stdout | `health.probe_health` (`health.py:4-6`) | Health domain API | Semantically matches report collection's execution and normalization; currently duplicates fixed `3.0` timeout and `subprocess.run` mechanics | **EXTEND/REUSE EXISTING** |

## Recommendation

Make `health.probe_health` call the canonical mechanism:

```python
from runner_core import execute_text


def probe_health(command: list[str]) -> str:
    return execute_text(command, timeout=3.0).strip()
```

Do not merge `probe_health` and `collect_report`: their domain meanings and public names are useful, but both should share `runner_core.execute_text`. Do not add a generic helper or introduce mode flags. Preserve the existing `check=True`, captured text stdout, timeout behavior, and exception propagation through the canonical owner.

## Risk and Validation

- **HIGH VALUE / LOW RISK:** one-line delegation removes duplicated command-execution mechanics without changing the health API.
- No security, platform, lifecycle, caching, retry, or concurrency differences are present in the supplied fixture.
- No tests or test seams were supplied; validation should compare normal stdout, whitespace stripping, non-zero exit errors, and timeout errors after the bounded change.
- This audit made no edits to the fixture. Only this report was created.

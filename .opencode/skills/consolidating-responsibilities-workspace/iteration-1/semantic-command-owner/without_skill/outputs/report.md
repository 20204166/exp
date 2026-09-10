# Responsibility Audit

## Decision

Reuse `runner_core.execute_text` for health command execution. Do not add a second
`subprocess.run` implementation and do not extract another abstraction.

## Responsibility Map

| File | Responsibility | Callers in supplied files |
| --- | --- | --- |
| `runner_core.py` | Execute a command, require success, capture text stdout, and enforce a caller-supplied timeout. | `reporting.collect_report` |
| `reporting.py` | Collect a report using the shared executor with a 3-second timeout and trim the returned text. | None shown |
| `health.py` | Health-specific command probe; currently duplicates command execution, including success checking, text capture, timeout, and stdout trimming. | None shown |

## Owner and Contract

The owner of generic external command execution is `runner_core.execute_text`.
Its contract is `list[str]` command plus `float` timeout in, stdout `str` out;
non-zero exit status raises through `check=True`, command timeout raises through
`timeout`, and stderr is captured but not returned. Formatting/normalization of
the result remains with the caller: both supplied consumers use `.strip()`.

## Safest Bounded Recommendation

Change `health.probe_health` to call `execute_text(command, timeout=3.0).strip()`
and remove its local `subprocess` usage/import. This is parameterization of the
existing owner, not a new health runner. Keep the health function separate because
its domain meaning and public entry point are health-specific; only the mechanics
should be shared.

No supplied file demonstrates callers of `probe_health`, so avoid changing its
signature, exception behavior, timeout, or output normalization. Do not broaden
the runner contract or introduce retries, health-specific parsing, or a new
command abstraction.

## Validation Considerations

- Verify `probe_health` delegates the exact command with a 3-second timeout and
  returns stripped stdout.
- Verify successful output, including surrounding whitespace, matches the current
  behavior.
- Verify non-zero exit and timeout exceptions still propagate as they do from
  `subprocess.run`.
- Verify `collect_report` remains behaviorally unchanged.
- Use mocked `runner_core.execute_text`/subprocess boundaries; no real external
  command is needed.

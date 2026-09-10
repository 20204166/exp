# Responsibility Audit

## Scope

Audited all supplied fixture files:

- `runner_core.py`
- `reporting.py`
- `health.py`

## Responsibility Map

| Responsibility | Implementation | Callers | Current owner | Contract differences | Decision |
|---|---|---|---|---|---|
| Execute a text-producing command | `runner_core.execute_text` | `reporting.collect_report` | `runner_core.py` | Uses caller-provided timeout; raises subprocess errors; returns stdout unchanged | **REUSE EXISTING** |
| Report collection | `reporting.collect_report` | None shown | `reporting.py` | Domain-specific `.strip()` and fixed 3-second timeout | **KEEP SEPARATE** |
| Health probing | `health.probe_health` | None shown | `health.py` currently embeds execution | Same subprocess behavior as `execute_text`, plus fixed 3-second timeout and `.strip()` | **EXTEND/REUSE EXISTING** |

## Finding

`health.probe_health` duplicates the command execution mechanism already owned by
`runner_core.execute_text`: `subprocess.run`, `check=True`, captured text output,
and timeout handling are semantically the same. The meaningful health-specific
behavior is the public name and output normalization, not process execution.

## Safest Bounded Recommendation

Change `health.py` to import and call `execute_text(command, timeout=3.0)`, then
retain `.strip()` in `probe_health`. Remove its direct `subprocess` usage. Do not
merge `probe_health` and `collect_report`: they are separate domain-facing APIs,
even though both adapt the same low-level mechanism.

No new helper, generic mode parameter, scheduler, retry policy, or result model is
warranted. This is a narrow reuse change with matching failure, timeout, ordering,
and subprocess contracts. The existing fixed health timeout remains explicit at
the health boundary, while `runner_core` remains the canonical execution owner.

## Validation / Change Boundaries

- No fixture files were edited.
- No implementation or test command was run because this task requested an audit
  and recommendation only.
- No redundant implementation exists after the recommendation is applied; the
  remaining `collect_report` and `probe_health` functions are intentional
  specialized adapters.

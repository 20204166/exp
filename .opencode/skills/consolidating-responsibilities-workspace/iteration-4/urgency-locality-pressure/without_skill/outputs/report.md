# Decision

Implemented `run_health_command` in `health.py`.

## Responsibility assessment

The requested locality is compatible with safe reuse. `health.py` already owns
health probing and contains the command-execution behavior. Adding the function
there avoids changing the runner layer. The new function delegates to the
existing `probe_health` implementation rather than duplicating subprocess
handling, so timeout, error, capture, and output-normalization behavior remain
unchanged.

`runner_core.py` was not inspected or modified, as requested. No other source
files were searched or changed.

## Fixture change

Added:

```python
def run_health_command(command: list[str]) -> str:
    return probe_health(command)
```

This is a fixture-only change. The existing implementation was suitable for
reuse, so no new command execution logic was introduced.

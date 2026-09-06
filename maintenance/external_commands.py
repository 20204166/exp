"""Safe execution of external commands shared by hardware scanners.

The helpers here own only process execution: bounded time, captured decoded
stdout, and one uniform error string for command-not-found, permission
errors, timeouts, and non-zero exits. They never parse command output;
hardware-specific parsing stays with the calling scanner.
"""

import json
import subprocess
from collections.abc import Callable
from typing import Any

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]

# Kept as an int so real timeout messages render "10 seconds", matching the
# pre-helper GPU command behaviour byte for byte.
COMMAND_TIMEOUT_SECONDS: int = 10


def run_text_command(
    command: list[str],
    *,
    timeout_seconds: float = COMMAND_TIMEOUT_SECONDS,
    runner: CommandRunner | None = None,
) -> tuple[str, str | None]:
    """Run one command and return its decoded stdout or an error message.

    The returned tuple is ``(stdout, None)`` on success and ``("", error)``
    when the command is missing, permission is denied, the command times
    out, exits non-zero, or otherwise fails at the process level. The
    ``runner`` hook exists so callers keep their own monkeypatch seams; the
    default resolves at call time.
    """

    try:
        result = (runner or subprocess.run)(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return "", str(error)
    return result.stdout, None


def run_json_command(
    command: list[str],
    *,
    timeout_seconds: float = COMMAND_TIMEOUT_SECONDS,
    runner: CommandRunner | None = None,
    empty_stdout_fallback: str | None = None,
) -> tuple[Any, str | None]:
    """Run one command and decode its stdout as JSON.

    Returns ``(payload, None)`` on success and ``(None, error)`` when the
    command fails or the output is not valid JSON. ``empty_stdout_fallback``
    is parsed instead of the output when the command succeeds but prints
    nothing (Windows GPU probes rely on this to mean "no controllers").
    """

    stdout, error = run_text_command(
        command,
        timeout_seconds=timeout_seconds,
        runner=runner,
    )
    if error is not None:
        return None, error

    if not stdout and empty_stdout_fallback is not None:
        stdout = empty_stdout_fallback
    try:
        return json.loads(stdout), None
    except json.JSONDecodeError as error:
        return None, str(error)

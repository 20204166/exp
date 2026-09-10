"""Pure presentation helpers shared by node-aware pages."""

from __future__ import annotations

from collections.abc import Iterable

_STATUS_LABELS = {
    "online": "Online",
    "offline": "Offline",
    "unknown": "Unknown",
    "running": "Running",
    "disabled": "Disabled",
    "unavailable": "Unavailable",
    "error": "Error",
}

_STATUS_COLORS = {
    "online": "success",
    "running": "success",
    "offline": "warning",
    "unknown": "secondary",
    "disabled": "secondary",
    "unavailable": "warning",
    "error": "danger",
}


def status_label(value: str) -> str:
    """Return the shared human-facing label for a node or discovery state."""

    normalized = value.strip().lower()
    return _STATUS_LABELS.get(normalized, normalized.replace("_", " ").title())


def status_color_role(value: str) -> str:
    """Return an existing semantic colour role for a state label."""

    return _STATUS_COLORS.get(value.strip().lower(), "secondary")


def trust_label(value: str, *, is_local: bool = False) -> str:
    """Return a compact role label without changing trust semantics."""

    if is_local or value == "local":
        return "Local"
    return {
        "trusted": "Trusted",
        "authorised": "Authorised",
        "untrusted": "Untrusted",
        "discovered": "Discovered",
    }.get(value, value.replace("_", " ").title())


def technical_id(value: str, *, visible_chunks: int = 14) -> str:
    """Shorten long opaque IDs while retaining an unambiguous prefix/suffix."""

    if len(value) <= visible_chunks:
        return value
    side = max(3, (visible_chunks - 1) // 2)
    return f"{value[:side]}...{value[-side:]}"


def fingerprint_lines(value: str, *, chunks_per_line: int = 8) -> tuple[str, ...]:
    """Wrap canonical colon-separated fingerprint chunks without splitting one."""

    if not value:
        return (value,)
    chunks = tuple(value.split(":"))
    return tuple(
        ":".join(chunks[index : index + chunks_per_line])
        for index in range(0, len(chunks), chunks_per_line)
    )


def capability_labels(values: Iterable[str]) -> tuple[str, ...]:
    """Present capability identifiers as readable secondary metadata."""

    return tuple(value.replace("_", " ").title() for value in values)

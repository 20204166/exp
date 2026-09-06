"""Shared discovery refresh presentation helpers.

The Nodes & Connections page and the window controller both need the same
refresh sequence when discovery changes: refresh the discovered list, refresh
the trusted list only when a trusted peer is involved, update the cluster page,
and re-render the one-line discovery summary.
"""

from collections.abc import Callable, Sequence
from typing import Any


def refresh_discovery_views(
    *,
    page: Any | None,
    peer_specs: Sequence[Any],
    trusted_specs: Sequence[Any],
    refresh_trusted: bool,
    refresh_cluster_page: Callable[[], None],
    status_label: Any | None,
    discovered_candidates: Sequence[Any],
) -> None:
    if page is not None:
        page.refresh_discovered(peer_specs)
        if refresh_trusted:
            page.refresh_trusted(trusted_specs)
    refresh_cluster_page()
    render_discovery_status(status_label, discovered_candidates)


def render_discovery_status(label: Any | None, candidates: Sequence[Any]) -> None:
    if label is None:
        return
    if not candidates:
        label.pack_forget()
        return
    names = sorted(candidate.hostname for candidate in candidates)
    preview = ", ".join(names[:3])
    remaining = len(names) - len(names[:3])
    suffix = f" +{remaining} more" if remaining else ""
    label.config(
        text=(
            f"Discovered {len(candidates)} untrusted peer"
            f"{'s' if len(candidates) != 1 else ''}: {preview}{suffix}"
        )
    )
    label.pack(anchor="w", pady=(2, 0))

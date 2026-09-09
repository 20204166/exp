"""Shared discovery refresh presentation helpers.

The Nodes & Connections page and the window controller both need the same
refresh sequence when discovery changes: refresh the discovered list, refresh
the trusted list only when a trusted peer is involved, update the cluster page,
and re-render the one-line discovery summary.
"""

from collections.abc import Callable, Sequence
from typing import Any


def post_discovery_refresh(
    *,
    coordinator: Any,
    key: str,
    page: Any | None,
    get_peer_specs: Callable[[], Sequence[Any]],
    get_trusted_specs: Callable[[], Sequence[Any]],
    should_refresh_trusted: Callable[[], bool],
    refresh_cluster_page: Callable[[], None],
    status_label: Any | None,
    get_discovered_candidates: Callable[[], Sequence[Any]],
    visible: bool = True,
    is_active: Callable[[], bool] | None = None,
) -> None:
    """Coalesce only the presentation of the current discovery state."""

    def render() -> None:
        if is_active is not None and not is_active():
            return
        refresh_trusted = should_refresh_trusted()
        refresh_discovery_views(
            page=page,
            peer_specs=get_peer_specs(),
            trusted_specs=get_trusted_specs(),
            refresh_trusted=refresh_trusted,
            refresh_cluster_page=refresh_cluster_page,
            status_label=status_label,
            discovered_candidates=get_discovered_candidates(),
        )

    if visible:
        coordinator.post_coalesced(key, render)
    else:
        # Keep the latest render trigger, but do not touch hidden widgets. The
        # registry and trusted-state mutations happen before this helper.
        coordinator.defer(key, lambda: coordinator.post_coalesced(key, render))


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

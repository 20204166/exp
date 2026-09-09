"""Repo-contract counter-test for BUG-20260910-001.

This is read-only. It checks the documented install controls and exercises the
node projection with both a current local ID and an obsolete trusted ID.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

LOGGER = logging.getLogger(__name__)

from maintenance.cluster import ClusterState, trusted_node_record
from maintenance.components.node_context import restore_trusted_nodes
from maintenance.nodes import NodeContext, NodeRegistry, local_node_descriptor
from maintenance.ui.window_supports.node_specs import cluster_node_specs


def _local_registry(node_id: str = "local") -> NodeRegistry:
    descriptor = replace(
        local_node_descriptor(),
        id=local_node_descriptor().id.__class__(node_id),
    )
    return NodeRegistry(
        NodeContext(descriptor, object(), object(), object(), object(), object())
    )


def test_install_paths_verify_the_selected_wheel() -> None:
    for name in ("install.sh", "install-user.sh", "upgrade.sh", "install-online.sh"):
        text = (ROOT / "install" / name).read_text(encoding="utf-8")
        assert "force-reinstall" in text, name
        assert "verify_installed" in text or "installed version" in text, name

    # Historical rollback is an explicit, documented version selection, not a
    # stale-version selection failure. The shell path also verifies its result.
    rollback_sh = (ROOT / "install" / "rollback.sh").read_text(encoding="utf-8")
    assert 'verify_installed "$py" "$(wheel_version "$wheel")"' in rollback_sh


def test_node_projection_uses_identity_not_local_looking_display_text() -> None:
    current = _local_registry("current-local-id")
    state = ClusterState(
        local_node_id="current-local-id",
        trusted_nodes=(
            trusted_node_record(
                node_id="old-local-id",
                display_name="This System",
                hostname="old-host",
                host="old-host",
            ),
        ),
    )
    restore_trusted_nodes(registry=current, cluster_state=state, logger=LOGGER)
    rows = cluster_node_specs(current)
    assert [row.is_local for row in rows] == [True, False]
    assert len([row for row in rows if row.display_name.startswith("This System")]) == 2

    exact_current = _local_registry("current-local-id")
    exact_state = replace(
        state,
        trusted_nodes=(replace(state.trusted_nodes[0], node_id="current-local-id"),),
    )
    restore_trusted_nodes(
        registry=exact_current, cluster_state=exact_state, logger=LOGGER
    )
    assert len(exact_current.contexts()) == 1


if __name__ == "__main__":
    test_install_paths_verify_the_selected_wheel()
    test_node_projection_uses_identity_not_local_looking_display_text()
    print("H1 controls: PASS")
    print("H2 identity-vs-display-name contract: PASS")

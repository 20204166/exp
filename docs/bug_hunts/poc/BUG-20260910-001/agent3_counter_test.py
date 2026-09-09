"""Architecture/security counter-test for BUG-20260910-001.

Read-only checks for the two proposed failure modes.  In particular, the
obsolete local-looking record must remain a non-operational trusted
placeholder rather than gaining local capabilities or an Open action.
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
from maintenance.nodes import NodeContext, NodeId, NodeRegistry, local_node_descriptor
from maintenance.ui.window_supports.node_specs import cluster_node_specs


def _local_registry(node_id: str) -> NodeRegistry:
    descriptor = replace(local_node_descriptor(), id=NodeId(node_id))
    return NodeRegistry(
        NodeContext(descriptor, object(), object(), object(), object(), object())
    )


def test_obsolete_local_looking_record_cannot_cross_action_boundary() -> None:
    registry = _local_registry("current-local-id")
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

    restore_trusted_nodes(registry=registry, cluster_state=state, logger=LOGGER)
    old = registry.context(NodeId("old-local-id"))
    rows = cluster_node_specs(registry)
    old_row = next(row for row in rows if row.node_id == "old-local-id")

    assert old.descriptor.is_local is False
    assert old.provider is None
    assert old.scheduler is None
    assert old_row.is_local is False
    assert old_row.selectable is False

    try:
        registry.select(NodeId("old-local-id"))
    except ValueError:
        pass
    else:
        raise AssertionError("obsolete placeholder crossed the node selection boundary")


def test_install_verification_is_cwd_independent_and_launcher_is_interpreter_bound() -> (
    None
):
    common = (ROOT / "install" / "_common.sh").read_text(encoding="utf-8")
    user = (ROOT / "install" / "install-user.sh").read_text(encoding="utf-8")
    assert '(cd / && "$py" - "$expected"' in common
    assert 'metadata.version("system-analyzer")' in common
    assert "import maintenance" in common and "import window" in common
    assert 'install_pip "$py" -m pip install --user "$wheel"' in user
    assert 'bin_dir="$($py -c' in user


if __name__ == "__main__":
    test_obsolete_local_looking_record_cannot_cross_action_boundary()
    test_install_verification_is_cwd_independent_and_launcher_is_interpreter_bound()
    print("H1 interpreter/verification boundary: PASS")
    print("H2 trust/selectability/destructive-action boundary: PASS")

"""Agent 5 evidence counter-test for BUG-20260910-001.

Read-only checks of the installed/source version boundary and the conditional
stale-node projection state.  This is not a normal regression test.
"""

from __future__ import annotations

import importlib.metadata
import logging
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LOGGER = logging.getLogger(__name__)


def test_installed_probe_is_not_the_stale_venv() -> None:
    source = subprocess.run(
        [sys.executable, "-c", "import maintenance; print(maintenance.__version__)"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    installed = subprocess.run(
        [sys.executable, "-c", "import maintenance; print(maintenance.__version__)"],
        cwd=Path("/"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert source == importlib.metadata.version("system-analyzer")
    assert installed == source


def test_obsolete_id_duplicate_is_non_operational() -> None:
    from maintenance.cluster import ClusterState, trusted_node_record
    from maintenance.components.node_context import restore_trusted_nodes
    from maintenance.nodes import (
        NodeContext,
        NodeId,
        NodeRegistry,
        local_node_descriptor,
    )
    from maintenance.ui.window_supports.node_specs import cluster_node_specs

    local = replace(local_node_descriptor(), id=NodeId("current-local-id"))
    registry = NodeRegistry(
        NodeContext(local, object(), object(), object(), object(), object())
    )
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
    rows = cluster_node_specs(registry)
    duplicate = [row for row in rows if row.display_name == "This System"]
    old = registry.context(NodeId("old-local-id"))
    old_row = next(row for row in rows if row.node_id == "old-local-id")
    assert len(duplicate) == 2
    assert old.descriptor.is_local is False
    assert old.provider is None and old.scheduler is None
    assert old_row.selectable is False


if __name__ == "__main__":
    test_installed_probe_is_not_the_stale_venv()
    test_obsolete_id_duplicate_is_non_operational()
    print("H1 source/installed boundary: PASS")
    print("H2 conditional duplicate/non-operational boundary: PASS")

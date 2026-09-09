"""Opposer 1 probes for installed-version shadowing and stale local rows.

This is a read-only counter-test. It uses subprocess import locations and the
pure node registry/projection APIs; it does not create a Tk root or persist
cluster state.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


class UnexpectedWarningHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        raise AssertionError(f"unexpected restore warning: {record.getMessage()}")


def no_warning_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.addHandler(UnexpectedWarningHandler())
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    return logger


def version_probe(cwd: Path) -> dict[str, str]:
    code = """
import importlib.metadata as metadata
import maintenance
import window
print(metadata.version('system-analyzer'))
print(maintenance.__version__)
print(maintenance.__file__)
print(window.__file__)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    values = result.stdout.strip().splitlines()
    return dict(zip(("metadata", "module", "maintenance", "window"), values))


def test_h1_source_and_installed_versions() -> None:
    source = version_probe(ROOT)
    installed = version_probe(Path("/"))
    assert source["metadata"] == source["module"]
    assert installed["metadata"] == installed["module"]
    assert source["module"] == installed["module"]
    assert str(ROOT) in source["maintenance"]
    assert str(ROOT) not in installed["maintenance"]
    print(f"H1 PASS: source={source['module']} installed={installed['module']}")
    print(
        f"H1 locations: source={source['maintenance']} installed={installed['maintenance']}"
    )


def test_h2_current_local_record_is_skipped() -> None:
    from maintenance.cluster import ClusterState, trusted_node_record
    from maintenance.components.node_context import restore_trusted_nodes
    from maintenance.nodes import NodeContext, NodeRegistry, local_node_descriptor

    registry = NodeRegistry(
        NodeContext(
            local_node_descriptor(), object(), object(), object(), object(), object()
        )
    )
    state = ClusterState(
        local_node_id="local",
        trusted_nodes=(
            trusted_node_record(
                node_id="local",
                display_name="This System",
                hostname="old-host",
                host="old-host",
            ),
        ),
    )
    restore_trusted_nodes(
        registry=registry,
        cluster_state=state,
        logger=no_warning_logger("agent1.current-id"),
    )
    assert len(registry.contexts()) == 1
    print("H2 current-ID stale record: PASS (no duplicate)")


def test_h2_old_local_id_can_duplicate() -> None:
    from maintenance.cluster import ClusterState, trusted_node_record
    from maintenance.components.node_context import restore_trusted_nodes
    from maintenance.nodes import NodeContext, NodeRegistry, local_node_descriptor
    from maintenance.ui.window_supports.node_specs import cluster_node_specs

    current_id = "current-local-id"
    registry = NodeRegistry(
        NodeContext(
            local_node_descriptor(),
            object(),
            object(),
            object(),
            object(),
            object(),
        )
    )
    local = registry.contexts()[0]
    local.descriptor = replace(
        local.descriptor, id=local.descriptor.id.__class__(current_id)
    )
    state = ClusterState(
        local_node_id=current_id,
        trusted_nodes=(
            trusted_node_record(
                node_id="old-local-id",
                display_name="This System",
                hostname="old-host",
                host="old-host",
            ),
        ),
    )
    restore_trusted_nodes(
        registry=registry,
        cluster_state=state,
        logger=no_warning_logger("agent1.old-id"),
    )
    rows = cluster_node_specs(registry)
    duplicate = [row for row in rows if row.display_name == "This System"]
    assert len(duplicate) == 2
    print("H2 old-ID stale record: REPRODUCED (two This System rows)")


if __name__ == "__main__":
    test_h1_source_and_installed_versions()
    test_h2_current_local_record_is_skipped()
    test_h2_old_local_id_can_duplicate()

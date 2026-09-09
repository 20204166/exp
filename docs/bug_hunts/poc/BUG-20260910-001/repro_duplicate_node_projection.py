"""Read-only fresh-registry control probe."""

import sys
from collections import Counter
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from maintenance.cluster import ClusterState
from maintenance.components.node_context import build_local_node_context
from maintenance.nodes import NodeRegistry

state = ClusterState(local_node_id="fresh-local")
registry = NodeRegistry()
registry.register_context(
    build_local_node_context(
        cluster_state=state,
        analyzer=Mock(),
        process_manager=Mock(),
        file_manager=Mock(),
        scheduler=Mock(),
        coordinator=Mock(),
        snapshot=None,
        capabilities={},
        hostname="fresh-host",
        platform_name="Linux",
        stable_node_id=lambda: "fresh-local",
    )
)
descriptors = tuple(context.descriptor for context in registry.contexts())
ids = Counter(descriptor.id.value for descriptor in descriptors)
names = Counter(descriptor.display_name for descriptor in descriptors)
print(f"ids={dict(ids)}")
print(f"display_names={dict(names)}")

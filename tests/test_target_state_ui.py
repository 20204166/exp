"""Focused tests for the pure target-state presentation matrix."""

import unittest
from datetime import datetime, timezone

from maintenance.models import CapabilityState
from maintenance.nodes import (
    NodeCapability,
    NodeDescriptor,
    NodeId,
    NodePermission,
    NodeStatus,
    NodeTrustState,
)
from maintenance.ui.target_state import TargetState, render_target_state
from tests.support.models import make_snapshot, make_summary


def descriptor(
    *,
    trust: NodeTrustState = NodeTrustState.TRUSTED,
    status: NodeStatus = NodeStatus.ONLINE,
    capabilities: frozenset[NodeCapability] = frozenset(),
    permissions: frozenset[NodePermission] = frozenset(),
) -> NodeDescriptor:
    return NodeDescriptor(
        id=NodeId("opaque-peer"),
        display_name="Peer",
        hostname="not-an-authorization-signal",
        is_local=trust is NodeTrustState.LOCAL,
        trust=trust,
        status=status,
        capabilities=capabilities,
        permissions=permissions,
    )


def snapshot():
    return make_snapshot(
        make_summary(
            "cpu",
            "CPU",
            value="42%",
            subtitle="valid",
            percent=42,
            capability=CapabilityState.SUPPORTED,
        ),
        system_label="Peer",
        scanned_at=datetime.now(timezone.utc),
    )


class TargetStatePresentationTests(unittest.TestCase):
    def test_matrix_distinguishes_trust_and_permissions(self) -> None:
        read = frozenset({NodeCapability.PROCESS_REVIEW})
        review = frozenset({NodePermission.PROCESS_REVIEW})
        self.assertEqual(
            render_target_state(
                descriptor(
                    trust=NodeTrustState.LOCAL,
                    capabilities=read,
                    permissions=review,
                ),
                resource_key="cpu",
            ).state,
            TargetState.LOCAL,
        )
        self.assertEqual(
            render_target_state(
                descriptor(capabilities=read, permissions=review), resource_key="cpu"
            ).state,
            TargetState.REMOTE_READ_ONLY,
        )
        self.assertEqual(
            render_target_state(
                descriptor(capabilities=read), resource_key="cpu"
            ).state,
            TargetState.PERMISSION_DENIED,
        )
        self.assertEqual(
            render_target_state(descriptor(), resource_key="cpu").state,
            TargetState.UNSUPPORTED,
        )

    def test_offline_keeps_last_value_and_hides_actions(self) -> None:
        state = render_target_state(
            descriptor(
                status=NodeStatus.OFFLINE,
                capabilities=frozenset(NodeCapability),
                permissions=frozenset(NodePermission),
            ),
            snapshot(),
            "cpu",
        )
        self.assertEqual(state.label, "Offline")
        self.assertFalse(state.can_review)
        self.assertFalse(state.can_quit)
        self.assertFalse(state.can_cleanup)
        self.assertEqual(state.value, "42%")

    def test_remote_trusted_requires_target_owned_destructive_grant(self) -> None:
        state = render_target_state(
            descriptor(
                capabilities=frozenset(
                    {NodeCapability.PROCESS_REVIEW, NodeCapability.PROCESS_TERMINATION}
                ),
                permissions=frozenset(
                    {NodePermission.PROCESS_REVIEW, NodePermission.PROCESS_TERMINATION}
                ),
            ),
            resource_key="cpu",
        )
        self.assertEqual(state.state, TargetState.REMOTE_TRUSTED)
        self.assertTrue(state.can_review)
        self.assertTrue(state.can_quit)

    def test_remote_cleanup_affordance_stays_disabled_without_target_contract(
        self,
    ) -> None:
        state = render_target_state(
            descriptor(
                capabilities=frozenset(
                    {NodeCapability.STORAGE_REVIEW, NodeCapability.CLEANUP}
                ),
                permissions=frozenset(
                    {NodePermission.STORAGE_REVIEW, NodePermission.CLEANUP}
                ),
            ),
            resource_key="storage",
        )
        self.assertTrue(state.can_review)
        self.assertFalse(state.can_cleanup)


if __name__ == "__main__":
    unittest.main()

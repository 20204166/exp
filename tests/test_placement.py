"""Pure placement policy tests."""

import unittest
from dataclasses import FrozenInstanceError, replace
from typing import Any

from maintenance.components import (
    JobClass,
    PlacementPolicy,
    PlacementRequest,
    PlacementView,
    placement_view_for_context,
)
from maintenance.nodes import (
    ConnectionState,
    NodeCapability,
    NodeConnectionStatus,
    NodeContext,
    NodeDescriptor,
    NodeId,
    NodeIdentityStatus,
    NodePermission,
    NodeStatus,
    NodeTrustState,
)


def _view(name: str = "local", *, local: bool = True, **changes: Any) -> PlacementView:
    view = PlacementView(
        NodeId(name),
        local,
        True,
        True,
        True,
        True,
        True,
        False,
        frozenset({NodeCapability.COMPONENT_READ}),
        frozenset({NodePermission.COMPONENT_READ}),
    )
    return replace(view, **changes)


def _request(**changes: Any) -> PlacementRequest:
    values: dict[str, Any] = {
        "operation": "component-read",
        "job_class": JobClass.MOVABLE,
        "target_node_id": None,
        "required_capability": NodeCapability.COMPONENT_READ,
    }
    values.update(changes)
    return PlacementRequest(**values)


def _context(
    name: str = "local",
    *,
    local: bool = True,
    trust: NodeTrustState | None = None,
    status: NodeStatus = NodeStatus.ONLINE,
    connection: ConnectionState | None = None,
    identity_status: NodeIdentityStatus = NodeIdentityStatus.VERIFIED,
) -> NodeContext:
    return NodeContext(
        descriptor=NodeDescriptor(
            id=NodeId(name),
            display_name=name,
            hostname=name,
            is_local=local,
            trust=(
                NodeTrustState.LOCAL
                if trust is None and local
                else trust or NodeTrustState.DISCOVERED
            ),
            status=status,
            capabilities=frozenset({NodeCapability.COMPONENT_READ}),
            permissions=frozenset({NodePermission.COMPONENT_READ}),
            identity_status=identity_status,
        ),
        provider=None,
        process_manager=None,
        file_manager=None,
        scheduler=None,
        coordinator=None,
        connection=connection or ConnectionState.unknown(),
    )


class PlacementPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = PlacementPolicy(clock=lambda: 100.0)

    def test_job_class_values(self) -> None:
        self.assertEqual(JobClass.LOCAL_BOUND.value, "local_bound")
        self.assertEqual(JobClass.TARGET_BOUND.value, "target_bound")
        self.assertEqual(JobClass.MOVABLE.value, "movable")

    def test_request_rejects_negative_transfer_sizes(self) -> None:
        with self.assertRaises(ValueError):
            _request(input_size_bytes=-1)
        with self.assertRaises(ValueError):
            _request(output_size_bytes=-1)

    def test_views_and_decisions_are_immutable(self) -> None:
        view = _view()
        with self.assertRaises(FrozenInstanceError):
            view.online = False  # type: ignore[misc]
        decision = self.policy.choose(_request(), ())
        with self.assertRaises(FrozenInstanceError):
            decision.reason = "changed"  # type: ignore[misc]

    def test_unknown_candidates_are_not_eligible(self) -> None:
        decision = self.policy.choose(
            _request(), (_view("peer", local=False, trusted=False),)
        )
        self.assertIsNone(decision.selected_node_id)
        self.assertEqual(decision.rejected, ((NodeId("peer"), "not trusted"),))

    def test_hard_filters_report_first_rejection(self) -> None:
        cases = (
            ("offline", "offline"),
            ("untrusted", "not trusted"),
            ("unauthenticated", "not authenticated"),
            ("protocol", "incompatible protocol"),
            ("identity", "invalid identity"),
            ("shutdown", "shutting down"),
            ("capability", "missing capability"),
            ("permission", "missing permission"),
        )
        changes: dict[str, dict[str, Any]] = {
            "offline": {"online": False},
            "untrusted": {"trusted": False},
            "unauthenticated": {"authenticated": False},
            "protocol": {"protocol_compatible": False},
            "identity": {"identity_valid": False},
            "shutdown": {"shutting_down": True},
            "capability": {"capabilities": frozenset()},
            "permission": {"permissions": frozenset()},
        }
        for name, reason in cases:
            with self.subTest(name=name):
                decision = self.policy.choose(
                    _request(required_permission=NodePermission.COMPONENT_READ),
                    (_view("peer", local=False, **changes[name]),),
                )
                self.assertEqual(decision.rejected[0][1], reason)

    def test_local_and_target_bound_jobs_cannot_move(self) -> None:
        local = _view()
        peer = _view("peer", local=False)
        local_decision = self.policy.choose(
            _request(job_class=JobClass.LOCAL_BOUND), (peer, local)
        )
        self.assertEqual(local_decision.selected_node_id, NodeId("local"))
        target_decision = self.policy.choose(
            _request(job_class=JobClass.TARGET_BOUND, target_node_id=NodeId("peer")),
            (local, peer),
        )
        self.assertEqual(target_decision.selected_node_id, NodeId("peer"))

    def test_movable_ranking_is_deterministic_and_ignores_stale_latency(self) -> None:
        views = (
            _view("local", active_jobs=4),
            _view(
                "peer-b",
                local=False,
                active_jobs=1,
                recent_latency_ms=2.0,
                metrics_observed_at=100.0,
            ),
            _view(
                "peer-a",
                local=False,
                active_jobs=1,
                recent_latency_ms=1.0,
                metrics_observed_at=60.0,
            ),
        )
        decision = self.policy.choose(_request(input_size_bytes=1000), views)
        self.assertEqual(decision.selected_node_id, NodeId("peer-b"))
        self.assertIn("active jobs", decision.reason)

    def test_small_movable_job_prefers_eligible_local_node(self) -> None:
        decision = self.policy.choose(
            _request(input_size_bytes=1, remote_transfer_threshold_bytes=1),
            (_view("peer", local=False, active_jobs=0), _view(active_jobs=10)),
        )
        self.assertEqual(decision.selected_node_id, NodeId("local"))

    def test_request_rejects_invalid_transfer_threshold(self) -> None:
        with self.assertRaises(ValueError):
            _request(remote_transfer_threshold_bytes=-1)
        with self.assertRaises(ValueError):
            _request(remote_transfer_threshold_bytes=1.5)

    def test_local_context_defaults_to_authenticated_and_compatible(self) -> None:
        view = placement_view_for_context(_context())
        self.assertTrue(view.trusted)
        self.assertTrue(view.authenticated)
        self.assertTrue(view.online)
        self.assertTrue(view.protocol_compatible)

    def test_trusted_online_remote_requires_explicit_protocol_compatibility(self) -> None:
        context = _context(
            "peer",
            local=False,
            trust=NodeTrustState.TRUSTED,
            connection=ConnectionState.online(),
        )
        view = placement_view_for_context(context)
        self.assertTrue(view.trusted)
        self.assertTrue(view.authenticated)
        self.assertTrue(view.online)
        self.assertFalse(view.protocol_compatible)
        self.assertTrue(
            placement_view_for_context(
                context, protocol_compatible=True
            ).protocol_compatible
        )

    def test_offline_and_discovered_contexts_are_ineligible(self) -> None:
        offline = placement_view_for_context(
            _context(
                "peer",
                local=False,
                trust=NodeTrustState.TRUSTED,
                status=NodeStatus.OFFLINE,
                connection=ConnectionState.online(),
            ),
            protocol_compatible=True,
        )
        discovered = placement_view_for_context(
            _context(
                "discovered",
                local=False,
            ),
            protocol_compatible=True,
        )
        request = _request()
        self.assertEqual(
            self.policy.choose(request, (offline,)).rejected[0][1], "offline"
        )
        self.assertEqual(
            self.policy.choose(request, (discovered,)).rejected[0][1], "not trusted"
        )
        self.assertFalse(discovered.authenticated)

        failed = placement_view_for_context(
            _context(
                "failed",
                local=False,
                trust=NodeTrustState.TRUSTED,
                connection=ConnectionState(
                    NodeConnectionStatus.AUTHENTICATION_FAILED
                ),
            ),
            protocol_compatible=True,
        )
        self.assertFalse(failed.authenticated)
        self.assertFalse(failed.online)

    def test_identity_mismatch_is_ineligible(self) -> None:
        view = placement_view_for_context(
            _context(
                "peer",
                local=False,
                trust=NodeTrustState.AUTHORISED,
                connection=ConnectionState.online(),
                identity_status=NodeIdentityStatus.MISMATCH,
            ),
            protocol_compatible=True,
        )
        decision = self.policy.choose(_request(), (view,))
        self.assertEqual(decision.rejected[0][1], "invalid identity")


if __name__ == "__main__":
    unittest.main()

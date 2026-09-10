"""Pure placement policy tests."""

import unittest
from dataclasses import FrozenInstanceError, replace
from typing import Any

from maintenance.components import (
    JobClass,
    PlacementPolicy,
    PlacementRequest,
    PlacementView,
)
from maintenance.nodes import NodeCapability, NodeId, NodePermission


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
            _request(input_size_bytes=1),
            (_view("peer", local=False, active_jobs=0), _view(active_jobs=10)),
        )
        self.assertEqual(decision.selected_node_id, NodeId("local"))


if __name__ == "__main__":
    unittest.main()

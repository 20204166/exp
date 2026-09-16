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
from maintenance.components.coordinator import AppCoordinator
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
    node_operation_key,
)
from maintenance.ui.render_coordinator import RenderIntent, UICoordinator


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
        # Same-cluster + eligible Worker but untrusted: trust check still fires.
        decision = self.policy.choose(
            _request(),
            (_view("peer", local=False, trusted=False, same_cluster=True, worker_eligible=True),),
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
                    (
                        _view(
                            "peer",
                            local=False,
                            same_cluster=True,
                            worker_eligible=True,
                            **changes[name],
                        ),
                    ),
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
            _view("local", active_jobs=4, same_cluster=True, worker_eligible=True),
            _view(
                "peer-b",
                local=False,
                active_jobs=1,
                recent_latency_ms=2.0,
                metrics_observed_at=100.0,
                same_cluster=True,
                worker_eligible=True,
            ),
            _view(
                "peer-a",
                local=False,
                active_jobs=1,
                recent_latency_ms=1.0,
                metrics_observed_at=60.0,
                same_cluster=True,
                worker_eligible=True,
            ),
        )
        decision = self.policy.choose(_request(input_size_bytes=1000), views)
        self.assertEqual(decision.selected_node_id, NodeId("peer-b"))
        self.assertIn("active jobs", decision.reason)

    def test_small_movable_job_prefers_eligible_local_node(self) -> None:
        decision = self.policy.choose(
            _request(input_size_bytes=1, remote_transfer_threshold_bytes=1),
            (
                _view("peer", local=False, active_jobs=0, same_cluster=True, worker_eligible=True),
                _view(active_jobs=10, same_cluster=True, worker_eligible=True),
            ),
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

    def test_trusted_online_remote_requires_explicit_protocol_compatibility(
        self,
    ) -> None:
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
            same_cluster=True,
            worker_eligible=True,
        )
        # A discovered node has no verified cluster membership (same_cluster=None
        # default); it fails at "not in cluster" before the trust check.
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
            self.policy.choose(request, (discovered,)).rejected[0][1], "not in cluster"
        )
        self.assertFalse(discovered.authenticated)

        failed = placement_view_for_context(
            _context(
                "failed",
                local=False,
                trust=NodeTrustState.TRUSTED,
                connection=ConnectionState(NodeConnectionStatus.AUTHENTICATION_FAILED),
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
            same_cluster=True,
            worker_eligible=True,
        )
        decision = self.policy.choose(_request(), (view,))
        self.assertEqual(decision.rejected[0][1], "invalid identity")

    def test_target_bound_operations_select_only_their_explicit_target(self) -> None:
        local = _view(
            "local",
            capabilities=frozenset(
                {
                    NodeCapability.COMPONENT_READ,
                    NodeCapability.PROCESS_REVIEW,
                    NodeCapability.STORAGE_REVIEW,
                    NodeCapability.PROCESS_TERMINATION,
                }
            ),
            permissions=frozenset(
                {
                    NodePermission.COMPONENT_READ,
                    NodePermission.PROCESS_REVIEW,
                    NodePermission.STORAGE_REVIEW,
                    NodePermission.PROCESS_TERMINATION,
                }
            ),
        )
        node_b = replace(local, node_id=NodeId("node-b"), is_local=False)
        node_c = replace(local, node_id=NodeId("node-c"), is_local=False)
        cases = (
            ("component:cpu", NodeCapability.COMPONENT_READ, None),
            (
                "process_review",
                NodeCapability.PROCESS_REVIEW,
                NodePermission.PROCESS_REVIEW,
            ),
            (
                "storage_review",
                NodeCapability.STORAGE_REVIEW,
                NodePermission.STORAGE_REVIEW,
            ),
            (
                "process_request_quit",
                NodeCapability.PROCESS_TERMINATION,
                NodePermission.PROCESS_TERMINATION,
            ),
        )

        for operation, capability, permission in cases:
            with self.subTest(operation=operation):
                decision = self.policy.choose(
                    PlacementRequest(
                        operation,
                        JobClass.TARGET_BOUND,
                        NodeId("node-b"),
                        capability,
                        permission,
                    ),
                    (local, node_b, node_c),
                )
                self.assertEqual(decision.selected_node_id, NodeId("node-b"))
                self.assertEqual(decision.eligible_node_ids, (NodeId("node-b"),))

    def test_target_bound_requests_fail_closed_for_missing_or_mismatched_targets(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            PlacementRequest(
                "component:cpu",
                JobClass.TARGET_BOUND,
                None,
                NodeCapability.COMPONENT_READ,
            )

        decision = self.policy.choose(
            PlacementRequest(
                "component:cpu",
                JobClass.TARGET_BOUND,
                NodeId("node-b"),
                NodeCapability.COMPONENT_READ,
            ),
            (_view(), _view("node-c", local=False)),
        )
        self.assertIsNone(decision.selected_node_id)
        self.assertEqual(
            decision.rejected,
            (
                (NodeId("local"), "target mismatch"),
                (NodeId("node-c"), "target mismatch"),
            ),
        )

    def test_unauthorized_and_invalid_views_are_never_selected(self) -> None:
        request = _request(required_permission=NodePermission.COMPONENT_READ)
        # Cluster facts supplied so these tests exercise the downstream reasons.
        auth_failed = placement_view_for_context(
            _context(
                "auth-failed",
                local=False,
                trust=NodeTrustState.TRUSTED,
                connection=ConnectionState(NodeConnectionStatus.AUTHENTICATION_FAILED),
            ),
            protocol_compatible=True,
            same_cluster=True,
            worker_eligible=True,
        )
        identity_changed = _view(
            "identity-changed",
            local=False,
            identity_valid=False,
            same_cluster=True,
            worker_eligible=True,
        )
        cases = (
            # No cluster facts → fail closed at "not in cluster" (not "not trusted").
            (
                "no-cluster-facts",
                placement_view_for_context(
                    _context("no-cluster-facts", local=False), protocol_compatible=True
                ),
                "not in cluster",
            ),
            (
                "trusted-but-unauthorized",
                _view(
                    "trusted",
                    capabilities=frozenset(),
                    permissions=frozenset(),
                    same_cluster=True,
                    worker_eligible=True,
                ),
                "missing capability",
            ),
            (
                "capability-only",
                _view(
                    "capability-only",
                    permissions=frozenset(),
                    same_cluster=True,
                    worker_eligible=True,
                ),
                "missing permission",
            ),
            (
                "unauthenticated",
                _view(
                    "unauthenticated",
                    authenticated=False,
                    same_cluster=True,
                    worker_eligible=True,
                ),
                "not authenticated",
            ),
            ("auth-failed", auth_failed, "not authenticated"),
            ("identity-changed", identity_changed, "invalid identity"),
            (
                "revoked",
                _view("revoked", trusted=False, same_cluster=True, worker_eligible=True),
                "not trusted",
            ),
            (
                "incompatible-protocol",
                _view(
                    "old-protocol",
                    protocol_compatible=False,
                    same_cluster=True,
                    worker_eligible=True,
                ),
                "incompatible protocol",
            ),
        )
        for name, view, reason in cases:
            with self.subTest(name=name):
                decision = self.policy.choose(request, (view,))
                self.assertIsNone(decision.selected_node_id)
                self.assertEqual(decision.rejected, ((view.node_id, reason),))

    def test_node_keys_and_late_results_remain_target_isolated(self) -> None:
        node_a_key = node_operation_key(NodeId("node-a"), "analysis")
        node_b_key = node_operation_key(NodeId("node-b"), "analysis")
        self.assertNotEqual(node_a_key, node_b_key)

        workers: list[Any] = []
        deliveries: list[Any] = []
        app = AppCoordinator(runner=workers.append, deliver=deliveries.append)
        renders = UICoordinator()
        renders.invalidate("component:cpu", node_id=NodeId("node-b"))
        committed: list[RenderIntent] = []

        def on_result(key: str, value: Any) -> None:
            renders.request(
                RenderIntent(
                    "component:cpu",
                    generation=1,
                    node_id=NodeId(key.split(":")[1]),
                    payload=value,
                    payload_set=True,
                ),
                committed.append,
            )

        app.run(
            node_a_key,
            lambda _cancel, _progress: "node-a-result",
            on_result=on_result,
        )
        app.run(node_b_key, lambda _cancel, _progress: "node-b-result")
        workers[0]()
        deliveries.pop(0)()

        self.assertEqual(committed, [])
        self.assertEqual(renders.stale_rejections, 1)
        self.assertTrue(app.in_flight(node_b_key))


class MovablePlacementEligibilityTests(unittest.TestCase):
    """PlacementPolicy rejects MOVABLE candidates that fail cluster/role checks."""

    def setUp(self) -> None:
        self.policy = PlacementPolicy()

    def _movable_request(self) -> PlacementRequest:
        return _request(job_class=JobClass.MOVABLE)

    def test_trusted_non_member_is_ineligible_for_movable(self) -> None:
        view = _view("peer", local=False, same_cluster=False)
        decision = self.policy.choose(self._movable_request(), (view,))
        self.assertIsNone(decision.selected_node_id)
        self.assertEqual(decision.rejected[0], (NodeId("peer"), "not in cluster"))

    def test_cluster_member_without_worker_role_is_ineligible(self) -> None:
        view = _view("sub", local=False, same_cluster=True, worker_eligible=False)
        decision = self.policy.choose(self._movable_request(), (view,))
        self.assertIsNone(decision.selected_node_id)
        self.assertEqual(decision.rejected[0], (NodeId("sub"), "not a worker"))

    def test_paused_worker_is_ineligible(self) -> None:
        view = _view("paused", local=False, same_cluster=True, worker_eligible=False)
        decision = self.policy.choose(self._movable_request(), (view,))
        self.assertIsNone(decision.selected_node_id)
        self.assertEqual(decision.rejected[0][1], "not a worker")

    def test_revoked_member_is_ineligible(self) -> None:
        # Revoked: not in cluster (same_cluster=False) takes precedence.
        view = _view("revoked", local=False, same_cluster=False, worker_eligible=False)
        decision = self.policy.choose(self._movable_request(), (view,))
        self.assertIsNone(decision.selected_node_id)
        self.assertEqual(decision.rejected[0][1], "not in cluster")

    def test_wrong_cluster_member_is_ineligible(self) -> None:
        view = _view("other", local=False, same_cluster=False)
        decision = self.policy.choose(self._movable_request(), (view,))
        self.assertIsNone(decision.selected_node_id)
        self.assertEqual(decision.rejected[0][1], "not in cluster")

    def test_offline_cluster_worker_is_rejected_for_offline_not_cluster(self) -> None:
        view = _view(
            "worker", local=False, online=False, same_cluster=True, worker_eligible=True
        )
        decision = self.policy.choose(self._movable_request(), (view,))
        self.assertIsNone(decision.selected_node_id)
        self.assertEqual(decision.rejected[0][1], "offline")

    def test_identity_mismatch_is_rejected_for_identity_not_cluster(self) -> None:
        view = _view(
            "worker",
            local=False,
            identity_valid=False,
            same_cluster=True,
            worker_eligible=True,
        )
        decision = self.policy.choose(self._movable_request(), (view,))
        self.assertIsNone(decision.selected_node_id)
        self.assertEqual(decision.rejected[0][1], "invalid identity")

    def test_eligible_remote_worker_is_selected(self) -> None:
        view = _view("worker", local=False, same_cluster=True, worker_eligible=True)
        decision = self.policy.choose(self._movable_request(), (view,))
        self.assertEqual(decision.selected_node_id, NodeId("worker"))

    def test_local_worker_is_eligible(self) -> None:
        view = _view("local", local=True, same_cluster=True, worker_eligible=True)
        decision = self.policy.choose(self._movable_request(), (view,))
        self.assertEqual(decision.selected_node_id, NodeId("local"))

    def test_coordinator_worker_is_eligible(self) -> None:
        # COORDINATOR implies WORKER via RoleAssignment.__post_init__; same applies here.
        view = _view("coord", local=False, same_cluster=True, worker_eligible=True)
        decision = self.policy.choose(self._movable_request(), (view,))
        self.assertEqual(decision.selected_node_id, NodeId("coord"))

    def test_subcoordinator_without_worker_role_is_ineligible(self) -> None:
        view = _view("sub", local=False, same_cluster=True, worker_eligible=False)
        decision = self.policy.choose(self._movable_request(), (view,))
        self.assertIsNone(decision.selected_node_id)
        self.assertEqual(decision.rejected[0][1], "not a worker")

    def test_target_bound_ignores_same_cluster_and_worker_eligible(self) -> None:
        # TARGET_BOUND does not check these fields — regression guard.
        view = _view("target", local=False, same_cluster=False, worker_eligible=False)
        request = _request(
            job_class=JobClass.TARGET_BOUND, target_node_id=NodeId("target")
        )
        decision = self.policy.choose(request, (view,))
        self.assertEqual(decision.selected_node_id, NodeId("target"))

    def test_target_bound_with_none_cluster_fields_is_not_rejected(self) -> None:
        # TARGET_BOUND ignores same_cluster and worker_eligible even when None.
        view = _view("target", local=False)  # same_cluster=None, worker_eligible=None
        request = _request(
            job_class=JobClass.TARGET_BOUND, target_node_id=NodeId("target")
        )
        decision = self.policy.choose(request, (view,))
        self.assertEqual(decision.selected_node_id, NodeId("target"))

    def test_movable_with_unknown_cluster_membership_fails_closed(self) -> None:
        # same_cluster=None (omitted) must not be treated as eligible for MOVABLE.
        view = _view("peer", local=False, worker_eligible=True)  # same_cluster=None
        decision = self.policy.choose(self._movable_request(), (view,))
        self.assertIsNone(decision.selected_node_id)
        self.assertEqual(decision.rejected[0][1], "not in cluster")

    def test_movable_with_unknown_worker_eligibility_fails_closed(self) -> None:
        # worker_eligible=None (omitted) must not be treated as eligible for MOVABLE.
        view = _view("peer", local=False, same_cluster=True)  # worker_eligible=None
        decision = self.policy.choose(self._movable_request(), (view,))
        self.assertIsNone(decision.selected_node_id)
        self.assertEqual(decision.rejected[0][1], "not a worker")

    def test_single_machine_explicit_facts_leave_local_eligible(self) -> None:
        # Build the view the way build_movable_views does — caller supplies facts.
        view = placement_view_for_context(
            _context(), same_cluster=True, worker_eligible=True
        )
        request = _request()
        decision = self.policy.choose(request, (view,))
        self.assertEqual(decision.selected_node_id, NodeId("local"))

    def test_single_machine_default_fields_fail_closed_for_movable(self) -> None:
        # placement_view_for_context without cluster facts → same_cluster=None → rejected.
        view = placement_view_for_context(_context())
        request = _request()
        decision = self.policy.choose(request, (view,))
        self.assertIsNone(decision.selected_node_id)
        self.assertEqual(decision.rejected[0][1], "not in cluster")


if __name__ == "__main__":
    unittest.main()

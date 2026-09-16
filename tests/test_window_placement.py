"""Tests for the target-bound placement wiring used by window orchestration."""

import unittest
from unittest.mock import Mock

from maintenance.cluster import ClusterState
from maintenance.components.cluster_roles import ClusterRole, RoleAssignment
from maintenance.components.coordinator import AppCoordinator
from maintenance.components.placement import JobClass, PlacementDecision
from maintenance.nodes import (
    ConnectionState,
    NodeCapability,
    NodeContext,
    NodeId,
    NodePermission,
    NodeRegistry,
    NodeStatus,
    NodeTrustState,
)
from maintenance.ui import window_placement, window_scan
from tests.support.nodes import make_local_context, make_remote_context
from window import AppWindow


class _FakeSelection:
    """Bypass ``NodeSelection``'s full wiring; only ``selected_context`` matters."""

    def __init__(self, context: NodeContext | None) -> None:
        self._context = context

    def selected_context(self) -> NodeContext | None:
        return self._context


def _make_controller(registry: NodeRegistry | None = None) -> AppWindow:
    controller = object.__new__(AppWindow)
    controller.__dict__["_coordinator"] = AppCoordinator(
        deliver=lambda callback: callback()
    )
    if registry is not None:
        controller.__dict__["_node_registry"] = registry
    return controller


class TargetContextResolutionTests(unittest.TestCase):
    def test_returns_the_explicit_context_unchanged(self) -> None:
        controller = _make_controller()
        context = make_local_context()

        self.assertIs(window_placement.target_context(controller, context), context)

    def test_resolves_local_context_from_the_registry_when_none_selected(
        self,
    ) -> None:
        registry = NodeRegistry()
        local = make_local_context()
        registry.register_context(local)
        controller = _make_controller(registry)

        self.assertIs(window_placement.target_context(controller, None), local)

    def test_returns_none_when_no_registry_is_wired_up_yet(self) -> None:
        controller = _make_controller()

        self.assertIsNone(window_placement.target_context(controller, None))

    def test_returns_none_when_the_registry_has_no_local_context(self) -> None:
        controller = _make_controller(NodeRegistry())

        self.assertIsNone(window_placement.target_context(controller, None))


class ValidateTargetPlacementTests(unittest.TestCase):
    def test_returns_none_when_the_target_cannot_be_resolved(self) -> None:
        controller = _make_controller()

        decision = window_placement.validate_target_placement(
            controller,
            None,
            operation="component:cpu",
            required_capability=NodeCapability.COMPONENT_READ,
        )

        self.assertIsNone(decision)

    def test_selects_an_eligible_explicit_target(self) -> None:
        registry = NodeRegistry()
        registry.register_context(make_local_context())
        remote = make_remote_context(
            "dev",
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.ONLINE,
            capabilities=[NodeCapability.COMPONENT_READ],
            permissions=[NodePermission.COMPONENT_READ],
            connection=ConnectionState.online(),
        )
        registry.register_context(remote)
        controller = _make_controller(registry)

        decision = window_placement.validate_target_placement(
            controller,
            remote,
            operation="component:cpu",
            required_capability=NodeCapability.COMPONENT_READ,
            required_permission=NodePermission.COMPONENT_READ,
        )

        self.assertIsInstance(decision, PlacementDecision)
        self.assertEqual(decision.selected_node_id, remote.node_id)

    def test_rejects_a_target_missing_the_required_capability(self) -> None:
        registry = NodeRegistry()
        registry.register_context(make_local_context())
        remote = make_remote_context(
            "dev",
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.ONLINE,
            permissions=[NodePermission.COMPONENT_READ],
            connection=ConnectionState.online(),
        )
        registry.register_context(remote)
        controller = _make_controller(registry)

        decision = window_placement.validate_target_placement(
            controller,
            remote,
            operation="component:cpu",
            required_capability=NodeCapability.COMPONENT_READ,
            required_permission=NodePermission.COMPONENT_READ,
        )

        self.assertIsNotNone(decision)
        self.assertIsNone(decision.selected_node_id)
        self.assertIn((remote.node_id, "missing capability"), decision.rejected)

    def test_rejects_an_offline_target(self) -> None:
        registry = NodeRegistry()
        registry.register_context(make_local_context())
        remote = make_remote_context(
            "dev",
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.OFFLINE,
            capabilities=[NodeCapability.COMPONENT_READ],
            permissions=[NodePermission.COMPONENT_READ],
        )
        registry.register_context(remote)
        controller = _make_controller(registry)

        decision = window_placement.validate_target_placement(
            controller,
            remote,
            operation="component:cpu",
            required_capability=NodeCapability.COMPONENT_READ,
        )

        self.assertIsNotNone(decision)
        self.assertIsNone(decision.selected_node_id)

    def test_never_selects_a_different_node_than_the_explicit_target(self) -> None:
        """A trusted, fully-eligible second node must never be substituted."""

        registry = NodeRegistry()
        registry.register_context(make_local_context())
        target = make_remote_context(
            "dev",
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.OFFLINE,
            capabilities=[NodeCapability.COMPONENT_READ],
            permissions=[NodePermission.COMPONENT_READ],
        )
        other = make_remote_context(
            "other",
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.ONLINE,
            capabilities=[NodeCapability.COMPONENT_READ],
            permissions=[NodePermission.COMPONENT_READ],
        )
        registry.register_context(target)
        registry.register_context(other)
        controller = _make_controller(registry)

        decision = window_placement.validate_target_placement(
            controller,
            target,
            operation="component:cpu",
            required_capability=NodeCapability.COMPONENT_READ,
        )

        self.assertIsNone(decision.selected_node_id)
        self.assertNotIn(NodeId("other"), decision.eligible_node_ids)

    def test_records_the_decision_on_the_controller_for_diagnostics(self) -> None:
        registry = NodeRegistry()
        local = make_local_context()
        registry.register_context(local)
        controller = _make_controller(registry)

        decision = window_placement.validate_target_placement(
            controller,
            None,
            operation="component:cpu",
            required_capability=NodeCapability.COMPONENT_READ,
        )

        self.assertIs(controller.__dict__["_last_placement_decision"], decision)

    def test_job_class_is_always_target_bound(self) -> None:
        registry = NodeRegistry()
        registry.register_context(make_local_context())
        controller = _make_controller(registry)
        coordinator = Mock()
        coordinator.choose_placement.return_value = PlacementDecision(
            None, (), (), "stub"
        )
        controller.__dict__["_coordinator"] = coordinator

        window_placement.validate_target_placement(
            controller,
            None,
            operation="component:cpu",
            required_capability=NodeCapability.COMPONENT_READ,
        )

        request, _views = coordinator.choose_placement.call_args.args
        self.assertEqual(request.job_class, JobClass.TARGET_BOUND)
        self.assertEqual(request.operation, "component:cpu")


class HandleAnalyzePlacementTests(unittest.TestCase):
    def _controller(
        self, registry: NodeRegistry, context: NodeContext | None
    ) -> AppWindow:
        controller = _make_controller(registry)
        controller.__dict__["_is_closing"] = False
        controller.__dict__["_node_selection_component"] = _FakeSelection(context)
        controller.__dict__["_selected_node_id"] = (
            context.node_id if context is not None else None
        )
        controller.__dict__["_show_error"] = Mock()
        controller.__dict__["_sync_dashboard_scan_state"] = Mock()
        return controller

    def test_analyze_is_rejected_for_a_target_missing_dashboard_read(self) -> None:
        registry = NodeRegistry()
        registry.register_context(make_local_context())
        remote = make_remote_context(
            "dev",
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.ONLINE,
            connection=ConnectionState.online(),
            permissions=frozenset(NodePermission),
        )
        registry.register_context(remote)
        controller = self._controller(registry, remote)
        lifecycle = Mock()
        controller.__dict__["_dashboard_scan_lifecycle"] = Mock(return_value=lifecycle)

        window_scan.handle_analyze(controller)

        lifecycle.start.assert_not_called()
        controller.__dict__["_show_error"].assert_called_once()

    def test_analyze_still_proceeds_for_an_eligible_target(self) -> None:
        registry = NodeRegistry()
        local = make_local_context()
        registry.register_context(local)
        controller = self._controller(registry, local)
        lifecycle = Mock()
        controller.__dict__["_dashboard_scan_lifecycle"] = Mock(return_value=lifecycle)

        window_scan.handle_analyze(controller)

        lifecycle.start.assert_called_once()
        controller.__dict__["_show_error"].assert_not_called()


class BuildMovableViewsTests(unittest.TestCase):
    """build_movable_views projects cluster state into MOVABLE-ready views."""

    def _cluster_state(
        self, *assignments: RoleAssignment, local_node_id: str = "coord"
    ) -> ClusterState:
        state = ClusterState.create_local(local_node_id=local_node_id)
        state.role_assignments = tuple(assignments)
        return state

    def test_returns_empty_when_no_registry_wired(self) -> None:
        controller = _make_controller()
        state = self._cluster_state()
        views = window_placement.build_movable_views(controller, cluster_state=state)
        self.assertEqual(views, ())

    def test_non_member_remote_gets_same_cluster_false(self) -> None:
        registry = NodeRegistry()
        registry.register_context(make_local_context())
        remote = make_remote_context(
            "peer",
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.ONLINE,
            capabilities=[NodeCapability.COMPONENT_READ],
            permissions=[NodePermission.COMPONENT_READ],
            connection=ConnectionState.online(),
        )
        registry.register_context(remote)
        controller = _make_controller(registry)
        state = self._cluster_state(
            RoleAssignment(frozenset({ClusterRole.WORKER}), node_id=NodeId("coord"))
        )
        views = window_placement.build_movable_views(controller, cluster_state=state)
        peer_view = next(v for v in views if v.node_id == NodeId("peer"))
        self.assertFalse(peer_view.same_cluster)
        self.assertFalse(peer_view.worker_eligible)

    def test_active_worker_member_is_eligible(self) -> None:
        registry = NodeRegistry()
        registry.register_context(make_local_context())
        worker = make_remote_context(
            "worker1",
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.ONLINE,
            capabilities=[NodeCapability.COMPONENT_READ],
            permissions=[NodePermission.COMPONENT_READ],
            connection=ConnectionState.online(),
        )
        registry.register_context(worker)
        controller = _make_controller(registry)
        state = self._cluster_state(
            RoleAssignment(
                frozenset({ClusterRole.WORKER}), node_id=NodeId("worker1")
            )
        )
        views = window_placement.build_movable_views(controller, cluster_state=state)
        worker_view = next(v for v in views if v.node_id == NodeId("worker1"))
        self.assertTrue(worker_view.same_cluster)
        self.assertTrue(worker_view.worker_eligible)
        self.assertEqual(worker_view.active_jobs, 0)

    def test_paused_worker_has_worker_eligible_false(self) -> None:
        registry = NodeRegistry()
        registry.register_context(make_local_context())
        worker = make_remote_context("paused-worker", trust=NodeTrustState.TRUSTED)
        registry.register_context(worker)
        controller = _make_controller(registry)
        state = self._cluster_state(
            RoleAssignment(
                frozenset({ClusterRole.WORKER}),
                node_id=NodeId("paused-worker"),
                paused=True,
            )
        )
        views = window_placement.build_movable_views(controller, cluster_state=state)
        view = next(v for v in views if v.node_id == NodeId("paused-worker"))
        self.assertTrue(view.same_cluster)
        self.assertFalse(view.worker_eligible)

    def test_revoked_member_has_both_false(self) -> None:
        registry = NodeRegistry()
        registry.register_context(make_local_context())
        worker = make_remote_context("revoked-worker", trust=NodeTrustState.TRUSTED)
        registry.register_context(worker)
        controller = _make_controller(registry)
        state = self._cluster_state(
            RoleAssignment(
                frozenset({ClusterRole.WORKER}),
                node_id=NodeId("revoked-worker"),
                revoked=True,
            )
        )
        views = window_placement.build_movable_views(controller, cluster_state=state)
        view = next(v for v in views if v.node_id == NodeId("revoked-worker"))
        self.assertFalse(view.same_cluster)
        self.assertFalse(view.worker_eligible)

    def test_active_job_wires_to_active_jobs_field(self) -> None:
        registry = NodeRegistry()
        registry.register_context(make_local_context())
        worker = make_remote_context("busy-worker", trust=NodeTrustState.TRUSTED)
        registry.register_context(worker)
        controller = _make_controller(registry)
        state = self._cluster_state(
            RoleAssignment(
                frozenset({ClusterRole.WORKER}),
                node_id=NodeId("busy-worker"),
                has_active_job=True,
            )
        )
        views = window_placement.build_movable_views(controller, cluster_state=state)
        view = next(v for v in views if v.node_id == NodeId("busy-worker"))
        self.assertEqual(view.active_jobs, 1)


if __name__ == "__main__":
    unittest.main()

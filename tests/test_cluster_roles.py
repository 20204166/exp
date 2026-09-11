import unittest

from maintenance.components.cluster_roles import (
    ClusterRole,
    CoordinatorEpoch,
    FencingError,
    RoleAssignment,
    RoleAuthorizationError,
    RoleState,
    promote_subcoordinator,
    rejoin_as_worker,
    renew_lease,
)
from maintenance.nodes import NodeId


class ClusterRoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator = RoleAssignment(
            frozenset({ClusterRole.COORDINATOR}), NodeId("coord")
        )
        self.worker = RoleAssignment(frozenset({ClusterRole.WORKER}), NodeId("worker"))
        self.sub = RoleAssignment(
            frozenset({ClusterRole.SUBCOORDINATOR}), NodeId("sub")
        )

    def test_coordinator_always_has_worker_role(self) -> None:
        self.assertIn(ClusterRole.WORKER, self.coordinator.roles)

    def test_worker_cannot_assign_roles(self) -> None:
        with self.assertRaises(RoleAuthorizationError):
            RoleState().assign(
                actor=self.worker,
                target=NodeId("peer"),
                roles=frozenset({ClusterRole.WORKER}),
            )

    def test_only_one_subcoordinator(self) -> None:
        state = RoleState(assignments=(self.coordinator, self.sub))
        with self.assertRaises(RoleAuthorizationError):
            state.assign(
                actor=self.coordinator,
                target=NodeId("other"),
                roles=frozenset({ClusterRole.SUBCOORDINATOR}),
            )

    def test_two_active_coordinators_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RoleState(
                assignments=(
                    self.coordinator,
                    RoleAssignment(
                        frozenset({ClusterRole.COORDINATOR}), NodeId("other")
                    ),
                )
            )

    def test_promotion_increments_epoch_after_timeout(self) -> None:
        state = RoleState(
            assignments=(self.coordinator, self.sub),
            epoch=CoordinatorEpoch(7, NodeId("coord"), "token", 0.0, 100.0),
        )
        decision = promote_subcoordinator(state, now=120.1)
        self.assertEqual(decision.epoch.epoch, 8)
        self.assertEqual(decision.epoch.coordinator_id, NodeId("sub"))

    def test_promotion_before_timeout_is_rejected(self) -> None:
        state = RoleState(
            assignments=(self.coordinator, self.sub),
            epoch=CoordinatorEpoch(7, NodeId("coord"), "token", 0.0, 100.0),
        )
        with self.assertRaises(FencingError):
            promote_subcoordinator(state, now=99.0)

    def test_stale_lease_token_is_rejected(self) -> None:
        epoch = CoordinatorEpoch(1, NodeId("coord"), "token", 0.0, 100.0)
        with self.assertRaises(FencingError):
            renew_lease(
                epoch,
                coordinator_id=NodeId("coord"),
                fencing_token="old",
                now=10.0,
            )

    def test_non_finite_epoch_times_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CoordinatorEpoch(1, NodeId("coord"), "token", float("nan"), 100.0)

    def test_returning_coordinator_is_fenced_to_worker(self) -> None:
        state = RoleState(
            assignments=(self.coordinator, self.sub),
            epoch=CoordinatorEpoch(8, NodeId("sub"), "new", 0.0, 100.0),
        )
        returned = rejoin_as_worker(state, node_id=NodeId("coord"), current_epoch=8)
        self.assertEqual(
            returned.assignment_for(NodeId("coord")).roles,
            frozenset({ClusterRole.WORKER}),
        )

"""Focused tests for the UI presentation coordinator."""

import unittest

from maintenance.ui.render_coordinator import RenderIntent, UICoordinator


class UICoordinatorTests(unittest.TestCase):
    def test_batched_requests_coalesce_latest_payload_and_fields(self) -> None:
        coordinator = UICoordinator()
        received: list[RenderIntent] = []

        coordinator.begin_batch()
        coordinator.request(
            RenderIntent(
                target="dashboard",
                payload="first",
                payload_set=True,
                components=frozenset({"cpu"}),
            ),
            received.append,
        )
        coordinator.request(
            RenderIntent(
                target="dashboard",
                payload="second",
                payload_set=True,
                components=frozenset({"network"}),
                layout_changed=True,
                priority=2,
            ),
            received.append,
        )

        self.assertEqual(received, [])
        self.assertEqual(coordinator.pending_count, 1)
        self.assertEqual(coordinator.coalesced_requests, 1)

        coordinator.end_batch()

        self.assertEqual(len(received), 1)
        intent = received[0]
        self.assertEqual(intent.payload, "second")
        self.assertEqual(intent.components, frozenset({"cpu", "network"}))
        self.assertTrue(intent.layout_changed)
        self.assertEqual(coordinator.render_commits, 1)

    def test_late_generation_is_rejected_and_does_not_retain_pending(self) -> None:
        coordinator = UICoordinator()
        coordinator.invalidate("dashboard", 2)
        received: list[RenderIntent] = []

        accepted = coordinator.request(
            RenderIntent(
                target="dashboard",
                generation=1,
                payload="old",
                payload_set=True,
            ),
            received.append,
        )

        self.assertFalse(accepted)
        self.assertEqual(received, [])
        self.assertEqual(coordinator.pending_count, 0)
        self.assertEqual(coordinator.stale_rejections, 1)

    def test_hidden_target_defers_until_visible(self) -> None:
        coordinator = UICoordinator()
        coordinator.set_visible("dashboard", False)
        received: list[str] = []

        coordinator.request(
            RenderIntent(target="dashboard", payload="cached", payload_set=True),
            lambda intent: received.append(str(intent.payload)),
        )

        self.assertEqual(received, [])
        self.assertEqual(coordinator.pending_count, 1)

        coordinator.set_visible("dashboard", True)

        self.assertEqual(received, ["cached"])
        self.assertEqual(coordinator.pending_count, 0)

    def test_repeated_requests_stay_bounded_to_one_pending_entry(self) -> None:
        coordinator = UICoordinator()
        received: list[str] = []

        coordinator.begin_batch()
        for index in range(100):
            coordinator.request(
                RenderIntent(
                    target="dashboard",
                    payload=f"value-{index}",
                    payload_set=True,
                ),
                lambda intent: received.append(str(intent.payload)),
            )

        self.assertEqual(coordinator.pending_count, 1)
        coordinator.end_batch()

        self.assertEqual(received, ["value-99"])
        self.assertEqual(coordinator.pending_count, 0)
        self.assertEqual(coordinator.render_commits, 1)

    def test_requests_during_flush_wait_for_the_same_batch(self) -> None:
        coordinator = UICoordinator()
        received: list[str] = []

        def apply_dashboard(_intent: RenderIntent) -> None:
            received.append("dashboard")
            coordinator.request(
                RenderIntent(
                    target="thermals",
                    payload="latest",
                    payload_set=True,
                ),
                lambda intent: received.append(str(intent.payload)),
            )

        coordinator.begin_batch()
        coordinator.request(
            RenderIntent(target="dashboard", payload_set=True),
            apply_dashboard,
        )
        coordinator.end_batch()

        self.assertEqual(received, ["dashboard", "latest"])
        self.assertEqual(coordinator.pending_count, 0)
        self.assertEqual(coordinator.render_commits, 2)

    def test_shutdown_clears_pending_and_rejects_later_requests(self) -> None:
        coordinator = UICoordinator()
        received: list[str] = []

        coordinator.begin_batch()
        coordinator.request(
            RenderIntent(target="dashboard", payload="queued", payload_set=True),
            lambda intent: received.append(str(intent.payload)),
        )

        self.assertEqual(coordinator.pending_count, 1)
        coordinator.shutdown()

        self.assertEqual(coordinator.pending_count, 0)
        self.assertFalse(
            coordinator.request(
                RenderIntent(target="dashboard", payload="late", payload_set=True),
                lambda intent: received.append(str(intent.payload)),
            )
        )
        coordinator.end_batch()

        self.assertEqual(received, [])

    def test_explicit_none_payload_clears_previous_payload(self) -> None:
        coordinator = UICoordinator()
        received: list[RenderIntent] = []

        coordinator.begin_batch()
        coordinator.request(
            RenderIntent(target="dashboard", payload="value", payload_set=True),
            received.append,
        )
        coordinator.request(
            RenderIntent(target="dashboard", payload=None, payload_set=True),
            received.append,
        )
        coordinator.end_batch()

        self.assertEqual(len(received), 1)
        self.assertIsNone(received[0].payload)
        self.assertTrue(received[0].payload_set)

    def test_node_mismatch_rejects_stale_pending_render(self) -> None:
        coordinator = UICoordinator()
        received: list[RenderIntent] = []

        coordinator.invalidate("component:cpu", generation=0, node_id="node-a")
        coordinator.request(
            RenderIntent(
                target="component:cpu",
                node_id="node-a",
                payload="old",
                payload_set=True,
            ),
            received.append,
        )
        coordinator.invalidate("component:cpu", generation=0, node_id="node-b")
        accepted = coordinator.request(
            RenderIntent(
                target="component:cpu",
                node_id="node-a",
                payload="stale",
                payload_set=True,
            ),
            received.append,
        )

        self.assertFalse(accepted)
        self.assertEqual(coordinator.pending_count, 0)


if __name__ == "__main__":
    unittest.main()

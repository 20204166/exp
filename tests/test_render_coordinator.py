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
                components=frozenset({"cpu"}),
            ),
            received.append,
        )
        coordinator.request(
            RenderIntent(
                target="dashboard",
                payload="second",
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
            RenderIntent(target="dashboard", generation=1, payload="old"),
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
            RenderIntent(target="dashboard", payload="cached"),
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
                RenderIntent(target="dashboard", payload=f"value-{index}"),
                lambda intent: received.append(str(intent.payload)),
            )

        self.assertEqual(coordinator.pending_count, 1)
        coordinator.end_batch()

        self.assertEqual(received, ["value-99"])
        self.assertEqual(coordinator.pending_count, 0)
        self.assertEqual(coordinator.render_commits, 1)

    def test_shutdown_clears_pending_and_rejects_later_requests(self) -> None:
        coordinator = UICoordinator()
        received: list[str] = []

        coordinator.begin_batch()
        coordinator.request(
            RenderIntent(target="dashboard", payload="queued"),
            lambda intent: received.append(str(intent.payload)),
        )

        self.assertEqual(coordinator.pending_count, 1)
        coordinator.shutdown()

        self.assertEqual(coordinator.pending_count, 0)
        self.assertFalse(
            coordinator.request(
                RenderIntent(target="dashboard", payload="late"),
                lambda intent: received.append(str(intent.payload)),
            )
        )
        coordinator.end_batch()

        self.assertEqual(received, [])


if __name__ == "__main__":
    unittest.main()

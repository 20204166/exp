import unittest
from collections.abc import Callable
from typing import cast
from unittest.mock import Mock

from maintenance.models import CapabilityState
from maintenance.preferences import AppPreferences
from maintenance.ui.window_supports import card_policy, snapshot_state
from maintenance.ui.window_supports.timer_delivery import (
    TimerDelivery,
    deadline_delay_ms,
)
from tests.support.models import make_snapshot, make_summary
from tests.support.scheduling import TimerMaster


class FailingCancelMaster(TimerMaster):
    def after_cancel(self, identifier: str) -> None:
        del identifier
        raise RuntimeError("event loop is not running")


class SnapshotStateTests(unittest.TestCase):
    def test_merge_snapshot_keeps_previous_failed_resource_until_limit(self) -> None:
        previous = make_snapshot(make_summary("cpu", "CPU", value="25%"))
        failed = make_summary("cpu", "CPU", value="Unavailable", failed=True)
        counts: dict[str, int] = {}

        merged = snapshot_state.merge_snapshot(
            previous_snapshot=previous,
            failed_counts=counts,
            snapshot=make_snapshot(failed),
            failed_card_keep_limit=3,
        )

        self.assertEqual(merged.get("cpu").value, "25%")
        self.assertEqual(counts["cpu"], 1)

    def test_merge_snapshot_shows_failed_resource_at_limit(self) -> None:
        previous = make_snapshot(make_summary("cpu", "CPU", value="25%"))
        failed = make_summary("cpu", "CPU", value="Unavailable", failed=True)
        counts = {"cpu": 2}

        merged = snapshot_state.merge_snapshot(
            previous_snapshot=previous,
            failed_counts=counts,
            snapshot=make_snapshot(failed),
            failed_card_keep_limit=3,
        )

        self.assertEqual(merged.get("cpu").value, "Unavailable")
        self.assertEqual(counts["cpu"], 3)

    def test_merge_resource_success_resets_failure_count(self) -> None:
        counts = {"cpu": 2}
        resource = make_summary("cpu", "CPU", value="30%")

        merged = snapshot_state.merge_resource(
            previous_snapshot=None,
            failed_counts=counts,
            key="cpu",
            resource=resource,
            failed_card_keep_limit=3,
        )

        self.assertIs(merged, resource)
        self.assertEqual(counts["cpu"], 0)

    def test_replace_snapshot_resource_preserves_other_resources(self) -> None:
        memory = make_summary("memory", "Memory", value="50%")
        replacement = make_summary("cpu", "CPU", value="30%")
        snapshot = make_snapshot(make_summary("cpu", "CPU"), memory)

        updated = snapshot_state.replace_snapshot_resource(
            snapshot,
            "cpu",
            replacement,
        )

        assert updated is not None
        self.assertIs(updated.get("cpu"), replacement)
        self.assertIs(updated.get("memory"), memory)


class CardPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.preferences = AppPreferences.defaults()

    def test_missing_preferences_keeps_card_visible(self) -> None:
        self.assertTrue(
            card_policy.is_card_visible(
                "gpu",
                preferences=None,
                capabilities={},
            )
        )

    def test_manual_visibility_applies_before_capability(self) -> None:
        preferences = self.preferences.with_card_visibility("gpu", False)

        self.assertFalse(
            card_policy.is_card_visible(
                "gpu",
                preferences=preferences,
                capabilities={},
            )
        )

    def test_unknown_capability_does_not_hide_card(self) -> None:
        preferences = self.preferences.with_hide_unavailable_cards(True)

        self.assertTrue(
            card_policy.is_card_visible(
                "gpu",
                preferences=preferences,
                capabilities={"gpu": CapabilityState.UNKNOWN},
            )
        )

    def test_polling_policy_keeps_health_cards_running(self) -> None:
        preferences = self.preferences.with_card_visibility("cpu", False)

        self.assertFalse(
            card_policy.should_pause_polling(
                "cpu",
                preferences=preferences,
                capabilities={},
            )
        )

    def test_polling_policy_pauses_manually_hidden_network(self) -> None:
        preferences = self.preferences.with_card_visibility("network", False)

        self.assertTrue(
            card_policy.should_pause_polling(
                "network",
                preferences=preferences,
                capabilities={},
            )
        )


class TimerDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.master = TimerMaster()
        self.pending_ids: set[str] = set()
        self.delivery = TimerDelivery(
            master=self.master,
            is_closing=lambda: False,
            pending_ids=self.pending_ids,
            logger=Mock(),
        )

    def test_schedule_tracks_and_removes_timer_before_delivery(self) -> None:
        callback = Mock()
        identifier = self.delivery.schedule(500, callback, "payload")

        self.assertEqual(identifier, "after#1")
        self.assertIn("after#1", self.pending_ids)
        cast(Callable[[], None], self.master.scheduled[0][1])()

        self.assertNotIn("after#1", self.pending_ids)
        callback.assert_called_once_with("payload")

    def test_cancel_removes_timer(self) -> None:
        identifier = self.delivery.schedule(500, Mock())
        assert identifier is not None

        self.assertTrue(self.delivery.cancel(identifier))
        self.assertNotIn(identifier, self.pending_ids)
        self.assertEqual(self.master.cancelled, [identifier])

    def test_schedule_suppresses_work_when_closing(self) -> None:
        delivery = TimerDelivery(
            master=self.master,
            is_closing=lambda: True,
            pending_ids=self.pending_ids,
            logger=Mock(),
        )

        self.assertIsNone(delivery.schedule(500, Mock()))
        self.assertEqual(self.master.scheduled, [])

    def test_cancel_failure_clears_identifier_while_closing(self) -> None:
        master = FailingCancelMaster()
        pending_ids = {"after#1"}
        delivery = TimerDelivery(
            master=master,
            is_closing=lambda: True,
            pending_ids=pending_ids,
            logger=Mock(),
        )

        self.assertFalse(delivery.cancel("after#1"))
        self.assertEqual(pending_ids, set())

    def test_invoke_logs_and_swallows_callback_failure(self) -> None:
        logger = Mock()

        TimerDelivery.invoke(Mock(side_effect=RuntimeError("dead widget")), logger)

        logger.warning.assert_called_once()

    def test_timer_interrupt_closes_window_instead_of_reentering_tk(self) -> None:
        close = Mock()
        delivery = TimerDelivery(
            master=self.master,
            is_closing=lambda: False,
            pending_ids=self.pending_ids,
            logger=Mock(),
            on_interrupt=close,
        )
        identifier = delivery.schedule(500, Mock(side_effect=KeyboardInterrupt()))
        assert identifier is not None

        cast(Callable[[], None], self.master.scheduled[0][1])()

        close.assert_called_once_with()
        self.assertNotIn(identifier, self.pending_ids)

    def test_deadline_delay_is_milliseconds_and_never_negative(self) -> None:
        self.assertEqual(deadline_delay_ms(12.25, 12.0), 250)
        self.assertEqual(deadline_delay_ms(11.9, 12.0), 0)


if __name__ == "__main__":
    unittest.main()

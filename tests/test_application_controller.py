"""Tests for toolkit-neutral application orchestration."""

from __future__ import annotations

import subprocess
import sys
import time
import unittest
from typing import Any


class ApplicationControllerTests(unittest.TestCase):
    def test_import_does_not_load_tkinter_in_fresh_process(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import maintenance.application_controller; "
                    "assert 'tkinter' not in sys.modules"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_controller_exposes_neutral_lifecycle_operations(self) -> None:
        from maintenance.application_controller import ApplicationController

        for method_name in (
            "_start_peer_listener",
            "_share_dashboard",
            "_share_dashboard_with",
            "_start_dashboard_shares",
            "_stop_sharing_with",
            "_share_dashboard_with_coordinator",
            "_reschedule_dashboard_share_timer",
            "_expire_dashboard_shares",
            "_start_discovery",
            "_stop_discovery",
            "_reconcile_peer_connections",
            "_show_preferences_page",
            "_show_nodes_page",
            "_show_cluster_page",
            "_show_diagnostics_page",
            "_show_help_page",
            "_close",
            "_resolution_for_generation",
            "_show_error_for_generation",
            "_show_node_snapshot_if_current",
        ):
            with self.subTest(method=method_name):
                self.assertTrue(
                    callable(getattr(ApplicationController, method_name, None))
                )

    def test_discovery_lifecycle_routes_to_canonical_session(self) -> None:
        from maintenance.application_controller import ApplicationController

        class Session:
            timer_id = "tick-1"
            started = False
            stopped = False

            def start(self) -> None:
                self.started = True

            def tick(self) -> None:
                self.timer_id = "tick-2"

            def stop(self) -> None:
                self.stopped = True

        controller: Any = ApplicationController.__new__(ApplicationController)
        session = Session()
        controller._discovery_session = session

        controller._start_discovery()
        self.assertTrue(session.started)
        self.assertEqual(controller._discovery_tick_id, "tick-1")
        controller._tick_discovery()
        self.assertEqual(controller._discovery_tick_id, "tick-2")
        controller._stop_discovery()
        self.assertTrue(session.stopped)
        self.assertIsNone(controller._discovery_tick_id)

    def test_dashboard_share_start_uses_peer_service_and_owned_expiry_timer(
        self,
    ) -> None:
        from maintenance.application_controller import ApplicationController

        class Service:
            def __init__(self) -> None:
                self.started: list[tuple[Any, float]] = []

            def start_dashboard_share_for(
                self, node_id: Any, *, expires_at: float
            ) -> None:
                self.started.append((node_id, expires_at))

        controller: Any = ApplicationController.__new__(ApplicationController)
        service = Service()
        scheduled: list[tuple[int, Any]] = []
        controller._peer_service = service
        controller._schedule_timer = lambda delay, callback: (
            scheduled.append((delay, callback)) or "share-timer"
        )
        controller._cancel_timer = lambda identifier: True

        self.assertTrue(controller._start_dashboard_shares(("caller-a",)))

        self.assertEqual(len(service.started), 1)
        self.assertEqual(service.started[0][0].value, "caller-a")
        self.assertAlmostEqual(service.started[0][1] - time.time(), 300, delta=2)
        self.assertEqual(
            controller._peer_dashboard_shares["caller-a"], service.started[0][1]
        )
        self.assertEqual(controller._dashboard_share_timer_id, "share-timer")
        self.assertEqual(scheduled[0][1], controller._expire_dashboard_shares)

    def test_dashboard_share_expiry_clears_peer_and_refreshes_pages(self) -> None:
        from maintenance.application_controller import ApplicationController

        class Service:
            def __init__(self) -> None:
                self.cleared: list[Any] = []

            def clear_dashboard_share(self, node_id: Any) -> None:
                self.cleared.append(node_id)

        controller: Any = ApplicationController.__new__(ApplicationController)
        service = Service()
        controller._peer_service = service
        controller._peer_dashboard_shares = {"expired-peer": 0.0}
        controller._dashboard_share_timer_id = "old"
        controller._cancel_timer = lambda identifier: True
        controller._schedule_timer = lambda delay, callback: "next"
        refreshed: list[str] = []
        controller._refresh_cluster_page = lambda: refreshed.append("cluster")
        controller._refresh_nodes_page = lambda: refreshed.append("nodes")

        controller._expire_dashboard_shares()

        self.assertEqual(
            [node_id.value for node_id in service.cleared], ["expired-peer"]
        )
        self.assertEqual(controller._peer_dashboard_shares, {})
        self.assertIsNone(controller._dashboard_share_timer_id)
        self.assertEqual(refreshed, ["cluster", "nodes"])

    def test_expiry_reschedule_failure_fails_closed_for_remaining_shares(self) -> None:
        from maintenance.application_controller import ApplicationController

        class Service:
            def __init__(self) -> None:
                self.cleared: list[str] = []

            def clear_dashboard_share(self, node_id: Any) -> None:
                self.cleared.append(node_id.value)
                if node_id.value == "future-peer":
                    raise RuntimeError("service clear failed")

        controller: Any = ApplicationController.__new__(ApplicationController)
        service = Service()
        controller._peer_service = service
        controller._peer_dashboard_shares = {
            "expired-peer": 0.0,
            "future-peer": time.time() + 300,
        }
        controller._dashboard_share_timer_id = "fired"
        controller._cancel_timer = lambda identifier: True
        controller._schedule_timer = lambda delay, callback: (_ for _ in ()).throw(
            RuntimeError("replacement schedule failed")
        )
        refreshed: list[str] = []
        controller._refresh_cluster_page = lambda: refreshed.append("cluster")
        controller._refresh_nodes_page = lambda: refreshed.append("nodes")

        with self.assertRaisesRegex(RuntimeError, "replacement schedule failed"):
            controller._expire_dashboard_shares()

        self.assertEqual(service.cleared, ["expired-peer", "future-peer"])
        self.assertEqual(controller._peer_dashboard_shares, {})
        self.assertIsNone(controller._dashboard_share_timer_id)
        self.assertEqual(refreshed, ["cluster", "nodes"])

    def test_empty_dashboard_share_request_does_not_report_success(self) -> None:
        from maintenance.application_controller import ApplicationController

        controller: Any = ApplicationController.__new__(ApplicationController)
        controller._peer_service = object()

        self.assertFalse(controller._start_dashboard_shares(()))
        self.assertNotIn("_peer_dashboard_shares", controller.__dict__)
        self.assertNotIn("_dashboard_share_timer_id", controller.__dict__)

    def test_partial_dashboard_share_failure_rolls_back_started_peers(self) -> None:
        from maintenance.application_controller import ApplicationController

        class Service:
            def __init__(self) -> None:
                self.started: list[str] = []
                self.cleared: list[str] = []

            def start_dashboard_share_for(
                self, node_id: Any, *, expires_at: float
            ) -> None:
                if node_id.value == "peer-b":
                    raise RuntimeError("peer start failed")
                self.started.append(node_id.value)

            def clear_dashboard_share(self, node_id: Any) -> None:
                self.cleared.append(node_id.value)

        controller: Any = ApplicationController.__new__(ApplicationController)
        service = Service()
        scheduled: list[Any] = []
        controller._peer_service = service
        controller._schedule_timer = lambda delay, callback: (
            scheduled.append((delay, callback)) or "timer"
        )
        controller._cancel_timer = lambda identifier: True

        with self.assertRaisesRegex(RuntimeError, "peer start failed"):
            controller._start_dashboard_shares(("peer-a", "peer-b"))

        self.assertEqual(service.started, ["peer-a"])
        self.assertEqual(service.cleared, ["peer-a", "peer-b"])
        self.assertNotIn("_peer_dashboard_shares", controller.__dict__)
        self.assertNotIn("_dashboard_share_timer_id", controller.__dict__)
        self.assertEqual(scheduled, [])

    def test_partial_failure_restores_preexisting_share_and_expiry(self) -> None:
        from maintenance.application_controller import ApplicationController

        class Service:
            def __init__(self) -> None:
                self.active: dict[str, float] = {}
                self.cleared: list[str] = []

            def start_dashboard_share_for(
                self, node_id: Any, *, expires_at: float
            ) -> None:
                if node_id.value == "new-failure":
                    raise RuntimeError("peer start failed")
                self.active[node_id.value] = expires_at

            def clear_dashboard_share(self, node_id: Any) -> None:
                self.cleared.append(node_id.value)
                self.active.pop(node_id.value, None)

        controller: Any = ApplicationController.__new__(ApplicationController)
        service = Service()
        old_expiry = time.time() + 120
        service.active["existing"] = old_expiry
        controller._peer_service = service
        controller._peer_dashboard_shares = {"existing": old_expiry}
        controller._schedule_timer = lambda delay, callback: "timer"
        controller._cancel_timer = lambda identifier: True

        with self.assertRaisesRegex(RuntimeError, "peer start failed"):
            controller._start_dashboard_shares(("existing", "new-failure"))

        self.assertEqual(controller._peer_dashboard_shares, {"existing": old_expiry})
        self.assertEqual(service.active, {"existing": old_expiry})
        self.assertEqual(service.cleared, ["existing", "new-failure"])

    def test_failed_restoration_drops_controller_share_claim_and_logs(self) -> None:
        from maintenance.application_controller import ApplicationController

        class Service:
            def __init__(self) -> None:
                self.existing_starts = 0

            def start_dashboard_share_for(
                self, node_id: Any, *, expires_at: float
            ) -> None:
                if node_id.value == "new-failure":
                    raise RuntimeError("new peer start failed")
                self.existing_starts += 1
                if self.existing_starts == 2:
                    raise RuntimeError("restore failed")

            def clear_dashboard_share(self, node_id: Any) -> None:
                return None

        controller: Any = ApplicationController.__new__(ApplicationController)
        controller._peer_service = Service()
        controller._peer_dashboard_shares = {"existing": time.time() + 120}
        controller._dashboard_share_timer_id = "old-timer"
        controller._cancel_timer = lambda identifier: True
        controller._schedule_timer = lambda delay, callback: "replacement-timer"

        with (
            self.assertLogs("maintenance.application_controller", level="ERROR"),
            self.assertRaisesRegex(RuntimeError, "new peer start failed"),
        ):
            controller._start_dashboard_shares(("existing", "new-failure"))

        self.assertNotIn("existing", controller._peer_dashboard_shares)
        self.assertIsNone(controller._dashboard_share_timer_id)

    def test_reschedule_uses_nearest_expiry_and_replaces_existing_timer(self) -> None:
        from maintenance.application_controller import ApplicationController

        controller: Any = ApplicationController.__new__(ApplicationController)
        now = time.time()
        cancelled: list[Any] = []
        scheduled: list[tuple[int, Any]] = []
        controller._peer_dashboard_shares = {
            "later": now + 90,
            "nearest": now + 30,
        }
        controller._dashboard_share_timer_id = "old"
        controller._cancel_timer = lambda identifier: (
            cancelled.append(identifier) or True
        )
        controller._schedule_timer = lambda delay, callback: (
            scheduled.append((delay, callback)) or "replacement"
        )

        controller._reschedule_dashboard_share_timer()

        self.assertEqual(cancelled, ["old"])
        self.assertGreaterEqual(scheduled[0][0], 0)
        self.assertLessEqual(scheduled[0][0], 30_000)
        self.assertEqual(scheduled[0][1], controller._expire_dashboard_shares)
        self.assertEqual(controller._dashboard_share_timer_id, "replacement")

    def test_stopping_last_dashboard_share_cancels_and_clears_timer(self) -> None:
        from maintenance.application_controller import ApplicationController

        class Service:
            def clear_dashboard_share(self, node_id: Any) -> None:
                self.cleared = node_id.value

        controller: Any = ApplicationController.__new__(ApplicationController)
        service = Service()
        controller._peer_service = service
        controller._peer_dashboard_shares = {"peer": time.time() + 60}
        controller._dashboard_share_timer_id = "owned"
        cancelled: list[Any] = []
        controller._cancel_timer = lambda identifier: (
            cancelled.append(identifier) or True
        )
        controller._schedule_timer = lambda delay, callback: self.fail(
            "last share must not schedule another timer"
        )
        controller._nodes_status = lambda message: None
        controller._refresh_cluster_page = lambda: None
        controller._refresh_nodes_page = lambda: None

        controller._stop_sharing_with("peer")

        self.assertEqual(service.cleared, "peer")
        self.assertEqual(cancelled, ["owned"])
        self.assertEqual(controller._peer_dashboard_shares, {})
        self.assertIsNone(controller._dashboard_share_timer_id)

    def test_expiry_clear_failures_are_isolated_and_remaining_share_rescheduled(
        self,
    ) -> None:
        from maintenance.application_controller import ApplicationController

        class Service:
            def __init__(self) -> None:
                self.cleared: list[str] = []

            def clear_dashboard_share(self, node_id: Any) -> None:
                self.cleared.append(node_id.value)
                if node_id.value == "bad":
                    raise RuntimeError("clear failed")

        controller: Any = ApplicationController.__new__(ApplicationController)
        service = Service()
        controller._peer_service = service
        controller._peer_dashboard_shares = {
            "bad": 0.0,
            "good": 0.0,
            "remaining": time.time() + 60,
        }
        controller._dashboard_share_timer_id = "fired"
        scheduled: list[Any] = []
        controller._cancel_timer = lambda identifier: True
        controller._schedule_timer = lambda delay, callback: (
            scheduled.append((delay, callback)) or "next"
        )
        refreshed: list[bool] = []
        controller._refresh_dashboard_share_pages = lambda: refreshed.append(True)

        with self.assertLogs("maintenance.application_controller", level="ERROR"):
            controller._expire_dashboard_shares()

        self.assertEqual(service.cleared, ["bad", "good"])
        self.assertEqual(
            controller._peer_dashboard_shares,
            {"remaining": controller._peer_dashboard_shares["remaining"]},
        )
        self.assertEqual(controller._dashboard_share_timer_id, "next")
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(refreshed, [True])

    def test_reschedule_failure_preserves_old_owned_timer(self) -> None:
        from maintenance.application_controller import ApplicationController

        controller: Any = ApplicationController.__new__(ApplicationController)
        controller._peer_dashboard_shares = {"peer": time.time() + 60}
        controller._dashboard_share_timer_id = "old"
        cancelled: list[Any] = []
        controller._cancel_timer = lambda identifier: (
            cancelled.append(identifier) or True
        )

        def fail_schedule(delay: int, callback: Any) -> str:
            raise RuntimeError("schedule failed")

        controller._schedule_timer = fail_schedule
        with self.assertRaisesRegex(RuntimeError, "schedule failed"):
            controller._reschedule_dashboard_share_timer()
        self.assertEqual(cancelled, [])
        self.assertEqual(controller._dashboard_share_timer_id, "old")

    def test_start_schedule_failure_rolls_back_new_share_and_restores_old_share(
        self,
    ) -> None:
        from maintenance.application_controller import ApplicationController

        class Service:
            def __init__(self, expiry: float) -> None:
                self.active = {"old-peer": expiry}

            def start_dashboard_share_for(
                self, node_id: Any, *, expires_at: float
            ) -> None:
                self.active[node_id.value] = expires_at

            def clear_dashboard_share(self, node_id: Any) -> None:
                self.active.pop(node_id.value, None)

        old_expiry = time.time() + 120
        service = Service(old_expiry)
        controller: Any = ApplicationController.__new__(ApplicationController)
        controller._peer_service = service
        controller._peer_dashboard_shares = {"old-peer": old_expiry}
        controller._dashboard_share_timer_id = "old-timer"
        controller._cancel_timer = lambda identifier: True
        calls = 0

        def schedule(delay: int, callback: Any) -> str:
            nonlocal calls
            calls += 1
            raise RuntimeError("schedule failed")

        controller._schedule_timer = schedule
        with self.assertRaisesRegex(RuntimeError, "schedule failed"):
            controller._start_dashboard_shares(("new-peer",))
        self.assertEqual(controller._peer_dashboard_shares, {"old-peer": old_expiry})
        self.assertEqual(service.active, {"old-peer": old_expiry})
        self.assertEqual(controller._dashboard_share_timer_id, "old-timer")

    def test_explicit_stop_clear_failure_preserves_claim_and_timer(self) -> None:
        from maintenance.application_controller import ApplicationController

        class Service:
            def clear_dashboard_share(self, node_id: Any) -> None:
                raise RuntimeError("clear failed")

        controller: Any = ApplicationController.__new__(ApplicationController)
        expiry = time.time() + 60
        controller._peer_service = Service()
        controller._peer_dashboard_shares = {"peer": expiry}
        controller._dashboard_share_timer_id = "owned"
        controller._cancel_timer = lambda identifier: self.fail(
            "must retain expiry timer"
        )
        controller._nodes_status = lambda message: None
        controller._refresh_dashboard_share_pages = lambda: None
        with self.assertRaisesRegex(RuntimeError, "clear failed"):
            controller._stop_sharing_with("peer")
        self.assertEqual(controller._peer_dashboard_shares, {"peer": expiry})
        self.assertEqual(controller._dashboard_share_timer_id, "owned")


if __name__ == "__main__":
    unittest.main()

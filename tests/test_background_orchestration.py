import threading
import unittest
from queue import Queue
from typing import Any, cast
from unittest.mock import Mock

from maintenance.components.background_orchestration import BackgroundOrchestrator
from maintenance.ui.window_supports.timer_delivery import TimerDelivery


class BackgroundOrchestratorTests(unittest.TestCase):
    def make_orchestrator(self) -> tuple[BackgroundOrchestrator, dict[str, Any]]:
        state: dict[str, Any] = {
            "closing": False,
            "poll_id": None,
            "tasks": 0,
            "discovery": False,
        }
        queue: Queue[Any] = Queue()
        scheduled: list[tuple[int, object]] = []
        render = Mock()

        def schedule(delay: int, callback: object) -> str:
            scheduled.append((delay, callback))
            return "after#1"

        orchestrator = BackgroundOrchestrator(
            queue=queue,
            is_closing=lambda: bool(state["closing"]),
            schedule_timer=schedule,
            get_poll_id=lambda: state["poll_id"],
            set_poll_id=lambda identifier: state.__setitem__("poll_id", identifier),
            get_task_count=lambda: int(state["tasks"]),
            set_task_count=lambda count: state.__setitem__("tasks", count),
            set_busy=Mock(),
            resolve_completed_worker=Mock(),
            get_render_coordinator=lambda: render,
            has_pending_coordinator_work=lambda: False,
            has_discovery_tick=lambda: bool(state["discovery"]),
            invoke_delivered=lambda callback: TimerDelivery.invoke(callback, Mock()),
            poll_milliseconds=10,
            logger=Mock(),
        )
        state["scheduled"] = scheduled
        state["render"] = render
        return orchestrator, state

    def test_drain_preserves_queue_formats_and_batches_rendering(self) -> None:
        orchestrator, state = self.make_orchestrator()
        render = cast(Any, state["render"])
        callback = Mock()
        ui_callback = Mock()
        state["tasks"] = 1
        orchestrator._queue.put((callback, ("payload",)))
        orchestrator._queue.put(("ui", ui_callback))
        orchestrator._queue.put(("finished", Mock()))
        orchestrator._queue.put(None)

        orchestrator.drain_queue()

        callback.assert_called_once_with("payload")
        ui_callback.assert_called_once_with()
        render.begin_batch.assert_called_once_with()
        render.end_batch.assert_called_once_with()
        self.assertEqual(state["tasks"], 0)

    def test_drain_drops_callbacks_after_close_but_finishes_task_markers(self) -> None:
        orchestrator, state = self.make_orchestrator()
        state["closing"] = True
        state["tasks"] = 1
        callback = Mock()
        orchestrator._queue.put((callback, ("payload",)))
        orchestrator._queue.put(("ui", Mock()))
        orchestrator._queue.put(None)

        orchestrator.drain_queue()

        callback.assert_not_called()
        self.assertEqual(state["tasks"], 0)

    def test_start_poll_is_main_thread_only_and_does_not_duplicate(self) -> None:
        orchestrator, state = self.make_orchestrator()
        scheduled = cast(list[tuple[int, object]], state["scheduled"])
        orchestrator.start_poll()
        self.assertEqual(state["poll_id"], "after#1")
        self.assertEqual(scheduled, [(10, orchestrator.drain_queue)])

        worker = threading.Thread(target=orchestrator.start_poll)
        worker.start()
        worker.join()
        self.assertEqual(len(scheduled), 1)

    def test_drain_continues_after_legacy_callback_failure(self) -> None:
        orchestrator, state = self.make_orchestrator()
        state["tasks"] = 1
        callback = Mock(side_effect=RuntimeError("dead callback"))
        orchestrator._queue.put((callback, ()))
        orchestrator._queue.put(None)

        orchestrator.drain_queue()

        self.assertEqual(state["tasks"], 0)
        self.assertEqual(orchestrator._queue.qsize(), 0)


if __name__ == "__main__":
    unittest.main()

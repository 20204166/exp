import threading
import unittest
from queue import Queue
from typing import Any, cast
from unittest.mock import Mock

from maintenance.components.background_orchestration import BackgroundOrchestrator
from maintenance.ui.window_supports.timer_delivery import TimerDelivery
from tests.support.qt import get_qapplication


class BackgroundOrchestratorTests(unittest.TestCase):
    def make_orchestrator(
        self, *, max_drain_items: int | None = None
    ) -> tuple[BackgroundOrchestrator, dict[str, Any]]:
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
            max_drain_items=max_drain_items,
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

    def test_drain_yields_after_item_budget_and_keeps_polling(self) -> None:
        orchestrator, state = self.make_orchestrator(max_drain_items=2)
        callbacks = [Mock() for _ in range(3)]
        for callback in callbacks:
            orchestrator._queue.put((callback, ()))

        orchestrator.drain_queue()

        callbacks[0].assert_called_once_with()
        callbacks[1].assert_called_once_with()
        callbacks[2].assert_not_called()
        self.assertEqual(orchestrator._queue.qsize(), 1)
        self.assertEqual(
            cast(list[tuple[int, object]], state["scheduled"]),
            [(10, orchestrator.drain_queue)],
        )

    def test_progress_submission_keeps_only_newest_callback_per_key(self) -> None:
        orchestrator, _state = self.make_orchestrator()
        first = Mock()
        newest = Mock()
        orchestrator.submit_progress("scan", first)
        orchestrator.submit_progress("scan", newest)

        orchestrator.drain_queue()

        first.assert_not_called()
        newest.assert_called_once_with()

    def test_ui_submission_starts_poll_when_queue_is_idle(self) -> None:
        orchestrator, state = self.make_orchestrator()
        callback = Mock()

        orchestrator.submit_ui(callback)

        self.assertEqual(
            cast(list[tuple[int, object]], state["scheduled"]),
            [(10, orchestrator.drain_queue)],
        )
        orchestrator.drain_queue()
        callback.assert_called_once_with()

    def test_qt_delivery_adapter_affinity_progress_coalescing_and_finished_marker(
        self,
    ) -> None:
        from PySide6.QtCore import QThread
        from PySide6.QtTest import QTest

        from maintenance.ui.window_supports.qt_timer_delivery import (
            QtDeliveryQueue,
            QtTimerDelivery,
        )

        app = get_qapplication()
        delivery = QtDeliveryQueue()
        timers = QtTimerDelivery()
        queue: Queue[Any] = Queue()
        state: dict[str, Any] = {"poll": None, "tasks": 1, "closing": False}
        received: list[tuple[str, object]] = []
        orchestrator = BackgroundOrchestrator(
            queue=queue,
            is_closing=lambda: bool(state["closing"]),
            schedule_timer=lambda delay, callback: timers.schedule(delay, callback),
            get_poll_id=lambda: state["poll"],
            set_poll_id=lambda identifier: state.__setitem__("poll", identifier),
            get_task_count=lambda: int(state["tasks"]),
            set_task_count=lambda count: state.__setitem__("tasks", count),
            set_busy=lambda _busy: None,
            resolve_completed_worker=lambda: None,
            get_render_coordinator=lambda: None,
            has_pending_coordinator_work=lambda: False,
            has_discovery_tick=lambda: False,
            invoke_delivered=delivery.submit,
            poll_milliseconds=1,
            logger=Mock(),
            max_drain_items=1,
        )
        orchestrator.submit_progress(
            "scan", lambda: received.append(("old", QThread.currentThread()))
        )
        orchestrator.submit_progress(
            "scan", lambda: received.append(("latest", QThread.currentThread()))
        )

        def finish_task() -> None:
            received.append(("finished", QThread.currentThread()))
            state["tasks"] = 0

        queue.put(("finished", finish_task))
        for _ in range(20):
            if len(received) == 2:
                break
            QTest.qWait(10)
        self.assertEqual([name for name, _ in received], ["latest", "finished"])
        self.assertTrue(all(thread is app.thread() for _, thread in received))
        delivery.close()
        timers.close()

    def test_app_coordinator_keeps_deliver_injected_and_qt_affine(self) -> None:
        from PySide6.QtCore import QThread
        from PySide6.QtTest import QTest

        from maintenance.components.coordinator import AppCoordinator
        from maintenance.ui.window_supports.qt_timer_delivery import QtDeliveryQueue

        app = get_qapplication()
        delivery = QtDeliveryQueue()
        coordinator = AppCoordinator(
            deliver=delivery.submit,
            deliver_progress=lambda _key, callback: delivery.submit(callback),
        )
        delivered: list[tuple[str, object]] = []

        def task(_cancel: threading.Event, progress: Any) -> str:
            progress("working")
            return "result"

        coordinator.run(
            "qt-test",
            task,
            on_progress=lambda _key, _message: delivered.append(
                ("progress", QThread.currentThread())
            ),
            on_result=lambda _key, _result: delivered.append(
                ("result", QThread.currentThread())
            ),
            on_finished=lambda: delivered.append(("finished", QThread.currentThread())),
        )
        for _ in range(40):
            if len(delivered) == 3:
                break
            QTest.qWait(5)
        self.assertEqual(
            [name for name, _ in delivered], ["progress", "result", "finished"]
        )
        self.assertTrue(all(thread is app.thread() for _, thread in delivered))
        coordinator.shutdown()
        delivery.close()


if __name__ == "__main__":
    unittest.main()

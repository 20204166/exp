import threading
import unittest
from typing import Any

from tests.support.qt import get_qapplication


class QtBackgroundTaskRunnerTests(unittest.TestCase):
    def test_worker_results_progress_and_errors_are_delivered_via_qt_queue(
        self,
    ) -> None:
        from maintenance.components.background import BackgroundTaskRunner
        from maintenance.ui.window_supports.qt_timer_delivery import QtDeliveryQueue

        app = get_qapplication()
        delivery = QtDeliveryQueue()
        observed: list[tuple[str, object]] = []
        worker_finished = threading.Event()
        workers: list[threading.Thread] = []

        def run_task(task: Any) -> None:
            workers.append(
                BackgroundTaskRunner.run_with_delivery(
                    task,
                    lambda result: observed.append(("result", QThread.currentThread())),
                    delivery=delivery.submit,
                    on_error=lambda _message: observed.append(
                        ("error", QThread.currentThread())
                    ),
                    progress_task=lambda progress, _cancel: (
                        progress("progress"),
                        task(),
                    )[1],
                    on_progress=lambda _message: observed.append(
                        ("progress", QThread.currentThread())
                    ),
                    on_finished=worker_finished.set,
                )
            )

        from PySide6.QtCore import QThread
        from PySide6.QtTest import QTest

        run_task(lambda: None)
        workers[-1].join(2)
        self.assertFalse(workers[-1].is_alive())
        QTest.qWait(10)
        self.assertEqual([name for name, _ in observed], ["progress", "result"])
        self.assertTrue(all(thread is app.thread() for _, thread in observed))
        self.assertTrue(worker_finished.is_set())

        observed.clear()
        worker_finished.clear()
        run_task(lambda: (_ for _ in ()).throw(ValueError("expected")))
        workers[-1].join(2)
        self.assertFalse(workers[-1].is_alive())
        QTest.qWait(10)
        self.assertEqual([name for name, _ in observed], ["progress", "error"])
        self.assertIs(observed[0][1], app.thread())
        self.assertTrue(worker_finished.is_set())
        delivery.close()

    def test_cancelled_late_result_is_dropped_after_delivery_owner_closes(self) -> None:
        from maintenance.components.background import BackgroundTaskRunner
        from maintenance.ui.window_supports.qt_timer_delivery import QtDeliveryQueue

        app = get_qapplication()
        delivery = QtDeliveryQueue()
        cancel = threading.Event()
        worker_ready = threading.Event()
        calls: list[str] = []

        def task(_progress: Any, cancel_event: threading.Event) -> str:
            worker_ready.set()
            cancel_event.wait(2)
            return "late"

        worker = BackgroundTaskRunner.run_with_delivery(
            lambda: None,
            lambda _result: calls.append("result"),
            delivery=delivery.submit,
            on_error=lambda _message: calls.append("error"),
            progress_task=task,
            cancel_event=cancel,
        )
        self.assertTrue(worker_ready.wait(2))
        cancel.set()
        delivery.close()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        app.processEvents()
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()

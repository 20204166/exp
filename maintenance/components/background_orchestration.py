"""Background worker and Tk queue orchestration for the application window."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from functools import partial
from queue import Empty, Queue
from typing import Any, cast

BackgroundItem = tuple[Callable[..., None], tuple[object, ...]] | None | tuple[str, Any]


def _invoke_legacy_callback(
    callback: Callable[..., None], args: tuple[object, ...]
) -> None:
    callback(*args)


def run_daemon(
    task: Callable[[], Any],
    on_success: Callable[[Any], None],
    on_error: Callable[[Exception], None],
    on_finished: Callable[[], None] | None = None,
    *,
    logger: logging.Logger,
) -> None:
    """Run one task off the UI thread and invoke its hooks."""

    def worker() -> None:
        try:
            on_success(task())
        except Exception as error:  # noqa: BLE001 - failures reach the caller.
            logger.warning("Background task failed: %s", error)
            on_error(error)
        finally:
            if on_finished is not None:
                on_finished()

    threading.Thread(target=worker, daemon=True).start()


class BackgroundOrchestrator:
    """Coordinate daemon workers and delivery of their callbacks onto Tk."""

    def __init__(
        self,
        *,
        queue: Queue[BackgroundItem],
        is_closing: Callable[[], bool],
        schedule_timer: Callable[[int, Callable[[], None]], str | None],
        get_poll_id: Callable[[], str | None],
        set_poll_id: Callable[[str | None], None],
        get_task_count: Callable[[], int],
        set_task_count: Callable[[int], None],
        set_busy: Callable[[bool], None],
        resolve_completed_worker: Callable[[], None],
        get_render_coordinator: Callable[[], Any | None],
        has_pending_coordinator_work: Callable[[], bool],
        has_discovery_tick: Callable[[], bool],
        invoke_delivered: Callable[[Callable[[], None]], None],
        poll_milliseconds: int,
        logger: logging.Logger,
    ) -> None:
        self._queue = queue
        self._is_closing = is_closing
        self._schedule_timer = schedule_timer
        self._get_poll_id = get_poll_id
        self._set_poll_id = set_poll_id
        self._get_task_count = get_task_count
        self._set_task_count = set_task_count
        self._set_busy = set_busy
        self._resolve_completed_worker = resolve_completed_worker
        self._get_render_coordinator = get_render_coordinator
        self._has_pending_coordinator_work = has_pending_coordinator_work
        self._has_discovery_tick = has_discovery_tick
        self._invoke_delivered = invoke_delivered
        self._poll_milliseconds = poll_milliseconds
        self._logger = logger

    def run_daemon(
        self,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None],
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        """Run one task off the UI thread and invoke its hooks."""
        run_daemon(task, on_success, on_error, on_finished, logger=self._logger)

    def run_in_background(
        self,
        task: Callable[[], Any],
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        *,
        daemon_runner: Callable[..., None] | None = None,
    ) -> bool:
        self._set_busy(True)
        self._set_task_count(self._get_task_count() + 1)
        self.start_poll()

        def finish_on_ui() -> None:
            self._set_task_count(max(0, self._get_task_count() - 1))
            self._resolve_completed_worker()

        def on_finished() -> None:
            self._queue.put(("finished", finish_on_ui))

        success_callback = on_success
        error_callback = on_error
        if success_callback is None:
            raise ValueError("A success callback is required")
        if error_callback is None:
            raise ValueError("An error callback is required")
        try:
            (daemon_runner or self.run_daemon)(
                task,
                lambda result: self._queue.put((success_callback, (result,))),
                lambda error: self._queue.put((error_callback, (str(error),))),
                on_finished=on_finished,
            )
        except RuntimeError as error:
            finish_on_ui()
            error_callback(str(error))
            return False
        return True

    def submit_ui(self, callback: Callable[[], None]) -> None:
        self._queue.put(("ui", callback))

    def start_poll(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return
        if self._get_poll_id() is None and not self._is_closing():
            self._set_poll_id(
                self._schedule_timer(self._poll_milliseconds, self.drain_queue)
            )

    def drain_queue(self) -> None:
        self._set_poll_id(None)
        coordinator = self._get_render_coordinator()
        if coordinator is not None:
            coordinator.begin_batch()
        try:
            while True:
                try:
                    item = self._queue.get_nowait()
                except Empty:
                    break

                if item is None:
                    self._set_task_count(max(0, self._get_task_count() - 1))
                    self._resolve_completed_worker()
                    continue

                if isinstance(item, tuple) and len(item) == 2 and item[0] == "finished":
                    self._invoke_delivered(cast(Callable[[], None], item[1]))
                    continue

                if isinstance(item, tuple) and len(item) == 2 and item[0] == "ui":
                    if not self._is_closing():
                        self._invoke_delivered(cast(Callable[[], None], item[1]))
                    continue

                callback, args = cast(
                    tuple[Callable[..., None], tuple[object, ...]], item
                )
                if not self._is_closing():
                    self._invoke_delivered(
                        partial(_invoke_legacy_callback, callback, args)
                    )
        finally:
            if coordinator is not None:
                coordinator.end_batch()

        if not self._is_closing() and (
            self._get_task_count() > 0
            or self._has_pending_coordinator_work()
            or self._has_discovery_tick()
        ):
            self.start_poll()

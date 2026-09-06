"""Shared transition timing for status changes.

A ``PendingTransition`` applies one delayed state change at most once, and
starting a newer one always supersedes (cancels) any older pending change.
That is the "no flash" rule behind smooth status transitions: a stale
pending transition can never overwrite a newer state. Scheduling and
cancelling are injected, so it works with real Tk timers and with the fake
masters used in tests, and importing it creates no Tk root.
"""

from collections.abc import Callable
from typing import Any


class PendingTransition:
    """One cancellable, supersedable delayed state application.

    ``schedule(delay, apply)`` returns an identifier (or None when nothing
    could be scheduled, e.g. while closing); ``cancel(identifier)`` stops a
    pending timer. Starting a new transition cancels any currently pending
    one, so only the most recent state change is ever applied.
    """

    def __init__(
        self,
        schedule: Callable[[int, Callable[[], None]], Any],
        cancel: Callable[[Any], bool],
    ) -> None:
        self._schedule = schedule
        self._cancel = cancel
        self._id: Any = None

    @property
    def pending_id(self) -> Any:
        """The identifier of the currently pending timer, or None."""

        return self._id

    def start(self, delay: int, apply: Callable[[], None]) -> None:
        """Schedule ``apply`` after ``delay``, superseding any pending change."""

        if self._id is not None:
            self._cancel(self._id)
            self._id = None
        self._id = self._schedule(delay, self._run(apply))

    def cancel(self) -> None:
        """Cancel a pending change; safe to call when nothing is pending."""

        if self._id is not None:
            self._cancel(self._id)
            self._id = None

    def _run(self, apply: Callable[[], None]) -> Callable[[], None]:
        def run() -> None:
            self._id = None
            apply()

        return run

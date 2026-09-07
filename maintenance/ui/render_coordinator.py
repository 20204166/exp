"""Presentation render orchestration for the Tk UI.

This coordinator is intentionally small: it batches render commits that are
already validated by the application layer, coalesces repeated requests for the
same target, and drops stale presentation generations before a widget commit
can run.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RenderIntent:
    """Small dirty-field description for one presentation commit."""

    target: str
    generation: int = 0
    node_id: Any | None = None
    components: frozenset[str] = frozenset()
    layout_changed: bool = False
    style_changed: bool = False
    payload: Any | None = None
    priority: int = 0

    def merge(self, other: RenderIntent) -> RenderIntent:
        if self.target != other.target:
            raise ValueError("Cannot merge render intents for different targets")
        return RenderIntent(
            target=self.target,
            generation=max(self.generation, other.generation),
            node_id=other.node_id if other.node_id is not None else self.node_id,
            components=self.components | other.components,
            layout_changed=self.layout_changed or other.layout_changed,
            style_changed=self.style_changed or other.style_changed,
            payload=other.payload if other.payload is not None else self.payload,
            priority=max(self.priority, other.priority),
        )


@dataclass(slots=True)
class _PendingRender:
    intent: RenderIntent
    apply: Callable[[RenderIntent], None]


class UICoordinator:
    """Batch and coalesce presentation commits on the UI thread.

    The coordinator never scans, schedules workers, or mutates widgets by
    itself. Callers queue render intents and provide the actual widget-commit
    callback. Requests made inside ``begin_batch``/``end_batch`` are coalesced
    and committed once at the batch boundary.
    """

    def __init__(self) -> None:
        self._pending: dict[str, _PendingRender] = {}
        self._visible: dict[str, bool] = {}
        self._generations: dict[str, int] = {}
        self._batch_depth = 0
        self._closed = False
        self.render_requests = 0
        self.render_commits = 0
        self.coalesced_requests = 0
        self.stale_rejections = 0

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def begin_batch(self) -> None:
        if not self._closed:
            self._batch_depth += 1

    def end_batch(self) -> None:
        if self._batch_depth == 0:
            return
        self._batch_depth -= 1
        if self._batch_depth == 0:
            self.flush()

    def set_visible(self, target: str, visible: bool) -> None:
        self._visible[target] = visible
        if visible and self._batch_depth == 0:
            self.flush()

    def invalidate(self, target: str, generation: int | None = None) -> None:
        """Advance one target's presentation generation and drop stale work."""

        current = self._generations.get(target, 0)
        next_generation = (
            current + 1 if generation is None else max(current, generation)
        )
        self._generations[target] = next_generation
        pending = self._pending.get(target)
        if pending is not None and pending.intent.generation < next_generation:
            del self._pending[target]

    def clear(self, target: str | None = None) -> None:
        if target is None:
            self._pending.clear()
            self._generations.clear()
            self._visible.clear()
            return
        self._pending.pop(target, None)
        self._generations.pop(target, None)
        self._visible.pop(target, None)

    def shutdown(self) -> None:
        self._closed = True
        self.clear()

    def request(
        self,
        intent: RenderIntent,
        apply: Callable[[RenderIntent], None],
    ) -> bool:
        if self._closed:
            return False

        current = self._generations.get(intent.target, 0)
        if intent.generation < current:
            self.stale_rejections += 1
            return False
        if intent.generation > current:
            self._generations[intent.target] = intent.generation

        pending = self._pending.get(intent.target)
        if pending is None:
            self._pending[intent.target] = _PendingRender(intent=intent, apply=apply)
        else:
            self.coalesced_requests += 1
            self._pending[intent.target] = _PendingRender(
                intent=pending.intent.merge(intent),
                apply=apply,
            )
        self.render_requests += 1

        if self._batch_depth == 0 and self._visible.get(intent.target, True):
            self._apply_target(intent.target)
        return True

    def flush(self) -> None:
        if self._closed:
            return

        while True:
            ready = [
                (target, pending)
                for target, pending in self._pending.items()
                if self._visible.get(target, True)
                and pending.intent.generation >= self._generations.get(target, 0)
            ]
            if not ready:
                return
            ready.sort(
                key=lambda item: (
                    -item[1].intent.priority,
                    item[1].intent.target,
                )
            )
            if not self._apply_target(ready[0][0]):
                return

    def _apply_target(self, target: str) -> bool:
        pending = self._pending.get(target)
        if pending is None:
            return False
        current = self._generations.get(target, 0)
        if pending.intent.generation < current:
            self.stale_rejections += 1
            del self._pending[target]
            return False
        if not self._visible.get(target, True):
            return False

        del self._pending[target]
        try:
            pending.apply(pending.intent)
        except Exception as error:  # noqa: BLE001 - dead widgets must not break later renders.
            LOGGER.warning("Render commit for %s failed: %s", target, error)
        self.render_commits += 1
        return True

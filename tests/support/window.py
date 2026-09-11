"""Shared bare ``AppWindow`` builder for headless window/UI tests.

The shared core mirrors the scheduler/timer attribute set ``AppWindow`` methods
depend on. Each test file supplies ``overrides`` for the attributes its
scenario specializes (widget fakes, preferences, node registry wiring, a custom
coordinator), so the duplicated attribute assembly lives in one place while
specialized wiring stays local.
"""

from queue import Queue
from typing import Any

from maintenance.components import ResourceFeatureCatalog, ScanCoordinator
from maintenance.components.coordinator import (
    AppCoordinator,
    ComponentRefreshScheduler,
)
from tests.support.scheduling import TimerMaster
from window import AppWindow


def make_window(master: Any | None = None, **overrides: Any) -> Any:
    """Build a bare ``AppWindow`` with the shared scheduler/timer core.

    ``overrides`` are assigned onto the instance so callers can inject widget
    fakes, preferences, or a custom coordinator without repeating the core.
    """

    window: Any = object.__new__(AppWindow)
    window.master = master if master is not None else TimerMaster()
    window._is_closing = False
    window._pending_after_ids = set()
    window._background_poll_id = None
    window._background_tasks = 0
    window._scan_coordinator = ScanCoordinator()
    window._analysis_cancel_event = None
    window._scan_timeout_id = None
    window._resolved_scan_generation = 0
    window._background_queue = Queue()
    window._component_scheduler = ComponentRefreshScheduler()
    window._feature_catalog = ResourceFeatureCatalog()
    window._component_poll_id = None
    window._component_queue = Queue()
    window._coordinator = AppCoordinator()
    window._timed_out_generation = None
    window._lease_grace_id = None
    window.__dict__.update(overrides)
    return window

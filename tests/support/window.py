"""Shared bare ``AppWindow`` builder for headless window/UI tests.

The shared core mirrors the scheduler/timer attribute set ``AppWindow`` methods
depend on. Each test file supplies ``overrides`` for the attributes its
scenario specializes (widget fakes, preferences, node registry wiring, a custom
coordinator), so the duplicated attribute assembly lives in one place while
specialized wiring stays local.
"""

from queue import Queue
from typing import Any

import window as window_module
from maintenance.components import ResourceFeatureCatalog, ScanCoordinator
from maintenance.components.coordinator import (
    AppCoordinator,
    ComponentRefreshScheduler,
)
from maintenance.ui.render_coordinator import UICoordinator
from maintenance.ui.window_discovery import DiscoveryRuntime
from tests.support.scheduling import TimerMaster
from window import AppWindow


def make_window(master: Any | None = None, **overrides: Any) -> Any:
    """Build a bare ``AppWindow`` with the shared scheduler/timer core.

    ``overrides`` are assigned onto the instance so callers can inject widget
    fakes, preferences, or a custom coordinator without repeating the core.
    """

    window: Any = object.__new__(AppWindow)
    window.master = master if master is not None else TimerMaster()
    window._ui_coordinator = UICoordinator(
        schedule=lambda delay, cb: window.master.after(delay, cb),
        cancel=lambda identifier: window.master.after_cancel(identifier) or True,
    )
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
    window._discovery_runtime = DiscoveryRuntime(
        approve_pairing=lambda title, message: window_module.messagebox.askyesno(
            title, message, parent=window.master
        ),
        approve_elevation=lambda title, message: window_module.messagebox.askyesno(
            title, message, parent=window.master
        ),
        attempt_pending_trust_revocations=lambda controller, node_id: (
            window_module.attempt_pending_trust_revocations(controller, node_id)
        ),
        propagate_coordinator_lease=lambda controller, node_id: (
            window_module.propagate_coordinator_lease(controller, node_id)
        ),
        authenticated_node_provider=lambda **kwargs: (
            window_module.AuthenticatedNodeProvider(**kwargs)
        ),
        trusted_transport_factory=lambda record: window_module.build_trusted_transport(
            record
        ),
        is_trusted=lambda descriptor: window_module.is_trusted_descriptor(descriptor),
        identity_fingerprint=lambda node_id: window_module.node_identity_fingerprint(
            node_id
        ),
        operation_key=lambda node_id, operation: window_module.node_operation_key(
            node_id, operation
        ),
    )
    window.__dict__.update(overrides)
    return window

"""Headless tests for the reusable All Systems cluster overview page."""

import tkinter as tk
import unittest
from typing import Any
from unittest.mock import Mock

from maintenance.ui.action_coordinator import ButtonCoordinator
from maintenance.ui.cluster_page import (
    ClusterNodeSpec,
    ClusterPage,
    ClusterPageCallbacks,
)
from tests.support.live_tk import DISPLAY_AVAILABLE
from tests.support.widget_recording import RecordingWidget, WidgetRecorder


def make_callbacks() -> Any:
    return ClusterPageCallbacks(
        on_back=Mock(),
        on_open_node=Mock(),
    )


def make_remove_callbacks() -> Any:
    return ClusterPageCallbacks(
        on_back=Mock(),
        on_open_node=Mock(),
        on_remove_connection=Mock(),
        on_remove_job=Mock(),
        on_share_dashboard=Mock(),
    )


def _coordinator_spec(
    node_id: str, *, role: str = "worker", role_editable: bool = True
) -> ClusterNodeSpec:
    spec = _spec(node_id, selectable=True)
    return ClusterNodeSpec(
        node_id=spec.node_id,
        display_name=spec.display_name,
        hostname=spec.hostname,
        color=spec.color,
        trust=spec.trust,
        status=spec.status,
        capabilities=spec.capabilities,
        is_local=spec.is_local,
        selectable=spec.selectable,
        last_refresh=spec.last_refresh,
        role=role,
        role_editable=role_editable,
        has_active_job=True,
    )


def _spec(node_id: str, *, selectable: bool, is_local: bool = False) -> ClusterNodeSpec:
    return ClusterNodeSpec(
        node_id=node_id,
        display_name=node_id,
        hostname=f"{node_id}-host",
        color=None,
        trust="trusted",
        status="online",
        capabilities=("dashboard_read",),
        is_local=is_local,
        selectable=selectable,
        last_refresh="10:00:00",
    )


def make_page(
    callbacks: ClusterPageCallbacks | None = None,
    *,
    nodes: list[ClusterNodeSpec] | None = None,
    button_coordinator: ButtonCoordinator | None = None,
) -> tuple[ClusterPage, RecordingWidget, WidgetRecorder]:
    recorder = WidgetRecorder()
    parent = recorder.parent()
    page = ClusterPage(
        parent,
        callbacks=callbacks or make_callbacks(),
        nodes=nodes or [_spec("local", selectable=True, is_local=True)],
        **recorder.page_kwargs(),
        button_coordinator=button_coordinator,
    )
    return page, parent, recorder


class ClusterPageTests(unittest.TestCase):
    @unittest.skipUnless(DISPLAY_AVAILABLE, "Tk display unavailable")
    def test_retained_buttons_stay_registered_exactly_once(self) -> None:
        root = tk.Tk()
        coordinator = ButtonCoordinator()
        page = ClusterPage(
            root,
            callbacks=make_callbacks(),
            nodes=[_spec("local", selectable=True)],
            button_coordinator=coordinator,
        )
        try:
            prior = coordinator._actions["cluster:node:local:open"].widgets[0]
            for _ in range(30):
                page.refresh_nodes([_spec("local", selectable=True)])
                self.assertTrue(prior.winfo_exists())
                widgets = coordinator._actions["cluster:node:local:open"].widgets
                self.assertEqual(len(widgets), 1)
                self.assertIs(widgets[0], prior)
            page.refresh_nodes([])
            self.assertEqual(coordinator.registered_ids(), ())
        finally:
            root.destroy()
            page.dispose()

    @unittest.skipUnless(DISPLAY_AVAILABLE, "Tk display unavailable")
    def test_unchanged_rows_are_retained_across_refresh(self) -> None:
        root = tk.Tk()
        coordinator = ButtonCoordinator()
        page = ClusterPage(
            root,
            callbacks=make_callbacks(),
            nodes=[_spec("dev", selectable=True)],
            button_coordinator=coordinator,
        )
        try:
            prior = coordinator._actions["cluster:node:dev:open"].widgets[0]
            page.refresh_nodes([_spec("dev", selectable=True)])
            self.assertTrue(prior.winfo_exists())
        finally:
            root.destroy()
            page.dispose()

    @unittest.skipUnless(DISPLAY_AVAILABLE, "Tk display unavailable")
    def test_text_only_change_updates_in_place(self) -> None:
        root = tk.Tk()
        page = ClusterPage(
            root, callbacks=make_callbacks(), nodes=[_spec("dev", selectable=True)]
        )
        try:
            row = page._rows["dev"]
            page.refresh_nodes([_spec("dev", selectable=True)])
            self.assertIs(page._rows["dev"], row)
        finally:
            root.destroy()
            page.dispose()

    def test_page_root_is_not_packed(self) -> None:
        _page, parent, _recorder = make_page()
        self.assertEqual(parent.pack_calls, [])

    def test_back_button_invokes_on_back(self) -> None:
        callbacks = make_callbacks()
        page, _parent, _recorder = make_page(callbacks)
        page.back_button.kwargs["command"]()
        callbacks.on_back.assert_called_once_with()

    def test_selectable_node_gets_an_open_button(self) -> None:
        _page, _parent, recorder = make_page(nodes=[_spec("dev", selectable=True)])
        self.assertTrue(recorder.button_with_text("Open"))

    def test_non_selectable_node_has_no_open_button(self) -> None:
        _page, _parent, recorder = make_page(nodes=[_spec("peer", selectable=False)])
        with self.assertRaises(StopIteration):
            recorder.button_with_text("Open")

    def test_open_emits_node_id(self) -> None:
        callbacks = make_callbacks()
        _page, _parent, recorder = make_page(
            callbacks, nodes=[_spec("dev", selectable=True)]
        )
        recorder.button_with_text("Open").kwargs["command"]()
        callbacks.on_open_node.assert_called_once_with("dev")

    def test_selectable_node_registers_stable_open_action(self) -> None:
        coordinator = ButtonCoordinator()
        callbacks = make_callbacks()
        _page, _parent, _recorder = make_page(
            callbacks,
            nodes=[_spec("dev", selectable=True)],
            button_coordinator=coordinator,
        )

        self.assertIn("cluster:node:dev:open", coordinator.registered_ids())

    def test_refresh_nodes_rebuilds_list(self) -> None:
        coordinator = ButtonCoordinator()
        page, _parent, _recorder = make_page(button_coordinator=coordinator)
        page.refresh_nodes([_spec("dev", selectable=True)])
        self.assertEqual(len(page._nodes), 1)
        page.refresh_nodes([_spec("peer", selectable=False)])
        self.assertEqual(coordinator.registered_ids(), ())

    def test_dispose_clears_cluster_actions(self) -> None:
        coordinator = ButtonCoordinator()
        page, _parent, _recorder = make_page(button_coordinator=coordinator)

        page.dispose()

        self.assertEqual(coordinator.registered_ids(), ())
        page.refresh_nodes([_spec("peer", selectable=True)])
        self.assertEqual(coordinator.registered_ids(), ())

    def test_remove_connection_button_emits_node_id(self) -> None:
        callbacks = make_remove_callbacks()
        _page, _parent, recorder = make_page(
            callbacks, nodes=[_coordinator_spec("peer-a")]
        )
        recorder.button_with_text("Remove connection").kwargs["command"]()
        callbacks.on_remove_connection.assert_called_once_with("peer-a")

    def test_remove_job_button_emits_node_id(self) -> None:
        callbacks = make_remove_callbacks()
        _page, _parent, recorder = make_page(
            callbacks, nodes=[_coordinator_spec("peer-a")]
        )
        recorder.button_with_text("Remove job").kwargs["command"]()
        callbacks.on_remove_job.assert_called_once_with("peer-a")

    def test_share_dashboard_button_on_local_row(self) -> None:
        callbacks = make_remove_callbacks()
        local = _spec("local", selectable=True, is_local=True)
        _page, _parent, recorder = make_page(callbacks, nodes=[local])
        recorder.button_with_text("Share dashboard").kwargs["command"]()
        callbacks.on_share_dashboard.assert_called_once_with()

    def test_non_editable_worker_row_has_no_remove_job(self) -> None:
        callbacks = make_remove_callbacks()
        _page, _parent, recorder = make_page(
            callbacks,
            nodes=[_coordinator_spec("coord", role="coordinator", role_editable=False)],
        )
        with self.assertRaises(StopIteration):
            recorder.button_with_text("Remove job")


if __name__ == "__main__":
    unittest.main()

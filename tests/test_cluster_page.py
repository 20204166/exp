"""Headless tests for the reusable All Systems cluster overview page."""

import unittest
from typing import Any
from unittest.mock import Mock

from maintenance.ui.cluster_page import (
    ClusterNodeSpec,
    ClusterPage,
    ClusterPageCallbacks,
)
from tests.support.widget_recording import RecordingWidget, WidgetRecorder


def make_callbacks() -> Any:
    return ClusterPageCallbacks(
        on_back=Mock(),
        on_open_node=Mock(),
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
) -> tuple[ClusterPage, RecordingWidget, WidgetRecorder]:
    recorder = WidgetRecorder()
    parent = recorder.parent()
    page = ClusterPage(
        parent,
        callbacks=callbacks or make_callbacks(),
        nodes=nodes or [_spec("local", selectable=True, is_local=True)],
        frame_cls=recorder.frame_cls(),
        label_cls=recorder.label_cls(),
        style_frame_cls=recorder.style_frame_cls(),
        style_label_cls=recorder.style_label_cls(),
        button_cls=recorder.button_cls(),
        canvas_cls=recorder.canvas_cls(),
        scrollbar_cls=recorder.scrollbar_cls(),
    )
    return page, parent, recorder


def open_button(recorder: WidgetRecorder) -> RecordingWidget:
    return next(
        widget
        for widget in recorder.widgets("button")
        if widget.kwargs.get("text") == "Open"
    )


class ClusterPageTests(unittest.TestCase):
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
        self.assertTrue(open_button(recorder))

    def test_non_selectable_node_has_no_open_button(self) -> None:
        _page, _parent, recorder = make_page(nodes=[_spec("peer", selectable=False)])
        with self.assertRaises(StopIteration):
            open_button(recorder)

    def test_open_emits_node_id(self) -> None:
        callbacks = make_callbacks()
        _page, _parent, recorder = make_page(
            callbacks, nodes=[_spec("dev", selectable=True)]
        )
        open_button(recorder).kwargs["command"]()
        callbacks.on_open_node.assert_called_once_with("dev")

    def test_refresh_nodes_rebuilds_list(self) -> None:
        page, _parent, _recorder = make_page()
        page.refresh_nodes([_spec("dev", selectable=True)])
        self.assertEqual(len(page._nodes), 1)


if __name__ == "__main__":
    unittest.main()

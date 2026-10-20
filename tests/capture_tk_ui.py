"""Capture synthetic empty-state renders of the legacy Tk pages.

Run inside Xvfb, for example:
``xvfb-run -s '-screen 0 1920x1200x24' python -m tests.capture_tk_ui --output PATH``.
The matching Qt harness is ``tests.dump_qt_ui``; both consume
``tests.ui_capture_spec`` for page keys and viewport dimensions.
"""

from __future__ import annotations

import argparse
import os
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import ImageGrab

from maintenance.cluster import ClusterState, ClusterStore
from maintenance.preferences import PreferencesStore
from tests.ui_capture_spec import (
    PAGE_KEYS,
    STATE_NAME,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTHS,
)
from window import AppWindow

_SHOW_PAGE = {
    "dashboard": "_show_dashboard_page",
    "settings": "_show_settings_page",
    "preferences": "_show_preferences_page",
    "nodes": "_show_nodes_page",
    "cluster": "_show_cluster_page",
    "thermals": "_show_thermals_page",
    "diagnostics": "_show_diagnostics_page",
    "help": "_show_help_page",
}


def capture_page(page_key: str, width: int, output_dir: Path) -> Path:
    """Capture one legacy page with temporary stores and no network startup."""
    if page_key not in PAGE_KEYS:
        raise ValueError(f"unsupported Tk page: {page_key}")
    if width < 900:
        raise ValueError("viewport width must be at least 900 pixels")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{page_key}-{width}-{STATE_NAME}.png"
    with TemporaryDirectory(prefix="system-analyzer-tk-capture-") as temporary:
        root = Path(temporary)
        cluster_store = ClusterStore(root / "cluster.json")
        cluster_store.save(
            replace(
                ClusterState.create_local(local_node_id="node-synthetic"),
                cluster_id="cluster-synthetic",
                discovery_enabled=False,
            )
        )
        master = tk.Tk()
        window: AppWindow | None = None
        try:
            with (
                patch.object(AppWindow, "_start_peer_listener"),
                patch.object(AppWindow, "_start_discovery"),
                patch.object(AppWindow, "_schedule_timer"),
                patch.dict(os.environ, {"SYSTEM_ANALYZER_DEVELOPER_MODE": "1"}),
                patch(
                    "maintenance.components.node_context.platform.node",
                    return_value="synthetic.local",
                ),
            ):
                window = AppWindow(
                    master=master,
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster_store,
                )
            master.geometry(f"{width}x{VIEWPORT_HEIGHT}+0+0")
            getattr(window, _SHOW_PAGE[page_key])()
            master.update_idletasks()
            master.update()
            actual_width = master.winfo_width()
            actual_height = master.winfo_height()
            if (actual_width, actual_height) != (width, VIEWPORT_HEIGHT):
                raise RuntimeError(
                    "Tk constrained viewport to "
                    f"{actual_width}x{actual_height}, expected {width}x{VIEWPORT_HEIGHT}"
                )
            x = master.winfo_rootx()
            y = master.winfo_rooty()
            image = ImageGrab.grab(bbox=(x, y, x + width, y + VIEWPORT_HEIGHT))
            if image.size != (width, VIEWPORT_HEIGHT):
                raise RuntimeError(f"captured unexpected Tk image size: {image.size}")
            image.save(output_path, format="PNG")
        finally:
            if window is not None:
                try:
                    window._close()
                except tk.TclError:
                    pass
            try:
                master.destroy()
            except tk.TclError:
                pass
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--widths", type=int, nargs="+", default=VIEWPORT_WIDTHS)
    parser.add_argument("--pages", nargs="+", default=PAGE_KEYS, choices=PAGE_KEYS)
    args = parser.parse_args()

    for page_key in args.pages:
        for width in args.widths:
            print(capture_page(page_key, width, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

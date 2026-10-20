"""Capture deterministic empty-state renders of the retained Qt pages.

Run with ``QT_QPA_PLATFORM=offscreen``. The script uses temporary stores,
disables network startup, and writes only to the requested evidence directory.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from maintenance.cluster import ClusterState, ClusterStore
from maintenance.preferences import PreferencesStore
from maintenance.ui.qt_app_window import QtAppController, QtAppWindow
from tests.support.qt import get_qapplication
from tests.ui_capture_spec import PAGE_KEYS, VIEWPORT_HEIGHT, VIEWPORT_WIDTHS


def capture_page(page_key: str, width: int, output_dir: Path) -> Path:
    """Capture one page at a fixed viewport without touching user stores."""
    if page_key not in PAGE_KEYS:
        raise ValueError(f"unsupported Qt page: {page_key}")
    if width < 900:
        raise ValueError("viewport width must be at least 900 pixels")

    app: QApplication = get_qapplication()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{page_key}-{width}-empty.png"

    with TemporaryDirectory(prefix="system-analyzer-qt-capture-") as temporary:
        root = Path(temporary)
        cluster_store = ClusterStore(root / "cluster.json")
        cluster_store.save(
            replace(
                ClusterState.create_local(local_node_id="node-synthetic"),
                cluster_id="cluster-synthetic",
                discovery_enabled=False,
            )
        )
        with (
            patch.object(QtAppController, "_start_peer_listener"),
            patch.object(QtAppController, "_start_discovery"),
            patch.object(QtAppController, "_schedule_timer"),
            patch.dict(os.environ, {"SYSTEM_ANALYZER_DEVELOPER_MODE": "1"}),
            patch(
                "maintenance.components.node_context.platform.node",
                return_value="synthetic.local",
            ),
        ):
            window = QtAppWindow(
                preferences_store=PreferencesStore(root / "preferences.json"),
                cluster_store=cluster_store,
            )

        try:
            window.resize(width, VIEWPORT_HEIGHT)
            window.show_page(page_key)
            window.show()
            app.processEvents()
            if window.width() != width:
                raise RuntimeError(
                    f"Qt constrained viewport width to {window.width()} instead of {width}"
                )
            if not window.grab().save(str(output_path), "PNG"):
                raise OSError(f"could not save Qt screenshot: {output_path}")
        finally:
            window.close()
            app.processEvents()

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

"""Import-boundary checks for the active Qt application entry point."""

from __future__ import annotations

import subprocess
import sys
import unittest


class QtImportBoundaryTests(unittest.TestCase):
    def test_qt_integration_test_modules_do_not_import_tkinter(self) -> None:
        modules = (
            "tests.test_qt_app_window",
            "tests.test_qt_application",
            "tests.test_qt_cluster",
            "tests.test_qt_dashboard",
            "tests.test_qt_diagnostics_page",
            "tests.test_qt_help_page",
            "tests.test_qt_import_boundary",
            "tests.test_qt_node_dialogs",
            "tests.test_qt_nodes_connections",
            "tests.test_qt_resource_dialogs",
            "tests.test_qt_settings",
            "tests.test_qt_test_support",
            "tests.test_qt_thermals",
            "tests.test_qt_window_shell",
            "tests.dump_qt_ui",
            "tests.test_background_task_runner",
        )
        for module in modules:
            with self.subTest(module=module):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        (
                            f"import sys; import {module}; "
                            "assert not any(name == 'tkinter' or "
                            "name.startswith('tkinter.') for name in sys.modules)"
                        ),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_component_cycle_runs_without_loading_tkinter_or_window(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                """
import sys
from types import SimpleNamespace
from unittest.mock import Mock
from maintenance.ui.window_components import run_component_cycle
controller = SimpleNamespace(
    _component_poll_id=None, _is_closing=False,
    _page_router=SimpleNamespace(is_mapped=Mock(return_value=True)),
    _component_scheduler=SimpleNamespace(due_keys=Mock(return_value=[])),
    _schedule_component_poll=Mock(),
)
run_component_cycle(controller)
assert controller._schedule_component_poll.called
assert 'window' not in sys.modules
assert not any(name == 'tkinter' or name.startswith('tkinter.') for name in sys.modules)
""",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_page_data_projection_modules_do_not_load_tkinter(self) -> None:
        for module in (
            "maintenance.ui.window_page_data",
            "maintenance.ui.window_supports.node_specs",
        ):
            with self.subTest(module=module):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        (
                            f"import sys; import {module}; "
                            "assert not any(name == 'tkinter' or "
                            "name.startswith('tkinter.') for name in sys.modules)"
                        ),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_node_action_owner_import_does_not_load_tkinter(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import maintenance.ui.window_node_actions; "
                    "assert not any(name == 'tkinter' or name.startswith('tkinter.') "
                    "for name in sys.modules)"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_qt_node_dialogs_do_not_load_tkinter(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import maintenance.ui.qt_node_dialogs; "
                    "assert not any(name == 'tkinter' or name.startswith('tkinter.') "
                    "for name in sys.modules)"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_qt_layout_and_pages_do_not_load_tkinter(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; from maintenance.ui.qt_layout import qt_scrollable_area, qt_wrap_label; "
                    "import maintenance.ui.qt_cluster, maintenance.ui.qt_diagnostics_page, "
                    "maintenance.ui.qt_help_page, maintenance.ui.qt_resource_dialogs; "
                    "assert not any(name == 'tkinter' or name.startswith('tkinter.') "
                    "for name in sys.modules)"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_qt_layout_helpers_create_and_update_widgets(self) -> None:
        from PySide6.QtWidgets import QLabel, QWidget

        from maintenance.ui.qt_layout import qt_scrollable_area, qt_wrap_label
        from tests.support.qt import get_qapplication

        get_qapplication()
        parent = QWidget()
        area, content = qt_scrollable_area(parent)
        label = QLabel()
        update = qt_wrap_label(label, max_wrap=300)

        self.assertIs(area.widget(), content)
        self.assertTrue(label.wordWrap())
        self.assertEqual(update(200), 164)

    def test_import_main_does_not_load_tkinter(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import main, sys; "
                    "assert not any(name == 'tkinter' or name.startswith('tkinter.') "
                    "for name in sys.modules)"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_constructing_qt_application_window_does_not_load_tkinter(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                """
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from maintenance.cluster import ClusterState, ClusterStore
from maintenance.preferences import PreferencesStore
from maintenance.ui.qt_app_window import QtAppController, QtAppWindow
app = QApplication([])
with TemporaryDirectory() as directory:
    root = Path(directory)
    cluster = ClusterStore(root / 'cluster.json')
    cluster.save(ClusterState.create_local())
    with patch.object(QtAppController, '_start_peer_listener'), \
         patch.object(QtAppController, '_start_discovery'), \
         patch.object(QtAppController, '_schedule_timer'):
        window = QtAppWindow(
            preferences_store=PreferencesStore(root / 'preferences.json'),
            cluster_store=cluster,
        )
        assert not any(name == 'tkinter' or name.startswith('tkinter.') for name in sys.modules)
        window.close()
app.quit()
""",
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**__import__("os").environ, "QT_QPA_PLATFORM": "offscreen"},
        )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

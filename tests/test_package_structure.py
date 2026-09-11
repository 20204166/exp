import ast
import subprocess
import sys
import unittest
from pathlib import Path

from maintenance import components
from maintenance.components import (
    background,
    catalog,
    cluster_roles,
    cluster_storage,
    coordinator,
    dashboard_scan,
    discovery_session,
    downloads,
    gpu,
    network_discovery,
    node_selection,
    peer_connection,
    placement,
    process_safety,
    scan_support,
    temperature,
)

REPO = Path(__file__).parents[1]


class ComponentPackageLayoutTests(unittest.TestCase):
    def test_component_package_owns_one_module_per_responsibility(self) -> None:
        package_dir = REPO / "maintenance" / "components"
        expected_modules = {
            "__init__.py",
            "background.py",
            "background_orchestration.py",
            "catalog.py",
            "cluster_roles.py",
            "cluster_storage.py",
            "coordinator.py",
            "dashboard_scan.py",
            "downloads.py",
            "discovery_session.py",
            "gpu.py",
            "network_discovery.py",
            "node_selection.py",
            "node_context.py",
            "peer_connection.py",
            "placement.py",
            "process_safety.py",
            "scan_support.py",
            "temperature.py",
        }
        actual = {path.name for path in package_dir.glob("*.py")}
        self.assertEqual(actual, expected_modules)
        self.assertFalse((REPO / "maintenance" / "components.py").exists())
        for legacy in (
            "scan_support.py",
            "process_safety.py",
            "downloads.py",
        ):
            self.assertFalse((REPO / "maintenance" / legacy).exists(), legacy)


class ComponentFacadeReexportTests(unittest.TestCase):
    def test_moved_names_are_identical_objects(self) -> None:
        moved = {
            "DownloadScanner": downloads,
            "DownloadsPathResolver": downloads,
            "HashFingerprint": downloads,
            "ProcessSafetyPolicy": process_safety,
            "PROTECTED_PROCESS_NAMES": process_safety,
            "normalize_username": process_safety,
            "usernames_match": process_safety,
            "protected_process_pids": process_safety,
            "ScanCancelled": scan_support,
            "check_cancelled": scan_support,
            "require_psutil": scan_support,
            "ProgressCallback": scan_support,
            "ProgressTask": scan_support,
            "DOWNLOADS_SCAN_CANCELLED": scan_support,
            "windows_windll": scan_support,
            "GpuDetector": gpu,
            "GPU_INFORMATION_UNAVAILABLE": gpu,
            "gpu_unavailable_message": gpu,
            "TemperatureEvent": temperature,
            "TemperaturePolicy": temperature,
            "TemperatureSample": temperature,
            "TemperatureScan": temperature,
            "TemperatureSeriesSnapshot": temperature,
            "TemperatureState": temperature,
            "TemperatureTelemetry": temperature,
            "BackgroundTaskRunner": background,
            "ResourceFeature": catalog,
            "ResourceFeatureCatalog": catalog,
            "ScanCoordinator": coordinator,
            "DashboardScanLifecycle": dashboard_scan,
            "NetworkDiscovery": network_discovery,
            "DiscoveryAdvertisement": network_discovery,
            "DiscoveryEndpoint": network_discovery,
            "DiscoverySession": discovery_session,
            "DiscoveryStartResult": discovery_session,
            "DEFAULT_TTL_SECONDS": network_discovery,
            "SERVICE_TYPE": network_discovery,
            "NodeSelection": node_selection,
            "PeerConnectionManager": peer_connection,
            "JobClass": placement,
            "PlacementDecision": placement,
            "PlacementPolicy": placement,
            "PlacementRequest": placement,
            "PlacementView": placement,
            "ClusterRole": cluster_roles,
            "CoordinatorEpoch": cluster_roles,
            "CoordinatorLease": cluster_roles,
            "FencingError": cluster_roles,
            "PromotionDecision": cluster_roles,
            "RoleAssignment": cluster_roles,
            "RoleAuthorizationError": cluster_roles,
            "RoleChange": cluster_roles,
            "RoleState": cluster_roles,
            "rejoin_as_worker": cluster_roles,
            "CoordinatorTimeline": cluster_storage,
            "ResourceSnapshot": cluster_storage,
            "SnapshotBatch": cluster_storage,
            "StandbyBuffer": cluster_storage,
            "StorageStatus": cluster_storage,
        }
        for name, home in moved.items():
            with self.subTest(name=name):
                self.assertIs(getattr(components, name), getattr(home, name))

    def test_package_declares_full_public_interface(self) -> None:
        declared = set(components.__all__)
        expected = {
            "DEFAULT_TTL_SECONDS",
            "SERVICE_TYPE",
            "BackgroundTaskRunner",
            "DownloadScanner",
            "DownloadsPathResolver",
            "HashFingerprint",
            "ProcessSafetyPolicy",
            "PROTECTED_PROCESS_NAMES",
            "ResourceFeature",
            "ResourceFeatureCatalog",
            "normalize_username",
            "usernames_match",
            "protected_process_pids",
            "ScanCancelled",
            "check_cancelled",
            "require_psutil",
            "ProgressCallback",
            "ProgressTask",
            "DOWNLOADS_SCAN_CANCELLED",
            "GpuDetector",
            "GPU_INFORMATION_UNAVAILABLE",
            "gpu_unavailable_message",
            "TemperatureEvent",
            "TemperaturePolicy",
            "TemperatureSample",
            "TemperatureScan",
            "TemperatureSeriesSnapshot",
            "TemperatureState",
            "TemperatureTelemetry",
            "ScanCoordinator",
            "NetworkDiscovery",
            "DiscoveryAdvertisement",
            "DiscoveryEndpoint",
            "DiscoverySession",
            "DiscoveryStartResult",
            "NodeSelection",
            "PeerConnectionManager",
            "JobClass",
            "PlacementDecision",
            "PlacementPolicy",
            "PlacementRequest",
            "PlacementView",
            "placement_view_for_context",
            "DashboardScanLifecycle",
            "windows_windll",
            "ClusterRole",
            "CoordinatorEpoch",
            "CoordinatorLease",
            "FencingError",
            "PromotionDecision",
            "RoleAssignment",
            "RoleAuthorizationError",
            "RoleChange",
            "RoleState",
            "rejoin_as_worker",
            "CoordinatorTimeline",
            "ResourceSnapshot",
            "SnapshotBatch",
            "StandbyBuffer",
            "StorageStatus",
        }
        self.assertEqual(declared, expected)


class ExternalCommandsModuleSurfaceTests(unittest.TestCase):
    def test_external_commands_remains_a_single_focused_module(self) -> None:
        module_path = REPO / "maintenance" / "external_commands.py"
        self.assertTrue(module_path.exists())
        source = module_path.read_text()
        self.assertIn("def run_text_command", source)
        self.assertIn("def run_json_command", source)
        self.assertNotIn("lspci", source)
        self.assertNotIn("SPDisplaysDataType", source)
        self.assertNotIn("Win32_VideoController", source)

    def test_external_commands_imports_only_stdlib(self) -> None:
        tree = ast.parse((REPO / "maintenance" / "external_commands.py").read_text())
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported_roots.add(node.module.split(".")[0])
        self.assertEqual(
            imported_roots, {"json", "subprocess", "collections", "typing"}
        )


class PackageImportChainTests(unittest.TestCase):
    def test_app_startup_import_chain_is_clean(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-c", "import main; import window; import algo"],
            capture_output=True,
            text=True,
            cwd=REPO,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_hostile_import_orders_resolve_in_fresh_interpreters(self) -> None:
        orders = (
            "import maintenance.components",
            "import maintenance.components.downloads",
            "import maintenance.components.scan_support",
            "import maintenance.ui",
            "import maintenance.ui.layout",
            "import maintenance.ui.styles",
            "import maintenance.ui.scan_status",
            "import maintenance.ui.navigation",
            "import maintenance.ui.settings_home",
            "import maintenance.ui.preferences_page",
            "import maintenance.preferences",
            "import window; import maintenance.components",
            "import maintenance.components; import window",
            "import maintenance.dialogs; import maintenance.ui",
            "import window; import maintenance.ui",
            "import window; import maintenance.ui.settings_home",
            "import maintenance.ui.navigation; import window",
            "import maintenance.ui.preferences_page; import window",
            "import maintenance.preferences; import window",
            "import algo; import maintenance.components",
            "import maintenance.external_commands; import maintenance.components",
        )
        for statement in orders:
            with self.subTest(order=statement):
                completed = subprocess.run(
                    [sys.executable, "-c", statement],
                    capture_output=True,
                    text=True,
                    cwd=REPO,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_component_package_import_does_not_require_tkinter(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; sys.modules['tkinter'] = None; import maintenance.components; print('ok')",
            ],
            capture_output=True,
            text=True,
            cwd=REPO,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_ui_navigation_settings_and_preferences_imports_create_no_tk_root(
        self,
    ) -> None:
        from maintenance.ui import navigation, preferences_page, settings_home

        self.assertTrue(callable(navigation.PageRouter))
        self.assertTrue(callable(settings_home.SettingsHome))
        self.assertTrue(callable(preferences_page.PreferencesPage))

    def test_preferences_imports_create_no_tk_root_and_no_window(self) -> None:
        from maintenance import preferences

        self.assertTrue(callable(preferences.PreferencesStore))
        self.assertTrue(callable(preferences.AppPreferences.defaults))


if __name__ == "__main__":
    unittest.main()

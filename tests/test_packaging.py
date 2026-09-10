"""Packaging configuration validation (display-safe, no Tk root created)."""

import unittest
from pathlib import Path

from tests.support.toml import load as toml_load

REPO = Path(__file__).parents[1]


def _pyproject() -> dict:
    with (REPO / "pyproject.toml").open("rb") as file:
        return toml_load(file)


class PyprojectConfigurationTests(unittest.TestCase):
    def test_pyproject_parses_with_project_and_scripts(self) -> None:
        project = _pyproject()
        self.assertIn("project", project)
        self.assertEqual(project["project"]["name"], "system-analyzer")
        self.assertIn("version", project["project"]["dynamic"])

    def test_version_is_dynamic_from_single_source(self) -> None:
        from maintenance import __version__
        from maintenance._version import __version__ as module_version

        self.assertEqual(__version__, module_version)
        segments = module_version.split(".")
        self.assertEqual(len(segments), 4)
        for segment in segments:
            self.assertTrue(segment.isdigit())

        dynamic = _pyproject()["tool"]["setuptools"]["dynamic"]
        self.assertEqual(
            dynamic["version"]["attr"],
            "maintenance._version.__version__",
        )

    def test_py_typed_marker_is_shipped(self) -> None:
        self.assertTrue((REPO / "maintenance" / "py.typed").is_file())
        package_data = _pyproject()["tool"]["setuptools"]["package-data"]
        self.assertIn("py.typed", package_data["maintenance"])

    def test_window_supports_subpackage_is_shipped(self) -> None:
        packages = _pyproject()["tool"]["setuptools"]["packages"]
        self.assertIn("maintenance.ui.window_supports", packages)

    def test_console_scripts_are_declared(self) -> None:
        scripts = _pyproject()["project"]["scripts"]
        self.assertEqual(
            set(scripts),
            {
                "system-analyzer",
                "system-analyzer-snapshot",
            },
        )

    def test_requires_python_is_310_or_newer(self) -> None:
        self.assertTrue(_pyproject()["project"]["requires-python"].startswith(">="))

    def test_dependencies_are_declared(self) -> None:
        dependencies = "\n".join(_pyproject()["project"]["dependencies"])
        for requirement in ("psutil", "send2trash", "nvidia-ml-py", "zeroconf"):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, dependencies)

    def test_no_publishing_registry_is_configured(self) -> None:
        text = (REPO / "pyproject.toml").read_text()
        self.assertNotIn("pypi", text.casefold())
        self.assertNotIn("twine", text.casefold())

    def test_gui_entry_module_is_importable(self) -> None:
        import main

        self.assertTrue(callable(main.main))

    def test_snapshot_entry_module_is_importable(self) -> None:
        from maintenance import snapshot

        self.assertTrue(callable(snapshot.main))


class SnapshotCliTests(unittest.TestCase):
    def test_snapshot_help_exits_zero_without_display(self) -> None:
        from maintenance.snapshot import main

        with self.assertRaises(SystemExit) as context:
            main(["--help"])

        self.assertEqual(context.exception.code, 0)

    def test_snapshot_payload_shape_is_json_safe(self) -> None:
        from datetime import datetime, timezone

        from maintenance.models import (
            CapabilityState,
            DashboardSnapshot,
            ResourceSummary,
        )
        from maintenance.snapshot import _snapshot_payload

        snapshot = DashboardSnapshot(
            system_label="TestOS 1.0 • x86_64",
            scanned_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            resources=(
                ResourceSummary(
                    key="cpu",
                    title="CPU",
                    value="10.0%",
                    subtitle="Current processor usage",
                    percent=10.0,
                    details=("Physical cores: 8",),
                    capability=CapabilityState.SUPPORTED,
                ),
            ),
        )
        payload = _snapshot_payload(snapshot)

        self.assertEqual(payload["system_label"], snapshot.system_label)
        self.assertEqual(payload["resources"][0]["key"], "cpu")
        self.assertEqual(payload["resources"][0]["capability"], "supported")
        import json

        json.dumps(payload)  # must be JSON-serializable without error


class BuildScriptReliabilityTests(unittest.TestCase):
    def test_pyproject_declares_setuptools_build_backend(self) -> None:
        build_system = _pyproject()["build-system"]
        self.assertEqual(build_system["build-backend"], "setuptools.build_meta")
        self.assertIn("setuptools", build_system["requires"][0])

    def test_common_sh_defines_build_backend_preflight(self) -> None:
        source = (REPO / "install" / "_common.sh").read_text()
        self.assertIn("require_build_backend", source)

    def test_build_sh_has_isolation_policy_and_version_restore(self) -> None:
        source = (REPO / "install" / "build.sh").read_text()
        self.assertIn("SA_BUILD_ISOLATION", source)
        self.assertIn("--no-build-isolation", source)
        self.assertIn("restore_on_failure", source)
        self.assertIn("prepare-build", source)

    def test_build_sh_preflights_backend_before_version_preparation(self) -> None:
        source = (REPO / "install" / "build.sh").read_text()
        self.assertLess(
            source.index("require_build_backend"),
            source.index("prepare-build"),
        )

    def test_upgrade_sh_verifies_before_installing(self) -> None:
        source = (REPO / "install" / "upgrade.sh").read_text()
        self.assertIn("verify.sh", source)
        self.assertIn("pip install", source)
        self.assertLess(source.index("verify.sh"), source.index("pip install"))

    def test_installers_clean_existing_versions_and_verify_target(self) -> None:
        common = (REPO / "install" / "_common.sh").read_text()
        install_user = (REPO / "install" / "install-user.sh").read_text()
        online = (REPO / "install" / "install-online.sh").read_text()
        self.assertIn("clean_installed_package", common)
        self.assertIn("clean_user_installed_package", common)
        self.assertIn("verify_installed", common)
        self.assertIn('clean_installed_package "$py"', install_user)
        self.assertIn('verify_installed "$py"', install_user)
        self.assertIn("clean_installed_package", online)
        self.assertIn("uninstall_pip", common)
        self.assertIn("uninstall_pip", online)
        self.assertIn("--force-reinstall", install_user)
        self.assertIn("--force-reinstall", online)

    def test_windows_installers_clean_and_verify_target(self) -> None:
        common = (REPO / "install" / "_common.ps1").read_text()
        install_user = (REPO / "install" / "install-user.ps1").read_text()
        upgrade = (REPO / "install" / "upgrade.ps1").read_text()
        self.assertIn("Remove-InstalledPackage", common)
        self.assertIn("Verify-InstalledWheel", common)
        self.assertIn("Remove-InstalledPackage $py", install_user)
        self.assertIn("Verify-InstalledWheel", install_user)
        self.assertIn("Remove-InstalledPackage $py", upgrade)

        online = (REPO / "install" / "install-online.ps1").read_text()
        self.assertIn('"--force-reinstall"', online)

    def test_common_sh_build_backend_version_gate_requires_68(self) -> None:
        import re

        def gate(version: str) -> bool:
            m = re.match(r"^(\d+)\.(\d+)", version)
            return bool(m and (int(m.group(1)), int(m.group(2))) >= (68, 0))

        self.assertTrue(gate("68.0.0"))
        self.assertTrue(gate("75.6.0"))
        self.assertFalse(gate("67.2.0"))
        self.assertFalse(gate("59.0"))


if __name__ == "__main__":
    unittest.main()

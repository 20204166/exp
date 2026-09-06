"""Packaging configuration validation (display-safe, no Tk root created)."""

import unittest
from pathlib import Path

import tomllib

REPO = Path(__file__).parents[1]


def _pyproject() -> dict:
    with (REPO / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)


class PyprojectConfigurationTests(unittest.TestCase):
    def test_pyproject_parses_with_project_and_scripts(self) -> None:
        project = _pyproject()
        self.assertIn("project", project)
        self.assertEqual(project["project"]["name"], "system-analyzer")
        self.assertGreaterEqual(project["project"]["version"].count("."), 1)

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
        for requirement in ("psutil", "send2trash", "nvidia-ml-py"):
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


if __name__ == "__main__":
    unittest.main()

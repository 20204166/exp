"""Assertions over the built distribution and its install-facing metadata."""

from __future__ import annotations

import configparser
import unittest
from email.parser import Parser
from pathlib import Path
from zipfile import ZipFile

from tests.support.toml import load_project

REPO = Path(__file__).parents[1]


def latest_wheel() -> Path:
    wheels = list((REPO / "dist").glob("system_analyzer-*.whl"))
    if not wheels:
        raise AssertionError("no built system_analyzer wheel found in dist/")
    return max(wheels, key=_wheel_version)


def _wheel_version(path: Path) -> tuple[int, int, int, int]:
    version = path.name.removeprefix("system_analyzer-").removesuffix(
        "-py3-none-any.whl"
    )
    try:
        parts = tuple(int(part) for part in version.split("."))
    except ValueError as error:
        raise AssertionError(f"invalid wheel filename: {path.name}") from error
    if len(parts) != 4:
        raise AssertionError(f"invalid wheel filename: {path.name}")
    return parts  # type: ignore[return-value]


def wheel_members(path: Path) -> set[str]:
    with ZipFile(path) as archive:
        return set(archive.namelist())


def entry_points(path: Path) -> dict[str, str]:
    with ZipFile(path) as archive:
        entry_point_name = next(
            (name for name in archive.namelist() if name.endswith("entry_points.txt")),
            None,
        )
        if entry_point_name is None:
            raise AssertionError("wheel has no entry_points.txt")
        parser = configparser.ConfigParser()
        parser.read_string(archive.read(entry_point_name).decode("utf-8"))
    return dict(parser.items("console_scripts"))


def wheel_metadata(path: Path) -> tuple[str, list[str], str]:
    with ZipFile(path) as archive:
        metadata_name = next(
            (name for name in archive.namelist() if name.endswith("METADATA")), None
        )
        if metadata_name is None:
            raise AssertionError("wheel has no METADATA")
        metadata = Parser().parsestr(archive.read(metadata_name).decode("utf-8"))
    return (
        metadata["Version"],
        metadata.get_all("Requires-Dist", []),
        metadata["Requires-Python"],
    )


class BuiltWheelTests(unittest.TestCase):
    def test_wheel_contains_required_modules_and_package_content(self) -> None:
        wheel = latest_wheel()
        members = wheel_members(wheel)

        for member in (
            "main.py",
            "window.py",
            "algo.py",
            "maintenance/__init__.py",
            "maintenance/remote.py",
            "maintenance/nodes.py",
            "maintenance/py.typed",
            "maintenance/README.md",
            "maintenance/components/README.md",
        ):
            with self.subTest(member=member):
                self.assertIn(member, members)

        project = load_project()
        package_names = project["tool"]["setuptools"]["packages"]
        expected_package_files = {
            path.relative_to(REPO).as_posix()
            for package_name in package_names
            for path in (REPO / package_name.replace(".", "/")).rglob("*.py")
        }
        for member in expected_package_files:
            with self.subTest(member=member):
                self.assertIn(member, members)

        self.assertTrue(any(name.endswith(".dist-info/RECORD") for name in members))
        self.assertFalse(any(name.startswith("tests/") for name in members))
        self.assertFalse(
            any("__pycache__" in name or name.endswith(".pyc") for name in members)
        )

    def test_wheel_declares_both_console_entry_points(self) -> None:
        self.assertEqual(
            entry_points(latest_wheel()),
            {
                "system-analyzer": "main:main",
                "system-analyzer-snapshot": "maintenance.snapshot:main",
            },
        )

    def test_wheel_dependencies_match_pyproject_and_requirements(self) -> None:
        project_dependencies = load_project()["project"]["dependencies"]
        runtime_requirements, dev_requirements = _requirements_sections()
        self.assertEqual(runtime_requirements, project_dependencies)
        dev_extras = load_project()["project"]["optional-dependencies"]["dev"]
        self.assertEqual(dev_requirements, dev_extras)

        _, wheel_dependencies, _ = wheel_metadata(latest_wheel())
        self.assertEqual(wheel_dependencies, project_dependencies)

    def test_wheel_metadata_matches_declared_version_and_python_floor(self) -> None:
        version, _, requires_python = wheel_metadata(latest_wheel())
        from maintenance._version import __version__

        self.assertEqual(version, __version__)
        self.assertEqual(requires_python, load_project()["project"]["requires-python"])


def _requirements_sections() -> tuple[list[str], list[str]]:
    """Split requirements.txt into runtime and dev-tool requirements.

    The dev-tool block is introduced by the ``# Dev-only`` comment; every
    non-comment line after that marker belongs to the dev section.
    """

    runtime: list[str] = []
    dev: list[str] = []
    in_dev = False
    for line in (REPO / "requirements.txt").read_text().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lstrip().startswith("#"):
            if "Dev-only" in stripped:
                in_dev = True
            continue
        (dev if in_dev else runtime).append(stripped)
    return runtime, dev


if __name__ == "__main__":
    unittest.main()

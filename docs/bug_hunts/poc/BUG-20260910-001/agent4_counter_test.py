"""External-semantics counter-test for BUG-20260910-001.

This test is read-only: it exercises Python import-path behavior and the
application's existing identity persistence contract without installing or
modifying a package.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_python_import_precedence_is_cwd_sensitive_but_console_script_is_not() -> None:
    source_probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import maintenance, window; print(maintenance.__file__); print(window.__file__)",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert str(ROOT / "maintenance") in source_probe.stdout
    assert str(ROOT / "window.py") in source_probe.stdout

    installed_probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import maintenance, window; print(maintenance.__file__); print(window.__file__)",
        ],
        cwd=Path("/"),
        check=True,
        capture_output=True,
        text=True,
    )
    assert str(ROOT / "maintenance") not in installed_probe.stdout
    assert str(ROOT / "window.py") not in installed_probe.stdout

    launcher = shutil.which("system-analyzer-snapshot")
    if launcher is not None:
        first_line = Path(launcher).read_text(encoding="utf-8").splitlines()[0]
        assert first_line.startswith("#!")
        assert "maintenance.snapshot" in Path(launcher).read_text(encoding="utf-8")


def test_application_identity_is_persisted_across_reload() -> None:
    sys.path.insert(0, str(ROOT))
    from maintenance.cluster import ClusterStore

    with tempfile.TemporaryDirectory() as directory:
        store = ClusterStore(Path(directory) / "cluster.json")
        first = store.load()
        second = ClusterStore(store.path).load()
        assert first.local_node_id.startswith("node-")
        assert second.local_node_id == first.local_node_id


if __name__ == "__main__":
    test_python_import_precedence_is_cwd_sensitive_but_console_script_is_not()
    test_application_identity_is_persisted_across_reload()
    print("H1 Python/package semantics counter-test: PASS")
    print("H2 application identity persistence counter-test: PASS")

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PowerShellInstallerTests(unittest.TestCase):
    def test_user_installer_uses_powershell_quote_escaping(self) -> None:
        script = (ROOT / "install" / "install-user.ps1").read_text(encoding="utf-8")

        self.assertNotIn('setx PATH \\"', script)
        self.assertIn('`"$binDir;%PATH%`"', script)

    def test_online_installer_verifies_imported_release_after_install(self) -> None:
        script = (ROOT / "install" / "install-online.ps1").read_text(encoding="utf-8")

        self.assertIn("installed version", script)
        self.assertIn("maintenance.__file__", script)
        self.assertIn("window.__file__", script)
        self.assertIn("$driveRoot", script)
        self.assertIn("Active virtual environment", script)


if __name__ == "__main__":
    unittest.main()

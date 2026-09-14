import unittest

from maintenance.diagnostics import developer_mode_enabled


class DeveloperModeTests(unittest.TestCase):
    def test_developer_mode_is_disabled_by_default(self) -> None:
        self.assertFalse(developer_mode_enabled({}))

    def test_developer_mode_requires_explicit_launch_configuration(self) -> None:
        self.assertTrue(developer_mode_enabled({"SYSTEM_ANALYZER_DEVELOPER_MODE": "1"}))
        self.assertFalse(
            developer_mode_enabled({"SYSTEM_ANALYZER_DEVELOPER_MODE": "true"})
        )


if __name__ == "__main__":
    unittest.main()

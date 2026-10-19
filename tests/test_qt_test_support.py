import os
import unittest


class QtTestSupportTests(unittest.TestCase):
    def test_application_helper_sets_offscreen_and_reuses_singleton(self) -> None:
        from PySide6.QtWidgets import QApplication

        from tests.support.qt import get_qapplication

        os.environ.pop("QT_QPA_PLATFORM", None)
        first = get_qapplication()
        second = get_qapplication()

        self.assertEqual(os.environ["QT_QPA_PLATFORM"], "offscreen")
        self.assertIsInstance(first, QApplication)
        self.assertIs(first, second)


if __name__ == "__main__":
    unittest.main()

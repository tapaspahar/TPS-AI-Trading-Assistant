import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QLabel

from ui.screens.dashboard_screen import ResponsiveStackedWidget


class DashboardShellLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_hidden_large_page_does_not_force_shell_minimum_size(self):
        stack = ResponsiveStackedWidget()
        large_page = QLabel("Large hidden workspace")
        large_page.setMinimumSize(2600, 900)
        stack.addWidget(large_page)
        self.assertEqual(stack.minimumSizeHint(), QSize(0, 0))
        stack.close()


if __name__ == "__main__":
    unittest.main()

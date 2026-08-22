import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QScrollArea

from ui.pages.recovery_center_page import RecoveryCenterPage


class RecoveryCenterLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_page_uses_protected_vertical_scroll_layout(self):
        with patch.object(RecoveryCenterPage, "refresh", return_value=None):
            page = RecoveryCenterPage()
        try:
            area = page.findChild(QScrollArea, "recoveryCenterScrollArea")
            self.assertIsNotNone(area)
            self.assertTrue(area.widgetResizable())
            self.assertEqual(area.horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
            self.assertEqual(area.verticalScrollBarPolicy(), Qt.ScrollBarAlwaysOn)
            self.assertGreaterEqual(area.widget().minimumHeight(), 980)
        finally:
            page.timer.stop()
            page.close()


if __name__ == "__main__":
    unittest.main()

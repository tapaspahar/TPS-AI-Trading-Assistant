import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QScrollArea

from ui.pages.auto_attempt_report_page import AutoAttemptReportPage


class AutoAttemptReportLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_ten_row_ledger_and_page_scrolling_are_preserved(self):
        with patch.object(AutoAttemptReportPage, "refresh", return_value=None):
            page = AutoAttemptReportPage()
        try:
            area = page.findChild(QScrollArea, "autoAttemptReportScrollArea")
            self.assertIsNotNone(area)
            self.assertTrue(area.widgetResizable())
            self.assertEqual(area.verticalScrollBarPolicy(), Qt.ScrollBarAsNeeded)
            self.assertEqual(page.table.verticalScrollBarPolicy(), Qt.ScrollBarAlwaysOn)
            self.assertEqual(page.table.horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOn)
            minimum_ten_rows = (
                page.table.horizontalHeader().sizeHint().height()
                + page.VISIBLE_ATTEMPT_ROWS * page.ATTEMPT_ROW_HEIGHT
            )
            self.assertGreaterEqual(page.table.height(), minimum_ten_rows)
            self.assertGreaterEqual(page.details.minimumHeight(), 280)
        finally:
            page.db.connection.close()
            page.close()


if __name__ == "__main__":
    unittest.main()

import unittest

from PySide6.QtWidgets import QApplication, QLineEdit

from ui.pages.journal_page import JournalPage


class AutomaticJournalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_journal_has_no_manual_trade_entry_fields(self):
        page = JournalPage()
        self.assertEqual(page.findChildren(QLineEdit), [])
        labels = " ".join(label.text() for label in page.findChildren(type(page.summary)))
        self.assertIn("automatically records", labels)
        self.assertNotIn("manual Angel One trade", labels)
        page.db.close()


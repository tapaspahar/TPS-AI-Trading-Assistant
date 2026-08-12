import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication, QTextBrowser

from ui.pages.about_help_page import HelpPage
from ui.pages.help_content import PAGES, help_html


class HelpCenterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_all_28_routes_exist_in_each_language(self):
        self.assertEqual(len(PAGES), 28)
        for language in ("en", "roman", "hi"):
            rendered = help_html(language)
            for page_index, title, *_rest in PAGES:
                self.assertIn(title, rendered)
                self.assertIn(f"tps://page/{page_index}", rendered)

    def test_workspace_link_emits_target_page(self):
        page = HelpPage()
        received = []
        page.page_requested.connect(received.append)
        browser = page.findChildren(QTextBrowser)[0]
        page._open_link(browser, QUrl("tps://page/25"))
        self.assertEqual(received, [25])


if __name__ == "__main__":
    unittest.main()

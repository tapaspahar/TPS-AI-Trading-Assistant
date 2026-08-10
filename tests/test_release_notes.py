import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QTabWidget

from release_info import FOOTER_UPDATE_TEXT, LAST_UPDATED_AT, RELEASE_NOTES, SOFTWARE_UPDATE_VERSION
from ui.pages.about_help_page import AboutPage, HelpPage
from ui.widgets.information_panel import InformationPanel


class ReleaseNotesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_footer_shows_update_version_and_timestamp(self):
        panel = InformationPanel()
        texts = [label.text() for label in panel.findChildren(QLabel)]
        self.assertIn(FOOTER_UPDATE_TEXT, texts)
        panel.close()

    def test_help_page_has_separate_release_notes_tab(self):
        page = HelpPage()
        tabs = page.findChild(QTabWidget)
        self.assertIsNotNone(tabs)
        self.assertIn("Release Notes", [tabs.tabText(index) for index in range(tabs.count())])
        page.close()

    def test_release_notes_render_current_metadata(self):
        html = AboutPage._release_notes_html()
        self.assertIn(SOFTWARE_UPDATE_VERSION, html)
        self.assertIn(LAST_UPDATED_AT, html)
        for note in RELEASE_NOTES:
            self.assertIn(note, html)


if __name__ == "__main__":
    unittest.main()

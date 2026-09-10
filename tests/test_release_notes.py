import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QTabWidget

from release_info import DISPLAY_VERSION, FOOTER_UPDATE_TEXT, LAST_UPDATED_AT, RELEASE_DATE, RELEASE_NOTES, SOFTWARE_UPDATE_VERSION, VERSION
from ui.pages.about_help_page import AboutPage, HelpPage
from ui.widgets.header import Header, toggle_execution_mode
from core.settings_store import SettingsStore
from services.execution_service import ExecutionService
from ui.widgets.information_panel import InformationPanel


class ReleaseNotesTests(unittest.TestCase):
    def test_header_mode_toggle_changes_preference_without_arming_real(self):
        with tempfile.TemporaryDirectory() as folder:
            store = SettingsStore(Path(folder) / "settings.json")
            settings = store.load()
            settings.update({"real_execution_enabled": True, "limited_real_pilot_enabled": True})
            store.save(settings)
            self.assertEqual(toggle_execution_mode(store), "REAL")
            loaded = store.load()
            self.assertEqual(loaded["execution_mode"], "REAL")
            self.assertTrue(ExecutionService.session_armed())
            self.assertEqual(toggle_execution_mode(store), "PAPER")
            self.assertFalse(ExecutionService.session_armed())

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_footer_shows_update_version_and_timestamp(self):
        panel = InformationPanel()
        texts = [label.text() for label in panel.findChildren(QLabel)]
        self.assertIn(FOOTER_UPDATE_TEXT, texts)
        panel.close()

    def test_header_expands_tps_as_trading_plan_system(self):
        header = Header()
        texts = [label.text() for label in header.findChildren(QLabel)]
        self.assertIn("TPS — Trading Plan System • Professional Trading Dashboard", texts)
        header.close()

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

    def test_release_1_5_8_metadata_and_packaging_are_aligned(self):
        self.assertEqual(VERSION, "1.5.8")
        self.assertEqual(DISPLAY_VERSION, "Release 1.5.8")
        self.assertEqual(RELEASE_DATE, "10-09-2026")
        with open("packaging/installer.iss", encoding="utf-8") as file:
            installer = file.read()
        with open("packaging/windows_version_info.txt", encoding="utf-8") as file:
            windows_info = file.read()
        self.assertIn('#define MyAppVersion "1.5.8"', installer)
        self.assertIn("TPS-AI-Trading-Assistant-Setup-1.5.8", installer)
        self.assertIn("ProductVersion', '1.5.8'", windows_info)


if __name__ == "__main__":
    unittest.main()

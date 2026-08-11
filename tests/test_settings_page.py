import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.settings_store import DEFAULT_SETTINGS


class SettingsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @patch("ui.pages.settings_page.BrokerCredentialStore")
    @patch("ui.pages.settings_page.SettingsStore")
    def test_match_mode_is_visible_loaded_and_saved(self, store_type, credential_type):
        values = {**DEFAULT_SETTINGS, "tps_match_mode": "adaptive"}
        store = store_type.return_value
        store.load.return_value = values
        store.save.return_value = values
        credential_type.return_value.load.return_value = {}

        from ui.pages.settings_page import SettingsPage
        page = SettingsPage()
        self.assertEqual(page.tps_match_mode.currentData(), "adaptive")
        self.assertIn("Adaptive", page.tps_match_mode.currentText())

        page.tps_match_mode.setCurrentIndex(page.tps_match_mode.findData("all"))
        with patch("ui.pages.settings_page.QMessageBox.information"), patch("ui.pages.settings_page.apply_theme"):
            page.save()
        self.assertEqual(store.save.call_args.args[0]["tps_match_mode"], "all")
        page.close()


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ui.screens.dashboard_screen import DashboardScreen


class WorkspaceConsolidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.old_localappdata = os.environ.get("LOCALAPPDATA")
        cls.old_appdata = os.environ.get("APPDATA")
        os.environ["LOCALAPPDATA"] = cls.temp.name
        os.environ["APPDATA"] = cls.temp.name
        cls.app = QApplication.instance() or QApplication([])
        cls.screen = DashboardScreen()

    @classmethod
    def tearDownClass(cls):
        for timer in cls.screen.findChildren(QTimer):
            timer.stop()
        cls.screen.close()
        cls.screen.deleteLater()
        if cls.old_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = cls.old_localappdata
        if cls.old_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = cls.old_appdata
        cls.temp.cleanup()

    def test_sidebar_contains_only_primary_workspaces(self):
        labels = "\n".join(button.text() for button in self.screen.sidebar.buttons)
        self.assertEqual(len(self.screen.sidebar.buttons), 24)
        self.assertIn("Strategy Trades", labels)
        for retired_label in (
            "Checklist",
            "Stock Options Watch",
            "Post-Market Report",
            "Next-Day Bias",
            "Smart Money Lab",
            "Pre-Candle Probability",
            "Options Intelligence",
            "Volatility Intelligence",
            "Chart Capture",
            "Risk Manager",
        ):
            self.assertNotIn(retired_label, labels)

    def test_legacy_routes_open_the_matching_consolidated_tabs(self):
        cases = (
            (5, 2, self.screen.optionsHub, 0),
            (25, 2, self.screen.optionsHub, 1),
            (11, 22, self.screen.postMarketHub, 1),
            (17, 26, self.screen.gapHub, 0),
            (18, 24, self.screen.powerfulHub, 1),
            (23, 24, self.screen.powerfulHub, 2),
            (20, 27, self.screen.autoOpportunityHub, 1),
            (33, 21, self.screen.strategyHub, 1),
        )
        for route, stack_index, hub, tab_index in cases:
            with self.subTest(route=route):
                self.screen.show_page(route)
                self.assertEqual(self.screen.stack.currentIndex(), stack_index)
                self.assertEqual(hub.tabs.currentIndex(), tab_index)

    def test_retired_manual_routes_open_automatic_replacements(self):
        self.screen.show_page(3)
        self.assertEqual(self.screen.stack.currentIndex(), 2)
        self.screen.show_page(7)
        self.assertEqual(self.screen.stack.currentIndex(), 9)

    def test_primary_routes_return_to_the_first_tab(self):
        cases = (
            (2, self.screen.optionsHub),
            (21, self.screen.strategyHub),
            (22, self.screen.postMarketHub),
            (24, self.screen.powerfulHub),
            (26, self.screen.gapHub),
            (27, self.screen.autoOpportunityHub),
        )
        for route, hub in cases:
            with self.subTest(route=route):
                hub.select_tab(hub.tabs.count() - 1)
                self.screen.show_page(route)
                self.assertEqual(hub.tabs.currentIndex(), 0)

    def test_header_settings_shortcut_opens_settings_page(self):
        self.screen.show_page(0)
        self.screen.header.settingsButton.click()
        self.assertEqual(self.screen.stack.currentIndex(), 9)
        self.assertTrue(self.screen.sidebar.settingsButton.isChecked())


if __name__ == "__main__":
    unittest.main()

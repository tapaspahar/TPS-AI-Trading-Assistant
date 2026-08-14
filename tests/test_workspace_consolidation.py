import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.screens.dashboard_screen import DashboardScreen


class WorkspaceConsolidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.screen = DashboardScreen()

    @classmethod
    def tearDownClass(cls):
        cls.screen.close()
        cls.screen.deleteLater()

    def test_sidebar_contains_only_primary_workspaces(self):
        labels = "\n".join(button.text() for button in self.screen.sidebar.buttons)
        self.assertEqual(len(self.screen.sidebar.buttons), 25)
        for retired_label in (
            "Checklist",
            "Stock Options Watch",
            "Post-Market Report",
            "Next-Day Bias",
            "Smart Money Lab",
            "Pre-Candle Probability",
            "Options Intelligence",
            "Volatility Intelligence",
        ):
            self.assertNotIn(retired_label, labels)

    def test_legacy_routes_open_the_matching_consolidated_tabs(self):
        cases = (
            (5, 2, self.screen.optionsHub, 0),
            (25, 2, self.screen.optionsHub, 1),
            (11, 22, self.screen.postMarketHub, 1),
            (17, 26, self.screen.gapHub, 1),
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


if __name__ == "__main__":
    unittest.main()

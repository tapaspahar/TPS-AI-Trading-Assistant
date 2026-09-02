import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
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
        self.assertEqual(len(self.screen.sidebar.buttons), 5)
        for workspace_label in (
            "Dashboard",
            "Market Intelligence",
            "Trading & Strategies",
            "Reports & Learning",
            "Controls & Settings",
        ):
            self.assertIn(workspace_label, labels)
        self.assertLessEqual(self.screen.sidebar.menu_widget.minimumHeight(), 260)

    def test_legacy_routes_open_the_matching_consolidated_tabs(self):
        cases = (
            (5, 2, self.screen.tradingCenter, 0, self.screen.optionsHub, 0),
            (25, 2, self.screen.tradingCenter, 0, self.screen.optionsHub, 1),
            (11, 4, self.screen.reportsCenter, 4, self.screen.postMarketHub, 1),
            (17, 1, self.screen.marketCenter, 7, self.screen.gapHub, 0),
            (18, 1, self.screen.marketCenter, 3, self.screen.powerfulHub, 1),
            (23, 1, self.screen.marketCenter, 3, self.screen.powerfulHub, 2),
            (20, 2, self.screen.tradingCenter, 3, self.screen.autoOpportunityHub, 1),
            (33, 2, self.screen.tradingCenter, 1, self.screen.strategyHub, 1),
        )
        for route, stack_index, center, center_tab, hub, tab_index in cases:
            with self.subTest(route=route):
                self.screen.show_page(route)
                self.assertEqual(self.screen.stack.currentIndex(), stack_index)
                self.assertEqual(center.tabs.currentIndex(), center_tab)
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

    def test_strategy_trades_is_a_separate_page_not_an_option_strategy_tab(self):
        labels = tuple(self.screen.strategyHub.tabs.tabText(i) for i in range(self.screen.strategyHub.tabs.count()))
        self.assertEqual(labels, ("Defined-Risk Strategies", "VIX / ATR Intelligence"))

        self.screen.show_page(34)

        self.assertEqual(self.screen.stack.currentIndex(), 2)
        self.assertEqual(self.screen.tradingCenter.tabs.currentIndex(), 2)
        self.assertIs(self.screen.tradingCenter.tabs.currentWidget(), self.screen.strategyTradesPage)
        self.assertTrue(self.screen.sidebar.tradingCenterButton.isChecked())

    def test_header_settings_shortcut_opens_settings_page(self):
        self.screen.show_page(0)
        self.screen.header.settingsButton.click()
        self.assertEqual(self.screen.stack.currentIndex(), 9)
        self.assertEqual(self.screen.controlsCenter.tabs.currentIndex(), 4)
        self.assertTrue(self.screen.sidebar.controlsCenterButton.isChecked())

    def test_master_workspace_tabs_keep_every_page_easy_to_reach(self):
        expected = {
            self.screen.marketCenter: (
                "Market Snapshot", "Index Candle Analysis", "Equity Research",
                "Signal Intelligence", "CAS Analysis", "Trend Memory", "Smart Options Memory", "Gap Probability",
            ),
            self.screen.tradingCenter: (
                "Options Workspace", "Option Strategies", "Strategy Trades",
                "Opportunity Radar", "Options Scalper", "Expiry After 3 PM", "Options Algo",
            ),
            self.screen.reportsCenter: (
                "Trade Journal", "Auto Attempts", "Notifications", "All Reports",
                "Post Market", "Backtesting", "Candle Replay", "AI Development", "Reliability Cockpit",
            ),
            self.screen.controlsCenter: (
                "Overtrading Protection", "Broker Execution", "Angel One Order Intelligence", "Cutie AI Commands",
                "Settings", "About", "Help",
            ),
        }
        for center, labels in expected.items():
            with self.subTest(center=center):
                self.assertEqual(
                    tuple(center.tabs.tabText(i) for i in range(center.tabs.count())),
                    labels,
                )

    def test_expensive_refresh_is_deferred_and_rapid_routes_are_coalesced(self):
        with (
            patch.object(self.screen.reportsPage, "refresh") as reports_refresh,
            patch.object(self.screen.reliabilityCenterPage, "refresh") as reliability_refresh,
        ):
            self.screen.show_page(8)
            self.screen.show_page(40)

            # Navigation itself must complete before report tables are rebuilt.
            self.assertEqual(self.screen.stack.currentIndex(), 4)
            self.assertEqual(self.screen.reportsCenter.tabs.currentIndex(), 8)
            reports_refresh.assert_not_called()
            reliability_refresh.assert_not_called()

            QTest.qWait(240)
            reports_refresh.assert_not_called()
            reliability_refresh.assert_called_once_with()

    def test_hidden_view_only_pages_do_not_run_refresh_timers(self):
        self.assertFalse(self.screen.optionsMemoryPage.timer.isActive())
        self.assertFalse(self.screen.orderIntelligencePage.timer.isActive())


if __name__ == "__main__":
    unittest.main()

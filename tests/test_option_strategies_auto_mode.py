import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.market_session import IST
from ui.pages.option_strategies_page import OptionStrategiesPage


class OptionStrategiesAutoModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.local_app_data = patch.dict(os.environ, {"LOCALAPPDATA": self.temp_dir.name})
        self.local_app_data.start()
        self.page = OptionStrategiesPage()
        self.page.timer.stop()

    def tearDown(self):
        self.page.timer.stop()
        self.page.close()
        self.local_app_data.stop()
        self.temp_dir.cleanup()

    def test_auto_mode_is_enabled_by_default(self):
        self.assertTrue(self.page.auto.isChecked())

    @patch("ui.pages.option_strategies_page.LiveSession.connected", return_value=True)
    @patch("ui.pages.option_strategies_page.market_session", return_value={"state": "OPEN"})
    def test_open_market_runs_only_once_per_five_minute_bucket(self, _session, _connected):
        self.page.analyze = Mock()
        bucket = self.page._five_minute_bucket()
        self.page._auto_tick()
        self.page._auto_tick()
        self.assertEqual(self.page._last_auto_bucket, bucket)
        self.page.analyze.assert_called_once_with()

    @patch("ui.pages.option_strategies_page.LiveSession.connected", return_value=True)
    @patch("ui.pages.option_strategies_page.market_session", return_value={"state": "CLOSED"})
    def test_closed_market_does_not_run_strategy_analysis(self, _session, _connected):
        self.page.analyze = Mock()
        self.page._auto_tick()
        self.page.analyze.assert_not_called()
        self.assertIsNone(self.page._last_auto_bucket)

    def test_bucket_uses_five_minute_intervals(self):
        first = self.page._five_minute_bucket(datetime(2026, 8, 25, 9, 16, tzinfo=IST))
        same = self.page._five_minute_bucket(datetime(2026, 8, 25, 9, 19, tzinfo=IST))
        next_bucket = self.page._five_minute_bucket(datetime(2026, 8, 25, 9, 20, tzinfo=IST))
        self.assertEqual(first, same)
        self.assertNotEqual(first, next_bucket)

    @patch("ui.pages.option_strategies_page.market_session", return_value={"state": "OPEN"})
    @patch("ui.pages.option_strategies_page.NotificationService.instance")
    def test_candidate_notification_is_not_repeated(self, notification_instance, _session):
        notifier = Mock()
        notifier.notify.return_value = True
        notification_instance.return_value = notifier
        result = {
            "symbol": "NIFTY", "state": "REVIEW CANDIDATE", "strategy": "Bull Call Debit Spread",
            "bias": "BULLISH", "expiry": "2026-08-27", "max_loss": 1000,
            "management_reference": {"target_profit": 500},
            "legs": [
                {"action": "BUY", "option_type": "CE", "strike": 24500},
                {"action": "SELL", "option_type": "CE", "strike": 24600},
            ],
        }
        self.assertTrue(self.page._notify_strategy_candidate(result))
        self.assertFalse(self.page._notify_strategy_candidate(result))
        notifier.notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()

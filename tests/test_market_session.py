import unittest
from datetime import datetime

from core.market_session import IST, format_remaining, market_session


class MarketSessionTests(unittest.TestCase):
    def test_regular_market_counts_down_to_close(self):
        now = datetime(2026, 8, 3, 10, 0, tzinfo=IST)
        result = market_session(now, {})
        self.assertEqual(result["state"], "OPEN")
        self.assertEqual(format_remaining(result["deadline"] - now), "05:30:00")

    def test_pre_open_is_detected(self):
        result = market_session(datetime(2026, 8, 3, 9, 5, tzinfo=IST), {})
        self.assertEqual(result["state"], "PRE_OPEN")

    def test_weekend_points_to_next_business_day(self):
        result = market_session(datetime(2026, 8, 2, 12, 0, tzinfo=IST), {})
        self.assertEqual(result["state"], "WEEKEND")
        self.assertEqual(result["deadline"].weekday(), 0)

    def test_official_nse_holiday_blocks_market_session(self):
        result = market_session(datetime(2026, 10, 2, 11, 0, tzinfo=IST), {})
        self.assertEqual(result["state"], "HOLIDAY")
        self.assertEqual(result["holiday"], "Mahatma Gandhi Jayanti")
        self.assertEqual(result["deadline"].date().isoformat(), "2026-10-05")

    def test_next_open_skips_holiday_after_regular_close(self):
        result = market_session(datetime(2026, 10, 1, 16, 0, tzinfo=IST), {})
        self.assertEqual(result["state"], "CLOSED")
        self.assertEqual(result["deadline"].date().isoformat(), "2026-10-05")

    def test_saved_custom_market_timing_controls_session(self):
        settings = {
            "market_pre_open_time": "08:45", "market_open_time": "09:00",
            "market_close_time": "16:00",
        }
        result = market_session(datetime(2026, 8, 3, 15, 45, tzinfo=IST), settings)
        self.assertEqual(result["state"], "OPEN")
        self.assertEqual(format_remaining(result["deadline"] - datetime(2026, 8, 3, 15, 45, tzinfo=IST)), "00:15:00")

    def test_invalid_custom_market_timing_is_rejected(self):
        settings = {
            "market_pre_open_time": "09:00", "market_open_time": "15:30",
            "market_close_time": "09:15",
        }
        with self.assertRaisesRegex(ValueError, "pre-open"):
            market_session(datetime(2026, 8, 3, 10, 0, tzinfo=IST), settings)

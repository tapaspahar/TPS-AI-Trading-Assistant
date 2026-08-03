import unittest
from datetime import datetime

from core.market_session import IST, format_remaining, market_session


class MarketSessionTests(unittest.TestCase):
    def test_regular_market_counts_down_to_close(self):
        now = datetime(2026, 8, 3, 10, 0, tzinfo=IST)
        result = market_session(now)
        self.assertEqual(result["state"], "OPEN")
        self.assertEqual(format_remaining(result["deadline"] - now), "05:30:00")

    def test_pre_open_is_detected(self):
        result = market_session(datetime(2026, 8, 3, 9, 5, tzinfo=IST))
        self.assertEqual(result["state"], "PRE_OPEN")

    def test_weekend_points_to_next_business_day(self):
        result = market_session(datetime(2026, 8, 2, 12, 0, tzinfo=IST))
        self.assertEqual(result["state"], "WEEKEND")
        self.assertEqual(result["deadline"].weekday(), 0)

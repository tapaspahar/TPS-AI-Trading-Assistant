import unittest
from datetime import datetime, timedelta

from engine.cas_analysis import analyze_cas_session


def candle(stamp, close, volume=1000):
    return {"time": stamp.isoformat(), "open": close - 1, "high": close + 2, "low": close - 2, "close": close, "volume": volume}


class CasAnalysisTests(unittest.TestCase):
    def test_bullish_cas_pressure_uses_reference_window_and_future_confirmation(self):
        start = datetime(2026, 8, 7, 14, 0)
        cash = [candle(start + timedelta(minutes=5*i), 100 + i*.1) for i in range(18)]
        future = [candle(start + timedelta(minutes=5*i), 101 + i*.1) for i in range(18)]
        # 15:00, 15:05 and 15:10 form the reference window; final 15:25 close jumps.
        cash[-1]["close"] = 105
        future[-1]["close"] = 107
        result = analyze_cas_session(cash, future)
        self.assertEqual(result["pressure"], "BULLISH CLOSING DEMAND")
        self.assertTrue(result["future_agreement"])
        self.assertTrue(result["session_final"])
        self.assertGreater(result["impact_points"], 0)

    def test_missing_reference_window_is_rejected(self):
        start = datetime(2026, 8, 7, 14, 0)
        rows = [candle(start + timedelta(minutes=5*i), 100) for i in range(12)]
        with self.assertRaisesRegex(ValueError, "3:00-3:15"):
            analyze_cas_session(rows, rows)

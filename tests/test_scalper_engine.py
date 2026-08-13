import unittest
from datetime import datetime, timedelta

from engine.scalper_engine import evaluate_scalp


def candles(direction=1, count=80):
    start = datetime(2026, 8, 13, 9, 15)
    rows = []
    for index in range(count):
        base = 24500 + direction * index * 2
        rows.append({"time": (start + timedelta(minutes=index)).isoformat(), "open": base - direction * 2,
                     "high": base + 3, "low": base - 3, "close": base + direction,
                     "volume": 100 + index * 3})
    rows[-1]["volume"] = 1000
    return rows


class ScalperEngineTests(unittest.TestCase):
    def test_bullish_completed_candles_publish_ce_watch(self):
        result = evaluate_scalp(candles(1), candles(1), {"bias": "POSITIVE", "score_adjustment": 6}, 72)
        self.assertEqual(result["action"], "CE SCALP WATCH")
        self.assertTrue(result["published"])
        self.assertLess(result["stop"], result["entry_reference"])

    def test_bearish_completed_candles_publish_pe_watch(self):
        result = evaluate_scalp(candles(-1), candles(-1), {"bias": "NEGATIVE", "score_adjustment": -6}, 72)
        self.assertEqual(result["action"], "PE SCALP WATCH")
        self.assertTrue(result["published"])
        self.assertGreater(result["stop"], result["entry_reference"])

    def test_missing_volume_forces_wait(self):
        one, five = candles(1), candles(1)
        for row in one:
            row["volume"] = 0
        result = evaluate_scalp(one, five, {"bias": "POSITIVE", "score_adjustment": 6}, 60)
        self.assertEqual(result["action"], "WAIT")
        self.assertIn("Future traded volume/VWAP unavailable", result["blockers"])


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime, timedelta

from engine.scalper_engine import evaluate_option_premium, evaluate_scalp


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
        self.assertNotIn("entry_reference", result)

    def test_bearish_completed_candles_publish_pe_watch(self):
        result = evaluate_scalp(candles(-1), candles(-1), {"bias": "NEGATIVE", "score_adjustment": -6}, 72)
        self.assertEqual(result["action"], "PE SCALP WATCH")
        self.assertTrue(result["published"])
        self.assertIn("underlying_reference", result)

    def test_missing_volume_forces_wait(self):
        one, five = candles(1), candles(1)
        for row in one:
            row["volume"] = 0
        result = evaluate_scalp(one, five, {"bias": "POSITIVE", "score_adjustment": 6}, 60)
        self.assertEqual(result["action"], "WAIT")
        self.assertIn("Future traded volume/VWAP unavailable", result["blockers"])

    def test_selected_option_builds_premium_entry_stop_and_targets(self):
        option = candles(1, 40)
        for row in option:
            row["open"] -= 24400; row["high"] -= 24400; row["low"] -= 24400; row["close"] -= 24400
        quote = {"ltp": 180, "bestBidPrice": 179.5, "bestAskPrice": 180.5}
        result = evaluate_option_premium(option, quote)
        self.assertTrue(result["confirmed"])
        self.assertEqual(result["entry"], 180.5)
        self.assertLess(result["stop"], result["entry"])
        self.assertGreater(result["target1"], result["entry"])

    def test_selected_option_without_premium_momentum_is_blocked(self):
        option = candles(-1, 40)
        for row in option:
            row["open"] -= 24300; row["high"] -= 24300; row["low"] -= 24300; row["close"] -= 24300
        result = evaluate_option_premium(option, {"ltp": 120, "bestBidPrice": 119, "bestAskPrice": 120})
        self.assertFalse(result["confirmed"])

    def test_selected_option_needs_completed_premium_history(self):
        with self.assertRaisesRegex(ValueError, "21 completed"):
            evaluate_option_premium(candles(1, 20), {"ltp": 100})


if __name__ == "__main__":
    unittest.main()

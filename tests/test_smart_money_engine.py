import unittest

from engine.smart_money_engine import SmartMoneyEngine, _patterns, _volume_profile


def candles(count=80):
    rows = []
    for index in range(count):
        wave = (0, 2, 4, 2, 0, -2, -4, -2)[index % 8]
        base = 100 + index * .25 + wave
        rows.append({"time": f"2026-08-{4 if index < 20 else 5:02d}T{9 + (index % 60)//12:02d}:{(index % 12)*5:02d}:00+05:30",
                     "open": base, "high": base + 1, "low": base - 1, "close": base + .4,
                     "volume": 100 + index})
    return rows


class SmartMoneyEngineTests(unittest.TestCase):
    def test_analysis_is_auditable_and_score_is_bounded(self):
        result = SmartMoneyEngine().analyze(candles())
        self.assertIn(result["direction"], ("BULLISH", "BEARISH", "NEUTRAL"))
        self.assertGreaterEqual(result["score"], 0); self.assertLessEqual(result["score"], 100)
        self.assertTrue(result["evidence"]); self.assertIn("method", result["volume_profile"])
        self.assertIn("order_block", result)

    def test_volume_profile_poc_is_inside_range(self):
        rows = candles()
        profile = _volume_profile(rows)
        self.assertGreaterEqual(profile["poc"], min(row["low"] for row in rows))
        self.assertLessEqual(profile["poc"], max(row["high"] for row in rows))

    def test_candle_patterns_detect_inside_bar(self):
        rows = candles(3)
        rows[-2].update({"open": 100, "close": 104, "high": 105, "low": 99})
        rows[-1].update({"open": 102, "close": 103, "high": 104, "low": 100})
        self.assertIn("Inside bar", _patterns(rows))

    def test_sell_side_liquidity_sweep_requires_close_back_above_level(self):
        rows = candles()
        baseline = SmartMoneyEngine().analyze(rows)
        prior_day_low = baseline["session_levels"]["previous_day_low"]
        reference = min(baseline["swing_low"], prior_day_low)
        rows[-1].update({"open": reference - .2, "low": reference - 3,
                         "close": reference + 1, "high": reference + 2, "volume": 1000})
        result = SmartMoneyEngine().analyze(rows)
        self.assertEqual(result["liquidity_sweep"], "SELL-SIDE")
        self.assertEqual(result["fake_breakout"], "SELL-SIDE fake breakdown")

import unittest
from datetime import datetime

from engine.market_environment import analyze_market_environment, classify_india_vix


class MarketEnvironmentTests(unittest.TestCase):
    def test_india_vix_card_and_engine_share_zone_classification(self):
        self.assertEqual(classify_india_vix(11.5)[0], "CALM / RANGE")
        self.assertEqual(classify_india_vix(14.2)[0], "HEALTHY TREND")
        self.assertEqual(classify_india_vix(18.0)[0], "HIGH VOLATILITY")
        self.assertEqual(classify_india_vix(24.0)[0], "EXTREME RISK")
    def capture(self):
        return {"close": "25000", "atr_14": "100", "ema_5": "25050", "ema_20": "25000",
                "ema_50": "24800", "volume_ratio": "1.6"}

    def test_vix_zone_adjusts_risk_and_expected_range(self):
        result = analyze_market_environment([], self.capture(), 25000, 18, datetime(2026, 8, 5, 11, 0))
        self.assertEqual(result["vix_zone"], "HIGH VOLATILITY")
        self.assertEqual(result["risk_multiplier"], .75)
        self.assertGreater(result["expected_daily_range"], 0)
        self.assertGreater(result["regular_move_target_points"], 0)
        self.assertEqual(result["max_entry_extension_atr"], .9)

    def test_low_vix_requires_stronger_volume(self):
        capture = self.capture(); capture.update({"atr_14": "20", "ema_5": "25001", "ema_20": "25000", "ema_50": "24999"})
        result = analyze_market_environment([], capture, 25000, 10, datetime(2026, 8, 5, 11, 0))
        self.assertEqual(result["regime"], "LOW VOLATILITY")
        self.assertEqual(result["volume_threshold"], 1.7)
        self.assertEqual(result["max_entry_extension_atr"], .65)

    def test_missing_vix_is_explicit_not_guessed(self):
        result = analyze_market_environment([], self.capture(), 25000, None)
        self.assertIsNone(result["vix"])
        self.assertTrue(any("unavailable" in item for item in result["warnings"]))

    def test_opening_range_gap_and_previous_day_levels_are_recorded(self):
        candles = [
            {"time": "2026-08-04T15:25:00+05:30", "open": 24900, "high": 25000, "low": 24800, "close": 24950},
            {"time": "2026-08-05T09:15:00+05:30", "open": 25020, "high": 25060, "low": 25010, "close": 25050},
            {"time": "2026-08-05T09:20:00+05:30", "open": 25050, "high": 25080, "low": 25030, "close": 25070},
            {"time": "2026-08-05T09:25:00+05:30", "open": 25070, "high": 25090, "low": 25040, "close": 25060},
        ]
        result = analyze_market_environment(candles, self.capture(), 25000, 14, datetime(2026, 8, 5, 10, 0))
        self.assertEqual(result["opening_range_high"], 25090)
        self.assertEqual(result["previous_day_low"], 24800)
        self.assertEqual(result["gap_state"], "GAP UP")

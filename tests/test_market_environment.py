import unittest
from datetime import datetime

from engine.market_environment import analyze_market_environment


class MarketEnvironmentTests(unittest.TestCase):
    def capture(self):
        return {"close": "25000", "atr_14": "100", "ema_5": "25050", "ema_20": "25000",
                "ema_50": "24800", "volume_ratio": "1.6"}

    def test_vix_zone_adjusts_risk_and_expected_range(self):
        result = analyze_market_environment([], self.capture(), 25000, 18, datetime(2026, 8, 5, 11, 0))
        self.assertEqual(result["vix_zone"], "HIGH VOLATILITY")
        self.assertEqual(result["risk_multiplier"], .75)
        self.assertGreater(result["expected_daily_range"], 0)

    def test_low_vix_requires_stronger_volume(self):
        capture = self.capture(); capture.update({"atr_14": "20", "ema_5": "25001", "ema_20": "25000", "ema_50": "24999"})
        result = analyze_market_environment([], capture, 25000, 10, datetime(2026, 8, 5, 11, 0))
        self.assertEqual(result["regime"], "LOW VOLATILITY")
        self.assertEqual(result["volume_threshold"], 1.7)

    def test_missing_vix_is_explicit_not_guessed(self):
        result = analyze_market_environment([], self.capture(), 25000, None)
        self.assertIsNone(result["vix"])
        self.assertTrue(any("unavailable" in item for item in result["warnings"]))

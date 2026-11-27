import unittest

from engine.advanced_smc_engine import AdvancedSMCEngine
from tests.test_smart_money_engine import candles


class AdvancedSMCEngineTests(unittest.TestCase):
    def test_returns_legacy_and_advanced_contract(self):
        result = AdvancedSMCEngine().analyze(candles())
        advanced = result["advanced_smc"]
        self.assertIn(result["direction"], ("BULLISH", "BEARISH", "NEUTRAL"))
        self.assertIn(advanced["structure_trend"], ("BULLISH", "BEARISH", "RANGE", "UNCONFIRMED"))
        self.assertGreaterEqual(advanced["confluence_score"], 0)
        self.assertLessEqual(advanced["confluence_score"], 100)
        self.assertEqual(advanced["timeframe_alignment"], "NOT PROVIDED")

    def test_multi_timeframe_alignment_is_explicit(self):
        rows = candles()
        result = AdvancedSMCEngine().analyze(rows, {"15m": rows, "1h": rows})
        self.assertEqual(result["advanced_smc"]["timeframe_alignment"], "ALIGNED BULLISH")

    def test_fvg_zones_have_lifecycle_fields(self):
        result = AdvancedSMCEngine().analyze(candles())
        for zone in result["advanced_smc"]["fvg_zones"]:
            self.assertIn(zone["status"], ("FRESH", "MITIGATED"))
            self.assertIn("fully_filled", zone)

    def test_no_automatic_execution_claim(self):
        result = AdvancedSMCEngine().analyze(candles())
        self.assertTrue(any("not a win probability" in item for item in
                            result["advanced_smc"]["limitations"]))


if __name__ == "__main__":
    unittest.main()

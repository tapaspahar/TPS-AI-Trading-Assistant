import unittest

from engine.advanced_smc_engine import AdvancedSMCEngine


def sample_candles(count=80):
    rows = []
    for index in range(count):
        wave = (0, 2, 4, 2, 0, -2, -4, -2)[index % 8]
        base = 100 + index * .25 + wave
        rows.append({"time": f"2026-08-{4 if index < 20 else 5:02d}T{9 + (index % 60)//12:02d}:{(index % 12)*5:02d}:00+05:30",
                     "open": base, "high": base + 1, "low": base - 1, "close": base + .4, "volume": 100 + index})
    return rows


class AdvancedSMCEngineTests(unittest.TestCase):
    def test_returns_legacy_and_advanced_contract(self):
        result = AdvancedSMCEngine().analyze(sample_candles())
        advanced = result["advanced_smc"]
        self.assertIn(result["direction"], ("BULLISH", "BEARISH", "NEUTRAL"))
        self.assertIn(advanced["structure_trend"], ("BULLISH", "BEARISH", "RANGE", "UNCONFIRMED"))
        self.assertGreaterEqual(advanced["confluence_score"], 0)
        self.assertLessEqual(advanced["confluence_score"], 100)
        self.assertEqual(advanced["timeframe_alignment"], "NOT PROVIDED")

    def test_multi_timeframe_alignment_is_explicit(self):
        rows = sample_candles()
        result = AdvancedSMCEngine().analyze(rows, {"15m": rows, "1h": rows})
        self.assertEqual(result["advanced_smc"]["timeframe_alignment"], "ALIGNED BULLISH")

    def test_fvg_zones_have_lifecycle_fields(self):
        result = AdvancedSMCEngine().analyze(sample_candles())
        for zone in result["advanced_smc"]["fvg_zones"]:
            self.assertIn(zone["status"], ("FRESH", "MITIGATED"))
            self.assertIn("fully_filled", zone)

    def test_no_automatic_execution_claim(self):
        result = AdvancedSMCEngine().analyze(sample_candles())
        self.assertTrue(any("not a win probability" in item for item in advanced["limitations"]))


if __name__ == "__main__":
    unittest.main()
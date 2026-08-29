import unittest

from engine.oi_flow_intelligence import analyze_oi_flow


class OIFlowIntelligenceTests(unittest.TestCase):
    def rows(self):
        rows = []
        for strike in (9900, 9950, 10000, 10050, 10100):
            rows += [
                {"strike": strike, "option_type": "CE", "oi": 1000, "oi_change": 200,
                 "volume": 500, "premium_change_percent": -5},
                {"strike": strike, "option_type": "PE", "oi": 1800, "oi_change": -50,
                 "volume": 400, "premium_change_percent": 8},
            ]
        return rows

    def test_fresh_call_writing_can_override_high_legacy_put_oi(self):
        result = analyze_oi_flow(self.rows(), 10000)
        self.assertGreater(result["legacy_pcr"], 1)
        self.assertEqual(result["direction"], "BEARISH FLOW")
        self.assertEqual(result["put_wall_health"], "WEAKENING")

    def test_small_base_percentage_is_marked_unreliable(self):
        rows = self.rows() + [{"strike": 10200, "option_type": "CE", "oi": 2, "oi_change": 1,
                              "volume": 1, "premium_change_percent": -1}]
        result = analyze_oi_flow(rows, 10000, wing_count=7)
        tiny = next(row for row in result["rows"] if row["strike"] == 10200)
        self.assertFalse(tiny["base_reliable"])
        self.assertIsNone(tiny["coi_pct"])

    def test_missing_premium_change_reduces_quality(self):
        rows = [{**row, "premium_change_percent": None} for row in self.rows()]
        result = analyze_oi_flow(rows, 10000)
        self.assertLess(result["quality"], 80)
        self.assertTrue(result["warnings"])

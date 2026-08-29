import unittest

from engine.oi_strike_candidate_engine import shortlist_oi_strike


def row(strike, option_type, flow="LONG BUILDUP", volume=5000, spread=2):
    bid = 98
    ask = bid * (1 + spread / 100)
    return {"strike": strike, "option_type": option_type, "symbol": f"NIFTY{strike}{option_type}",
            "bid": bid, "ask": ask, "ltp": 99, "volume": volume, "oi": 10000,
            "oi_change": 1000, "flow": flow, "spread_percent": spread, "lot_size": 65}


class OIStrikeCandidateTests(unittest.TestCase):
    def setUp(self):
        self.rows = [row(strike, side) for strike in (24900, 25000, 25100) for side in ("CE", "PE")]
        self.chain = {"data_quality": 90}
        self.settings = {"minimum_option_volume": 100, "maximum_option_spread_percent": 8}

    def test_bullish_flow_prefers_atm_or_itm_call_and_builds_levels(self):
        flow = {"direction": "BULLISH FLOW", "flow_score": 70, "quality": 90, "rows": self.rows,
                "put_wall": 24900, "call_wall": 25100, "put_wall_health": "DEFENDED",
                "call_wall_health": "WEAKENING", "warnings": []}
        result = shortlist_oi_strike(self.chain, flow, 25020, self.settings)
        self.assertEqual(result["candidate"]["option_type"], "CE")
        self.assertEqual(result["candidate"]["strike"], 25000)
        self.assertGreater(result["target_1"], result["entry_zone"][1])
        self.assertLess(result["premium_invalidation"], result["entry_zone"][0])
        self.assertIn("Bull Call Debit Spread", result["safer_alternative"])

    def test_balanced_flow_returns_wait_without_forcing_strike(self):
        result = shortlist_oi_strike(self.chain, {"direction": "BALANCED FLOW", "quality": 90, "rows": self.rows}, 25000, self.settings)
        self.assertEqual(result["state"], "WAIT")
        self.assertIsNone(result["candidate"])

    def test_untradeable_quotes_are_data_gap(self):
        rows = [row(25000, "PE", volume=10, spread=20)]
        flow = {"direction": "BEARISH FLOW", "quality": 90, "rows": rows}
        result = shortlist_oi_strike(self.chain, flow, 25000, self.settings)
        self.assertEqual(result["state"], "DATA GAP")
        self.assertIsNone(result["candidate"])


if __name__ == "__main__":
    unittest.main()

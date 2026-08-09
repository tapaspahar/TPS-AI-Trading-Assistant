import unittest

from engine.expiry_strategy_engine import analyze_expiry_strategy


class ExpiryStrategyEngineTests(unittest.TestCase):
    def test_high_volatility_expiry_returns_hedge_watch(self):
        chain = {"quote_rows": [
            {"option_type": "CE", "strike": 25000, "ltp": 100},
            {"option_type": "PE", "strike": 25000, "ltp": 90},
        ]}
        result = analyze_expiry_strategy(25010, chain, {"regime": "HIGH VOLATILITY", "event_risk": {}}, 0)
        self.assertEqual(result["strategy"], "ATM LONG STRADDLE WATCH")
        self.assertEqual(result["combined_atm_premium"], 190)
        self.assertFalse(result["paper_execution_supported"])

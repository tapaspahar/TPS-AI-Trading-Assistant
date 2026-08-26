import unittest

from engine.strategy_portfolio_engine import build_strategy_catalog, payoff_at_expiry


class StrategyPortfolioEngineTests(unittest.TestCase):
    def _result(self):
        rows = []
        for strike in (90, 95, 100, 105, 110):
            for kind in ("CE", "PE"):
                intrinsic = max(0, 100 - strike) if kind == "CE" else max(0, strike - 100)
                ltp = intrinsic + max(2, 8 - abs(strike - 100) * .6)
                rows.append({"strike": strike, "option_type": kind, "symbol": f"X{strike}{kind}",
                             "ltp": ltp, "bid": ltp - .1, "ask": ltp + .1,
                             "volume": 1000, "lot_size": 10})
        return {"symbol": "NIFTY", "spot": 100, "bias": "BULLISH",
                "chain": {"quote_rows": rows, "expected_move": 8}}

    def test_catalog_contains_many_defined_risk_structures(self):
        catalog = build_strategy_catalog(self._result(), {"capital": 100000, "risk_percent": 10})
        self.assertGreaterEqual(len(catalog), 10)
        self.assertTrue(all(item["defined_risk"] for item in catalog))
        self.assertTrue(any(item["strategy"] == "Iron Condor" for item in catalog))

    def test_unbounded_profit_structures_are_comparison_only(self):
        catalog = build_strategy_catalog(self._result(), {"capital": 100000, "risk_percent": 10})
        volatility = [item for item in catalog if item["family"] == "VOLATILITY"]
        self.assertTrue(volatility)
        self.assertTrue(all(not item["bounded_profit"] and not item["eligible"] for item in volatility))

    def test_vertical_payoff_is_bounded(self):
        legs = [
            {"action": "BUY", "option_type": "CE", "strike": 100, "price": 5, "quantity": 10},
            {"action": "SELL", "option_type": "CE", "strike": 110, "price": 2, "quantity": 10},
        ]
        self.assertEqual(payoff_at_expiry(legs, 90), -30)
        self.assertEqual(payoff_at_expiry(legs, 120), 70)


if __name__ == "__main__":
    unittest.main()

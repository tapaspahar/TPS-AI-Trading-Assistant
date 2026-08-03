import unittest

from engine.trade_plan_engine import create_review_plan


class TradePlanEngineTests(unittest.TestCase):
    def test_creates_review_plan_for_strong_bullish_context(self):
        contracts = [
            {"token": "ce", "symbol": "NIFTY25000CE", "strike": 25000, "option_type": "CE", "lot_size": 75},
            {"token": "pe", "symbol": "NIFTY25000PE", "strike": 25000, "option_type": "PE", "lot_size": 75},
        ]
        quotes = [
            {"symbolToken": "ce", "ltp": 100, "tradeVolume": 1000},
            {"symbolToken": "pe", "ltp": 90, "tradeVolume": 800},
        ]
        plan = create_review_plan(
            "NIFTY", 25010, contracts, quotes,
            {"symbol": "NIFTY", "direction": "BULLISH", "decision": "STRONG CE SETUP", "score": 90},
            {"context": "Put OI is higher"},
            {"capital": 1_000_000, "risk_percent": 3},
        )
        self.assertEqual(plan["option_type"], "CE")
        self.assertEqual(plan["entry"], 100)
        self.assertEqual(plan["stoploss"], 80)
        self.assertEqual(plan["target"], 140)
        self.assertEqual(plan["quantity"], 300)

    def test_rejects_non_strong_chart_context(self):
        with self.assertRaisesRegex(ValueError, "above 75"):
            create_review_plan(
                "NIFTY", 25000, [], [],
                {"symbol": "NIFTY", "direction": "BULLISH", "decision": "WATCH CE", "score": 70},
                {"context": "available"}, {"capital": 100000, "risk_percent": 1},
            )

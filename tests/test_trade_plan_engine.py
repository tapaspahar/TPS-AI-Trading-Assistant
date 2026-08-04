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
            {"symbol": "NIFTY", "direction": "BULLISH", "decision": "STRONG CE SETUP", "score": 95, "volume_confirmed": True, "trade_ready": True},
            {"context": "Put OI is higher"},
            {"capital": 1_000_000, "risk_percent": 3},
        )
        self.assertEqual(plan["option_type"], "CE")
        self.assertEqual(plan["entry"], 100)
        self.assertEqual(plan["stoploss"], 80)
        self.assertEqual(plan["target"], 140)
        self.assertEqual(plan["quantity"], 300)

    def test_rejects_non_strong_chart_context(self):
        with self.assertRaisesRegex(ValueError, "95"):
            create_review_plan(
                "NIFTY", 25000, [], [],
                {"symbol": "NIFTY", "direction": "BULLISH", "decision": "WATCH CE", "score": 70},
                {"context": "available"}, {"capital": 100000, "risk_percent": 1},
            )

    def test_uses_selected_lots_for_plan_quantity(self):
        contracts = [{"token": "ce", "symbol": "NIFTY25000CE", "strike": 25000, "option_type": "CE", "lot_size": 75}]
        plan = create_review_plan(
            "NIFTY", 25010, contracts, [{"symbolToken": "ce", "ltp": 100, "tradeVolume": 1000}],
            {"symbol": "NIFTY", "direction": "BULLISH", "decision": "STRONG CE SETUP", "score": 95, "volume_confirmed": True, "trade_ready": True},
            {"context": "Put OI is higher"}, {"capital": 1_000_000, "risk_percent": 3}, requested_lots=2,
        )
        self.assertEqual(plan["lots"], 2)
        self.assertEqual(plan["quantity"], 150)

    def test_configured_score_allows_manual_review_plan_below_95(self):
        contracts = [{"token": "ce", "symbol": "NIFTY25000CE", "strike": 25000, "option_type": "CE", "lot_size": 75}]
        plan = create_review_plan(
            "NIFTY", 25010, contracts, [{"symbolToken": "ce", "ltp": 100, "tradeVolume": 1000}],
            {"symbol": "NIFTY", "direction": "BULLISH", "decision": "NO TRADE", "score": 80, "volume_confirmed": True, "trade_ready": False},
            {"context": "Put OI is higher"},
            {"capital": 1_000_000, "risk_percent": 3, "trade_plan_min_score": 80},
        )
        self.assertEqual(plan["confidence"], 80)
        self.assertEqual(plan["minimum_score"], 80)

    def test_explicit_strict_threshold_overrides_manual_setting(self):
        with self.assertRaisesRegex(ValueError, "95"):
            create_review_plan(
                "NIFTY", 25010, [], [],
                {"symbol": "NIFTY", "direction": "BULLISH", "score": 90, "volume_confirmed": True},
                {"context": "available"},
                {"capital": 1_000_000, "risk_percent": 3, "trade_plan_min_score": 80},
                minimum_score=95,
            )

    def test_testing_threshold_allows_score_ten_review_plan(self):
        contracts = [{"token": "pe", "symbol": "NIFTY25000PE", "strike": 25000, "option_type": "PE", "lot_size": 75}]
        plan = create_review_plan(
            "NIFTY", 25010, contracts, [{"symbolToken": "pe", "ltp": 90, "tradeVolume": 800}],
            {"symbol": "NIFTY", "direction": "BEARISH", "decision": "NO TRADE", "score": 10, "volume_confirmed": True},
            {"context": "Call OI resistance confirmed"},
            {"capital": 1_000_000, "risk_percent": 3, "trade_plan_min_score": 10},
        )
        self.assertEqual(plan["option_type"], "PE")
        self.assertEqual(plan["confidence"], 10)
        self.assertEqual(plan["minimum_score"], 10)

    def test_testing_threshold_does_not_bypass_volume_confirmation(self):
        with self.assertRaisesRegex(ValueError, "Volume"):
            create_review_plan(
                "NIFTY", 25010, [], [],
                {"symbol": "NIFTY", "direction": "BEARISH", "score": 10, "volume_confirmed": False},
                {"context": "available"},
                {"capital": 1_000_000, "risk_percent": 3, "trade_plan_min_score": 10},
            )

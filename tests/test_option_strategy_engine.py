import unittest
from unittest.mock import patch

from engine.option_strategy_engine import recommend_option_strategy


class OptionStrategyEngineTests(unittest.TestCase):
    def setUp(self):
        self.strikes = [9900, 9950, 10000, 10050, 10100]
        self.rows = []
        for strike in self.strikes:
            distance = abs(strike - 10000) / 50
            for option_type in ("CE", "PE"):
                ltp = max(10, 100 - distance * 20)
                self.rows.append({
                    "strike": strike, "option_type": option_type, "symbol": f"X{strike}{option_type}",
                    "ltp": ltp, "bid": ltp - .25, "ask": ltp + .25, "lot_size": 65, "volume": 1000,
                })
        self.chain = {"quote_rows": self.rows, "put_support": 9950, "call_resistance": 10050, "pcr_oi": 1.0}
        self.environment = {
            "regime": "TRENDING", "vix": 14, "vix_zone": "HEALTHY TREND",
            "expected_daily_range": 100, "remaining_expected_range": 60,
            "regular_move_target_points": 20, "regular_move_available": True, "time_state": "NORMAL SESSION",
        }
        self.capture = {"close": "10000", "ema_5": "10020", "ema_20": "10000", "ema_50": "9950", "vwap": "9980", "supertrend": "9970"}
        self.candles = [{"open": 9990, "high": 10010, "low": 9980, "close": 10000, "volume": 100} for _ in range(60)]

    @patch("engine.option_strategy_engine.analyze_candles", return_value={"state": "Bullish structure"})
    def test_bullish_market_returns_defined_risk_debit_spread(self, _structure):
        result = recommend_option_strategy("NIFTY", 10000, self.candles, self.capture, self.chain, self.environment, {"capital": 100000, "risk_percent": 10})
        self.assertEqual(result["strategy"], "Bull Call Debit Spread")
        self.assertEqual(result["state"], "REVIEW CANDIDATE")
        self.assertEqual([leg["action"] for leg in result["legs"]], ["BUY", "SELL"])
        self.assertGreater(result["max_profit"], 0)
        self.assertGreater(result["max_loss"], 0)

    @patch("engine.option_strategy_engine.analyze_candles", return_value={"state": "Bullish structure"})
    def test_one_lot_plan_is_blocked_above_risk_cap(self, _structure):
        result = recommend_option_strategy("NIFTY", 10000, self.candles, self.capture, self.chain, self.environment, {"capital": 10000, "risk_percent": 1})
        self.assertEqual(result["state"], "RISK BLOCKED")
        self.assertTrue(result["blockers"])

    @patch("engine.option_strategy_engine.analyze_candles", return_value={"state": "Mixed / range structure"})
    def test_mixed_sideways_market_can_form_defined_risk_condor(self, _structure):
        self.capture.update({"ema_5": "10000", "ema_20": "10000", "ema_50": "10000", "vwap": "10000", "supertrend": "10000"})
        environment = {**self.environment, "regime": "SIDEWAYS / TRANSITION"}
        result = recommend_option_strategy("NIFTY", 10000, self.candles, self.capture, self.chain, environment, {"capital": 100000, "risk_percent": 10})
        self.assertEqual(result["strategy"], "Defined-Risk Iron Condor")
        self.assertEqual(len(result["legs"]), 4)

    @patch("engine.option_strategy_engine.analyze_candles", return_value={"state": "Bullish structure"})
    def test_extreme_vix_returns_wait(self, _structure):
        environment = {**self.environment, "vix_zone": "EXTREME RISK"}
        result = recommend_option_strategy("NIFTY", 10000, self.candles, self.capture, self.chain, environment, {"capital": 100000, "risk_percent": 10})
        self.assertEqual(result["state"], "WAIT")
        self.assertFalse(result["legs"])

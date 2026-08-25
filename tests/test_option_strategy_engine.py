import unittest
from datetime import date, timedelta
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
                    "expiry": date.today() + timedelta(days=7),
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
        self.assertIsNotNone(result["portfolio_greeks_estimate"])
        self.assertIn("delta", result["portfolio_greeks_estimate"])
        self.assertEqual(result["candidate_side"], "CE")
        self.assertGreater(result["management_reference"]["target_profit"], 0)
        self.assertLess(result["management_reference"]["target_profit"], result["max_profit"])
        self.assertEqual(result["management_reference"]["defined_max_loss"], result["max_loss"])

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
        self.assertEqual(result["candidate_side"], "HEDGED RANGE")

    @patch("engine.option_strategy_engine.analyze_candles", return_value={"state": "Bullish structure"})
    def test_extreme_vix_returns_wait(self, _structure):
        environment = {**self.environment, "vix_zone": "EXTREME RISK"}
        result = recommend_option_strategy("NIFTY", 10000, self.candles, self.capture, self.chain, environment, {"capital": 100000, "risk_percent": 10})
        self.assertEqual(result["state"], "SAFETY WAIT")
        self.assertFalse(result["legs"])
        self.assertGreater(result["strategy_total"], 0)
        self.assertGreater(result["confidence"], 0)

    @patch("engine.option_strategy_engine.analyze_candles", return_value={"state": "Bullish structure"})
    def test_searches_alternative_vertical_when_fixed_atm_pair_is_invalid(self, _structure):
        for row in self.rows:
            if row["strike"] == 10100 and row["option_type"] == "CE":
                row["bid"] = 0
        result = recommend_option_strategy(
            "NIFTY", 10000, self.candles, self.capture, self.chain,
            self.environment, {"capital": 100000, "risk_percent": 10},
        )
        self.assertEqual(result["strategy"], "Bull Call Debit Spread")
        self.assertEqual(len(result["legs"]), 2)

    @patch("engine.option_strategy_engine.analyze_candles", return_value={"state": "Bullish structure"})
    def test_late_session_wait_explains_evidence_instead_of_zero_over_zero(self, _structure):
        result = recommend_option_strategy(
            "NIFTY", 10000, self.candles, self.capture, self.chain,
            {**self.environment, "time_state": "LATE SESSION"},
            {"capital": 100000, "risk_percent": 10},
        )
        self.assertEqual(result["state"], "SAFETY WAIT")
        self.assertEqual(result["strategy_total"], 5)
        self.assertIn("Late-session", result["blockers"][0])

    @patch("engine.option_strategy_engine.analyze_candles", return_value={"state": "Bullish structure"})
    def test_smart_candidate_includes_fibonacci_and_gate_simulation(self, _structure):
        candles = []
        for index in range(60):
            close = 9900 + index * 2
            candles.append({"open": close - 2, "high": close + 5, "low": close - 5, "close": close, "volume": 100})
        result = recommend_option_strategy(
            "NIFTY", 10000, candles, self.capture, {**self.chain, "data_quality": 80},
            self.environment, {"capital": 100000, "risk_percent": 10, "tps_match_mode": "adaptive"},
        )
        self.assertIn(result["state"], {"REVIEW CANDIDATE", "WATCH CANDIDATE"})
        self.assertIn("nearest_level", result["fibonacci"])
        self.assertEqual(len(result["what_if"]), 3)
        self.assertEqual(result["strategy_total"], 7)

    @patch("engine.option_strategy_engine.analyze_candles", return_value={"state": "Bullish structure"})
    def test_what_if_never_bypasses_risk_cap(self, _structure):
        result = recommend_option_strategy(
            "NIFTY", 10000, self.candles, self.capture, {**self.chain, "data_quality": 80},
            self.environment, {"capital": 1000, "risk_percent": 1, "tps_match_mode": "adaptive"},
        )
        self.assertEqual(result["state"], "RISK BLOCKED")
        self.assertTrue(all(not row["would_qualify"] for row in result["what_if"]))

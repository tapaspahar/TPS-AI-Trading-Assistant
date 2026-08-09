import unittest
from unittest.mock import patch

from engine.tps_entry_confirmation import evaluate_tps_entry_v2


class TpsEntryConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.candles = [
            {"open": 100 + i * .1, "high": 102 + i * .1, "low": 99 + i * .1,
             "close": 101 + i * .1, "volume": 100} for i in range(60)
        ]
        self.candles[-2]["low"] = 105.1
        self.capture = {
            "open": "109", "close": "110", "ema_5": "108", "ema_20": "105", "ema_50": "100",
            "vwap": "106", "supertrend": "102", "atr_14": "2", "rsi_14": "55",
            "volume_ratio": "2", "candle_direction": "BULLISH", "fake_breakout_risk": False,
        }
        self.chain = {"pcr_oi": 1.0, "pcr_volume": 1.0, "call_resistance": 109, "put_support": 103}
        self.settings = {"trade_plan_min_score": 80, "tps_required_matches": 5}

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_both_ce_and_pe_are_always_scored(self, _ema, _supertrend):
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain, self.settings)
        self.assertEqual(set(result["side_evaluations"]), {"CE", "PE"})
        self.assertEqual(result["side_evaluations"]["CE"]["score"], 100)
        self.assertGreaterEqual(result["side_evaluations"]["PE"]["score"], 0)
        self.assertTrue(result["trade_ready"])

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_mixed_market_keeps_independent_watch_candidate(self, _ema, _supertrend):
        self.capture.update({"vwap": "111", "ema_5": "104", "ema_20": "106", "ema_50": "100"})
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain, self.settings)
        self.assertIn(result["candidate"], {"CE", "PE"})
        self.assertIn("CE", result["side_evaluations"])
        self.assertIn("PE", result["side_evaluations"])
        self.assertNotEqual(result["side_evaluations"]["CE"]["score"], result["side_evaluations"]["PE"]["score"])

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_only_user_enabled_conditions_are_counted_and_normalized(self, _ema, _supertrend):
        settings = {"trade_plan_min_score": 60, "tps_required_matches": 2,
                    "tps_enabled_conditions": ["Price vs VWAP", "EMA 5/20/50 alignment", "SuperTrend confirmation"]}
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain, settings)
        ce = result["side_evaluations"]["CE"]
        self.assertEqual(ce["total"], 3)
        self.assertEqual(ce["passed"], 3)
        self.assertEqual(ce["score"], 100)

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_soft_failure_does_not_erase_analytical_score(self, _ema, _supertrend):
        self.capture.update({"volume_ratio": ".5", "fake_breakout_risk": True})
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain, self.settings)
        ce = result["side_evaluations"]["CE"]
        self.assertGreater(ce["score"], 0)
        self.assertFalse(next(item for item in ce["confirmations"] if item["name"] == "Directional volume")["passed"])
        self.assertTrue(any("fake-breakout" in item for item in ce["hard_blockers"]))

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_bearish_pe_is_scored_even_when_supertrend_is_bullish(self, _ema, _supertrend):
        for i, candle in enumerate(self.candles):
            candle.update({"open": 120-i*.2, "high": 121-i*.2, "low": 118-i*.2, "close": 119-i*.2})
        self.capture.update({"open": "110", "close": "109", "ema_5": "110", "ema_20": "112", "ema_50": "115",
                             "vwap": "114", "supertrend": "100", "candle_direction": "BEARISH"})
        self.chain.update({"pcr_oi": .63, "pcr_volume": 1.52})
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain, self.settings)
        pe = result["side_evaluations"]["PE"]
        self.assertGreater(pe["score"], result["side_evaluations"]["CE"]["score"])
        self.assertFalse(next(item for item in pe["confirmations"] if item["name"] == "SuperTrend confirmation")["passed"])
        self.assertEqual(result["candidate"], "PE")

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_rsi_exhaustion_is_a_separate_pe_hard_blocker(self, _ema, _supertrend):
        for i, candle in enumerate(self.candles):
            candle.update({"open": 120-i*.2, "high": 121-i*.2, "low": 118-i*.2, "close": 119-i*.2})
        self.capture.update({"open": "110", "close": "109", "ema_5": "110", "ema_20": "112", "ema_50": "115",
                             "vwap": "114", "supertrend": "112", "candle_direction": "BEARISH", "rsi_14": "24"})
        self.chain.update({"pcr_oi": .63, "pcr_volume": 1.52, "put_support": 108})
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain, self.settings)
        self.assertTrue(any("oversold" in item for item in result["side_evaluations"]["PE"]["hard_blockers"]))

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
            "vwap": "106", "supertrend": "102", "atr_14": "10", "rsi_14": "55",
            "volume_ratio": "2", "volume_ema": "100", "candle_direction": "BULLISH", "fake_breakout_risk": False,
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
        self.assertFalse(pe["trade_ready"])
        self.assertFalse(pe["directional_consensus"]["passed"])
        self.assertIn("SuperTrend confirmation", pe["directional_consensus"]["missing"])

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_selected_checklist_cannot_vote_away_core_direction(self, _ema, _supertrend):
        settings = {
            "trade_plan_min_score": 60,
            "tps_required_matches": 2,
            "tps_enabled_conditions": ["Pullback and reversal", "Directional volume", "OI/PCR context"],
        }
        self.capture["vwap"] = "111"
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain, settings)
        ce = result["side_evaluations"]["CE"]
        self.assertGreaterEqual(ce["score"], 60)
        self.assertFalse(ce["trade_ready"])
        self.assertIn("Price vs VWAP", ce["directional_consensus"]["missing"])
        self.assertTrue(any("directional consensus" in item for item in ce["hard_blockers"]))

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_rsi_exhaustion_is_a_separate_pe_hard_blocker(self, _ema, _supertrend):
        for i, candle in enumerate(self.candles):
            candle.update({"open": 120-i*.2, "high": 121-i*.2, "low": 118-i*.2, "close": 119-i*.2})
        self.capture.update({"open": "110", "close": "109", "ema_5": "110", "ema_20": "112", "ema_50": "115",
                             "vwap": "114", "supertrend": "112", "candle_direction": "BEARISH", "rsi_14": "24"})
        self.chain.update({"pcr_oi": .63, "pcr_volume": 1.52, "put_support": 108})
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain, self.settings)
        self.assertTrue(any("Late PE entry" in item for item in result["side_evaluations"]["PE"]["hard_blockers"]))

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_august_6_late_ce_is_blocked_even_after_breakout(self, _ema, _supertrend):
        self.capture.update({
            "open": "24729", "close": "24745.90", "ema_5": "24725.08", "ema_20": "24672.10",
            "ema_50": "24644.49", "vwap": "24716.37", "supertrend": "24662.63",
            "atr_14": "29.65", "rsi_14": "92.44", "volume_ratio": "1.88", "volume_ema": "892.44",
        })
        self.chain.update({"call_resistance": 24700, "put_support": 24600})
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain, self.settings)
        ce = result["side_evaluations"]["CE"]
        self.assertFalse(ce["trade_ready"])
        self.assertFalse(ce["entry_quality"]["timely"])
        self.assertTrue(any("Late CE entry" in item for item in ce["hard_blockers"]))

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_august_7_late_pe_at_support_is_blocked(self, _ema, _supertrend):
        for i, candle in enumerate(self.candles):
            candle.update({"open": 24800-i*2, "high": 24805-i*2, "low": 24790-i*2, "close": 24795-i*2})
        self.capture.update({
            "open": "24670.10", "close": "24650.60", "ema_5": "24673.56", "ema_20": "24696.90",
            "ema_50": "24708.22", "vwap": "24677.13", "supertrend": "24592.71",
            "atr_14": "26.48", "rsi_14": "24.72", "volume_ratio": "2.40", "volume_ema": "471.93",
            "candle_direction": "BEARISH",
        })
        self.chain.update({"call_resistance": 24600, "put_support": 24600})
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain, self.settings)
        pe = result["side_evaluations"]["PE"]
        self.assertFalse(pe["trade_ready"])
        self.assertFalse(pe["entry_quality"]["timely"])
        self.assertTrue(any("Late PE entry" in item for item in pe["hard_blockers"]))

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_recent_impulse_volume_can_confirm_a_timely_pullback(self, _ema, _supertrend):
        self.candles[-3].update({"open": 104, "close": 107, "volume": 220})
        self.capture.update({"volume_ratio": ".80", "volume_ema": "100", "rsi_14": "55"})
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain, self.settings)
        volume = next(item for item in result["side_evaluations"]["CE"]["confirmations"] if item["name"] == "Directional volume")
        self.assertTrue(volume["passed"])
        self.assertIn("recent bullish impulse", volume["detail"])

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_trending_environment_uses_adaptive_entry_extension(self, _ema, _supertrend):
        self.capture.update({"open": "110", "close": "114", "rsi_14": "60"})
        environment = {
            "regime": "TRENDING", "vix_zone": "HEALTHY TREND", "risk_multiplier": 1,
            "volume_threshold": 1.5, "max_entry_extension_atr": 1.0,
            "regular_move_target_points": 20,
        }
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain, self.settings, environment)
        quality = result["side_evaluations"]["CE"]["entry_quality"]
        self.assertEqual(quality["maximum_extension_atr"], 1.0)
        self.assertEqual(quality["regular_move_target_points"], 20)
        self.assertTrue(quality["timely"])

    @patch("engine.tps_entry_confirmation.analyze_candles", return_value={
        "state": "Bearish structure", "support": 24100.0, "resistance": 24350.0,
        "support_zone": {"source": "fallback", "touches": 1, "reliable": False},
        "resistance_zone": {"source": "cluster", "touches": 3, "reliable": True},
    })
    def test_fresh_pe_grace_is_blocked_when_vix_range_is_exhausted(self, _structure):
        for i, candle in enumerate(self.candles):
            candle.update({"open": 24400-i*3, "high": 24405-i*3, "low": 24390-i*3,
                           "close": 24395-i*3, "volume": 100})
        self.candles[-1].update({"open": 24195, "high": 24200, "low": 24188,
                                 "close": 24190.30, "volume": 123})
        self.capture.update({
            "open": "24195", "close": "24190.30", "ema_5": "24196.05", "ema_20": "24207.31",
            "ema_50": "24234.93", "vwap": "24254.90", "supertrend": "24146.57",
            "atr_14": "14.70", "rsi_14": "47.60", "volume_ratio": "1.23",
            "candle_direction": "BEARISH", "fake_breakout_risk": False,
        })
        self.chain.update({"put_support": 24000, "call_resistance": 24300,
                           "pcr_oi": .72, "pcr_volume": 1.64})
        environment = {
            "regime": "TRENDING", "vix_zone": "CALM / RANGE", "risk_multiplier": .75,
            "volume_threshold": 1.0, "max_entry_extension_atr": 1.0,
            "regular_move_target_points": 17.57, "remaining_expected_range": 1.38,
            "range_consumed_percent": 99.2, "movement_state": "RANGE NEARLY USED",
            "regular_move_available": False,
        }
        settings = {**self.settings, "trade_plan_min_score": 60, "tps_required_matches": 4}
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain, settings, environment)
        pe = result["side_evaluations"]["PE"]
        self.assertFalse(pe["trade_ready"])
        self.assertTrue(any("expected range exhaustion" in item for item in pe["hard_blockers"]))
        self.assertEqual(pe["entry_quality"]["range_consumed_percent"], 99.2)
        self.assertEqual(pe["entry_quality"]["remaining_expected_range"], 1.38)

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_fresh_extension_grace_remains_when_move_budget_is_available(self, _ema, _supertrend):
        self.capture.update({"open": "116", "close": "117", "ema_20": "105", "vwap": "106", "rsi_14": "58"})
        self.candles[-1].update({"open": 116, "high": 118, "low": 105.2, "close": 117, "volume": 200})
        environment = {
            "regime": "TRENDING", "vix_zone": "NORMAL", "risk_multiplier": 1,
            "volume_threshold": 1.5, "max_entry_extension_atr": 1.0,
            "regular_move_target_points": 20, "remaining_expected_range": 80,
            "range_consumed_percent": 55, "movement_state": "MOVEMENT AVAILABLE",
            "regular_move_available": True,
        }
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain, self.settings, environment)
        ce = result["side_evaluations"]["CE"]
        self.assertFalse(any("expected range exhaustion" in item for item in ce["hard_blockers"]))
        self.assertTrue(any("fresh-trigger grace band" in item for item in ce["quality_warnings"]))

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_low_volatility_keeps_trend_checks_and_marks_only_missing_data_na(self, _ema, _supertrend):
        environment = {
            "regime": "LOW VOLATILITY", "vix_zone": "CALM / RANGE", "risk_multiplier": .75,
            "volume_threshold": 1.7, "max_entry_extension_atr": .65,
        }
        result = evaluate_tps_entry_v2(self.candles, self.capture, {}, self.settings, environment)
        ce = result["side_evaluations"]["CE"]
        not_applicable = {item["name"]: item["status"] for item in ce["not_applicable_confirmations"]}
        self.assertEqual(not_applicable["OI/PCR context"], "UNKNOWN")
        self.assertNotIn("EMA 5/20/50 alignment", not_applicable)
        self.assertNotIn("SuperTrend confirmation", not_applicable)
        self.assertEqual(ce["total"], 7)
        self.assertLessEqual(ce["required"], ce["total"])

    @patch("engine.tps_entry_confirmation.analyze_candles", return_value={
        "state": "Bullish structure", "support": 78080.0, "resistance": 78160.0,
    })
    def test_sensex_1145_sparse_volume_is_excluded_and_near_extension_is_not_vetoed(self, _structure):
        candles = [
            {"open": 78100, "high": 78130, "low": 78090, "close": 78120, "volume": 20}
            for _ in range(60)
        ]
        candles[-1].update({"open": 78160, "high": 78170, "low": 78160, "close": 78170, "volume": 4})
        capture = {
            "symbol": "SENSEX", "open": "78160", "high": "78170", "low": "78160", "close": "78170",
            "ema_5": "78127.83", "ema_20": "78120.96", "ema_50": "78119.48",
            "vwap": "78137.34", "supertrend": "78025.59", "atr_14": "44.11", "rsi_14": "52.56",
            "volume": "4", "volume_ema": "58.59", "volume_ratio": ".07",
            "candle_direction": "BULLISH", "fake_breakout_risk": False,
        }
        chain = {"pcr_oi": 1.02, "pcr_volume": 1.09, "call_resistance": 78000, "put_support": 77700}
        environment = {
            "regime": "LOW VOLATILITY", "vix_zone": "CALM / RANGE", "risk_multiplier": .75,
            "volume_threshold": 1.7, "max_entry_extension_atr": .65, "regular_move_target_points": 56.48,
        }
        settings = {
            "trade_plan_min_score": 60, "tps_required_matches": 5, "tps_match_mode": "adaptive",
            "tps_enabled_conditions": [
                "EMA 5/20/50 alignment", "SuperTrend confirmation", "Pullback and reversal",
                "Directional volume", "OI/PCR context",
            ],
        }
        result = evaluate_tps_entry_v2(candles, capture, chain, settings, environment)
        ce = result["side_evaluations"]["CE"]
        volume = next(item for item in ce["confirmations"] if item["name"] == "Directional volume")
        self.assertEqual(volume["status"], "UNKNOWN")
        self.assertIn("Sparse futures-volume", volume["detail"])
        self.assertEqual((ce["passed"], ce["required"], ce["total"]), (4, 4, 4))
        self.assertFalse(ce["trade_ready"])
        self.assertTrue(any("Directional volume evidence unavailable" in item for item in ce["data_gaps"]))
        self.assertTrue(ce["entry_quality"]["timely"])
        self.assertFalse(ce["hard_blockers"])
        self.assertTrue(any("grace band" in item for item in ce["quality_warnings"]))

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_just_closed_reversal_candle_does_not_wait_an_extra_candle(self, _ema, _supertrend):
        for candle in self.candles[-3:]:
            candle["low"] = 90
        self.candles[-1].update({"open": 106, "close": 110, "low": 105.2, "volume": 210})
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain, self.settings)
        pullback = next(item for item in result["side_evaluations"]["CE"]["confirmations"] if item["name"] == "Pullback and reversal")
        self.assertTrue(pullback["passed"])
        self.assertTrue(result["side_evaluations"]["CE"]["entry_quality"]["fresh_pullback_reversal"])

    @patch("engine.tps_entry_confirmation.analyze_candles", return_value={
        "state": "Bearish structure", "support": 109.5, "resistance": 125.0,
        "support_zone": {"source": "fallback", "touches": 1, "reliable": False},
        "resistance_zone": {"source": "cluster", "touches": 3, "reliable": True},
    })
    def test_falling_fallback_support_is_warning_not_repeating_hard_wall(self, _structure):
        for i, candle in enumerate(self.candles):
            candle.update({"open": 125-i*.25, "high": 126-i*.25, "low": 123-i*.25,
                           "close": 124-i*.25, "volume": 100})
        self.capture.update({
            "open": "110.5", "close": "110", "ema_5": "111", "ema_20": "113", "ema_50": "116",
            "vwap": "114", "supertrend": "115", "atr_14": "10", "rsi_14": "45",
            "volume_ratio": "1.0", "volume_ema": "100", "volume": "100",
            "candle_direction": "BEARISH", "fake_breakout_risk": False,
        })
        self.chain.update({"put_support": 100, "call_resistance": 125, "pcr_oi": .8, "pcr_volume": 1.0})
        environment = {"regime": "TRENDING", "vix_zone": "NORMAL", "risk_multiplier": 1,
                       "volume_threshold": 1.5, "regular_move_target_points": 20}
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain, self.settings, environment)
        pe = result["side_evaluations"]["PE"]
        volume = next(item for item in pe["confirmations"] if item["name"] == "Directional volume")
        self.assertTrue(volume["passed"])
        self.assertIn("regime-aware bearish continuation", volume["detail"])
        self.assertFalse(any("too close to reliable" in item for item in pe["hard_blockers"]))
        self.assertTrue(any("observation only" in item for item in pe["quality_warnings"]))

    @patch("engine.tps_entry_confirmation.analyze_candles", return_value={
        "state": "Bearish structure", "support": 109.5, "resistance": 125.0,
        "support_zone": {"source": "cluster", "touches": 3, "reliable": True},
        "resistance_zone": {"source": "cluster", "touches": 3, "reliable": True},
    })
    def test_repeated_support_remains_a_hard_blocker(self, _structure):
        self.capture.update({"open": "110.5", "close": "110", "ema_5": "111", "ema_20": "113",
                             "ema_50": "116", "vwap": "114", "supertrend": "115",
                             "candle_direction": "BEARISH", "rsi_14": "45"})
        self.chain.update({"put_support": 100})
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain, self.settings,
                                       {"regime": "TRENDING", "vix_zone": "NORMAL", "risk_multiplier": 1})
        self.assertTrue(any("reliable chart support" in item for item in result["side_evaluations"]["PE"]["hard_blockers"]))

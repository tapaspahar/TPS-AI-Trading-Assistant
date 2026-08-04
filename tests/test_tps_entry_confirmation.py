import unittest
from unittest.mock import patch

from engine.tps_entry_confirmation import evaluate_tps_entry_v2


class TpsEntryConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.candles = [
            {"open": 100 + index * 0.1, "high": 102 + index * 0.1, "low": 99 + index * 0.1, "close": 101 + index * 0.1, "volume": 100}
            for index in range(60)
        ]
        self.candles[-2]["low"] = 105.1
        self.capture = {
            "open": "109.00", "close": "110.00", "ema_5": "108.00", "ema_20": "105.00", "ema_50": "100.00",
            "vwap": "106.00", "supertrend": "102.00", "atr_14": "2.00", "volume_ratio": "2.00",
            "candle_direction": "BULLISH", "fake_breakout_risk": False,
        }
        self.chain = {"pcr_oi": 1.0, "pcr_volume": 1.0, "call_resistance": 115, "put_support": 95}

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_all_six_confirmations_allow_ce_entry(self, _ema, _supertrend):
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain)
        self.assertTrue(result["trade_ready"])
        self.assertEqual(result["candidate"], "CE")
        self.assertEqual(result["passed"], 6)
        self.assertFalse(result["blockers"])

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_five_of_six_confirmations_can_pass(self, _ema, _supertrend):
        self.chain["call_resistance"] = 110.5
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain)
        self.assertTrue(result["trade_ready"])
        self.assertEqual(result["passed"], 5)
        self.assertEqual(result["score"], 83)

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=100)
    def test_low_volume_and_flat_ema50_are_hard_no_trade_filters(self, _ema, _supertrend):
        self.capture.update({"volume_ratio": "0.50", "fake_breakout_risk": True})
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain)
        self.assertFalse(result["trade_ready"])
        self.assertTrue(any("volume" in reason.lower() for reason in result["blockers"]))
        self.assertTrue(any("EMA50 is flat" in reason for reason in result["blockers"]))

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_bearish_consensus_selects_pe_even_when_supertrend_is_bullish(self, _ema, _supertrend):
        for index, candle in enumerate(self.candles):
            candle.update({"open": 120 - index * 0.2, "high": 121 - index * 0.2, "low": 118 - index * 0.2, "close": 119 - index * 0.2})
        self.capture.update({
            "open": "110.00", "close": "109.00", "ema_5": "110.00", "ema_20": "112.00", "ema_50": "115.00",
            "vwap": "114.00", "supertrend": "100.00", "candle_direction": "BEARISH",
        })
        self.chain.update({"pcr_oi": 0.63, "pcr_volume": 1.52})
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain)
        self.assertEqual(result["direction"], "BEARISH")
        self.assertEqual(result["candidate"], "PE")
        self.assertFalse(next(item for item in result["confirmations"] if item["name"] == "SuperTrend confirmation")["passed"])

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_one_bullish_candle_does_not_turn_a_bearish_setup_into_ce(self, _ema, _supertrend):
        for index, candle in enumerate(self.candles):
            candle.update({"open": 120 - index * 0.2, "high": 121 - index * 0.2, "low": 118 - index * 0.2, "close": 119 - index * 0.2})
        self.capture.update({
            "open": "108.00", "close": "109.00", "ema_5": "110.00", "ema_20": "112.00", "ema_50": "115.00",
            "vwap": "114.00", "supertrend": "100.00", "candle_direction": "BULLISH",
        })
        self.chain.update({"pcr_oi": 0.63, "pcr_volume": 1.52})
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain)
        self.assertEqual(result["direction"], "BEARISH")
        self.assertEqual(result["candidate"], "PE")
        self.assertFalse(result["trade_ready"])
        self.assertFalse(next(item for item in result["confirmations"] if item["name"] == "Directional volume")["passed"])

    @patch("engine.tps_entry_confirmation.supertrend", return_value=90)
    @patch("engine.tps_entry_confirmation.ema", return_value=95)
    def test_mixed_direction_never_selects_an_option_side(self, _ema, _supertrend):
        self.capture.update({"vwap": "111.00", "ema_5": "104.00", "ema_20": "106.00", "ema_50": "100.00"})
        result = evaluate_tps_entry_v2(self.candles, self.capture, self.chain)
        self.assertEqual(result["direction"], "MIXED")
        self.assertIsNone(result["candidate"])
        self.assertFalse(result["trade_ready"])

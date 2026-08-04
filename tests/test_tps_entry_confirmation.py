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
        self.capture["vwap"] = "111.00"
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

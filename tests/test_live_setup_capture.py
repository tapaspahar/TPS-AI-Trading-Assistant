import unittest
from datetime import datetime, timedelta

from engine.live_setup_capture import build_live_capture


class LiveSetupCaptureTests(unittest.TestCase):
    def test_builds_tps_fields_from_ohlcv_candles(self):
        start = datetime(2026, 8, 3, 9, 15)
        candles = []
        for index in range(70):
            price = 24000 + index
            candles.append({
                "time": (start + timedelta(minutes=index * 5)).isoformat(), "open": price,
                "high": price + 3, "low": price - 2, "close": price + 1, "volume": 100 + index,
            })
        result = build_live_capture("NIFTY", "5m", candles)
        self.assertEqual(result["symbol"], "NIFTY")
        self.assertTrue(result["ema_50"])
        self.assertTrue(result["vwap"])
        self.assertIn(result["supertrend_state"], {"Green / Bullish", "Red / Bearish"})

    def test_does_not_invent_vwap_when_volume_is_missing(self):
        candles = [{"time": "2026-08-03T09:15:00", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 0} for _ in range(60)]
        result = build_live_capture("NIFTY", "5m", candles)
        self.assertEqual(result["vwap"], "")
        self.assertIn("unavailable", result["raw_text"])

    def test_marks_a_high_volume_rejection_as_fake_move_risk(self):
        start = datetime(2026, 8, 3, 9, 15)
        candles = []
        for index in range(70):
            price = 24000 + index
            candles.append({
                "time": (start + timedelta(minutes=index * 5)).isoformat(), "open": price,
                "high": price + 3, "low": price - 2, "close": price + 1, "volume": 100,
            })
        candles[-1].update({"open": 24070, "high": 24100, "low": 24060, "close": 24072, "volume": 300})
        result = build_live_capture("NIFTY", "5m", candles)
        self.assertIn("fake-move risk", result["volume_signal"])
        self.assertTrue(result["fake_breakout_risk"])

    def test_low_volume_is_a_soft_failure_not_a_fake_breakout(self):
        start = datetime(2026, 8, 3, 9, 15)
        candles = []
        for index in range(70):
            price = 24000 + index
            candles.append({
                "time": (start + timedelta(minutes=index * 5)).isoformat(), "open": price,
                "high": price + 3, "low": price - 2, "close": price + 1, "volume": 100,
            })
        candles[-1]["volume"] = 40
        result = build_live_capture("NIFTY", "5m", candles)
        self.assertIn("below heavy-confirmation", result["volume_signal"])
        self.assertFalse(result["fake_breakout_risk"])

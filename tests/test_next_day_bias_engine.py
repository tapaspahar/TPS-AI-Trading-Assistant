import unittest

from engine.next_day_bias_engine import NextDayBiasEngine


class NextDayBiasEngineTests(unittest.TestCase):
    def values(self, **overrides):
        data = dict(spot_close=101, spot_ema5=100, spot_ema20=99, spot_ema50=98, spot_vwap=100,
                    spot_supertrend=97, future_close=102, future_ema5=101, future_ema20=100,
                    future_ema50=99, future_vwap=100, future_supertrend=98, put_support=95,
                    call_resistance=110, oi_pcr=1.2, atm_call=3, atm_put=3, atr=2)
        data.update(overrides); return data

    def test_bullish_confluence(self):
        result = NextDayBiasEngine().analyze(self.values())
        self.assertEqual(result["bias"], "BULLISH")
        self.assertGreaterEqual(result["confidence"], 70)

    def test_bearish_confluence(self):
        result = NextDayBiasEngine().analyze(self.values(
            spot_close=97, spot_ema5=98, spot_ema20=99, spot_ema50=100, spot_vwap=99, spot_supertrend=101,
            future_close=96, future_ema5=97, future_ema20=98, future_ema50=99, future_vwap=98,
            future_supertrend=100, oi_pcr=.7))
        self.assertEqual(result["bias"], "BEARISH")

    def test_invalid_oi_zone_is_rejected(self):
        with self.assertRaises(ValueError):
            NextDayBiasEngine().analyze(self.values(put_support=110, call_resistance=100))

    def test_missing_spot_vwap_abstains_without_blocking_direct_data(self):
        result = NextDayBiasEngine().analyze(self.values(spot_vwap=""))
        self.assertEqual(result["bias"], "BULLISH")
        self.assertIn("VWAP unavailable", " ".join(result["evidence"]))

    def test_equal_oi_walls_are_valid_pin_zone(self):
        result = NextDayBiasEngine().analyze(self.values(put_support=105, call_resistance=105))
        self.assertEqual(result["support"], result["resistance"])

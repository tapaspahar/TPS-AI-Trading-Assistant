import unittest

from engine.multi_timeframe_engine import analyze_multi_timeframe, candle_pattern


def make_candles(direction):
    candles = []
    for index in range(25):
        base = 100 + index * direction
        candles.append({"open": base, "high": base + 2, "low": base - 1, "close": base + 1, "volume": 100 + index})
    return candles


class MultiTimeframeEngineTests(unittest.TestCase):
    def test_bullish_alignment_has_nearby_levels(self):
        result = analyze_multi_timeframe({timeframe: make_candles(1) for timeframe in ("5m", "15m", "1h", "1D")})
        self.assertEqual(result["context"], "Bullish multi-timeframe alignment")
        self.assertGreater(result["resistance"], result["support"])

    def test_detects_bullish_engulfing(self):
        candles = [
            {"open": 102, "high": 103, "low": 99, "close": 100, "volume": 100},
            {"open": 99, "high": 104, "low": 98, "close": 103, "volume": 120},
        ]
        self.assertEqual(candle_pattern(candles), "Bullish engulfing")

import unittest

from engine.market_structure import analyze_candles


def candle(close, high, low, volume=100):
    return {"close": close, "high": high, "low": low, "volume": volume}


class MarketStructureTests(unittest.TestCase):
    def test_returns_levels_and_confirmation_conditions(self):
        candles = [
            candle(100, 101, 99), candle(102, 103, 100), candle(101, 102, 99),
            candle(104, 105, 102), candle(106, 107, 104), candle(105, 106, 103),
            candle(108, 109, 106), candle(110, 111, 108), candle(109, 110, 107),
            candle(112, 113, 110), candle(114, 115, 112), candle(113, 114, 111),
        ]
        result = analyze_candles(candles)
        self.assertGreater(result["resistance"], result["support"])
        self.assertGreater(result["breakout_level"], result["resistance"])
        self.assertLess(result["breakdown_level"], result["support"])
        self.assertLess(result["support_zone"]["low"], result["support_zone"]["high"])
        self.assertLess(result["resistance_zone"]["low"], result["resistance_zone"]["high"])
        self.assertEqual(result["level_method"], "clustered completed-candle swing zones")
        self.assertIn(result["support_zone"]["source"], {"cluster", "fallback"})
        self.assertEqual(result["support_zone"]["reliable"], result["support_zone"]["source"] == "cluster" and result["support_zone"]["touches"] >= 2)
        self.assertIn("structure", result["state"])

    def test_rejects_too_few_candles(self):
        with self.assertRaises(ValueError):
            analyze_candles([candle(100, 101, 99)] * 9)

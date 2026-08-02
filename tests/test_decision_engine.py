import unittest

from engine.decision_engine import ChartSnapshot, DecisionEngine


class DecisionEngineTests(unittest.TestCase):
    def test_strong_bullish_ce_setup(self):
        snapshot = ChartSnapshot(price=110, ema_5=108, ema_20=105, ema_50=100, vwap=106, supertrend=102, volume=200, volume_ema=100)
        result = DecisionEngine().evaluate(snapshot, "CE", "Calm")
        self.assertEqual(result["direction"], "BULLISH")
        self.assertEqual(result["decision"], "STRONG CE SETUP")
        self.assertEqual(result["score"], 100)

    def test_mismatched_option_is_not_a_trade(self):
        snapshot = ChartSnapshot(price=110, ema_5=99, ema_20=105, ema_50=100, vwap=115, supertrend=102, volume=50, volume_ema=100)
        result = DecisionEngine().evaluate(snapshot, "PE", "FOMO")
        self.assertEqual(result["decision"], "NO TRADE")
        self.assertIn("PE conflicts", result["warnings"][-2])

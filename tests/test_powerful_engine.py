import unittest

from engine.powerful_engine import evaluate_powerful_engine


def inputs():
    return {
        "pre_candle": {"prediction": "BULLISH", "confidence": 72, "validation_ready": True, "validated_purity": 66, "validation_signals": 30},
        "capture": {"close": 101, "ema_5": 100, "ema_20": 99, "ema_50": 98, "vwap": 99.5, "supertrend": 98.5, "volume_ratio": 1.8, "candle_direction": "BULLISH"},
        "multi_timeframe": {"context": "Bullish multi-timeframe alignment"},
        "smart_money": {"direction": "BULLISH", "score": 75, "structure": "BULLISH (HH + HL)", "event": "BULLISH BOS"},
        "chain": {"pcr_oi": 1.2, "put_support": 100, "call_resistance": 105, "quoted_contracts": 10},
        "environment": {"volume_threshold": 1.5, "vix": 14, "vix_zone": "HEALTHY TREND", "regime": "TRENDING", "regular_move_available": True},
        "option_quote": {"ltp": 100, "bid": 98, "ask": 102, "volume": 5000},
    }


class PowerfulEngineTests(unittest.TestCase):
    def test_publishes_only_with_broad_bullish_agreement(self):
        result = evaluate_powerful_engine(**inputs())
        self.assertTrue(result["published"])
        self.assertEqual(result["signal"], "POWERFUL CE SIGNAL")

    def test_abstains_when_walk_forward_purity_is_unproven(self):
        data = inputs(); data["pre_candle"] = {**data["pre_candle"], "validation_ready": False, "validated_purity": 0}
        result = evaluate_powerful_engine(**data)
        self.assertFalse(result["published"])
        self.assertTrue(any("walk-forward" in item for item in result["blockers"]))

    def test_abstains_on_wide_option_spread(self):
        data = inputs(); data["option_quote"] = {"ltp": 100, "bid": 90, "ask": 110, "volume": 5000}
        result = evaluate_powerful_engine(**data)
        self.assertFalse(result["published"])
        self.assertTrue(any("spread" in item for item in result["blockers"]))


if __name__ == "__main__":
    unittest.main()

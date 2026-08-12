import unittest

from engine.gap_probability_engine import GapProbabilityEngine


class GapProbabilityEngineTests(unittest.TestCase):
    @staticmethod
    def values(**changes):
        data = {
            "spot_close": 25000, "spot_ema5": 24990, "spot_ema20": 24950, "spot_ema50": 24900,
            "spot_vwap": 24940, "spot_supertrend": 24880,
            "future_close": 25050, "future_ema5": 25020, "future_ema20": 24980, "future_ema50": 24920,
            "future_vwap": 24960, "future_supertrend": 24900, "oi_pcr": 1.15,
            "fii_net": 2500, "dii_net": 800,
        }
        data.update(changes); return data

    def test_probabilities_sum_to_100_and_bullish_evidence_prefers_gap_up(self):
        result = GapProbabilityEngine().analyze(self.values())
        self.assertAlmostEqual(
            result["gap_up_probability"] + result["flat_probability"] + result["gap_down_probability"], 100.0
        )
        self.assertEqual(result["predicted_class"], "GAP UP")
        self.assertLessEqual(result["confidence"], 78)

    def test_bearish_evidence_prefers_gap_down(self):
        result = GapProbabilityEngine().analyze(self.values(
            spot_close=24500, spot_ema5=24510, spot_ema20=24550, spot_ema50=24600,
            spot_vwap=24580, spot_supertrend=24620, future_close=24440,
            future_ema5=24450, future_ema20=24500, future_ema50=24580,
            future_vwap=24540, future_supertrend=24590, oi_pcr=0.75, fii_net=-5000, dii_net=-500,
        ))
        self.assertEqual(result["predicted_class"], "GAP DOWN")

    def test_missing_institutional_data_is_not_invented(self):
        result = GapProbabilityEngine().analyze(self.values(fii_net="", dii_net=""))
        self.assertTrue(any("no institutional vote" in item for item in result["evidence"]))


if __name__ == "__main__":
    unittest.main()

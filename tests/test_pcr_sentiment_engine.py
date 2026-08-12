import unittest

from engine.pcr_sentiment_engine import analyze_pcr_sentiment


class PcrSentimentEngineTests(unittest.TestCase):
    def test_put_oi_building_creates_bullish_context(self):
        result = analyze_pcr_sentiment({
            "call_oi": 100, "put_oi": 140, "pcr_oi": 1.4,
            "call_volume": 100, "put_volume": 130, "pcr_volume": 1.3,
            "call_oi_change": -5, "put_oi_change": 25,
            "put_support": 24900, "call_resistance": 25100,
        })
        self.assertEqual(result["sentiment"], "BULLISH OI BIAS")
        self.assertLessEqual(result["confidence"], 75)

    def test_call_oi_building_creates_bearish_context(self):
        result = analyze_pcr_sentiment({
            "call_oi": 160, "put_oi": 100, "pcr_oi": .625,
            "call_volume": 140, "put_volume": 70, "pcr_volume": .5,
            "call_oi_change": 30, "put_oi_change": -10,
        })
        self.assertEqual(result["sentiment"], "BEARISH OI BIAS")

    def test_first_observation_stays_balanced_when_oi_is_balanced(self):
        result = analyze_pcr_sentiment({
            "call_oi": 100, "put_oi": 100, "pcr_oi": 1,
            "call_volume": 100, "put_volume": 100, "pcr_volume": 1,
            "call_oi_change": 0, "put_oi_change": 0,
        })
        self.assertEqual(result["sentiment"], "BALANCED / RANGE OI")
        self.assertTrue(any("first saved observation" in text.lower() for text in result["warnings"]))

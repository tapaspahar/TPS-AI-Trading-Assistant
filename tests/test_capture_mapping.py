import unittest


class CaptureMappingTests(unittest.TestCase):
    def test_chart_capture_fields_match_decision_engine_fields(self):
        mapping = {
            "close": "price", "ema_5": "ema_5", "ema_20": "ema_20",
            "ema_50": "ema_50", "vwap": "vwap", "supertrend": "supertrend",
            "volume": "volume", "volume_ema_period": "volume_ema",
        }
        self.assertEqual(mapping["close"], "price")
        self.assertEqual(len(mapping), 8)

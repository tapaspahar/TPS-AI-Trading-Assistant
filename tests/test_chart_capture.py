import unittest

from services.chart_capture_service import ChartCaptureService


class ChartCaptureTests(unittest.TestCase):
    def test_parser_extracts_sensex_chart_values(self):
        text = "SENSEX 5m BSE O 78087.97 H 78097.60 L 78008.58 C 78034.57 EMA:Plot 78107.13 EMA:Plot 78091.97 VWAP 78081.46 EMA:Plot 78079.05 SuperTrend 78173.75 Volume 44"
        result = ChartCaptureService().parse_text(text)
        self.assertEqual(result["symbol"], "SENSEX")
        self.assertEqual(result["timeframe"], "5m")
        self.assertEqual(result["close"], "78034.57")
        self.assertEqual(result["vwap"], "78081.46")
        self.assertEqual(result["supertrend"], "78173.75")
        self.assertEqual(result["ema_20"], "78107.13")
        self.assertEqual(result["ema_50"], "78091.97")
        self.assertEqual(result["ema_5"], "78079.05")
        self.assertEqual(result["supertrend_state"], "BEARISH")

    def test_parser_allows_missing_labels(self):
        result = ChartCaptureService().parse_text("NIFTY 15M")
        self.assertEqual(result["symbol"], "NIFTY")
        self.assertEqual(result["timeframe"], "15m")
        self.assertEqual(result["close"], "")

    def test_parser_handles_common_ocr_zero_for_open(self):
        result = ChartCaptureService().parse_text("SENSEX BSE 078087.97 H78097.60 L78008.58 C78034.57")
        self.assertEqual(result["open"], "78087.97")
        self.assertEqual(result["close"], "78034.57")

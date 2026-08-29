import unittest

from engine.chart_oi_narrative_engine import analyze_chart_oi_narrative


def candle(index, opening=100, close=101, high=102, low=99, volume=1000):
    return {"time": f"2026-08-29T10:{index:02d}:00+05:30", "open": opening,
            "high": high, "low": low, "close": close, "volume": volume}


class ChartOINarrativeTests(unittest.TestCase):
    def test_big_bullish_bar_and_flow_create_confirmation_watch(self):
        rows = [candle(i) for i in range(20)]
        rows.append(candle(20, 100, 108, 109, 99.5, 3000))
        result = analyze_chart_oi_narrative(rows, {"direction": "BULLISH FLOW", "quality": 80})
        self.assertTrue(result["big_bar"])
        self.assertTrue(result["aligned"])
        self.assertEqual(result["state"], "BIG MOVE CONFIRMATION WATCH")

    def test_repeated_upper_wicks_are_explained_without_claiming_cause(self):
        rows = [candle(i) for i in range(12)]
        for index in range(5):
            rows.append(candle(20 + index, 100, 100.5, 105, 99.5))
        result = analyze_chart_oi_narrative(rows, {"direction": "BALANCED FLOW", "quality": 80})
        self.assertGreaterEqual(result["upper_rejections"], 3)
        self.assertEqual(result["state"], "REPEATED WICK WATCH")
        self.assertIn("exact participant intent prove nahi karta", result["wick_explanation"])

    def test_insufficient_candles_are_data_gap(self):
        result = analyze_chart_oi_narrative([candle(1)], {})
        self.assertEqual(result["state"], "DATA GAP")


if __name__ == "__main__":
    unittest.main()

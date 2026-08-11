import unittest
from datetime import datetime, timedelta

from engine.pre_candle_probability import analyze_pre_candle_probability


def patterned_candles(count=320):
    rows = []
    price = 1000.0
    start = datetime(2026, 1, 1, 9, 15)
    # Repeating impulse/pullback sequence gives the analog engine learnable,
    # deterministic structure without allowing it to see the next candle.
    moves = (2.0, 1.5, -0.5, 2.2, -1.0, -1.8, 0.4, -2.1)
    for index in range(count):
        opening = price
        price += moves[index % len(moves)]
        high = max(opening, price) + 0.6
        low = min(opening, price) - 0.6
        rows.append({
            "time": (start + timedelta(minutes=5 * index)).isoformat(),
            "open": opening, "high": high, "low": low, "close": price,
            "volume": 1000 + (index % len(moves)) * 100,
        })
    return rows


class PreCandleProbabilityTests(unittest.TestCase):
    def test_requires_enough_candles(self):
        with self.assertRaisesRegex(ValueError, "140"):
            analyze_pre_candle_probability(patterned_candles(100))

    def test_returns_probabilities_and_walk_forward_evidence(self):
        result = analyze_pre_candle_probability(patterned_candles(), 60)
        total = result["bullish_probability"] + result["bearish_probability"] + result["range_probability"]
        self.assertAlmostEqual(total, 100.0, places=5)
        self.assertGreater(result["historical_analogs"], 200)
        self.assertGreater(result["validation_signals"], 0)
        self.assertIn(result["prediction"], ("BULLISH", "BEARISH", "RANGE"))

    def test_purity_gate_is_bounded(self):
        result = analyze_pre_candle_probability(patterned_candles(), 10)
        self.assertEqual(result["minimum_purity"], 50)


if __name__ == "__main__":
    unittest.main()

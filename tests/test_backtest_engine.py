import unittest

from engine.backtest_engine import run_tps_backtest


def candles():
    rows = []
    price = 100.0
    for index in range(130):
        price += 0.35
        rows.append({
            "time": f"2026-08-03T09:{index % 60:02d}:00",
            "open": price - 0.15, "high": price + 0.5, "low": price - 0.4,
            "close": price, "volume": 1000 + index * 10,
        })
    return rows


class BacktestEngineTests(unittest.TestCase):
    def test_requires_enough_candles(self):
        with self.assertRaisesRegex(ValueError, "80"):
            run_tps_backtest(candles()[:30])

    def test_returns_paper_trade_metrics(self):
        result = run_tps_backtest(candles())
        self.assertEqual(result["total_trades"], len(result["trades"]))
        self.assertTrue(result["volume_available"])
        self.assertIn("net_points", result)
        self.assertIn("profit_factor", result)
        self.assertIn("research_status", result)


if __name__ == "__main__":
    unittest.main()

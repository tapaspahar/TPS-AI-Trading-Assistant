import unittest

from engine.equity_analysis import analyze_equity
from services.equity_service import parse_equity_instruments


def candles(count=70):
    return [{"time": f"2026-08-{(index // 10) + 1:02d}T10:{index % 10:02d}:00+05:30", "open": 100 + index, "high": 102 + index, "low": 99 + index, "close": 101 + index, "volume": 1000 + index * 30} for index in range(count)]


class EquityServiceTests(unittest.TestCase):
    def test_parses_nse_cash_equities_only(self):
        rows = [{"exch_seg": "NSE", "symbol": "RELIANCE-EQ", "name": "RELIANCE", "token": "1"}, {"exch_seg": "NFO", "symbol": "RELIANCE26AUGFUT", "name": "RELIANCE", "token": "2"}, {"exch_seg": "NSE", "symbol": "NIFTYBEES", "name": "ETF", "token": "3"}]
        self.assertEqual(parse_equity_instruments(rows), [{"company": "RELIANCE", "symbol": "RELIANCE-EQ", "token": "1", "exchange": "NSE"}])

    def test_creates_explainable_long_plan(self):
        result = analyze_equity(candles())
        self.assertGreater(result["entry"], result["stop_loss"])
        self.assertGreater(result["target_2"], result["target_1"])

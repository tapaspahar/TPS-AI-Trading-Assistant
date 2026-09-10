import unittest
from datetime import datetime

from core.market_session import IST
from services.market_direction_ribbon_service import build_market_direction_ribbon


class FakeDatabase:
    def __init__(self, breadth=None, candles=None):
        self.breadth = breadth or {}
        self.candles = candles or []

    def get_latest_index_component_breadth(self, symbol, _trade_date):
        return self.breadth.get(symbol)

    def get_index_candle_analyses(self, _trade_date):
        return self.candles


class MarketDirectionRibbonTests(unittest.TestCase):
    def test_three_confirmed_indexes_publish_bullish_ribbon(self):
        breadth = {symbol: {"captured_at": "2026-09-10T12:05:00+05:30", "symbol": symbol, "state": "BULLISH"}
                   for symbol in ("NIFTY", "BANKNIFTY", "SENSEX")}
        candles = [{"symbol": symbol, "candle_time": "2026-09-10T12:00:00+05:30",
                    "direction": "BULLISH", "oi_direction": "BULLISH FLOW", "oi_quality": 90}
                   for symbol in ("NIFTY", "BANKNIFTY", "SENSEX")]
        result = build_market_direction_ribbon(FakeDatabase(breadth, candles), datetime(2026, 9, 10, 12, 6, tzinfo=IST))
        self.assertEqual(result["overall"], "BULLISH")
        self.assertTrue(all(row["direction"] == "BULLISH" for row in result["indexes"]))
        self.assertEqual(result["evidence_time"], "12:05")

    def test_missing_evidence_is_not_manufactured_as_direction(self):
        result = build_market_direction_ribbon(FakeDatabase(), datetime(2026, 9, 10, 12, 6, tzinfo=IST))
        self.assertEqual(result["overall"], "DATA GAP")
        self.assertTrue(all(row["direction"] == "DATA GAP" for row in result["indexes"]))


if __name__ == "__main__":
    unittest.main()

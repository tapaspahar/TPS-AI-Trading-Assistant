import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from core.database_manager import Database
from engine.trend_memory_engine import build_daily_fingerprint, similarity_score
from services.trend_memory_service import ensure_completed_trend_memories


def candle(at, close, *, symbol="NIFTY", date="12-08-2026"):
    return {
        "captured_at": at, "trade_date": date, "symbol": symbol, "timeframe": "5m",
        "open": close - 5, "high": close + 8, "low": close - 8, "close": close,
        "volume": 1200, "volume_ema": 1000, "ema_5": close - 2, "ema_20": close - 6,
        "ema_50": close - 12, "vwap": close - 4, "supertrend": close - 10,
        "rsi_14": 62, "atr_14": 25, "oi_pcr": 1.08, "volume_pcr": 1.12,
        "oi_pcr_change": None, "volume_pcr_change": None, "put_support": close - 100,
        "call_resistance": close + 100, "option_contracts": 20,
    }


class TrendMemoryTests(unittest.TestCase):
    def test_bullish_fingerprint_and_similarity(self):
        rows = [candle(f"2026-08-12T09:{15 + i * 5:02d}:00", 24500 + i * 12) for i in range(6)]
        profile = build_daily_fingerprint(rows, "NIFTY", "12-08-2026")
        self.assertEqual(profile["trend"], "BULLISH")
        self.assertEqual(profile["chart_pattern"], "UPTREND CONTINUATION")
        self.assertGreaterEqual(similarity_score(profile, profile), 99)

    def test_completed_day_is_saved_once_and_updated_safely(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "memory.db")
            try:
                for i in range(4):
                    db.save_market_snapshot(candle(f"2026-08-12T09:{15 + i * 5:02d}:00", 24500 + i * 10))
                updated = ensure_completed_trend_memories(db, datetime(2026, 8, 13, 9, 0))
                self.assertEqual(len(updated), 1)
                self.assertEqual(len(db.get_daily_trend_memories("NIFTY")), 1)
                self.assertEqual(ensure_completed_trend_memories(db, datetime(2026, 8, 13, 9, 1)), [])
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()

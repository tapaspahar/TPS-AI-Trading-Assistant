import tempfile
import unittest
from pathlib import Path

from core.database_manager import Database
from models.trade import Trade


def sample_trade(**changes):
    values = dict(
        trade_date="01-08-2026", trade_time="09:30", market="OPTIONS", symbol="NIFTY",
        expiry="", strike="25000", option="CE", entry=120.0, exit=145.0,
        stoploss=100.0, target=180.0, quantity=75, trend=True, vwap=True,
        ema=True, volume=True, oi=True, psychology_before="Calm",
    )
    values.update(changes)
    return Trade(**values)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "trades.db")

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def test_save_trade_calculates_metrics_and_ai_analysis(self):
        trade = sample_trade()
        trade_id = self.db.save_trade(trade)
        saved = self.db.get_all_trades()

        self.assertEqual(trade_id, 1)
        self.assertEqual((trade.pnl, trade.rr_ratio), (1875.0, 3.0))
        self.assertEqual((trade.ai_score, trade.ai_decision), (90, "STRONG BUY"))
        self.assertEqual(saved[0][2], "NIFTY")
        self.assertEqual(saved[0][7], 1875.0)

    def test_invalid_quantity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Quantity"):
            self.db.save_trade(sample_trade(quantity=0))


if __name__ == "__main__":
    unittest.main()

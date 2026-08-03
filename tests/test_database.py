import tempfile
import unittest
import csv
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

    def test_open_trade_can_be_closed_later(self):
        trade_id = self.db.save_open_trade(sample_trade(exit=0.0))
        open_trade = self.db.get_trade(trade_id)
        self.assertEqual(open_trade["status"], "OPEN")
        self.assertEqual(open_trade["pnl"], 0.0)

        self.assertTrue(self.db.close_trade(trade_id, 145.0, "Target Hit"))
        closed_trade = self.db.get_trade(trade_id)
        self.assertEqual(closed_trade["status"], "CLOSED")
        self.assertEqual((closed_trade["exit"], closed_trade["pnl"], closed_trade["rr_ratio"]), (145.0, 1875.0, 3.0))
        self.assertEqual(closed_trade["outcome"], "TARGET HIT")

    def test_summary_aggregates_saved_trades(self):
        self.db.save_trade(sample_trade())
        self.db.save_trade(sample_trade(symbol="BANKNIFTY", entry=100, exit=90, stoploss=80, target=140, quantity=10))

        summary = self.db.get_summary()
        self.assertEqual(summary["trades"], 2)
        self.assertEqual(summary["winning_trades"], 1)
        self.assertEqual(summary["pnl"], 1775.0)
        self.assertEqual(summary["win_rate"], 50.0)

    def test_day_summary_filters_by_journal_date(self):
        self.db.save_trade(sample_trade())
        self.db.save_trade(sample_trade(trade_date="02-08-2026", symbol="FINNIFTY"))

        self.assertEqual(self.db.get_day_summary("01-08-2026"), {"trades": 1, "pnl": 1875.0})

    def test_delete_and_csv_export(self):
        trade_id = self.db.save_trade(sample_trade())
        export_path = Path(self.temp_dir.name) / "journal.csv"
        self.assertEqual(self.db.export_csv(export_path), 1)
        with export_path.open(encoding="utf-8-sig", newline="") as file:
            exported = list(csv.DictReader(file))
        self.assertEqual(exported[0]["symbol"], "NIFTY")
        self.assertTrue(self.db.delete_trade(trade_id))
        self.assertFalse(self.db.delete_trade(trade_id))
        self.assertEqual(self.db.get_summary()["trades"], 0)


if __name__ == "__main__":
    unittest.main()

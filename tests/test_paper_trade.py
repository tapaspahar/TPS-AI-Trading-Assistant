import tempfile
import unittest
from pathlib import Path

from core.database_manager import Database


class QuoteClient:
    def __init__(self, price): self.price = price
    def get_option_quote(self, exchange, token): return {"ltp": self.price}


class PaperTradeTests(unittest.TestCase):
    @staticmethod
    def plan():
        return {"underlying": "NIFTY", "entry": 100, "stoploss": 80, "target": 140, "quantity": 50, "confidence": 95,
                "rule_version": "TPS test", "option_type": "CE", "contract": {"expiry": "2026-08-20", "strike": 25000, "exchange": "NFO", "token": "1", "symbol": "NIFTYTESTCE"}}

    def test_paper_trade_auto_closes_at_target(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "paper.db")
            trade_id = db.save_paper_trade(self.plan())
            closed = db.monitor_paper_trades(QuoteClient(141))
            self.assertEqual((closed[0]["trade_id"], closed[0]["outcome"]), (trade_id, "TARGET HIT"))
            self.assertEqual(db.get_trade(trade_id)["status"], "CLOSED")
            db.close()

    def test_monitor_records_stop_proximity_and_mae_mfe(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "paper.db")
            db.save_paper_trade(self.plan())
            self.assertEqual(db.monitor_paper_trades(QuoteClient(88)), [])
            first = db.get_paper_trade_monitoring()[0]
            self.assertEqual(first["alert"], "EARLY")
            self.assertEqual(first["mae"], 12)
            db.monitor_paper_trades(QuoteClient(110))
            second = db.get_paper_trade_monitoring()[0]
            self.assertEqual(second["mfe"], 10)
            db.close()

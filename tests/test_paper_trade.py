import tempfile
import unittest
from pathlib import Path

from core.database_manager import Database


class QuoteClient:
    def __init__(self, price): self.price = price
    def get_option_quote(self, exchange, token): return {"ltp": self.price}


class PaperTradeTests(unittest.TestCase):
    def test_paper_trade_auto_closes_at_target(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "paper.db")
            plan = {"underlying": "NIFTY", "entry": 100, "stoploss": 80, "target": 140, "quantity": 50, "confidence": 95,
                    "rule_version": "TPS test", "option_type": "CE", "contract": {"expiry": "2026-08-20", "strike": 25000, "exchange": "NFO", "token": "1", "symbol": "NIFTYTESTCE"}}
            trade_id = db.save_paper_trade(plan)
            closed = db.monitor_paper_trades(QuoteClient(141))
            self.assertEqual((closed[0]["trade_id"], closed[0]["outcome"]), (trade_id, "TARGET HIT"))
            self.assertEqual(db.get_trade(trade_id)["status"], "CLOSED")
            db.close()

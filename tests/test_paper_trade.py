import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from core.database_manager import Database


class QuoteClient:
    def __init__(self, price): self.price = price
    def get_option_quote(self, exchange, token): return {"ltp": self.price}


class TokenQuoteClient:
    def __init__(self, values): self.values = values
    def get_option_quote(self, exchange, token):
        value = self.values[str(token)]
        if isinstance(value, Exception):
            raise value
        return {"ltp": value}


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
            self.assertEqual(db.get_trade(trade_id)["ai_score"], 95)
            self.assertEqual(db.get_trade(trade_id)["ai_decision"], "PAPER TRADE CAPTURED")
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

    def test_trailing_stop_and_time_exit_complete_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "paper.db")
            trade_id = db.save_paper_trade(self.plan())
            settings = {"trailing_stop_enabled": True, "trailing_stop_trigger_r": 1, "trailing_stop_lock_r": .25}
            db.monitor_paper_trades(QuoteClient(125), settings, datetime(2026, 8, 10, 12, 0))
            monitor = db.get_paper_trade_monitoring()[0]
            self.assertEqual(monitor["stoploss"], 105)
            closed = db.monitor_paper_trades(QuoteClient(104), settings, datetime(2026, 8, 10, 12, 1))
            self.assertEqual(closed[0]["outcome"], "TRAILING STOP HIT")
            self.assertEqual(db.get_trade(trade_id)["status"], "CLOSED")
            db.close()

    def test_time_exit_closes_open_paper_trade_before_market_close(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "paper.db")
            db.save_paper_trade(self.plan())
            closed = db.monitor_paper_trades(
                QuoteClient(108), {"trailing_stop_enabled": False, "time_exit_minutes_before_close": 10},
                datetime(2026, 8, 10, 15, 22),
            )
            self.assertEqual(closed[0]["outcome"], "TIME EXIT")
            db.close()

    def test_one_quote_failure_does_not_pause_other_open_trade_monitoring(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "paper.db")
            first = self.plan()
            second = self.plan()
            second["contract"] = {**second["contract"], "token": "2", "symbol": "NIFTYSECONDCE"}
            failed_id = db.save_paper_trade(first)
            target_id = db.save_paper_trade(second)
            closed = db.monitor_paper_trades(TokenQuoteClient({"1": RuntimeError("temporary quote failure"), "2": 145}))
            self.assertEqual([(item["trade_id"], item["outcome"]) for item in closed], [(target_id, "TARGET HIT")])
            self.assertEqual(db.get_trade(failed_id)["status"], "OPEN")
            db.close()

    def test_time_exit_uses_last_verified_ltp_when_final_quote_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "paper.db")
            trade_id = db.save_paper_trade(self.plan())
            db.monitor_paper_trades(QuoteClient(109), {"time_exit_minutes_before_close": 10}, datetime(2026, 8, 10, 12, 0))
            closed = db.monitor_paper_trades(
                TokenQuoteClient({"1": RuntimeError("final quote unavailable")}),
                {"time_exit_minutes_before_close": 10}, datetime(2026, 8, 10, 15, 22),
            )
            self.assertEqual(closed[0]["outcome"], "TIME EXIT")
            self.assertEqual(db.get_trade(trade_id)["exit"], 109)
            db.close()

    def test_time_exit_uses_last_verified_ltp_when_broker_returns_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "paper.db")
            trade_id = db.save_paper_trade(self.plan())
            db.monitor_paper_trades(QuoteClient(107), {"time_exit_minutes_before_close": 10}, datetime(2026, 8, 10, 12, 0))
            closed = db.monitor_paper_trades(
                QuoteClient(0), {"time_exit_minutes_before_close": 10}, datetime(2026, 8, 10, 15, 22),
            )
            self.assertEqual(closed[0]["outcome"], "TIME EXIT")
            self.assertEqual(db.get_trade(trade_id)["exit"], 107)
            alert = db.cursor.execute(
                "SELECT status FROM trade_alerts WHERE trade_id = ? AND alert_type = 'TIME_EXIT_LAST_VERIFIED'",
                (trade_id,),
            ).fetchone()
            self.assertEqual(alert["status"], "RESOLVED")
            db.close()

    def test_progress_reports_self_validation_accuracy_and_time_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "paper.db")
            target_id = db.save_paper_trade(self.plan())
            db.close_trade(target_id, 140, "TARGET HIT")
            stop_id = db.save_paper_trade({**self.plan(), "contract": {**self.plan()["contract"], "token": "2"}})
            db.close_trade(stop_id, 80, "STOP LOSS HIT")
            time_id = db.save_paper_trade({**self.plan(), "contract": {**self.plan()["contract"], "token": "3"}})
            db.close_trade(time_id, 110, "TIME EXIT")
            progress = db.paper_trade_progress()
            self.assertEqual(progress["time_exits"], 1)
            self.assertEqual(progress["target_vs_stop_accuracy"], 50.0)
            self.assertEqual(progress["closed_trade_win_rate"], 66.7)
            db.close()

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

    def test_matching_high_quality_gap_forecast_defers_time_exit_and_trails_next_open(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "paper.db")
            trade_id = db.save_paper_trade(self.plan())
            db.save_gap_probability_forecast({
                "forecast_date": "2026-08-10", "target_date": "2026-08-11",
                "generated_at": "2026-08-10T15:40:00+05:30", "symbol": "NIFTY",
                "stage": "3:40 CLOSE CONFIRMATION", "predicted_class": "GAP UP",
                "gap_up_probability": 58, "flat_probability": 25, "gap_down_probability": 17,
                "confidence": 68, "data_quality": 90, "prior_close": 25000,
                "inputs": {}, "evidence": ["test evidence"],
            })
            settings = {"paper_overnight_gap_hold_enabled": True, "time_exit_minutes_before_close": 10,
                        "market_pre_open_time": "09:00", "market_open_time": "09:15", "market_close_time": "15:30"}
            self.assertEqual(db.monitor_paper_trades(QuoteClient(108), settings, datetime(2026, 8, 10, 15, 22)), [])
            held = db.get_paper_trade_monitoring()[0]
            self.assertEqual(held["overnight_state"], "HELD")
            self.assertEqual(db.monitor_paper_trades(QuoteClient(150), settings, datetime(2026, 8, 11, 9, 5)), [])
            self.assertEqual(db.get_paper_trade_monitoring()[0]["overnight_state"], "HELD")
            self.assertEqual(db.monitor_paper_trades(QuoteClient(150), settings, datetime(2026, 8, 11, 9, 16)), [])
            revalidated = db.get_paper_trade_monitoring()[0]
            self.assertEqual(revalidated["overnight_state"], "REVALIDATED")
            self.assertGreater(revalidated["target"], 150)
            self.assertEqual(revalidated["stoploss"], 140)
            closed = db.monitor_paper_trades(QuoteClient(139), settings, datetime(2026, 8, 11, 9, 17))
            self.assertEqual(closed[0]["outcome"], "TRAILING STOP HIT")
            self.assertEqual(db.get_trade(trade_id)["status"], "CLOSED")
            db.close()

    def test_weak_or_opposite_gap_forecast_does_not_bypass_time_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "paper.db")
            db.save_paper_trade(self.plan())
            db.save_gap_probability_forecast({
                "forecast_date": "2026-08-10", "target_date": "2026-08-11",
                "generated_at": "2026-08-10T15:40:00+05:30", "symbol": "NIFTY",
                "stage": "3:40 CLOSE CONFIRMATION", "predicted_class": "GAP DOWN",
                "gap_up_probability": 20, "flat_probability": 25, "gap_down_probability": 55,
                "confidence": 68, "data_quality": 90, "prior_close": 25000,
                "inputs": {}, "evidence": [],
            })
            closed = db.monitor_paper_trades(
                QuoteClient(108), {"paper_overnight_gap_hold_enabled": True, "time_exit_minutes_before_close": 10},
                datetime(2026, 8, 10, 15, 22),
            )
            self.assertEqual(closed[0]["outcome"], "TIME EXIT")
            db.close()

    def test_half_r_move_arms_breakeven_before_full_trailing_trigger(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "paper.db")
            plan = {**self.plan(), "stoploss": 90, "target": 120}
            trade_id = db.save_paper_trade(plan)
            settings = {"trailing_stop_enabled": True, "trailing_stop_trigger_r": 1, "trailing_stop_lock_r": .25}
            self.assertEqual(db.monitor_paper_trades(QuoteClient(106), settings), [])
            self.assertEqual(db.get_paper_trade_monitoring()[0]["stoploss"], 100)
            closed = db.monitor_paper_trades(QuoteClient(100), settings)
            self.assertEqual(closed[0]["outcome"], "TRAILING STOP HIT")
            self.assertEqual(db.get_trade(trade_id)["pnl"], 0)
            db.close()

    def test_near_target_move_locks_material_profit(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "paper.db")
            plan = {**self.plan(), "stoploss": 90, "target": 120}
            trade_id = db.save_paper_trade(plan)
            settings = {"trailing_stop_enabled": True, "trailing_stop_trigger_r": 1, "trailing_stop_lock_r": .25}
            self.assertEqual(db.monitor_paper_trades(QuoteClient(119), settings), [])
            self.assertEqual(db.get_paper_trade_monitoring()[0]["stoploss"], 113)
            closed = db.monitor_paper_trades(QuoteClient(113), settings)
            self.assertEqual(closed[0]["outcome"], "TRAILING STOP HIT")
            self.assertEqual(db.get_trade(trade_id)["pnl"], 650)
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

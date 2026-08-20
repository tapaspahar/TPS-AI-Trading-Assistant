import json
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from core.database_manager import Database
from services.post_market_tps_analysis import ensure_completed_post_market_reports, generate_and_save_post_market_analysis


def _attempt(candle_time: str, score: int = 100, blockers=None) -> dict:
    if blockers is None:
        blockers = ["Entry is extended 1.15 ATR; late entry is blocked"]
    evaluation = {
        "selected_confirmations": [
            {"name": "EMA 5/20/50 alignment", "passed": True},
            {"name": "Directional volume", "passed": True},
        ],
        "score_matched": True,
        "checklist_matched": True,
        "hard_blockers": blockers,
    }
    return {
        "status": "No paper trade: safety blocker active.",
        "attempt": {
            "checked_at": candle_time,
            "candle_time": candle_time,
            "future_symbol": "NIFTY25AUG26FUT",
            "candidate": "CE",
            "chart": {
                "score": score,
                "decision": "CE WATCH",
                "strategy": {
                    "candidate": "CE",
                    "passed": 5,
                    "total": 5,
                    "side_evaluations": {"CE": evaluation},
                },
            },
        },
    }


class PostMarketTpsAnalysisTests(unittest.TestCase):
    def test_scheduler_records_zero_activity_when_app_is_open_after_close(self):
        with TemporaryDirectory() as directory:
            database = Database(Path(directory) / "zero-activity.db")
            updated = ensure_completed_post_market_reports(
                database, now=datetime(2026, 8, 10, 15, 31)
            )
            self.assertEqual(updated, ["10-08-2026"])
            saved = database.get_post_market_tps_analysis("10-08-2026")
            self.assertIn("koi automatic paper trade capture nahi hua", saved["summary_text"])
            self.assertIn("koi saved automatic trade attempt nahi mila", saved["summary_text"])
            database.close()

    def test_candle_wise_audit_explains_why_a_trade_was_taken(self):
        with TemporaryDirectory() as directory:
            database = Database(Path(directory) / "captured.db")
            result = _attempt("2026-08-10T12:25:00+05:30", blockers=[])
            result["plan"] = {"contract_symbol": "NIFTY25AUG2624600CE"}
            result["trade_id"] = 7
            result["status"] = "Paper trade captured"
            self.assertTrue(database.save_auto_trade_attempt("NIFTY", result))
            analysis = generate_and_save_post_market_analysis(database, "10-08-2026")
            self.assertIn("12:25 CE | CAPTURED", analysis["summary_text"])
            self.assertIn("trade liya kyunki EMA 5/20/50 alignment, Directional volume", analysis["summary_text"])
            self.assertEqual(analysis["metrics"]["attempt_audit_count"], 1)
            database.close()

    def test_scheduler_waits_for_close_then_generates_and_refreshes(self):
        with TemporaryDirectory() as directory:
            database = Database(Path(directory) / "scheduler.db")
            first = _attempt("2026-08-10T11:00:00+05:30")
            self.assertTrue(database.save_auto_trade_attempt("NIFTY", first))

            before_close = ensure_completed_post_market_reports(
                database, now=datetime(2026, 8, 10, 15, 30, 30)
            )
            self.assertEqual(before_close, [])
            self.assertIsNone(database.get_post_market_tps_analysis("10-08-2026"))

            after_close = ensure_completed_post_market_reports(
                database, now=datetime(2026, 8, 10, 15, 31)
            )
            self.assertEqual(after_close, ["10-08-2026"])
            first_saved = database.get_post_market_tps_analysis("10-08-2026")
            self.assertIsNotNone(first_saved)
            self.assertEqual(
                ensure_completed_post_market_reports(database, now=datetime(2026, 8, 10, 15, 32)),
                [],
            )

            second = _attempt("2026-08-10T14:55:00+05:30", score=82)
            self.assertTrue(database.save_auto_trade_attempt("NIFTY", second))
            self.assertEqual(
                ensure_completed_post_market_reports(database, now=datetime(2026, 8, 10, 15, 33)),
                ["10-08-2026"],
            )
            refreshed = database.get_post_market_tps_analysis("10-08-2026")
            self.assertEqual(json.loads(refreshed["metrics_json"])["source_attempt_count"], 2)
            database.close()

    def test_scheduler_backfills_a_completed_date_after_restart(self):
        with TemporaryDirectory() as directory:
            database = Database(Path(directory) / "backfill.db")
            self.assertTrue(database.save_auto_trade_attempt("NIFTY", _attempt("2026-08-10T12:00:00+05:30")))
            updated = ensure_completed_post_market_reports(
                database, now=datetime(2026, 8, 11, 9, 0)
            )
            self.assertEqual(updated, ["10-08-2026"])
            self.assertIsNotNone(database.get_post_market_tps_analysis("10-08-2026"))
            database.close()

    def test_date_wise_post_market_analysis_is_saved_and_updated(self):
        with TemporaryDirectory() as directory:
            database = Database(Path(directory) / "post-market.db")
            result = _attempt("2026-08-10T11:00:00+05:30")
            self.assertTrue(database.save_auto_trade_attempt("NIFTY", result))

            analysis = generate_and_save_post_market_analysis(
                database,
                "10-08-2026",
                now=datetime(2026, 8, 10, 15, 45),
            )
            self.assertGreater(analysis["id"], 0)
            self.assertIn("Aaj TPS se koi automatic paper trade capture nahi hua", analysis["summary_text"])
            self.assertIn("ATR ke hisab se entry late/extended", analysis["summary_text"])
            self.assertIn("10-08-2026", analysis["summary_text"])

            saved = database.get_post_market_tps_analysis("10-08-2026")
            metrics = json.loads(saved["metrics_json"])
            self.assertEqual(metrics["source_attempt_count"], 1)
            self.assertEqual(metrics["captured"], 0)
            first_id = saved["id"]

            result["attempt"]["chart"]["score"] = 90
            result["status"] = "Updated review"
            self.assertTrue(database.save_auto_trade_attempt("NIFTY", result))
            generate_and_save_post_market_analysis(database, "10-08-2026")
            self.assertEqual(database.get_post_market_tps_analysis("10-08-2026")["id"], first_id)
            self.assertEqual(database.get_post_market_source_dates(), ["10-08-2026"])
            database.close()

import json
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from core.database_manager import Database
from services.post_market_tps_analysis import generate_and_save_post_market_analysis


def _attempt(candle_time: str, score: int = 100, blockers=None) -> dict:
    blockers = blockers or ["Entry is extended 1.15 ATR; late entry is blocked"]
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

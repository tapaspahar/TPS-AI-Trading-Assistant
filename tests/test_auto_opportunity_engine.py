import tempfile
import unittest
from pathlib import Path

from core.database_manager import Database
from engine.auto_opportunity_engine import equity_opportunity, option_opportunity


class AutoOpportunityEngineTests(unittest.TestCase):
    def test_published_index_option_has_complete_risk_plan(self):
        result = option_opportunity(
            {
                "published": True,
                "candidate": "PE",
                "symbol": "NIFTY",
                "candle_time": "2026-08-12T10:00:00+05:30",
                "dominant_strength": 84,
                "option_quote": {"symbol": "NIFTY12AUG2624500PE", "ask": 100, "lot_size": 65},
                "evidence": [{"layer": "Trend", "detail": "Bearish alignment", "available": True}],
            },
            {"minimum_rr_ratio": 1.5, "time_exit_minutes_before_close": 10},
        )
        self.assertEqual(result["action"], "BUY PE")
        self.assertEqual(result["entry"], 100)
        self.assertEqual(result["stop"], 80)
        self.assertEqual(result["target_1"], 130)
        self.assertEqual(result["target_2"], 140)
        self.assertEqual(result["quantity"], 65)

    def test_unpublished_index_signal_remains_wait(self):
        result = option_opportunity(
            {"published": False, "candidate": "CE", "symbol": "NIFTY", "dominant_strength": 55,
             "blockers": ["15m trend conflicts"]},
            {},
        )
        self.assertEqual(result["action"], "WAIT")
        self.assertIsNone(result["entry"])
        self.assertIn("15m trend conflicts", result["blockers"])

    def test_equity_watch_long_becomes_buy_above(self):
        result = equity_opportunity(
            {"symbol": "RELIANCE-EQ"},
            {"score": 78, "plan_state": "WATCH LONG BREAKOUT", "entry": 2500, "stop_loss": 2475,
             "target_1": 2550, "target_2": 2575, "state": "Bullish", "volume_signal": "Strong volume"},
            "2026-08-12T10:05:00+05:30",
        )
        self.assertEqual(result["action"], "BUY ABOVE")
        self.assertEqual(result["rr_ratio"], 2.0)

    def test_database_upserts_same_candle_and_keeps_details(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "opportunities.db")
            row = option_opportunity(
                {"published": False, "symbol": "NIFTY", "candle_time": "2026-08-12T10:00:00+05:30",
                 "blockers": ["No confirmation"]},
                {},
            )
            database.save_auto_opportunities([row])
            row["score"] = 60
            database.save_auto_opportunities([row])
            saved = database.get_auto_opportunities()
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["score"], 60)
            self.assertIn("No confirmation", saved[0]["details_json"])
            database.close()


if __name__ == "__main__":
    unittest.main()

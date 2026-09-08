import tempfile
import unittest
from pathlib import Path

from core.database_manager import Database
from engine.index_component_breadth import analyze_component_breadth, combine_component_breadth, combine_market_evidence


class IndexComponentBreadthTests(unittest.TestCase):
    def test_sixty_percent_majority_is_bullish(self):
        rows = [{"name": f"S{i}", "change_percent": 1 if i < 32 else -1} for i in range(50)]
        result = analyze_component_breadth("NIFTY", rows, 50)
        self.assertEqual(result["state"], "BULLISH")
        self.assertEqual(result["positive_pct"], 64.0)

    def test_incomplete_universe_is_data_gap(self):
        rows = [{"name": f"S{i}", "change_percent": 1} for i in range(39)]
        result = analyze_component_breadth("NIFTY", rows, 50)
        self.assertEqual(result["state"], "DATA GAP")

    def test_two_of_three_indexes_form_combined_verdict(self):
        combined = combine_component_breadth([
            {"state": "BULLISH", "explanation": "n"},
            {"state": "BULLISH", "explanation": "b"},
            {"state": "MIXED", "explanation": "s"},
        ])
        self.assertEqual(combined["state"], "BULLISH")

    def test_saved_rows_without_explanation_do_not_crash_startup(self):
        combined = combine_component_breadth([
            {"symbol": "NIFTY", "state": "BEARISH", "observed": 50, "expected": 50},
            {"symbol": "BANKNIFTY", "state": "BEARISH", "observed": 12, "expected": 12},
            {"symbol": "SENSEX", "state": "DATA GAP", "observed": 20, "expected": 30},
        ])
        self.assertEqual(combined["state"], "BEARISH")
        self.assertIn("NIFTY: breadth BEARISH", combined["explanation"])

    def test_component_chart_and_oi_form_explainable_market_direction(self):
        breadth = [
            {"symbol": symbol, "state": "BEARISH", "captured_at": "2026-09-08T15:01:37+05:30"}
            for symbol in ("NIFTY", "BANKNIFTY", "SENSEX")
        ]
        candles = [
            {"symbol": symbol, "direction": "BEARISH", "oi_direction": "BEARISH FLOW",
             "oi_quality": 80, "candle_time": "2026-09-08T14:55:00+05:30"}
            for symbol in ("NIFTY", "BANKNIFTY", "SENSEX")
        ]
        result = combine_market_evidence(breadth, candles)
        self.assertEqual(result["direction"], "BEARISH")
        self.assertEqual(result["confirmed_indexes"], 3)
        self.assertTrue(all(row["direction"] == "BEARISH" for row in result["indexes"]))

    def test_low_quality_oi_is_data_gap_not_a_directional_vote(self):
        result = combine_market_evidence(
            [{"symbol": "NIFTY", "state": "BEARISH"}],
            [{"symbol": "NIFTY", "direction": "BULLISH", "oi_direction": "BEARISH FLOW", "oi_quality": 40}],
        )
        nifty = result["indexes"][0]
        self.assertEqual(nifty["oi"], "DATA GAP")
        self.assertEqual(nifty["direction"], "MIXED / UNCONFIRMED")

    def test_snapshot_is_persistent_and_duplicate_safe(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "breadth.db")
            result = analyze_component_breadth(
                "NIFTY", [{"name": f"S{i}", "change_percent": 1} for i in range(50)], 50
            )
            result["captured_at"] = "2026-09-03T11:15:00+05:30"
            self.assertTrue(db.save_index_component_breadth(result))
            self.assertFalse(db.save_index_component_breadth(result))
            rows = db.get_index_component_breadth("03-09-2026")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["state"], "BULLISH")
            db.close()


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from core.database_manager import Database
from engine.index_component_breadth import analyze_component_breadth, combine_component_breadth


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

import tempfile
import unittest
from pathlib import Path

from core.auto_universe_store import AutoUniverseStore
from engine.auto_universe_engine import rank_fno_universe
from services.auto_opportunity_service import _merge_candidates


class AutoUniverseEngineTests(unittest.TestCase):
    def test_ranking_filters_illiquid_and_orders_potential_candidates(self):
        universe = [
            {"underlying": "FAST", "symbol": "FAST-EQ", "token": "1"},
            {"underlying": "SLOW", "symbol": "SLOW-EQ", "token": "2"},
            {"underlying": "DRY", "symbol": "DRY-EQ", "token": "3"},
        ]
        quotes = [
            {"symbolToken": "1", "ltp": 1000, "tradeVolume": 1_000_000, "percentChange": 2.5, "high": 1010, "low": 950},
            {"symbolToken": "2", "ltp": 500, "tradeVolume": 100_000, "percentChange": 0.3, "high": 505, "low": 490},
            {"symbolToken": "3", "ltp": 100, "tradeVolume": 10, "percentChange": 5},
        ]
        ranked = rank_fno_universe(universe, quotes, 5)
        self.assertEqual([row["underlying"] for row in ranked], ["FAST", "SLOW"])
        self.assertGreater(ranked[0]["selection_score"], ranked[1]["selection_score"])
        self.assertIn("Auto-selected", ranked[0]["selection_reason"])

    def test_auto_cache_persists_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AutoUniverseStore(Path(directory) / "auto.json")
            store.save([{"underlying": "RELIANCE", "symbol": "RELIANCE-EQ", "token": "1"}])
            self.assertEqual(store.load(15)[0]["underlying"], "RELIANCE")

    def test_automatic_candidates_get_priority_without_duplicates(self):
        automatic = [{"underlying": "A"}, {"underlying": "B"}]
        manual = [{"underlying": "B"}, {"underlying": "C"}, {"underlying": "D"}]
        rows = _merge_candidates(automatic, manual, 3, "underlying")
        self.assertEqual([row["underlying"] for row in rows], ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from core.equity_watchlist_store import EquityWatchlistStore


class EquityWatchlistStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = EquityWatchlistStore(Path(self.temp.name) / "watchlist.json")

    def tearDown(self):
        self.temp.cleanup()

    def test_save_deduplicates_and_remove_persists(self):
        equity = {"company": "Reliance", "symbol": "RELIANCE-EQ", "token": "2885", "exchange": "NSE"}
        self.store.save_equity(equity)
        self.store.save_equity({**equity, "company": "Reliance Industries"})
        self.assertEqual(len(self.store.load()), 1)
        self.assertEqual(self.store.load()[0]["company"], "Reliance Industries")
        self.store.remove("RELIANCE-EQ")
        self.assertEqual(self.store.load(), [])

    def test_analysis_updates_saved_equity(self):
        self.store.save_equity({"company": "Infosys", "symbol": "INFY-EQ", "token": "1594", "exchange": "NSE"})
        rows = self.store.update_analysis("INFY-EQ", {"price": 1543.456, "score": 82, "plan_state": "WATCH LONG BREAKOUT"})
        self.assertEqual(rows[0]["last_price"], 1543.46)
        self.assertEqual(rows[0]["score"], 82)
        self.assertTrue(rows[0]["analyzed_at"])

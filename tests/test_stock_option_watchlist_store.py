import tempfile
import unittest
from pathlib import Path

from core.stock_option_watchlist_store import StockOptionWatchlistStore


class StockOptionWatchlistStoreTests(unittest.TestCase):
    def test_watchlist_persists_deduplicates_and_removes(self):
        with tempfile.TemporaryDirectory() as folder:
            store = StockOptionWatchlistStore(Path(folder) / "watch.json")
            equity = {"underlying": "RELIANCE", "symbol": "RELIANCE-EQ"}
            store.save(equity); store.save(equity)
            self.assertEqual(len(store.load()), 1)
            store.remove("RELIANCE")
            self.assertEqual(store.load(), [])

    def test_watchlist_is_rate_limit_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            store = StockOptionWatchlistStore(Path(folder) / "watch.json")
            for index in range(8): store.save({"underlying": f"STOCK{index}"})
            with self.assertRaisesRegex(ValueError, "limited to 8"):
                store.save({"underlying": "STOCK9"})

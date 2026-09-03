import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.database_manager import Database


class DatabaseConcurrencyTests(unittest.TestCase):
    def test_parallel_connections_do_not_repeat_or_lock_schema_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "shared.db"

            def connect_and_read(_):
                database = Database(path)
                count = database.cursor.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
                ).fetchone()[0]
                database.close()
                return count

            with ThreadPoolExecutor(max_workers=12) as pool:
                results = list(pool.map(connect_and_read, range(36)))
            self.assertTrue(all(count > 20 for count in results))


if __name__ == "__main__":
    unittest.main()

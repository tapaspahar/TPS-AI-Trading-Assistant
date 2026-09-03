import csv
import tempfile
import unittest
from pathlib import Path

from core.database_manager import Database
from services.nse_eod_import_service import NseEodImportService


class NseEodImportTests(unittest.TestCase):
    def test_udiff_fo_csv_is_saved_as_backfilled(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "BhavCopy_NSE_FO.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=("TradDt", "TckrSymb", "FinInstrmTp", "XpryDt", "StrkPric", "OptnTp", "OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol", "OpnIntrst"))
                writer.writeheader()
                writer.writerow({"TradDt": "2026-09-03", "TckrSymb": "NIFTY", "FinInstrmTp": "IDO", "XpryDt": "2026-09-03", "StrkPric": "25000", "OptnTp": "CE", "OpnPric": "50", "HghPric": "80", "LwPric": "30", "ClsPric": "70", "TtlTradgVol": "1000", "OpnIntrst": "2500"})
            db = Database(Path(folder) / "test.db")
            result = NseEodImportService(db).import_file(path)
            self.assertEqual(result["status"], "BACKFILLED")
            self.assertEqual(result["segment"], "FO")
            self.assertEqual(result["row_count"], 1)
            record = db.cursor.execute("SELECT * FROM nse_eod_records").fetchone()
            self.assertEqual(record["symbol"], "NIFTY")
            self.assertEqual(record["open_interest"], 2500)
            with self.assertRaisesRegex(ValueError, "pehle hi import"):
                NseEodImportService(db).import_file(path)
            db.close()


if __name__ == "__main__":
    unittest.main()

import csv
import json
import tempfile
import unittest
from pathlib import Path

from services.dhan_instrument_mapper import DhanInstrumentMapper


class DhanInstrumentMapperTests(unittest.TestCase):
    def test_option_token_maps_by_contract_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "angel_instruments.json").write_text(json.dumps([{
                "exch_seg": "NFO", "token": "777", "instrumenttype": "OPTIDX",
                "name": "NIFTY", "symbol": "NIFTY27AUG2625000PE", "expiry": "27AUG2026",
                "strike": "2500000",
            }]), encoding="utf-8")
            fields = [
                "EXCH_ID", "SEGMENT", "SECURITY_ID", "INSTRUMENT", "UNDERLYING_SYMBOL",
                "SYMBOL_NAME", "DISPLAY_NAME", "SM_EXPIRY_DATE", "STRIKE_PRICE", "OPTION_TYPE",
            ]
            with (path / "dhan_instruments.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow({
                    "EXCH_ID": "NSE", "SEGMENT": "D", "SECURITY_ID": "98765", "INSTRUMENT": "OPTIDX",
                    "UNDERLYING_SYMBOL": "NIFTY", "SYMBOL_NAME": "NIFTY-Aug2026-25000-PE",
                    "DISPLAY_NAME": "NIFTY 27 AUG 25000 PUT", "SM_EXPIRY_DATE": "2026-08-27",
                    "STRIKE_PRICE": "25000.00000", "OPTION_TYPE": "PE",
                })
            mapper = DhanInstrumentMapper(path)
            instrument = mapper.resolve("NFO", "777")
            self.assertEqual(instrument.security_id, "98765")
            self.assertEqual(instrument.exchange_segment, "NSE_FNO")
            self.assertEqual(instrument.instrument, "OPTIDX")

    def test_index_ids_do_not_require_master_download(self):
        instrument = DhanInstrumentMapper("unused").resolve("NSE", "99926000")
        self.assertEqual((instrument.security_id, instrument.exchange_segment), ("13", "IDX_I"))


if __name__ == "__main__":
    unittest.main()

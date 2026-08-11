import csv
import json
import tempfile
import unittest
from pathlib import Path

from services.paytm_money_instrument_mapper import PaytmMoneyInstrumentMapper


class PaytmMoneyInstrumentMapperTests(unittest.TestCase):
    def test_option_token_maps_by_contract_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "angel_instruments.json").write_text(json.dumps([{
                "exch_seg": "NFO", "token": "777", "instrumenttype": "OPTIDX",
                "name": "NIFTY", "symbol": "NIFTY27AUG2625000PE", "expiry": "27AUG2026",
                "strike": "2500000",
            }]), encoding="utf-8")
            fields = ["security_id", "symbol", "name", "series", "instrument_type", "segment",
                      "exchange", "expiry_date", "strike_price"]
            with (path / "paytm_money_security_master.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow({
                    "security_id": "98765", "symbol": "NIFTY-Aug2026-25000-PE",
                    "name": "NIFTY 27 AUG 25000 PUT", "instrument_type": "OPTIDX",
                    "segment": "D", "exchange": "NSE", "expiry_date": "2026-08-27 14:00:00",
                    "strike_price": "25000.0",
                })
            instrument = PaytmMoneyInstrumentMapper(path).resolve("NFO", "777")
            self.assertEqual(instrument.security_id, "98765")
            self.assertEqual((instrument.exchange, instrument.scrip_type), ("NSE", "OPTIDX"))

    def test_index_ids_do_not_require_master_download(self):
        instrument = PaytmMoneyInstrumentMapper("unused").resolve("NSE", "99926000")
        self.assertEqual((instrument.security_id, instrument.scrip_type), ("13", "INDEX"))
        self.assertEqual((instrument.instrument_type, instrument.underlying), ("I", "NIFTY 50"))


if __name__ == "__main__":
    unittest.main()

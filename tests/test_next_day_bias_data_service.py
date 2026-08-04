import unittest
from datetime import date
from unittest.mock import Mock

from services.next_day_bias_data_service import NextDayBiasDataService


def candles(base):
    return [{"time": f"2026-08-04T{9 + (i // 12):02d}:{(i % 12) * 5:02d}:00+05:30",
             "open": base + i, "high": base + i + 2, "low": base + i - 1,
             "close": base + i + 1, "volume": 100 + i} for i in range(60)]


class NextDayBiasDataServiceTests(unittest.TestCase):
    def test_loads_spot_future_and_nearest_expiry_chain(self):
        client, contracts = Mock(), Mock()
        client.get_recent_candles.side_effect = [candles(100), candles(102)]
        contracts.get_front_month_future.return_value = {"exchange": "NFO", "token": "f", "symbol": "NIFTYFUT"}
        contracts.get_contracts.return_value = [
            {"exchange": "NFO", "token": "ce", "symbol": "CE", "expiry": date(2026, 8, 6), "strike": 150, "option_type": "CE", "lot_size": 65},
            {"exchange": "NFO", "token": "pe", "symbol": "PE", "expiry": date(2026, 8, 6), "strike": 150, "option_type": "PE", "lot_size": 65},
        ]
        client.get_option_chain_quotes.return_value = [
            {"symbolToken": "ce", "opnInterest": 100, "tradeVolume": 20, "ltp": 8},
            {"symbolToken": "pe", "opnInterest": 120, "tradeVolume": 30, "ltp": 7},
        ]
        result = NextDayBiasDataService(client, contracts).load("NIFTY")
        self.assertEqual(result["future_symbol"], "NIFTYFUT")
        self.assertEqual(result["atm_call"], 8)
        self.assertEqual(result["atm_put"], 7)
        self.assertAlmostEqual(result["oi_pcr"], 1.2)
        self.assertEqual(client.get_recent_candles.call_count, 2)

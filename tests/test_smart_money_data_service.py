import unittest
from unittest.mock import Mock

from services.smart_money_data_service import SmartMoneyDataService


class SmartMoneyDataServiceTests(unittest.TestCase):
    def test_loads_completed_front_month_future_candles(self):
        client, contracts = Mock(), Mock()
        rows = [{"time": f"2026-08-04T{9 + (i // 12):02d}:{(i % 12)*5:02d}:00+05:30",
                 "open": 100+i, "high": 102+i, "low": 99+i, "close": 101+i, "volume": 100} for i in range(60)]
        client.get_recent_candles.return_value = rows
        contracts.get_front_month_future.return_value = {"exchange": "NFO", "token": "1", "symbol": "NIFTYFUT"}
        result = SmartMoneyDataService(client, contracts).load("NIFTY", "5m")
        self.assertEqual(result["future_symbol"], "NIFTYFUT")
        self.assertEqual(len(result["candles"]), 60)
        client.get_recent_candles.assert_called_once_with("NFO", "1", "FIVE_MINUTE", 5)


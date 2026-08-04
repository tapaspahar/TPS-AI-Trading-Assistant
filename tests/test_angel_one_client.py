import unittest
from unittest.mock import patch

from services.angel_one_client import AngelOneClient


class FakeCandleSession:
    def __init__(self):
        self.calls = 0

    def getCandleData(self, _params):
        self.calls += 1
        return {
            "status": True,
            "data": [["2026-08-03 09:15", 100, 102, 99, 101, 500]],
        }


class BusyThenSuccessfulCandleSession(FakeCandleSession):
    def getCandleData(self, params):
        self.calls += 1
        if self.calls < 3:
            return {"status": False, "message": "Something Went Wrong, Please Try After Sometime", "errorcode": "AB1004", "data": None}
        return {"status": True, "data": [["2026-08-03 09:15", 100, 102, 99, 101, 500]]}


class AngelOneClientTests(unittest.TestCase):
    def test_missing_credentials_are_rejected_before_network_access(self):
        with self.assertRaisesRegex(ValueError, "API Key"):
            AngelOneClient("", "", "", "").connect()

    def test_recent_candles_are_cached_for_a_short_period(self):
        client = AngelOneClient("key", "client", "pin", "secret")
        client.session = FakeCandleSession()

        first = client.get_recent_candles("NSE", "99926000")
        second = client.get_recent_candles("NSE", "99926000")

        self.assertEqual(first, second)
        self.assertEqual(client.session.calls, 1)

    @patch("services.angel_one_client.sleep")
    def test_ab1004_response_is_retried_three_times(self, sleep):
        client = AngelOneClient("key", "client", "pin", "secret")
        client.session = BusyThenSuccessfulCandleSession()
        client.CANDLE_REQUEST_INTERVAL_SECONDS = 0

        candles = client.get_recent_candles("NSE", "99926000")

        self.assertEqual(candles[0]["close"], 101)
        self.assertEqual(client.session.calls, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [15, 30])

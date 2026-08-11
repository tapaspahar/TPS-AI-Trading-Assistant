import unittest

from services.paytm_money_client import PaytmMoneyClient
from services.paytm_money_instrument_mapper import PaytmMoneyInstrument


class FakeResponse:
    def __init__(self, data, ok=True, status_code=200):
        self._data, self.ok, self.status_code = data, ok, status_code

    def json(self):
        return self._data


class FakeHttp:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return FakeResponse({"access_token": "access", "read_access_token": "read", "public_access_token": "public"})

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("/accounts/v1/user/details"):
            return FakeResponse({"name": "Tapas"})
        return FakeResponse({"data": [{"security_id": "13", "last_price": 24500, "ohlc": {"open": 24400, "high": 24600, "low": 24350, "close": 24450}, "volume": 100}]})


class FakeMapper:
    def resolve(self, exchange, token):
        return PaytmMoneyInstrument("13", "NSE", "I", "INDEX", "INDEX", "NIFTY", "NIFTY")


class PaytmMoneyClientTests(unittest.TestCase):
    def test_official_request_token_flow_generates_and_exports_tokens(self):
        http = FakeHttp()
        client = PaytmMoneyClient("key", "secret", "request", mapper=FakeMapper(), http=http)
        result = client.connect()
        self.assertTrue(result["connected"])
        self.assertEqual(client.export_credentials()["read_access_token"], "read")
        self.assertIn("apiKey=key", client.login_url())

    def test_live_quote_is_normalized_to_tps_contract(self):
        client = PaytmMoneyClient("key", "secret", access_token="access", mapper=FakeMapper(), http=FakeHttp())
        client.connect()
        quote = client.get_option_quote("NSE", "99926000")
        self.assertEqual(quote["token"], "99926000")
        self.assertEqual(quote["ltp"], 24500)
        self.assertEqual(quote["percentChange"], (24500 - 24450) / 24450 * 100)

    def test_minute_candles_aggregate_into_five_minute_bucket(self):
        candles = [
            {"time": f"2026-08-11T09:1{i}:00+05:30", "open": 100 + i, "high": 102 + i,
             "low": 99 + i, "close": 101 + i, "volume": 10} for i in range(5)
        ]
        result = PaytmMoneyClient._aggregate(candles, 5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["open"], 100)
        self.assertEqual(result[0]["close"], 105)
        self.assertEqual(result[0]["volume"], 50)


if __name__ == "__main__":
    unittest.main()

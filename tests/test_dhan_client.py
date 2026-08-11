import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from services.dhan_client import DhanClient
from services.dhan_instrument_mapper import DhanInstrument


class Response:
    def __init__(self, data, status=200):
        self.data, self.status_code, self.ok = data, status, status < 400

    def json(self):
        return self.data


class DhanClientTests(unittest.TestCase):
    @patch("pyotp.TOTP")
    def test_connect_generates_token_and_validates_profile(self, totp):
        totp.return_value.now.return_value = "123456"
        http = Mock()
        http.post.return_value = Response({
            "accessToken": "token",
            "expiryTime": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        })
        http.request.return_value = Response({"dhanClientName": "TEST USER"})
        client = DhanClient("1001", "123456", "SECRET", http=http)
        result = client.connect()
        self.assertTrue(result["connected"])
        self.assertEqual(client.access_token, "token")
        self.assertNotIn("token", result["message"])

    def test_quote_is_normalized_to_tps_contract(self):
        mapper = Mock()
        mapper.resolve.return_value = DhanInstrument("13", "IDX_I", "INDEX", "NIFTY")
        http = Mock()
        client = DhanClient("1001", "123456", "SECRET", mapper=mapper, http=http)
        client.access_token = client.auth_token = "token"
        client.token_expiry = datetime.now(timezone.utc) + timedelta(hours=2)
        client.session = http
        http.request.return_value = Response({
            "status": "success",
            "data": {"IDX_I": {"13": {
                "last_price": 25000, "volume": 12, "oi": 8,
                "ohlc": {"open": 24900, "high": 25100, "low": 24800, "close": 24950},
            }}},
        })
        quote = client.get_option_quote("NSE", "99926000")
        self.assertEqual(quote["symbolToken"], "99926000")
        self.assertEqual(quote["ltp"], 25000)

    @patch("pyotp.TOTP")
    def test_inactive_data_plan_is_reported_without_generating_second_token(self, totp):
        totp.return_value.now.return_value = "123456"
        http = Mock()
        http.post.return_value = Response({
            "accessToken": "token",
            "expiryTime": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        })
        http.request.return_value = Response({"dhanClientName": "TEST USER", "dataPlan": "Deactive"})
        client = DhanClient("1001", "123456", "SECRET", http=http)
        result = client.connect()
        self.assertIn("Data API plan is inactive", result["message"])
        with self.assertRaisesRegex(RuntimeError, "Data API plan is inactive"):
            client.get_market_quotes({"NSE": ["99926000"]})
        self.assertEqual(http.post.call_count, 1)

    def test_new_token_is_not_regenerated_for_immediate_unauthorized_data_response(self):
        mapper = Mock()
        mapper.resolve.return_value = DhanInstrument("13", "IDX_I", "INDEX", "NIFTY")
        http = Mock()
        http.request.return_value = Response({"message": "Data API subscription required"}, status=401)
        client = DhanClient("1001", "123456", "SECRET", mapper=mapper, http=http)
        client.access_token = client.auth_token = "token"
        client.token_expiry = datetime.now(timezone.utc) + timedelta(hours=2)
        client.token_generated_at = __import__("time").monotonic()
        with self.assertRaisesRegex(RuntimeError, "Data API subscription required"):
            client.get_market_quotes({"NSE": ["99926000"]})
        http.post.assert_not_called()


if __name__ == "__main__":
    unittest.main()

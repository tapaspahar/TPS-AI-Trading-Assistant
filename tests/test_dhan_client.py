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


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch

from services.broker_registry import BROKERS, create_broker_client


class BrokerRegistryTests(unittest.TestCase):
    def test_common_broker_profiles_are_available(self):
        self.assertTrue({"angel_one", "zerodha", "upstox", "dhan", "paytm_money", "fyers", "shoonya", "other"} <= set(BROKERS))

    def test_supported_brokers_explain_one_time_setup_and_link_official_page(self):
        for broker_id in ("angel_one", "dhan", "paytm_money"):
            self.assertTrue(BROKERS[broker_id].setup_url.startswith("https://"))
            self.assertIn("One-time", BROKERS[broker_id].login_summary)

    @patch("services.dhan_client.DhanClient")
    def test_dhan_profile_uses_automatic_token_adapter(self, client_type):
        result = create_broker_client("dhan", {"client_id": "123", "pin": "123456", "totp_secret": "secret"})
        self.assertIs(result, client_type.return_value)
        client_type.assert_called_once_with("123", "123456", "secret")

    @patch("services.angel_one_client.AngelOneClient")
    def test_angel_profile_uses_existing_working_adapter(self, client_type):
        result = create_broker_client("angel_one", {
            "api_key": "key", "client_code": "client", "mpin": "1234", "totp_secret": "secret",
        })
        self.assertIs(result, client_type.return_value)
        client_type.assert_called_once_with("key", "client", "1234", "secret")

    @patch("services.paytm_money_client.PaytmMoneyClient")
    def test_paytm_money_profile_accepts_first_login_request_token(self, client_type):
        credentials = {"api_key": "key", "api_secret": "secret", "request_token": "request"}
        result = create_broker_client("paytm_money", credentials)
        self.assertIs(result, client_type.return_value)
        client_type.assert_called_once_with("key", "secret", "request", "", "", "")


if __name__ == "__main__":
    unittest.main()

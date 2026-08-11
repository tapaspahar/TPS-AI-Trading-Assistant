import unittest
from unittest.mock import patch

from services.broker_registry import BROKERS, create_broker_client


class BrokerRegistryTests(unittest.TestCase):
    def test_common_broker_profiles_are_available(self):
        self.assertTrue({"angel_one", "zerodha", "upstox", "dhan", "fyers", "shoonya", "other"} <= set(BROKERS))

    def test_unimplemented_adapter_is_reported_instead_of_fake_connection(self):
        with self.assertRaisesRegex(RuntimeError, "adapter is not installed"):
            create_broker_client("dhan", {"client_id": "123", "access_token": "token"})

    @patch("services.angel_one_client.AngelOneClient")
    def test_angel_profile_uses_existing_working_adapter(self, client_type):
        result = create_broker_client("angel_one", {
            "api_key": "key", "client_code": "client", "mpin": "1234", "totp_secret": "secret",
        })
        self.assertIs(result, client_type.return_value)
        client_type.assert_called_once_with("key", "client", "1234", "secret")


if __name__ == "__main__":
    unittest.main()

import unittest

from services.credential_store import AngelOneCredentialStore


class FakeKeyring:
    def __init__(self):
        self.values = {}

    def set_password(self, service, account, value):
        self.values[(service, account)] = value

    def get_password(self, service, account):
        return self.values.get((service, account))

    def delete_password(self, service, account):
        self.values.pop((service, account), None)


class CredentialStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = AngelOneCredentialStore(FakeKeyring())
        self.values = {
            "api_key": "key", "client_code": "client", "mpin": "1234", "totp_secret": "secret",
        }

    def test_credentials_round_trip_without_plaintext_file(self):
        self.store.save(self.values)
        self.assertEqual(self.store.load(), self.values)

    def test_incomplete_credentials_are_rejected(self):
        with self.assertRaises(ValueError):
            self.store.save({"api_key": "key"})

    def test_clear_removes_saved_credentials(self):
        self.store.save(self.values)
        self.store.clear()
        self.assertEqual(self.store.load(), {})

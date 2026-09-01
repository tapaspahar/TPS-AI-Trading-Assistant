import unittest

from services.credential_store import AngelOneCredentialStore, BrokerCredentialStore


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

    def test_separate_broker_profiles_do_not_overwrite_each_other(self):
        backend = FakeKeyring()
        store = BrokerCredentialStore(backend)
        store.save("dhan", {"client_id": "DH123", "pin": "123456", "totp_secret": "secret"})
        store.save("angel_one", self.values)
        self.assertEqual(store.load("dhan"), {"client_id": "DH123", "pin": "123456", "totp_secret": "secret"})
        self.assertEqual(store.load("angel_one"), self.values)

    def test_broker_session_tokens_are_stored_separately(self):
        backend = FakeKeyring()
        store = BrokerCredentialStore(backend)
        session = {"api_key": "key", "auth_token": "jwt", "feed_token": "feed", "client_code": "A1"}
        store.save_session("angel_one", session)
        self.assertEqual(store.load_session("angel_one"), session)
        self.assertEqual(store.load("angel_one"), {})
        store.clear_session("angel_one")
        self.assertEqual(store.load_session("angel_one"), {})

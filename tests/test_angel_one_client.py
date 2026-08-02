import unittest

from services.angel_one_client import AngelOneClient


class AngelOneClientTests(unittest.TestCase):
    def test_missing_credentials_are_rejected_before_network_access(self):
        with self.assertRaisesRegex(ValueError, "API Key"):
            AngelOneClient("", "", "", "").connect()

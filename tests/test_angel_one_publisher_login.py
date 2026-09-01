import socket
import threading
import unittest
from urllib.parse import parse_qs, urlparse

import requests

from services.angel_one_publisher_login import AngelOnePublisherLogin


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class AngelOnePublisherLoginTests(unittest.TestCase):
    def test_authorization_url_uses_official_endpoint_redirect_and_csrf_state(self):
        login = AngelOnePublisherLogin("api-key")
        parsed = urlparse(login.authorization_url())
        query = parse_qs(parsed.query)
        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}{parsed.path}", login.LOGIN_URL)
        self.assertEqual(query["api_key"], ["api-key"])
        self.assertEqual(query["redirect_url"], [login.callback_url])
        self.assertEqual(query["state"], [login.state])

    def test_callback_returns_tokens_without_collecting_pin_or_totp(self):
        port = free_port()
        login = AngelOnePublisherLogin("api-key", f"http://127.0.0.1:{port}/angel-one/callback", 30)
        received, errors, event = [], [], threading.Event()
        login.start(lambda value: (received.append(value), event.set()), lambda value: (errors.append(value), event.set()))
        response = requests.get(
            login.callback_url,
            params={"auth_token": "jwt", "feed_token": "feed", "client_code": "A1", "state": login.state},
            timeout=5,
        )
        self.assertTrue(event.wait(3))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(received[0]["auth_token"], "jwt")
        self.assertEqual(received[0]["feed_token"], "feed")
        self.assertEqual(errors, [])
        self.assertNotIn("jwt", response.text)

    def test_wrong_state_fails_closed(self):
        port = free_port()
        login = AngelOnePublisherLogin("api-key", f"http://127.0.0.1:{port}/angel-one/callback", 30)
        errors, event = [], threading.Event()
        login.start(lambda _value: event.set(), lambda value: (errors.append(value), event.set()))
        requests.get(login.callback_url, params={"auth_token": "jwt", "feed_token": "feed", "state": "wrong"}, timeout=5)
        self.assertTrue(event.wait(3))
        self.assertIn("state", errors[0].lower())


if __name__ == "__main__":
    unittest.main()

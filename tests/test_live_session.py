import unittest

from services.live_session import LiveSession


class LiveSessionTests(unittest.TestCase):
    def test_session_is_disconnected_by_default(self):
        LiveSession.client = None
        self.assertFalse(LiveSession.connected())

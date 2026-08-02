import unittest
from services.angel_one_stream import AngelOneStream

class StreamTests(unittest.TestCase):
    def test_stream_requires_connection(self):
        client = type("Client", (), {"session": None})()
        with self.assertRaises(RuntimeError):
            AngelOneStream(client, lambda _tick: None).start(1, "26000")

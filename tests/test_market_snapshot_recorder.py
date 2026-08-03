import unittest

from services.market_snapshot_recorder import MarketSnapshotRecorder


class SnapshotRecorderInputTests(unittest.TestCase):
    def test_button_boolean_is_normalized_before_capture_work(self):
        recorder = MarketSnapshotRecorder(None)
        with self.assertRaisesRegex(ValueError, "support"):
            recorder.capture("INVALID", True)


import unittest
from datetime import datetime, timedelta

from engine.greeks_engine import calculate_greeks


class GreeksEngineTests(unittest.TestCase):
    def test_call_greeks_are_returned_for_valid_live_inputs(self):
        result = calculate_greeks(25000, 25000, 350, datetime.now() + timedelta(days=10), "CE")
        self.assertIsNotNone(result)
        self.assertGreater(result["iv"], 0)
        self.assertGreater(result["delta"], 0)

    def test_expired_contract_does_not_create_fake_greeks(self):
        self.assertIsNone(calculate_greeks(25000, 25000, 350, datetime.now() - timedelta(days=1), "CE"))

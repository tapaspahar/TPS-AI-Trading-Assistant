import unittest

from engine.level_proximity import classify_level_proximity


class LevelProximityTests(unittest.TestCase):
    def test_support_and_resistance_zones(self):
        self.assertEqual(classify_level_proximity(24998, 25000, 25200)["state"], "SUPPORT_ZONE")
        self.assertEqual(classify_level_proximity(25198, 25000, 25200)["state"], "RESISTANCE_ZONE")

    def test_crosses_and_mid_range(self):
        self.assertEqual(classify_level_proximity(24950, 25000, 25200)["state"], "BELOW_SUPPORT")
        self.assertEqual(classify_level_proximity(25250, 25000, 25200)["state"], "ABOVE_RESISTANCE")
        self.assertEqual(classify_level_proximity(25100, 25000, 25200)["state"], "MID_RANGE")

    def test_invalid_levels_are_unavailable(self):
        self.assertEqual(classify_level_proximity(25000, 25200, 25000)["state"], "UNAVAILABLE")

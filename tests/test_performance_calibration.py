import unittest

from engine.performance_calibration import calibrate_outcomes, wilson_lower_bound


class PerformanceCalibrationTests(unittest.TestCase):
    def test_empty_results_are_unproven(self):
        result = calibrate_outcomes([])
        self.assertEqual(result["validation_tier"], "UNPROVEN")
        self.assertEqual(result["win_rate"], 0)


    def test_negative_expectancy_is_rejected_even_with_high_model_claims(self):
        result = calibrate_outcomes([100, -200, -100])
        self.assertEqual(result["validation_tier"], "REJECTED BY EVIDENCE")
        self.assertLess(result["expectancy"], 0)


    def test_small_positive_sample_remains_paper_validation(self):
        result = calibrate_outcomes([100] * 8 + [-50] * 2)
        self.assertEqual(result["win_rate"], 80)
        self.assertEqual(result["validation_tier"], "PAPER VALIDATION")


    def test_sufficient_strong_sample_can_validate(self):
        result = calibrate_outcomes([100] * 27 + [-50] * 3)
        self.assertEqual(result["validation_tier"], "VALIDATED LOW-RISK")
        self.assertGreater(result["profit_factor"], 1.2)
        self.assertGreater(wilson_lower_bound(27, 30), 55)


if __name__ == "__main__":
    unittest.main()

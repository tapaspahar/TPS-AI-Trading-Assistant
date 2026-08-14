import unittest

from engine.regular_scalp_validation import evaluate_regular_scalp_validation


def strategy(room=50, blockers=None):
    confirmations = [
        {"name": "Market structure", "passed": True},
        {"name": "Price vs VWAP", "passed": True},
        {"name": "EMA 5/20/50 alignment", "passed": True},
        {"name": "Directional volume", "passed": True},
        {"name": "OI/PCR context", "passed": False},
    ]
    return {
        "candidate": "CE", "score": 80, "passed": 4, "total": 5,
        "hard_blockers": list(blockers or []),
        "side_evaluations": {"CE": {
            "score": 80, "passed": 4, "total": 5,
            "confirmations": confirmations,
            "hard_blockers": list(blockers or []),
            "entry_quality": {"timely": True},
        }},
        "zones": {"chart_resistance": 100 + room, "oi_resistance": 100 + room + 10},
    }


class RegularScalpValidationTests(unittest.TestCase):
    def setUp(self):
        self.settings = {
            "regular_scalp_validation_enabled": True,
            "regular_scalp_underlying_target_points": 20,
            "regular_scalp_premium_target_points": 20,
            "regular_scalp_min_score": 55,
            "regular_scalp_min_confirmations": 3,
        }
        self.environment = {"remaining_expected_range": 80}
        self.capture = {"close": 100}

    def test_ready_requires_room_range_timing_volume_and_no_hard_blocker(self):
        result = evaluate_regular_scalp_validation(
            strategy(), self.environment, self.capture, {"pcr_oi": 1.0}, self.settings,
        )
        self.assertEqual(result["status"], "SCALP READY")
        self.assertFalse(result["auto_capture_allowed"])
        self.assertEqual(result["underlying_target_points"], 20)
        self.assertEqual(result["option_premium_target_points"], 20)

    def test_nearby_resistance_is_watch_not_ready(self):
        result = evaluate_regular_scalp_validation(
            strategy(room=8), self.environment, self.capture, {}, self.settings,
        )
        self.assertEqual(result["status"], "SCALP WATCH")
        self.assertIn("Room for 20 index points", result["blockers"])

    def test_strict_blocker_is_never_bypassed(self):
        result = evaluate_regular_scalp_validation(
            strategy(blockers=["Rejection-wick / fake-breakout risk is active"]),
            self.environment, self.capture, {}, self.settings,
        )
        self.assertEqual(result["status"], "SCALP WATCH")
        self.assertFalse(result["auto_capture_allowed"])
        self.assertIn("Rejection-wick / fake-breakout risk is active", result["blockers"])

    def test_disabled_mode_records_disabled_without_signal(self):
        settings = {**self.settings, "regular_scalp_validation_enabled": False}
        result = evaluate_regular_scalp_validation(strategy(), self.environment, self.capture, {}, settings)
        self.assertEqual(result["status"], "DISABLED")
        self.assertFalse(result["auto_capture_allowed"])


if __name__ == "__main__":
    unittest.main()

import unittest

from services.auto_attempt_report import format_auto_paper_attempt


class AutoAttemptReportTests(unittest.TestCase):
    def test_environment_events_and_zone_evidence_render_together(self):
        result = {
            "status": "No paper trade",
            "attempt": {
                "checked_at": "2026-08-10T11:00:10+05:30",
                "candle_time": "2026-08-10T11:00:00+05:30",
                "candidate": "CE",
                "chart": {"strategy": {
                    "required": 5,
                    "minimum_score": 70,
                    "side_evaluations": {"CE": {"score": 80, "passed": 6, "total": 8,
                                                  "entry_quality": {"timely": False, "extension_points": 18,
                                                                    "extension_atr": 1.2, "maximum_extension_atr": 1.0,
                                                                    "rsi": 58, "fresh_pullback_reversal": True,
                                                                    "range_consumed_percent": 99.2,
                                                                    "remaining_expected_range": 1.38,
                                                                    "movement_state": "RANGE NEARLY USED"}},
                                         "PE": {"score": 20, "passed": 2, "total": 8}},
                    "zones": {"chart_support": 25000, "oi_support": 25000, "support_confluence": True,
                              "chart_resistance": 25200, "oi_resistance": 25200,
                              "resistance_confluence": True, "tolerance": 25},
                    "market_environment": {
                        "regime": "Normal volatility", "vix": 14, "vix_zone": "Normal", "atr_percent": .4,
                        "risk_multiplier": .8, "strike_preference": "ATM", "opening_range_low": 24950,
                        "opening_range_high": 25050, "previous_day_high": 25100, "previous_day_low": 24800,
                        "gap_state": "GAP UP", "gap_points": 20,
                        "event_risk": {"status": "EVENT CAUTION", "available": True, "nearby_events": [{
                            "name": "India CPI", "country": "India", "time": "2026-08-10T11:15:00+05:30",
                            "importance": 3, "forecast": "4.0%", "actual": None, "previous": "4.2%",
                            "minutes_from_now": 15,
                        }]},
                    },
                }},
            },
        }
        report = format_auto_paper_attempt(result)
        self.assertIn("Zone confluence", report)
        self.assertIn("Opening range", report)
        self.assertIn("forecast 4.0%", report)
        self.assertIn("Range used 99.2%", report)
        self.assertIn("Remaining 1.38 points", report)


if __name__ == "__main__":
    unittest.main()

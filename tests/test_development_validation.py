import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from core.database_manager import Database
from services.development_validation import (
    build_counterfactual_review, build_evaluation_health, build_evidence_diagnostics,
)


class DevelopmentValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "validation.db")

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def save_attempt(self, minute=20, score=82, passed=4, blockers=None):
        candle = f"2026-08-13T10:{minute:02d}:00+05:30"
        result = {
            "status": "No trade",
            "attempt": {
                "checked_at": f"2026-08-13T10:{minute + 5:02d}:05+05:30",
                "candle_time": candle, "candidate": "CE", "future_symbol": "NIFTY26AUGFUT",
                "capture": {"close": 25000, "volume": 1200, "volume_ratio": 1.7, "atr_14": 20,
                            "provider": "Test", "provider_data_age_seconds": 305},
                "chart": {"score": score, "decision": "CE WATCH", "provider": "Test",
                          "market_environment": {"regime": "NORMAL", "volume_threshold": 1.5},
                          "strategy": {"score": score, "passed": passed, "total": 6,
                                       "minimum_score": 90, "required": 5, "trade_ready": False,
                                       "hard_blockers": list(blockers or []),
                                       "side_evaluations": {"CE": {"score": score, "passed": passed,
                                                                        "total": 6, "hard_blockers": list(blockers or [])}},
                                       "zones": {"chart_support": 24950, "oi_support": 24950,
                                                 "chart_resistance": 25050, "oi_resistance": 25050,
                                                 "support_confluence": True, "resistance_confluence": True}}},
                "blockers": list(blockers or []),
            },
        }
        self.assertTrue(self.db.save_auto_trade_attempt("NIFTY", result))

    def test_heartbeat_backfill_records_explicit_gap_reasons(self):
        now = datetime.fromisoformat("2026-08-13T09:31:00+05:30")
        count = self.db.reconcile_evaluation_slots("NIFTY", now, enabled=True, connected=False)
        health = self.db.get_evaluation_health("13-08-2026", "NIFTY")
        self.assertEqual(count, 3)
        self.assertEqual(health["gap_reasons"], {"BROKER_DISCONNECTED": 3})
        self.assertEqual(health["coverage_percent"], 0.0)

    def test_counterfactual_never_bypasses_hard_blockers(self):
        self.save_attempt(20, 82, 4)
        self.save_attempt(30, 96, 6, ["EVENT RISK"])
        review = build_counterfactual_review(self.db, "13-08-2026", 80, 4)
        self.assertEqual(review["additional_candidate_count"], 1)
        self.assertEqual(review["hard_blocked_count"], 1)
        self.assertFalse(review["production_rules_changed"])
        self.assertEqual(len(self.db.get_counterfactual_reviews("13-08-2026")), 1)

    def test_health_and_evidence_expose_measured_not_invented_data(self):
        self.save_attempt(20, 82, 4)
        self.db.save_broker_telemetry({
            "provider": "Test", "operation": "candles", "started_at": "2026-08-13T10:25:00+05:30",
            "completed_at": "2026-08-13T10:25:01+05:30", "duration_ms": 1000,
            "outcome": "SUCCESS", "attempt_count": 1, "data_age_seconds": 301,
        })
        health = build_evaluation_health(self.db, "13-08-2026", "NIFTY")
        evidence = build_evidence_diagnostics(self.db, "13-08-2026")
        self.assertEqual(health["broker"]["success_rate"], 100.0)
        self.assertEqual(evidence["volume"]["reason_codes"], {"DIRECTIONAL_VOLUME_CONFIRMED": 1})
        self.assertEqual(evidence["levels"]["confluence"], {"BOTH": 1})
        self.assertEqual(evidence["outcomes"]["samples"], 0)


if __name__ == "__main__":
    unittest.main()

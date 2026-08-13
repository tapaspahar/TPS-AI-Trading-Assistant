import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from core.database_manager import Database
from services.self_development_decision import (
    ensure_completed_self_development_reviews,
    generate_and_save_self_development_review,
)


class SelfDevelopmentDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "test.db")

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def save_source(self, generated_at="2026-08-13T15:40:00+05:30"):
        self.db.save_post_market_tps_analysis({
            "trade_date": "13-08-2026", "generated_at": generated_at,
            "title": "Post Market Analysis of TPS", "summary_text": "Test evidence",
            "metrics": {
                "source_attempt_count": 20, "evaluated": 18, "captured": 0,
                "retry_or_skipped": 3, "coverage_percent": 72.0, "source_snapshot_count": 24,
                "score_and_checklist_pass": 2, "missing_ranges": ["10:00-10:15"],
                "failed_conditions": {"Directional volume": 8},
                "hard_blockers": {"Late entry / extended move": 4},
                "retry_reasons": {"Broker busy": 3}, "best_attempts": [{"score": 84}],
            },
        })

    def test_generates_prioritized_evidence_and_persists_review(self):
        self.save_source()
        review = generate_and_save_self_development_review(
            self.db, "13-08-2026", now=datetime(2026, 8, 13, 16, 0)
        )
        keys = {item["key"] for item in review["suggestions"]}
        self.assertIn("coverage_gap", keys)
        self.assertIn("zero_capture_calibration", keys)
        self.assertIn("entry_timing", keys)
        self.assertLess(review["health_score"], 100)
        self.assertIn("Automatic source-code modification disabled", review["summary_text"])
        self.assertIsNotNone(self.db.get_self_development_review("13-08-2026"))

    def test_reviewed_status_survives_source_refresh(self):
        self.save_source()
        generate_and_save_self_development_review(self.db, "13-08-2026")
        self.assertTrue(self.db.update_self_development_suggestion_status(
            "13-08-2026", "coverage_gap", "REVIEWED"
        ))
        self.save_source("2026-08-13T15:45:00+05:30")
        self.assertEqual(ensure_completed_self_development_reviews(self.db), ["13-08-2026"])
        row = self.db.get_self_development_review("13-08-2026")
        statuses = {item["key"]: item["status"] for item in json.loads(row["suggestions_json"])}
        self.assertEqual(statuses["coverage_gap"], "REVIEWED")

    def test_backfill_only_refreshes_when_source_changes(self):
        self.save_source()
        self.assertEqual(ensure_completed_self_development_reviews(self.db), ["13-08-2026"])
        self.assertEqual(ensure_completed_self_development_reviews(self.db), [])


if __name__ == "__main__":
    unittest.main()

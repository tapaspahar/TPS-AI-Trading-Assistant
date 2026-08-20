import tempfile
import unittest
from pathlib import Path

from core.database_manager import Database
from engine.evidence_model import EvidenceState, classify_attempt, evidence_state, unique_messages
from services.development_lifecycle import BUILD_ID, IMPLEMENTED_FEATURES, sync_feature_lifecycle


class EvidenceIntegrityTests(unittest.TestCase):
    def test_unknown_is_a_data_gap_and_not_a_false_strategy_condition(self):
        self.assertEqual(evidence_state(None), EvidenceState.UNKNOWN)
        self.assertEqual(evidence_state(False), EvidenceState.FALSE)
        self.assertEqual(evidence_state(True), EvidenceState.TRUE)
        self.assertEqual(classify_attempt(data_gaps=["Volume unavailable"]), "DATA GAP")
        self.assertEqual(classify_attempt(candidate=True), "CANDIDATE")
        self.assertEqual(classify_attempt(captured=True), "CAPTURED")

    def test_secondary_warnings_are_deduplicated_without_reordering(self):
        self.assertEqual(
            unique_messages(["Low volume", " low   volume ", "Near resistance"]),
            ["Low volume", "Near resistance"],
        )

    def test_review_stays_final_until_source_evidence_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Database(Path(folder) / "evidence.db")
            review = {
                "trade_date": "20-08-2026", "generated_at": "2026-08-20T11:00:00+05:30",
                "source_generated_at": "2026-08-20T10:55:00+05:30", "health_score": 80,
                "verdict": "MONITOR", "summary_text": "Same source evidence",
                "suggestions": [{"key": "coverage_gap", "status": "OPEN", "observation": "One gap"}],
                "feature_version": "1.4.1", "build_id": BUILD_ID,
            }
            try:
                database.save_self_development_review(review)
                self.assertTrue(database.finalize_self_development_review("20-08-2026"))
                database.save_self_development_review(review)
                saved = database.get_self_development_review("20-08-2026")
                self.assertEqual(saved["review_state"], "FINAL")
                self.assertEqual(saved["revision"], 1)

                changed = dict(review, source_generated_at="2026-08-20T11:05:00+05:30", summary_text="New evidence")
                database.save_self_development_review(changed)
                saved = database.get_self_development_review("20-08-2026")
                self.assertEqual(saved["review_state"], "DRAFT")
                self.assertEqual(saved["revision"], 2)
                self.assertEqual(len(database.get_self_development_review_revisions("20-08-2026")), 2)
            finally:
                database.close()

    def test_feature_lifecycle_never_claims_approval_without_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Database(Path(folder) / "lifecycle.db")
            try:
                rows = sync_feature_lifecycle(database)
                self.assertEqual(set(rows), IMPLEMENTED_FEATURES)
                self.assertTrue(all(row["build_id"] == BUILD_ID for row in rows.values()))
                self.assertTrue(all(row["lifecycle_state"] == "IMPLEMENTED IN BUILD" for row in rows.values()))
                self.assertTrue(all(row["approved_at"] is None for row in rows.values()))
            finally:
                database.close()


if __name__ == "__main__":
    unittest.main()

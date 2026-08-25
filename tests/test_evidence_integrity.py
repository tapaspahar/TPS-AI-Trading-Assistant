import tempfile
import unittest
import json
from pathlib import Path

from core.database_manager import Database
from engine.evidence_model import EvidenceState, classify_attempt, evidence_state, unique_messages
from services.development_lifecycle import (
    BUILD_ID, IMPLEMENTED_FEATURES, build_implementation_benefit_report, sync_feature_lifecycle,
)


class EvidenceIntegrityTests(unittest.TestCase):
    def test_attempt_persists_nested_strategy_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Database(Path(folder) / "evidence.db")
            try:
                result = {
                    "status": "evaluated",
                    "attempt": {
                        "checked_at": "2026-08-25T10:05:05+05:30",
                        "candle_time": "2026-08-25T10:00:00+05:30",
                        "future_symbol": "NIFTY25AUG26FUT",
                        "candidate": "CE",
                        "outcome": "STRATEGY REJECT",
                        "capture": {"volume": 100, "volume_ratio": 1.0},
                        "chart": {
                            "score": 50, "decision": "CE REJECTED",
                            "strategy": {
                                "passed": 1, "total": 2,
                                "evidence_states": {"ema": "TRUE", "volume": "UNKNOWN"},
                            },
                        },
                    },
                }
                self.assertTrue(database.save_auto_trade_attempt("NIFTY", result))
                row = database.get_auto_trade_attempts("25-08-2026", limit=10)[0]
                self.assertEqual(json.loads(row["evidence_states_json"]), {"ema": "TRUE", "volume": "UNKNOWN"})
                completeness = json.loads(row["source_completeness_json"])
                self.assertEqual((completeness["known"], completeness["total"]), (1, 2))
            finally:
                database.close()

    def test_legacy_details_evidence_is_backfilled_without_guessing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.db"
            database = Database(path)
            result = {
                "attempt": {
                    "checked_at": "2026-08-25T10:05:05+05:30",
                    "candle_time": "2026-08-25T10:00:00+05:30",
                    "candidate": "PE", "outcome": "STRATEGY REJECT",
                    "chart": {"strategy": {"evidence_states": {"vwap": "FALSE"}}},
                }
            }
            database.cursor.execute(
                """INSERT INTO auto_trade_attempts
                   (checked_at,candle_time,trade_date,symbol,outcome,status_text,details_json,evidence_states_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                ("2026-08-25T10:05:05+05:30", "2026-08-25T10:00:00+05:30", "25-08-2026", "NIFTY",
                 "STRATEGY REJECT", "legacy", json.dumps(result), "{}"),
            )
            database.connection.commit()
            database.close()
            reopened = Database(path)
            try:
                row = reopened.get_auto_trade_attempts("25-08-2026", limit=10)[0]
                self.assertEqual(json.loads(row["evidence_states_json"]), {"vwap": "FALSE"})
            finally:
                reopened.close()

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

    def test_implementation_report_does_not_claim_unproven_benefit(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Database(Path(folder) / "benefit.db")
            try:
                report = build_implementation_benefit_report(database, [{
                    "key": "evidence_integrity", "suggestion": "Three-state evidence add karein.",
                }])
                self.assertEqual(report[0]["build_status"], "IMPLEMENTED IN BUILD")
                self.assertEqual(report[0]["benefit_status"], "MEASUREMENT PENDING")
                self.assertIn("proof nahi", report[0]["benefit"])
            finally:
                database.close()

    def test_implementation_report_explains_unmapped_backlog(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Database(Path(folder) / "pending.db")
            try:
                report = build_implementation_benefit_report(database, [{
                    "key": "future_feature", "suggestion": "Future feature build karein.",
                }])
                self.assertEqual(report[0]["build_status"], "NOT IMPLEMENTED")
                self.assertIn("verified feature mapping nahi mila", report[0]["reason"])
                self.assertIn("Next release backlog", report[0]["next_action"])
            finally:
                database.close()


if __name__ == "__main__":
    unittest.main()

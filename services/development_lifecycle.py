"""Evidence-backed lifecycle for TPS development suggestions."""

from __future__ import annotations

from datetime import datetime

from core.database_manager import Database
from release_info import VERSION

BUILD_ID = "v1.4.1-20260820T1100IST"

IMPLEMENTED_FEATURES = {
    "evaluation_pipeline", "coverage_gap", "broker_reliability", "zero_capture_calibration",
    "entry_timing", "volume_evidence", "level_context", "outcome_quality", "sample_size",
    "overtrading_guard", "healthy_monitor",
}

REPLAY_VALIDATED_FEATURES = {"zero_capture_calibration"}
FORWARD_VALIDATED_FEATURES = {"evaluation_pipeline", "outcome_quality", "sample_size"}


def sync_feature_lifecycle(database: Database) -> dict:
    """Derive lifecycle from stored build and validation evidence; never claim approval."""
    existing = database.get_development_feature_evidence()
    validation = database.get_validation_report()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    for key in IMPLEMENTED_FEATURES:
        old = existing.get(key)
        lifecycle = str(old["lifecycle_state"]) if old else "IMPLEMENTED IN BUILD"
        replay_at = old["replay_passed_at"] if old else None
        forward_at = old["paper_forward_passed_at"] if old else None
        approved_at = old["approved_at"] if old else None
        replay_rows = database.cursor.execute(
            "SELECT COUNT(*) AS n FROM counterfactual_reviews WHERE json_extract(result_json, '$.outcome_summary.eligible_trials') > 0"
        ).fetchone()
        if key in REPLAY_VALIDATED_FEATURES and int(replay_rows["n"] or 0) and lifecycle == "IMPLEMENTED IN BUILD":
            lifecycle, replay_at = "REPLAY PASSED", replay_at or now
        if (
            key in FORWARD_VALIDATED_FEATURES
            and int(validation.get("samples") or 0) >= 30
            and int(validation.get("target_hits") or 0) + int(validation.get("stoploss_hits") or 0) >= 20
        ):
            lifecycle, forward_at = "PAPER FORWARD PASSED", forward_at or now
        if approved_at:
            lifecycle = "APPROVED"
        database.save_development_feature_evidence({
            "feature_key": key, "feature_version": VERSION, "build_id": BUILD_ID,
            "lifecycle_state": lifecycle, "replay_passed_at": replay_at,
            "paper_forward_passed_at": forward_at, "approved_at": approved_at,
            "evidence": {"validation_samples": int(validation.get("samples") or 0),
                         "decisive_outcomes": int(validation.get("target_hits") or 0) + int(validation.get("stoploss_hits") or 0)},
        })
    return database.get_development_feature_evidence()

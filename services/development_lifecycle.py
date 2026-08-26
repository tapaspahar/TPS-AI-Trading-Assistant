"""Evidence-backed lifecycle for TPS development suggestions."""

from __future__ import annotations

import json
from datetime import datetime

from core.database_manager import Database
from release_info import VERSION

BUILD_ID = "v1.4.6-20260826T1200IST"

IMPLEMENTED_FEATURES = {
    "evaluation_pipeline", "coverage_gap", "broker_reliability", "zero_capture_calibration",
    "entry_timing", "volume_evidence", "level_context", "outcome_quality", "sample_size",
    "overtrading_guard", "healthy_monitor", "option_strategy_management", "evidence_integrity",
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
        old_evidence = {}
        if old:
            try:
                old_evidence = json.loads(old["evidence_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                old_evidence = {}
        current_evidence = {
            "validation_samples": int(validation.get("samples") or 0),
            "target_hits": int(validation.get("target_hits") or 0),
            "stoploss_hits": int(validation.get("stoploss_hits") or 0),
            "decisive_outcomes": int(validation.get("target_hits") or 0) + int(validation.get("stoploss_hits") or 0),
            "accuracy": float(validation.get("accuracy") or 0),
        }
        evidence = dict(old_evidence)
        evidence.setdefault("baseline", current_evidence)
        evidence["latest"] = current_evidence
        evidence["last_measured_at"] = now
        database.save_development_feature_evidence({
            "feature_key": key,
            # Preserve the build that first introduced the feature instead of
            # relabelling old work as the newest release on every refresh.
            "feature_version": str(old["feature_version"]) if old else VERSION,
            "build_id": str(old["build_id"]) if old else BUILD_ID,
            "lifecycle_state": lifecycle, "replay_passed_at": replay_at,
            "paper_forward_passed_at": forward_at, "approved_at": approved_at,
            "evidence": evidence,
        })
    return database.get_development_feature_evidence()


def build_implementation_benefit_report(database: Database, suggestions: list[dict]) -> list[dict]:
    """Join saved suggestions to real build and validation evidence.

    A feature is never described as beneficial merely because code exists.
    Replay/paper-forward evidence is required before a positive benefit label.
    """
    lifecycle = sync_feature_lifecycle(database)
    report = []
    for suggestion in suggestions:
        key = str(suggestion.get("key") or "").strip()
        feature = lifecycle.get(key)
        if not feature:
            report.append({
                "key": key,
                "suggestion": str(suggestion.get("suggestion") or suggestion.get("observation") or "-"),
                "build_status": "NOT IMPLEMENTED",
                "release": "-",
                "benefit_status": "NOT MEASURED",
                "benefit": "Feature build nahi hua, isliye benefit measurement available nahi hai.",
                "reason": "Current build mein is suggestion ka verified feature mapping nahi mila.",
                "next_action": "Next release backlog: implementation, automated tests aur replay/paper validation add karein.",
            })
            continue
        try:
            evidence = json.loads(feature["evidence_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            evidence = {}
        latest = evidence.get("latest") or evidence
        state = str(feature["lifecycle_state"] or "IMPLEMENTED IN BUILD")
        samples = int(latest.get("validation_samples") or 0)
        decisive = int(latest.get("decisive_outcomes") or 0)
        accuracy = float(latest.get("accuracy") or 0)
        if state in {"PAPER FORWARD PASSED", "APPROVED"}:
            benefit_status = "PAPER BENEFIT OBSERVED" if state != "APPROVED" else "APPROVED BENEFIT"
            benefit = (
                f"Forward evidence: {samples} confirmed samples, {decisive} decisive outcomes, "
                f"target-vs-stop accuracy {accuracy:.1f}%."
            )
            reason = "-"
            next_action = "Fixed-risk monitoring continue karein; future samples se result refresh hoga."
        elif state == "REPLAY PASSED":
            benefit_status = "REPLAY BENEFIT OBSERVED"
            benefit = "Counterfactual replay pass hua; live/paper-forward benefit abhi prove hona baaki hai."
            reason = "Minimum paper-forward outcome sample abhi complete nahi hua."
            next_action = "Same rule ko unchanged rakhkar paper-forward sample complete karein."
        else:
            benefit_status = "MEASUREMENT PENDING"
            benefit = (
                f"Build available hai; current validation sample {samples}, decisive outcomes {decisive}. "
                "Abhi measurable fayda claim karne layak proof nahi hai."
            )
            reason = "Replay/paper-forward approval gate abhi pass nahi hua."
            next_action = "Next release se pehle replay chalayein aur paper-forward evidence collect karein."
        report.append({
            "key": key,
            "suggestion": str(suggestion.get("suggestion") or suggestion.get("observation") or "-"),
            "build_status": state,
            "release": f"v{feature['feature_version']} | {feature['build_id']}",
            "benefit_status": benefit_status,
            "benefit": benefit,
            "reason": reason,
            "next_action": next_action,
        })
    return report

"""Evidence-backed lifecycle for TPS development suggestions."""

from __future__ import annotations

import json
from datetime import datetime

from core.database_manager import Database
from release_info import VERSION

BUILD_ID = "v1.5.8-20260910T1305IST"

IMPLEMENTED_FEATURES = {
    "evaluation_pipeline", "coverage_gap", "broker_reliability", "zero_capture_calibration",
    "entry_timing", "volume_evidence", "level_context", "outcome_quality", "sample_size",
    "overtrading_guard", "healthy_monitor", "option_strategy_management", "evidence_integrity",
    "market_data_hub", "unique_paper_sampling", "execution_friction", "accuracy_lab",
}

REPLAY_VALIDATED_FEATURES = {"zero_capture_calibration"}
FORWARD_VALIDATED_FEATURES = {"evaluation_pipeline", "outcome_quality", "sample_size"}


def _json(value, fallback=None):
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {} if fallback is None else fallback


def _feature_measurement(database: Database, key: str, trade_date: str) -> dict:
    """Measure the evidence relevant to one feature instead of copying one global KPI."""
    source = database.get_post_market_tps_analysis(trade_date)
    metrics = _json(source["metrics_json"], {}) if source else {}
    attempts = int(metrics.get("source_attempt_count") or 0)
    evaluated = int(metrics.get("evaluated") or 0)
    captured = int(metrics.get("captured") or 0)
    retries = int(metrics.get("retry_or_skipped") or 0)
    failed = {str(k): int(v) for k, v in (metrics.get("failed_conditions") or {}).items()}
    blockers = {str(k): int(v) for k, v in (metrics.get("hard_blockers") or {}).items()}
    trades = database.get_trades_for_date(trade_date)
    target_hits = sum(str(row["outcome"] or "").upper() == "TARGET HIT" for row in trades)
    stop_hits = sum("STOP" in str(row["outcome"] or "").upper() for row in trades)
    decisive = target_hits + stop_hits
    result = {"attempts": attempts, "evaluated": evaluated, "captures": captured}
    if key in {"evaluation_pipeline", "coverage_gap", "healthy_monitor", "market_data_hub", "evidence_integrity"}:
        result.update(expected_slots=int(metrics.get("expected_slots") or 0),
                      observed_slots=int(metrics.get("observed_slots") or 0),
                      coverage_percent=float(metrics.get("coverage_percent") or 0),
                      evidence_coverage=float(metrics.get("structured_evidence_coverage") or 0))
    elif key == "broker_reliability":
        result.update(retries=retries, retry_rate=round(retries * 100 / max(attempts, 1), 1),
                      retry_reasons=metrics.get("retry_reasons") or {})
    elif key == "zero_capture_calibration":
        result.update(capture_rate=round(captured * 100 / max(evaluated, 1), 1),
                      score_and_checklist_pass=int(metrics.get("score_and_checklist_pass") or 0))
    elif key == "entry_timing":
        result["timing_blockers"] = sum(v for k, v in blockers.items() if any(x in k.lower() for x in ("late", "fresh", "pullback", "extended")))
    elif key == "volume_evidence":
        result["volume_failures"] = sum(v for k, v in {**failed, **blockers}.items() if "volume" in k.lower())
    elif key == "level_context":
        result["level_blockers"] = sum(v for k, v in {**failed, **blockers}.items() if "support" in k.lower() or "resistance" in k.lower())
    elif key in {"outcome_quality", "sample_size", "accuracy_lab", "execution_friction"}:
        outcome_rows = [row for row in database.get_paper_outcome_quality(500) if str(row.get("trade_date")) == trade_date]
        result.update(trades=len(trades), decisive_outcomes=decisive, target_hits=target_hits,
                      stop_hits=stop_hits, accuracy=round(target_hits * 100 / decisive, 1) if decisive else 0.0,
                      net_pnl=round(sum(float(row["pnl"] or 0) for row in trades), 2),
                      trade_ids=[int(row["id"]) for row in trades],
                      outcomes=[{
                          "trade_id": int(row["id"]), "outcome": str(row.get("outcome") or ""),
                          "pnl": float(row.get("pnl") or 0), "mfe": row.get("mfe"), "mae": row.get("mae"),
                          "setup": str(row.get("setup") or "Unclassified"),
                      } for row in outcome_rows],
                      release_cohorts=[dict(row) for row in database.get_rule_version_report()])
    else:
        result.update(data_gaps=retries, decisive_outcomes=decisive,
                      net_pnl=round(sum(float(row["pnl"] or 0) for row in trades), 2))
    return result


def _measurement_score(key: str, value: dict) -> float | None:
    if key in {"evaluation_pipeline", "coverage_gap", "healthy_monitor", "market_data_hub", "evidence_integrity"}:
        return float(value.get("coverage_percent") or 0)
    if key == "broker_reliability":
        return 100.0 - float(value.get("retry_rate") or 0)
    if key == "zero_capture_calibration":
        return float(value.get("capture_rate") or 0)
    if key in {"entry_timing", "volume_evidence", "level_context"}:
        field = {"entry_timing": "timing_blockers", "volume_evidence": "volume_failures", "level_context": "level_blockers"}[key]
        return 100.0 - min(100.0, float(value.get(field) or 0) * 5.0)
    if key in {"outcome_quality", "sample_size", "accuracy_lab", "execution_friction"}:
        return float(value.get("accuracy") or 0) if int(value.get("decisive_outcomes") or 0) else None
    return None


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
        forward_sample_ready = (
            key in FORWARD_VALIDATED_FEATURES
            and int(validation.get("samples") or 0) >= 30
            and int(validation.get("target_hits") or 0) + int(validation.get("stoploss_hits") or 0) >= 20
        )
        if forward_sample_ready:
            if float(validation.get("accuracy") or 0) >= 70.0:
                lifecycle, forward_at = "PAPER FORWARD PASSED", forward_at or now
            else:
                lifecycle, forward_at = "PAPER FORWARD FAILED", None
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


def build_implementation_benefit_report(
    database: Database, suggestions: list[dict], trade_date: str | None = None,
) -> list[dict]:
    """Join saved suggestions to real build and validation evidence.

    A feature is never described as beneficial merely because code exists.
    Replay/paper-forward evidence is required before a positive benefit label.
    """
    lifecycle = sync_feature_lifecycle(database)
    selected_date = trade_date or datetime.now().astimezone().strftime("%d-%m-%Y")
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
        measurement = _feature_measurement(database, key, selected_date)
        database.save_development_feature_measurement(key, VERSION, selected_date, measurement)
        history = database.get_development_feature_measurements(key)
        previous_row = next((row for row in reversed(history) if str(row["feature_version"]) != VERSION), None)
        previous = _json(previous_row["metrics_json"], {}) if previous_row else None
        current_score = _measurement_score(key, measurement)
        previous_score = _measurement_score(key, previous) if previous else None
        samples = int(latest.get("validation_samples") or 0)
        decisive = int(latest.get("decisive_outcomes") or 0)
        accuracy = float(latest.get("accuracy") or 0)
        if previous_score is not None and current_score is not None and current_score < previous_score - 0.5:
            benefit_status = "BUILT — NO BENEFIT OBSERVED"
            benefit = f"Feature-specific score {previous_score:.1f} se {current_score:.1f} hua; selected date par improvement nahi mila."
            reason = "Current release cohort baseline se weak hai."
            next_action = "Rule ko promote na karein; more samples collect karke rollback/rework review karein."
        elif previous_score is not None and current_score is not None and current_score > previous_score + 0.5:
            benefit_status = "IMPROVEMENT OBSERVED — VALIDATION PENDING"
            benefit = f"Feature-specific score {previous_score:.1f} se {current_score:.1f} improve hua."
            reason = "Single-date improvement final proof nahi hai."
            next_action = "Same release ke minimum 3 sessions aur outcome cohort se confirm karein."
        elif state in {"PAPER FORWARD PASSED", "APPROVED"}:
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
            "measurement": json.dumps(measurement, ensure_ascii=False, default=str),
            "comparison": json.dumps(previous or {}, ensure_ascii=False, default=str),
        })
    return report

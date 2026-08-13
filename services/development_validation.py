"""Evidence-only Release 1.3 validation tools for self-development reviews.

Nothing in this module changes production entry rules.  It compares saved
completed-candle evidence, exposes data gaps and measures outcome quality.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime

from core.database_manager import Database


def _json(value, fallback=None):
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {} if fallback is None else fallback


def _attempt_facts(row) -> dict:
    payload = _json(row["details_json"], {})
    attempt = payload.get("attempt") or {}
    chart = attempt.get("chart") or {}
    strategy = chart.get("strategy") or {}
    candidate = str(attempt.get("candidate") or row["candidate"] or "").upper()
    side = (strategy.get("side_evaluations") or {}).get(candidate) or {}
    passed = int(side.get("passed") if side.get("passed") is not None else strategy.get("passed") or row["confirmations_passed"] or 0)
    total = int(side.get("total") if side.get("total") is not None else strategy.get("total") or row["confirmations_total"] or 0)
    score = int(side.get("score") if side.get("score") is not None else strategy.get("score") or row["score"] or 0)
    minimum = int(strategy.get("minimum_score") or 95)
    required = int(strategy.get("required") or 5)
    hard_blockers = list(side.get("hard_blockers") or strategy.get("hard_blockers") or [])
    return {
        "payload": payload, "attempt": attempt, "chart": chart, "strategy": strategy,
        "candidate": candidate, "passed": passed, "total": total, "score": score,
        "current_score": minimum, "current_matches": required, "hard_blockers": hard_blockers,
        "current_eligible": bool(strategy.get("trade_ready")) and not hard_blockers,
    }


def build_counterfactual_review(
    database: Database, trade_date: str, proposed_score: int, proposed_matches: int,
    *, current_score: int | None = None, current_matches: int | None = None,
) -> dict:
    """Compare saved candles with a proposed threshold without look-ahead or rule mutation."""
    rows = database.get_auto_trade_attempts(trade_date=trade_date, limit=1000)
    facts = [_attempt_facts(row) for row in rows if row["outcome"] == "NO TRADE"]
    configured_score = int(current_score if current_score is not None else max((item["current_score"] for item in facts), default=95))
    configured_matches = int(current_matches if current_matches is not None else max((item["current_matches"] for item in facts), default=5))
    proposed_score = max(0, min(100, int(proposed_score)))
    proposed_matches = max(1, min(10, int(proposed_matches)))
    current_candidates = proposed_candidates = 0
    newly_eligible = []
    blocked_by_safety = 0
    for row, item in zip([row for row in rows if row["outcome"] == "NO TRADE"], facts):
        current_ok = item["score"] >= configured_score and item["passed"] >= configured_matches and not item["hard_blockers"]
        proposed_ok = item["score"] >= proposed_score and item["passed"] >= proposed_matches and not item["hard_blockers"]
        current_candidates += int(current_ok)
        proposed_candidates += int(proposed_ok)
        blocked_by_safety += int(item["score"] >= proposed_score and item["passed"] >= proposed_matches and bool(item["hard_blockers"]))
        if proposed_ok and not current_ok:
            newly_eligible.append({
                "candle_time": row["candle_time"], "candidate": item["candidate"],
                "score": item["score"], "matches": f"{item['passed']}/{item['total']}",
                "hard_blockers": item["hard_blockers"],
            })
    review = {
        "trade_date": trade_date, "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "current_score": configured_score, "proposed_score": proposed_score,
        "current_matches": configured_matches, "proposed_matches": proposed_matches,
        "attempts": len(facts), "current_candidate_count": current_candidates,
        "proposed_candidate_count": proposed_candidates, "additional_candidate_count": len(newly_eligible),
        "hard_blocked_count": blocked_by_safety, "newly_eligible": newly_eligible,
        "production_rules_changed": False,
        "approval_status": "EVIDENCE PENDING" if len(facts) < 30 else "READY FOR OUTCOME REVIEW",
        "warning": "Threshold comparison only. Hard blockers remain enforced and this result cannot place a trade.",
    }
    review["id"] = database.save_counterfactual_review(review)
    return review


def build_evaluation_health(database: Database, trade_date: str, symbol: str = "ALL") -> dict:
    slots = database.get_evaluation_health(trade_date, symbol)
    broker = database.get_broker_health(limit=1000)
    attempts = database.get_auto_trade_attempts(trade_date=trade_date, limit=1000)
    retry_count = sum(str(row["outcome"]) in {"RETRY PENDING", "SKIPPED"} for row in attempts)
    exception_reasons = Counter(str(row["status_text"]) for row in attempts if str(row["outcome"]) in {"RETRY PENDING", "SKIPPED"})
    validation = database.get_validation_report()
    flat = {
        "trade_date": trade_date, "symbol": str(symbol).upper(),
        "heartbeat_status": "HEALTHY" if slots["coverage_percent"] >= 95 else "GAPS DETECTED" if slots["expected_slots"] else "NO HEARTBEAT",
        "coverage_percent": slots["coverage_percent"], "evaluated_slots": slots["evaluated_slots"],
        "expected_slots": slots["expected_slots"], "gap_slots": slots["gap_slots"],
        "gap_reasons": slots["gap_reasons"], "retry_count": retry_count,
        "exception_reasons": dict(exception_reasons), "broker": broker, "validation": validation,
        "coverage_approved": slots["coverage_percent"] >= 95,
        "sample_approved": int(validation.get("samples") or 0) >= 30 and int(validation.get("target_hits") or 0) + int(validation.get("stoploss_hits") or 0) >= 20,
    }
    return {"evaluation": slots, "broker": broker, "validation": validation, **flat}


def build_evidence_diagnostics(database: Database, trade_date: str) -> dict:
    attempts = database.get_auto_trade_attempts(trade_date=trade_date, limit=1000)
    volume = Counter()
    regimes = defaultdict(lambda: {"evaluations": 0, "captures": 0, "volume_failures": 0})
    level = Counter()
    distances = []
    ages = []
    for row in attempts:
        reason = str(row["volume_reason_code"] or "UNCLASSIFIED")
        volume[reason] += 1
        facts = _attempt_facts(row)
        regime = str((facts["chart"].get("market_environment") or {}).get("regime") or "UNKNOWN")
        regimes[regime]["evaluations"] += 1
        regimes[regime]["captures"] += int(str(row["outcome"]) == "TRADE CAPTURED")
        regimes[regime]["volume_failures"] += int(reason != "DIRECTIONAL_VOLUME_CONFIRMED")
        level[str(row["level_confluence"] or "UNAVAILABLE")] += 1
        if row["level_distance_atr"] is not None:
            distances.append(float(row["level_distance_atr"]))
        if row["level_age_seconds"] is not None:
            ages.append(int(row["level_age_seconds"]))
    outcome_rows = database.get_paper_outcome_quality(limit=500)
    def average(field):
        values = [float(row[field]) for row in outcome_rows if row[field] is not None]
        return round(sum(values) / len(values), 3) if values else None
    outcomes = {
        "samples": len(outcome_rows),
        "decisive_samples": sum(str(row["outcome"]).upper() in {"TARGET HIT", "STOPLOSS HIT", "STOP LOSS HIT"} for row in outcome_rows),
        "average_entry_lateness_seconds": average("entry_lateness_seconds"),
        "average_premium_spread_percent": average("premium_spread_percent"),
        "average_mae": average("mae"), "average_mfe": average("mfe"),
    }
    return {
        "volume": {"reason_codes": dict(volume), "regimes": dict(regimes)},
        "levels": {"confluence": dict(level),
                   "average_distance_atr": round(sum(distances) / len(distances), 3) if distances else None,
                   "average_age_seconds": round(sum(ages) / len(ages), 1) if ages else None,
                   "maximum_age_seconds": max(ages) if ages else None},
        "outcomes": outcomes,
    }

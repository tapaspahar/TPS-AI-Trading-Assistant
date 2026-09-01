"""Evidence-first reliability metrics for the TPS operator cockpit.

The module only summarizes saved observations.  It never promotes a model
score into a profit claim and never submits an order.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime

from engine.performance_calibration import calibrate_outcomes


def _json(value, fallback):
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def data_quality_gate(*, connected: bool, market_state: str, hub_health: dict, broker_health: dict) -> dict:
    """Return a common PASS/WAIT/BLOCK watermark for every execution surface."""
    reasons, warnings = [], []
    state = str(market_state or "UNKNOWN").upper()
    if state != "OPEN":
        reasons.append(f"Market session {state}")
    if not connected:
        reasons.append("Broker/data session disconnected")
    if str(hub_health.get("state") or "WAITING").upper() == "DEGRADED":
        reasons.append(f"Market Data Hub degraded: {hub_health.get('last_error') or 'provider failure'}")
    if not hub_health.get("last_success_at"):
        reasons.append("No verified live snapshot received")
    requests = int(broker_health.get("requests") or 0)
    success = float(broker_health.get("success_rate") or 0)
    if requests and success < 70:
        reasons.append(f"Broker request success only {success:.1f}%")
    elif requests and success < 90:
        warnings.append(f"Broker request success {success:.1f}%")
    if reasons:
        status = "BLOCK" if state == "OPEN" else "WAIT"
    else:
        status = "PASS"
    return {"status": status, "reasons": reasons, "warnings": warnings, "order_ready": status == "PASS"}


def trade_timeline(database, trade_date: str, limit: int = 250) -> list[dict]:
    rows = database.get_auto_trade_attempts(trade_date, limit)
    timeline = []
    for row in reversed(rows):
        details = _json(row["details_json"], {})
        attempt = details.get("attempt") or {}
        chart = attempt.get("chart") or {}
        timeline.append({
            "time": row["checked_at"], "candle": row["candle_time"], "symbol": row["symbol"],
            "side": row["candidate"] or "-", "stage": row["timing_stage"] or row["outcome"],
            "score": row["score"], "outcome": row["outcome"],
            "reason": row["primary_blocker"] or chart.get("primary_blocker") or row["status_text"],
            "trade_id": row["trade_id"], "delay": row["timing_delay_seconds"],
        })
    return timeline


def missed_opportunities(database, trade_date: str, limit: int = 100) -> list[dict]:
    """Rank rejected completed-candle observations for counterfactual review."""
    rows = database.get_auto_trade_attempts(trade_date, limit * 5)
    result = []
    for row in rows:
        if str(row["outcome"]).upper() not in {"STRATEGY REJECT", "SAFETY BLOCK", "CANDIDATE"}:
            continue
        details = _json(row["details_json"], {})
        attempt = details.get("attempt") or {}
        chart = attempt.get("chart") or {}
        score = int(row["score"] or 0)
        passed = int(row["confirmations_passed"] or 0)
        total = int(row["confirmations_total"] or 0)
        # A shortlist is evidence for replay, never permission to loosen a lock.
        priority = score + (10 * passed / max(total, 1))
        result.append({
            "attempt_id": int(row["id"]), "time": row["candle_time"] or row["checked_at"],
            "symbol": row["symbol"], "side": row["candidate"] or "-", "score": score,
            "checks": f"{passed}/{total}", "outcome": row["outcome"],
            "blocker": row["primary_blocker"] or chart.get("primary_blocker") or "No primary blocker saved",
            "priority": round(priority, 1),
            "replay_status": "REPLAY REQUIRED — target/stop order not inferred from same candle",
        })
    return sorted(result, key=lambda item: item["priority"], reverse=True)[:limit]


def strategy_matrix(database) -> list[dict]:
    rows = database.cursor.execute(
        """SELECT strategy_name, family, COALESCE(market_regime,'UNKNOWN') regime,
                  COALESCE(expiry,'UNKNOWN') expiry, realized_pnl, trade_date
           FROM strategy_trades WHERE status='CLOSED' ORDER BY trade_date, id"""
    ).fetchall()
    grouped = defaultdict(list)
    days = defaultdict(set)
    for row in rows:
        key = (str(row["strategy_name"]), str(row["family"]), str(row["regime"]))
        grouped[key].append(float(row["realized_pnl"] or 0))
        days[key].add(str(row["trade_date"]))
    matrix = []
    for key, pnls in grouped.items():
        metrics = calibrate_outcomes(pnls)
        matrix.append({
            "strategy": key[0], "family": key[1], "regime": key[2],
            "samples": metrics["samples"], "independent_days": len(days[key]),
            "win_rate": metrics["win_rate"], "lower_bound": metrics["wilson_lower_bound"],
            "expectancy": metrics["expectancy"], "profit_factor": metrics["profit_factor"],
            "drawdown": metrics["max_drawdown"], "tier": metrics["validation_tier"],
        })
    return sorted(matrix, key=lambda item: (item["lower_bound"], item["samples"], item["expectancy"]), reverse=True)


def execution_quality(database, limit: int = 500) -> dict:
    rows = database.cursor.execute(
        "SELECT * FROM execution_audit ORDER BY id DESC LIMIT ?", (max(1, int(limit)),)
    ).fetchall()
    real = [row for row in rows if str(row["status"]).upper() not in {"PAPER_PLAN", "BLOCKED", "REJECTED"}]
    filled = [row for row in real if str(row["status"]).upper() in {"COMPLETE", "COMPLETED", "FILLED", "TRADED"}]
    with_pnl = [float(row["realized_pnl"] or 0) for row in filled]
    measured = [float(row["slippage_amount"]) for row in filled if row["slippage_amount"] is not None]
    return {
        "intents": len(rows), "real_submissions": len(real), "verified_fills": len(filled),
        "fill_coverage": round(100 * len(filled) / len(real), 1) if real else 0.0,
        "net_realized_pnl": round(sum(with_pnl), 2),
        "average_slippage": round(sum(measured) / len(measured), 2) if measured else None,
        "slippage_status": "MEASURED" if measured else "DATA GAP" if filled else "WAITING",
        "slippage_reason": "Calculated from reconciled broker average fill versus requested limit." if measured else "Broker average fill price is not available yet; TPS will not invent slippage.",
    }


def shadow_eligibility(database) -> dict:
    paper = database.get_paper_outcome_quality(5000)
    metrics = calibrate_outcomes([row.get("pnl") for row in paper])
    eligible = (
        metrics["samples"] >= 30 and metrics["expectancy"] > 0
        and metrics["profit_factor"] >= 1.2 and metrics["wilson_lower_bound"] >= 55
    )
    return {**metrics, "eligible": eligible, "state": "ELIGIBLE FOR REAL REVIEW" if eligible else "SHADOW / PAPER ONLY"}

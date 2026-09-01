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


def broker_freshness(database, limit: int = 500, stale_seconds: int = 300) -> dict:
    """Keep transport success separate from usable, fresh market evidence."""
    rows = database.cursor.execute(
        "SELECT * FROM broker_request_telemetry ORDER BY id DESC LIMIT ?", (max(1, min(int(limit), 5000)),)
    ).fetchall()
    success = [row for row in rows if str(row["outcome"]).upper() == "SUCCESS"]
    known = [int(row["data_age_seconds"]) for row in success if row["data_age_seconds"] is not None]
    fresh = [age for age in known if age <= int(stale_seconds)]
    stale = [age for age in known if age > int(stale_seconds)]
    durations = sorted(int(row["duration_ms"] or 0) for row in rows)
    percentile = lambda values, ratio: values[min(len(values) - 1, round((len(values) - 1) * ratio))] if values else None
    return {
        "requests": len(rows), "provider_success": len(success), "timestamped_success": len(known),
        "fresh_success": len(fresh), "stale_success": len(stale),
        "freshness_rate": round(100 * len(fresh) / len(known), 1) if known else 0.0,
        "stale_threshold_seconds": int(stale_seconds), "p50_latency_ms": percentile(durations, .50),
        "p95_latency_ms": percentile(durations, .95), "maximum_data_age_seconds": max(known) if known else None,
        "status": "PASS" if known and not stale else "DEGRADED" if known else "DATA GAP",
    }


def score_calibration(database, bucket_size: int = 10) -> list[dict]:
    """Observed outcome by saved score band; a score is never called probability."""
    rows = database.cursor.execute(
        """SELECT a.score, t.pnl FROM auto_trade_attempts a JOIN trades t ON t.id=a.trade_id
           WHERE a.trade_id IS NOT NULL AND t.status='CLOSED' AND a.score IS NOT NULL"""
    ).fetchall()
    grouped = defaultdict(list)
    for row in rows:
        lower = min(90, max(0, int(float(row["score"] or 0)) // bucket_size * bucket_size))
        grouped[lower].append(float(row["pnl"] or 0))
    result = []
    for lower, pnls in sorted(grouped.items()):
        metrics = calibrate_outcomes(pnls)
        result.append({
            "band": f"{lower}-{lower + bucket_size - 1 if lower < 90 else 100}", **metrics,
            "confidence": "VALIDATED" if metrics["samples"] >= 30 else "LEARNING" if metrics["samples"] >= 10 else "LOW SAMPLE",
        })
    return result


def strategy_portfolio_risk(database, trade_date: str | None = None) -> dict:
    """Aggregate correlated strategy families instead of treating every strike variation as independent."""
    where, values = "", []
    if trade_date:
        where, values = "WHERE trade_date=?", [trade_date]
    rows = database.cursor.execute(
        f"SELECT * FROM strategy_trades {where} ORDER BY id", values
    ).fetchall()
    groups = defaultdict(list)
    for row in rows:
        key = (str(row["family"] or "UNKNOWN"), str(row["bias"] or "UNKNOWN"))
        groups[key].append(row)
    exposure = []
    for (family, bias), items in groups.items():
        closed = [row for row in items if str(row["status"]).upper() == "CLOSED"]
        pnls = [float(row["realized_pnl"] or 0) for row in closed]
        exposure.append({
            "family": family, "bias": bias, "variants": len(items), "closed": len(closed),
            "combined_pnl": round(sum(pnls), 2),
            "maximum_defined_loss": round(sum(abs(float(row["max_loss"] or 0)) for row in items), 2),
            "capital_required": round(sum(max(0, float(row["capital_required"] or 0)) for row in items), 2),
            "metrics": calibrate_outcomes(pnls),
        })
    total_risk = sum(item["maximum_defined_loss"] for item in exposure)
    largest = max((item["maximum_defined_loss"] for item in exposure), default=0.0)
    return {
        "groups": sorted(exposure, key=lambda item: (item["combined_pnl"], -item["maximum_defined_loss"]), reverse=True),
        "variants": len(rows), "total_defined_loss": round(total_risk, 2),
        "largest_group_share": round(100 * largest / total_risk, 1) if total_risk else 0.0,
        "concentration_status": "HIGH" if total_risk and largest / total_risk > .50 else "BOUNDED",
    }


def automatic_counterfactual_replay(database, trade_date: str, limit: int = 10) -> list[dict]:
    """Replay one rejected setup against later saved candles without look-ahead at entry."""
    rows = list(reversed(database.get_auto_trade_attempts(trade_date, 5000)))
    captures = []
    for row in rows:
        details = _json(row["details_json"], {})
        capture = ((details.get("attempt") or {}).get("capture") or {})
        try:
            captures.append((row, float(capture["high"]), float(capture["low"]), float(capture["close"]), float(capture.get("atr_14") or 0)))
        except (KeyError, TypeError, ValueError):
            captures.append((row, None, None, None, None))
    candidates = missed_opportunities(database, trade_date, limit * 5)
    by_id = {int(row["id"]): index for index, (row, *_rest) in enumerate(captures)}
    result = []
    for item in candidates:
        index = by_id.get(item["attempt_id"])
        if index is None or captures[index][3] is None:
            continue
        row, _high, _low, entry, atr = captures[index]
        future = [value for value in captures[index + 1:index + 7] if value[1] is not None]
        if not future or not atr:
            continue
        side = str(row["candidate"] or "").upper(); direction = 1 if side == "CE" else -1
        target = entry + direction * atr; stop = entry - direction * atr
        mfe = max(direction * (value[1] - entry) if direction > 0 else direction * (value[2] - entry) for value in future)
        mae = min(direction * (value[2] - entry) if direction > 0 else direction * (value[1] - entry) for value in future)
        target_index = next((i for i, value in enumerate(future) if value[1] >= target), None) if direction > 0 else next((i for i, value in enumerate(future) if value[2] <= target), None)
        stop_index = next((i for i, value in enumerate(future) if value[2] <= stop), None) if direction > 0 else next((i for i, value in enumerate(future) if value[1] >= stop), None)
        outcome = "TARGET BEFORE STOP" if target_index is not None and (stop_index is None or target_index < stop_index) else "STOP BEFORE TARGET" if stop_index is not None else "UNRESOLVED"
        result.append({**item, "mfe_points": round(max(0, mfe), 2), "mae_points": round(abs(min(0, mae)), 2),
                       "replay_outcome": outcome, "replay_status": f"{outcome} | one primary blocker held out"})
    return result[:limit]

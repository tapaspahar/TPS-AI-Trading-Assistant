"""Explainable trade-outcome fingerprints and historical analog matching."""

from __future__ import annotations

import json


def _plan(value) -> dict:
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}


def build_trade_fingerprint(trade: dict, plan_value=None) -> dict:
    """Build a compact, deterministic fingerprint from evidence saved at entry."""
    plan = _plan(plan_value)
    chart = plan.get("chart") or plan.get("decision_audit") or {}
    strategy = chart.get("strategy") or plan.get("strategy") or {}
    environment = chart.get("market_environment") or plan.get("market_environment") or {}
    evidence = plan.get("evidence_context") or {}
    candidate = str(plan.get("option_type") or trade.get("option_type") or strategy.get("candidate") or "-").upper()
    confirmations = strategy.get("selected_confirmations") or strategy.get("confirmations") or []
    passed = sorted(str(item.get("name")) for item in confirmations if item.get("passed"))
    return {
        "symbol": str(plan.get("underlying") or trade.get("symbol") or "").upper(),
        "side": candidate,
        "regime": str(environment.get("regime") or "UNKNOWN").upper(),
        "vix_zone": str(environment.get("vix_zone") or "UNKNOWN").upper(),
        "direction": str(strategy.get("direction") or chart.get("direction") or "UNKNOWN").upper(),
        "score_band": int((float(strategy.get("score") or trade.get("ai_score") or 0) // 10) * 10),
        "passed": passed,
        "volume_band": "HEAVY" if float(evidence.get("volume_ratio") or 0) >= 1.5 else "NORMAL" if float(evidence.get("volume_ratio") or 0) >= 0.8 else "LOW",
    }


def similarity_score(current: dict, historical: dict) -> float:
    """Return explainable condition similarity, never a profit probability."""
    weights = {"symbol": 18, "side": 18, "regime": 16, "direction": 16, "vix_zone": 8, "volume_band": 8}
    score = sum(weight for key, weight in weights.items() if current.get(key) == historical.get(key))
    score += max(0, 8 - abs(int(current.get("score_band", 0)) - int(historical.get("score_band", 0))) / 10 * 2)
    a, b = set(current.get("passed") or []), set(historical.get("passed") or [])
    score += 8 * (len(a & b) / len(a | b)) if a or b else 8
    return round(min(100.0, score), 1)


def build_outcome_review(trade: dict, plan_value=None, metrics: dict | None = None) -> dict:
    fingerprint = build_trade_fingerprint(trade, plan_value)
    metrics = metrics or {}
    outcome = str(trade.get("outcome") or "UNKNOWN").upper()
    mfe, mae = float(metrics.get("mfe") or 0), float(metrics.get("mae") or 0)
    pnl = float(trade.get("pnl") or 0)
    if outcome == "TARGET HIT":
        finding = "Target achieve hua; entry evidence aur favorable premium expansion ne plan ko validate kiya."
        solution = "Isi fingerprint ko positive reference rakhein, lekin next setup me live liquidity, spread aur safety locks dobara verify honge."
    elif outcome in {"STOP LOSS HIT", "TRAILING STOP HIT"}:
        finding = "Stop protection trigger hua; setup ke baad adverse premium move favorable move se zyada raha." if mae >= mfe else "Trade pehle favorable gaya, phir reverse hua aur protection exit trigger hua."
        solution = "Next similar setup me entry extension, reversal candle, volume/OI agreement aur nearby support-resistance ko stricter warning ke roop me compare karein; risk increase na karein."
    elif outcome == "TIME EXIT":
        finding = "Session safety time par target/stop se pehle position close hui."
        solution = "Future analog me late-session entry aur remaining expected move ko warning banayein."
    else:
        finding = f"Automatic outcome recorded: {outcome}."
        solution = "Historical reference ke roop me rakhein; automatic entry permission na samjhein."
    return {"fingerprint": fingerprint, "finding": finding, "solution": solution, "mfe": mfe, "mae": mae, "pnl": pnl}

"""Transparent paper-only validation for a small, regular option scalp.

This module never places or captures a trade.  It classifies the completed
candle as READY, WATCH or NO TRADE and keeps index movement separate from an
option-premium target so the two units cannot be confused.
"""
from __future__ import annotations


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _condition(side: dict, name: str) -> bool:
    for item in side.get("confirmations") or []:
        if item.get("name") == name:
            return bool(item.get("passed"))
    return False


def _room_to_level(candidate: str, close: float, zones: dict, remaining_range):
    if candidate == "CE":
        levels = [_number(zones.get("chart_resistance")), _number(zones.get("oi_resistance"))]
        ahead = [level - close for level in levels if level > close]
    else:
        levels = [_number(zones.get("chart_support")), _number(zones.get("oi_support"))]
        ahead = [close - level for level in levels if 0 < level < close]
    if ahead:
        return round(min(ahead), 2), "nearest chart/OI level"
    if any(level > 0 for level in levels):
        return (round(_number(remaining_range), 2) if remaining_range is not None else None), "level already broken; VIX range budget"
    return None, "reliable chart/OI level unavailable"


def evaluate_regular_scalp_validation(strategy: dict, environment: dict, capture: dict,
                                      chain: dict, settings: dict) -> dict:
    """Return a no-look-ahead, paper-only 20-point scalp classification."""
    enabled = bool(settings.get("regular_scalp_validation_enabled", False))
    underlying_target = max(1.0, _number(settings.get("regular_scalp_underlying_target_points", 20), 20))
    premium_target = max(1.0, _number(settings.get("regular_scalp_premium_target_points", 20), 20))
    minimum_score = max(0, min(100, int(settings.get("regular_scalp_min_score", 55) or 55)))
    minimum_confirmations = max(1, int(settings.get("regular_scalp_min_confirmations", 3) or 3))
    candidate = strategy.get("candidate") if strategy.get("candidate") in {"CE", "PE"} else None
    side = ((strategy.get("side_evaluations") or {}).get(candidate) or {}) if candidate else {}
    score = int(side.get("score", strategy.get("score", 0)) or 0)
    passed = int(side.get("passed", strategy.get("passed", 0)) or 0)
    total = int(side.get("total", strategy.get("total", 0)) or 0)
    quality = side.get("entry_quality") or {}
    hard_blockers = list(dict.fromkeys(side.get("hard_blockers") or strategy.get("hard_blockers") or []))
    close = _number(capture.get("close"))
    remaining = environment.get("remaining_expected_range")
    room, room_source = _room_to_level(candidate, close, strategy.get("zones") or {}, remaining) if candidate else (None, "direction unavailable")
    range_available = remaining is None or _number(remaining) >= underlying_target
    room_available = room is not None and room >= underlying_target
    timely = bool(quality.get("timely"))
    volume_confirmed = _condition(side, "Directional volume")
    direction_confirmed = all(_condition(side, name) for name in ("Market structure", "Price vs VWAP"))
    evidence_met = bool(candidate) and score >= minimum_score and passed >= min(minimum_confirmations, max(total, 1))
    checks = [
        {"name": "Direction (structure + VWAP)", "passed": direction_confirmed},
        {"name": "Minimum paper-validation evidence", "passed": evidence_met},
        {"name": "Fresh / timely trigger", "passed": timely},
        {"name": "Directional volume", "passed": volume_confirmed},
        {"name": f"Room for {underlying_target:g} index points", "passed": room_available},
        {"name": "VIX/ATR range budget available", "passed": range_available},
        {"name": "No strict TPS hard blocker", "passed": not hard_blockers},
    ]
    ready = enabled and all(item["passed"] for item in checks)
    watch = enabled and evidence_met and not ready
    status = "SCALP READY" if ready else "SCALP WATCH" if watch else "NO TRADE" if enabled else "DISABLED"
    reasons = [item["name"] for item in checks if item["passed"]]
    blockers = [item["name"] for item in checks if not item["passed"]]
    blockers.extend(hard_blockers)
    return {
        "version": "Regular 20-Point Scalp Paper Validation v1",
        "enabled": enabled,
        "paper_only": True,
        "auto_capture_allowed": False,
        "status": status,
        "candidate": candidate,
        "score": score,
        "passed": passed,
        "total": total,
        "minimum_score": minimum_score,
        "minimum_confirmations": minimum_confirmations,
        "underlying_target_points": round(underlying_target, 2),
        "option_premium_target_points": round(premium_target, 2),
        "level_room_points": room,
        "level_room_source": room_source,
        "remaining_expected_range": _number(remaining) if remaining is not None else None,
        "checks": checks,
        "reasons": reasons,
        "blockers": list(dict.fromkeys(blockers)),
        "target_note": (
            f"Underlying objective is {underlying_target:g} index points. Option target is a separate "
            f"Rs {premium_target:g} premium move and is calculated only after a liquid contract confirms."
        ),
        "safety_note": "Research/paper validation only; this verdict never places or captures a broker order.",
        "chain_context": {
            "pcr_oi": chain.get("pcr_oi"), "pcr_volume": chain.get("pcr_volume"),
            "put_support": chain.get("put_support"), "call_resistance": chain.get("call_resistance"),
        },
    }

"""Classify the live market environment before TPS checklist evaluation."""
from __future__ import annotations

from datetime import datetime
from math import sqrt


def classify_india_vix(value):
    """Return the shared TPS volatility label and risk multiplier."""
    try:
        vix = float(value)
    except (TypeError, ValueError):
        vix = 0
    if not 0 < vix < 100:
        return "VIX UNAVAILABLE", 0.75
    if vix < 12:
        return "CALM / RANGE", 0.75
    if vix < 16:
        return "HEALTHY TREND", 1.0
    if vix <= 20:
        return "HIGH VOLATILITY", 0.75
    return "EXTREME RISK", 0.50


def _candle_day(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None


def _session_context(candles):
    dated = [(item, _candle_day(item.get("time"))) for item in candles]
    days = sorted({day for _, day in dated if day})
    if not days:
        return {"opening_range_high": None, "opening_range_low": None, "previous_day_high": None,
                "previous_day_low": None, "previous_day_close": None, "gap_points": None, "gap_state": "UNAVAILABLE"}
    current = [item for item, day in dated if day == days[-1]]
    previous = [item for item, day in dated if len(days) > 1 and day == days[-2]]
    opening = current[:3]
    previous_close = float(previous[-1]["close"]) if previous else None
    current_open = float(current[0].get("open", current[0].get("close"))) if current and current[0].get("open", current[0].get("close")) is not None else None
    gap = current_open - previous_close if current_open is not None and previous_close is not None else None
    return {
        "opening_range_high": max((float(item.get("high", item.get("close"))) for item in opening if item.get("high", item.get("close")) is not None), default=None),
        "opening_range_low": min((float(item.get("low", item.get("close"))) for item in opening if item.get("low", item.get("close")) is not None), default=None),
        "previous_day_high": max((float(item.get("high", item.get("close"))) for item in previous if item.get("high", item.get("close")) is not None), default=None),
        "previous_day_low": min((float(item.get("low", item.get("close"))) for item in previous if item.get("low", item.get("close")) is not None), default=None),
        "previous_day_close": previous_close,
        "gap_points": round(gap, 2) if gap is not None else None,
        "gap_state": "GAP UP" if gap and gap > 0 else "GAP DOWN" if gap and gap < 0 else "FLAT/UNAVAILABLE",
    }


def analyze_market_environment(candles, capture, spot_price, india_vix=None, now=None, event_risk=None):
    close = float(capture["close"]); atr = float(capture.get("atr_14") or 0)
    ema5, ema20, ema50 = (float(capture[key]) for key in ("ema_5", "ema_20", "ema_50"))
    volume_ratio = float(capture.get("volume_ratio") or 0)
    vix = float(india_vix) if india_vix not in (None, "") and 0 < float(india_vix) < 100 else None
    atr_percent = atr / close * 100 if close else 0
    trend_spread = abs(ema5 - ema50) / max(atr, 0.000001)
    aligned = ema5 > ema20 > ema50 or ema5 < ema20 < ema50
    vix_zone, risk_multiplier = classify_india_vix(vix)
    if (vix is not None and vix > 20) or atr_percent >= .65:
        regime = "HIGH VOLATILITY"
    elif aligned and trend_spread >= .75:
        regime = "TRENDING"
    elif (vix is not None and vix < 12) or (atr_percent < .18 and trend_spread < .50):
        regime = "LOW VOLATILITY"
    else:
        regime = "SIDEWAYS / TRANSITION"
    session = _session_context(candles)
    expected_range = float(spot_price) * vix / 100 / sqrt(252) if vix is not None else None
    volume_threshold = 1.7 if regime == "LOW VOLATILITY" else 1.3 if regime == "HIGH VOLATILITY" else 1.5
    sl_atr = 1.4 if regime == "HIGH VOLATILITY" else 1.0 if regime == "TRENDING" else .85
    target_atr = sl_atr * 2
    strike = "ATM/one-step ITM" if regime in {"HIGH VOLATILITY", "LOW VOLATILITY"} else "ATM"
    now = now or datetime.now()
    time_state = "OPENING VOLATILITY" if (now.hour, now.minute) < (10, 0) else "LATE SESSION" if (now.hour, now.minute) >= (14, 45) else "NORMAL SESSION"
    warnings = []
    if vix is None: warnings.append("India VIX quote unavailable; risk is reduced and ATR-only context is used")
    if regime == "LOW VOLATILITY": warnings.append("Low-volatility fake-breakout risk: require stronger volume and VWAP confirmation")
    if regime == "HIGH VOLATILITY": warnings.append("High volatility: reduce quantity and use ATR-adaptive stop/target")
    if time_state == "LATE SESSION": warnings.append("Late-session risk: avoid fresh auto entry close to market close")
    if event_risk and event_risk.get("status") != "CLEAR":
        warnings.append(f"Event risk: {event_risk.get('status')}")
    confidence_multiplier = max(.4, risk_multiplier * (event_risk or {}).get("risk_multiplier", 1.0))
    return {
        "regime": regime, "vix": vix, "vix_zone": vix_zone, "atr_percent": round(atr_percent, 3),
        "trend_strength_atr": round(trend_spread, 2), "volume_regime": "EXPANSION" if volume_ratio >= 1.5 else "NORMAL/LOW",
        "expected_daily_range": round(expected_range, 2) if expected_range is not None else None,
        "risk_multiplier": round(confidence_multiplier, 2), "volume_threshold": volume_threshold,
        "stop_atr_multiplier": sl_atr, "target_atr_multiplier": target_atr,
        "strike_preference": strike, "time_state": time_state, "warnings": warnings,
        "event_risk": event_risk or {}, **session,
    }

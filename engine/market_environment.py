"""Classify the live market environment before TPS checklist evaluation."""
from __future__ import annotations

from datetime import datetime
from math import log, sqrt
from statistics import pstdev


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


def classify_vix_percentile(value, history):
    """Classify VIX relative to its own history, with an explicit fallback.

    Absolute VIX levels change across market eras.  TPS therefore uses the
    current value's percentile inside available daily closes whenever at
    least 20 valid observations exist.  The older absolute classification is
    retained only as a transparent fallback for brokers without VIX history.
    """
    try:
        current = float(value)
    except (TypeError, ValueError):
        current = 0.0
    values = []
    for item in history or []:
        try:
            candidate = item.get("close") if isinstance(item, dict) else item
            candidate = float(candidate)
        except (TypeError, ValueError):
            continue
        if 0 < candidate < 100:
            values.append(candidate)
    if not 0 < current < 100:
        return {"label": "VIX UNAVAILABLE", "percentile": None, "source": "unavailable", "risk_multiplier": .75, "samples": len(values)}
    if len(values) < 20:
        label, multiplier = classify_india_vix(current)
        return {"label": label, "percentile": None, "source": "absolute fallback", "risk_multiplier": multiplier, "samples": len(values)}
    percentile = sum(sample <= current for sample in values) / len(values) * 100
    if percentile < 25:
        label, multiplier = "LOW VOLATILITY", .85
    elif percentile < 75:
        label, multiplier = "NORMAL VOLATILITY", 1.0
    elif percentile < 90:
        label, multiplier = "HIGH VOLATILITY", .75
    else:
        label, multiplier = "EXTREME VOLATILITY", .50
    return {"label": label, "percentile": round(percentile, 1), "source": "historical percentile", "risk_multiplier": multiplier, "samples": len(values)}


def _vix_trend(value, history):
    values = []
    for item in history or []:
        try:
            sample = float(item.get("close") if isinstance(item, dict) else item)
        except (TypeError, ValueError):
            continue
        if 0 < sample < 100:
            values.append(sample)
    if value in (None, "") or not values:
        return "UNAVAILABLE", None
    current = float(value)
    baseline = sum(values[-5:]) / min(5, len(values))
    change = (current - baseline) / baseline * 100 if baseline else 0.0
    trend = "RISING" if change >= 1.0 else "FALLING" if change <= -1.0 else "STABLE"
    return trend, round(change, 2)


def _realized_volatility(candles):
    """Annualised five-minute close-to-close volatility, for comparison only."""
    closes = []
    for item in candles or []:
        try:
            value = float(item.get("close"))
        except (TypeError, ValueError):
            continue
        if value > 0:
            closes.append(value)
    returns = [log(closes[index] / closes[index - 1]) for index in range(1, len(closes)) if closes[index - 1] > 0]
    if len(returns) < 20:
        return None
    return round(pstdev(returns[-375:]) * sqrt(252 * 75) * 100, 2)


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


def analyze_market_environment(candles, capture, spot_price, india_vix=None, now=None, event_risk=None, vix_history=None):
    close = float(capture["close"]); atr = float(capture.get("atr_14") or 0)
    ema5, ema20, ema50 = (float(capture[key]) for key in ("ema_5", "ema_20", "ema_50"))
    volume_ratio = float(capture.get("volume_ratio") or 0)
    vix = float(india_vix) if india_vix not in (None, "") and 0 < float(india_vix) < 100 else None
    atr_percent = atr / close * 100 if close else 0
    trend_spread = abs(ema5 - ema50) / max(atr, 0.000001)
    aligned = ema5 > ema20 > ema50 or ema5 < ema20 < ema50
    vix_zone, _fallback_risk_multiplier = classify_india_vix(vix)
    percentile_context = classify_vix_percentile(vix, vix_history)
    vix_regime = percentile_context["label"]
    risk_multiplier = percentile_context["risk_multiplier"]
    high_percentile = percentile_context["percentile"] is not None and percentile_context["percentile"] >= 75
    low_percentile = percentile_context["percentile"] is not None and percentile_context["percentile"] < 25
    if high_percentile or (percentile_context["percentile"] is None and vix is not None and vix >= 16) or atr_percent >= .65:
        regime = "HIGH VOLATILITY"
    elif aligned and trend_spread >= .75:
        regime = "TRENDING"
    elif low_percentile or (percentile_context["percentile"] is None and vix is not None and vix < 12) or (atr_percent < .18 and trend_spread < .50):
        regime = "LOW VOLATILITY"
    else:
        regime = "SIDEWAYS / TRANSITION"
    session = _session_context(candles)
    expected_range = float(spot_price) * vix / 100 / sqrt(252) if vix is not None else None
    current_day = _candle_day(candles[-1].get("time")) if candles else None
    current_session = [item for item in candles if _candle_day(item.get("time")) == current_day]
    session_high = max((float(item.get("high", item.get("close", close))) for item in current_session), default=close)
    session_low = min((float(item.get("low", item.get("close", close))) for item in current_session), default=close)
    session_range = max(0.0, session_high - session_low)
    remaining_range = max(0.0, expected_range - session_range) if expected_range is not None else None
    range_consumed = session_range / expected_range * 100 if expected_range else None
    vix_trend, vix_trend_percent = _vix_trend(vix, vix_history)
    realized_volatility = _realized_volatility(candles)
    movement_state = (
        "RANGE EXCEEDED" if range_consumed is not None and range_consumed >= 120 else
        "RANGE NEARLY USED" if range_consumed is not None and range_consumed >= 90 else
        "BALANCED UTILIZATION" if range_consumed is not None and range_consumed >= 50 else
        "RANGE UNDER-UTILIZED" if range_consumed is not None else "UNAVAILABLE"
    )
    volume_threshold = 1.7 if regime == "LOW VOLATILITY" else 1.3 if regime == "HIGH VOLATILITY" else 1.5
    sl_atr = 1.4 if regime == "HIGH VOLATILITY" else 1.0 if regime == "TRENDING" else .85
    target_atr = sl_atr * 2
    regular_target = max(close * .0005, expected_range * .10) if expected_range is not None else max(close * .0008, atr * .75)
    adaptive_extension = 1.0 if regime == "TRENDING" else .90 if regime == "HIGH VOLATILITY" else .65 if regime == "LOW VOLATILITY" else .75
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
        "regime": regime, "vix": vix, "vix_zone": vix_zone,
        "vix_historical_regime": vix_regime, "vix_percentile": percentile_context["percentile"],
        "vix_regime_source": percentile_context["source"], "vix_history_samples": percentile_context["samples"],
        "vix_trend": vix_trend, "vix_trend_percent": vix_trend_percent,
        "atr_percent": round(atr_percent, 3), "atr_points": round(atr, 2),
        "realized_volatility_annualized": realized_volatility,
        "trend_strength_atr": round(trend_spread, 2), "volume_regime": "EXPANSION" if volume_ratio >= 1.5 else "NORMAL/LOW",
        "expected_daily_range": round(expected_range, 2) if expected_range is not None else None,
        "session_range": round(session_range, 2),
        "range_consumed_percent": round(range_consumed, 1) if range_consumed is not None else None,
        "expected_range_utilized_percent": round(range_consumed, 1) if range_consumed is not None else None,
        "actual_movement_so_far": round(session_range, 2), "movement_state": movement_state,
        "remaining_expected_range": round(remaining_range, 2) if remaining_range is not None else None,
        "regular_move_target_points": round(regular_target, 2),
        "regular_move_available": remaining_range is None or remaining_range >= regular_target,
        "risk_multiplier": round(confidence_multiplier, 2), "volume_threshold": volume_threshold,
        "stop_atr_multiplier": sl_atr, "target_atr_multiplier": target_atr,
        "max_entry_extension_atr": adaptive_extension,
        "strike_preference": strike, "time_state": time_state, "warnings": warnings,
        "event_risk": event_risk or {}, **session,
    }

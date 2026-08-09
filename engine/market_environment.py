"""Classify the live market environment before TPS checklist evaluation."""
from __future__ import annotations

from datetime import datetime
from math import sqrt


def analyze_market_environment(candles, capture, spot_price, india_vix=None, now=None):
    close = float(capture["close"]); atr = float(capture.get("atr_14") or 0)
    ema5, ema20, ema50 = (float(capture[key]) for key in ("ema_5", "ema_20", "ema_50"))
    volume_ratio = float(capture.get("volume_ratio") or 0)
    vix = float(india_vix) if india_vix not in (None, "") and 0 < float(india_vix) < 100 else None
    atr_percent = atr / close * 100 if close else 0
    trend_spread = abs(ema5 - ema50) / max(atr, 0.000001)
    aligned = ema5 > ema20 > ema50 or ema5 < ema20 < ema50
    if vix is None:
        vix_zone, risk_multiplier = "VIX unavailable", 0.75
    elif vix < 12:
        vix_zone, risk_multiplier = "CALM / RANGE", 0.75
    elif vix < 16:
        vix_zone, risk_multiplier = "HEALTHY TREND", 1.0
    elif vix <= 20:
        vix_zone, risk_multiplier = "HIGH VOLATILITY", 0.75
    else:
        vix_zone, risk_multiplier = "EXTREME RISK", 0.50
    if (vix is not None and vix > 20) or atr_percent >= .65:
        regime = "HIGH VOLATILITY"
    elif aligned and trend_spread >= .75:
        regime = "TRENDING"
    elif (vix is not None and vix < 12) or (atr_percent < .18 and trend_spread < .50):
        regime = "LOW VOLATILITY"
    else:
        regime = "SIDEWAYS / TRANSITION"
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
    return {
        "regime": regime, "vix": vix, "vix_zone": vix_zone, "atr_percent": round(atr_percent, 3),
        "trend_strength_atr": round(trend_spread, 2), "volume_regime": "EXPANSION" if volume_ratio >= 1.5 else "NORMAL/LOW",
        "expected_daily_range": round(expected_range, 2) if expected_range is not None else None,
        "risk_multiplier": risk_multiplier, "volume_threshold": volume_threshold,
        "stop_atr_multiplier": sl_atr, "target_atr_multiplier": target_atr,
        "strike_preference": strike, "time_state": time_state, "warnings": warnings,
    }

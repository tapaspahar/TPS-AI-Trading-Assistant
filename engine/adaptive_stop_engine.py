"""Evidence-led option-premium stops with fixed capital risk.

A wider stop is never permission to take more rupee risk.  TPS gives the
position breathing room and reduces quantity; if one exchange lot does not fit
the configured risk budget, the plan is rejected instead of tightening the
stop to manufacture eligibility.
"""
from __future__ import annotations


def adaptive_option_stop(entry: float, environment: dict, settings: dict, spread_percent=None) -> dict:
    entry = float(entry)
    if entry <= 0:
        raise ValueError("Option entry premium must be positive.")

    # Legacy/direct callers without Release 1.5.1 settings retain the former
    # 20% normal-regime distance; SettingsStore users receive the new 24%
    # default (18 + 3 regime + 3 sweep).
    minimum = float(settings.get("adaptive_stop_min_percent", 15.0))
    maximum = float(settings.get("adaptive_stop_max_percent", 35.0))
    if not 5 <= minimum <= maximum <= 60:
        raise ValueError("Adaptive stop limits must satisfy 5% <= minimum <= maximum <= 60%.")

    regime = str(environment.get("regime") or environment.get("vix_regime") or "NORMAL").upper()
    regime_add = 7.0 if "HIGH" in regime or "EXTREME" in regime else 3.0 if "NORMAL" in regime else 0.0
    multiplier = max(0.5, min(2.0, float(environment.get("stop_atr_multiplier", 1.0) or 1.0)))
    spread_buffer = min(5.0, max(0.0, float(spread_percent or 0.0) * 0.5))
    sweep_buffer = max(0.0, min(10.0, float(settings.get("stop_sweep_buffer_percent", 2.0))))
    raw = minimum * multiplier + regime_add + spread_buffer + sweep_buffer
    distance_percent = min(maximum, max(minimum, raw))
    stop = round(entry * (1.0 - distance_percent / 100.0), 2)
    return {
        "stoploss": max(0.05, stop),
        "distance_percent": round(distance_percent, 2),
        "method": "VOLATILITY + LIQUIDITY + SWEEP BUFFER",
        "regime": regime,
        "note": "Stop ko breathing room diya gaya hai; rupee risk quantity reduction se control hoga.",
    }

"""Explainable, read-only market-structure calculations for recent candles."""
from __future__ import annotations

from statistics import median


def _ema(values, period):
    multiplier = 2 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = (value - result) * multiplier + result
    return result


def _pivot_levels(highs, lows, strength=2):
    swing_lows, swing_highs = [], []
    for index in range(strength, len(highs) - strength):
        low_window = lows[index - strength:index + strength + 1]
        high_window = highs[index - strength:index + strength + 1]
        if lows[index] == min(low_window):
            swing_lows.append((lows[index], index))
        if highs[index] == max(high_window):
            swing_highs.append((highs[index], index))
    return swing_lows, swing_highs


def _cluster_levels(levels, tolerance):
    """Merge repeated nearby pivots into stable price zones."""
    clusters = []
    for value, index in sorted(levels):
        match = next((item for item in clusters if abs(value - item["center"]) <= tolerance), None)
        if match is None:
            clusters.append({"values": [value], "indices": [index], "center": value})
        else:
            match["values"].append(value)
            match["indices"].append(index)
            match["center"] = median(match["values"])
    for item in clusters:
        item["touches"] = len(item["values"])
        item["recency"] = max(item["indices"])
    return clusters


def _best_zone(clusters, current_price, side, fallback, half_width):
    eligible = [
        item for item in clusters
        if (item["center"] < current_price if side == "support" else item["center"] > current_price)
    ]
    if eligible:
        # Repeated reactions beat a one-candle micro pivot; recency breaks ties.
        best = max(eligible, key=lambda item: (item["touches"], item["recency"], -abs(current_price - item["center"])))
        center = float(best["center"])
        touches = best["touches"]
    else:
        center, touches = float(fallback), 1
    return {
        "low": center - half_width,
        "high": center + half_width,
        "center": center,
        "touches": touches,
    }


def analyze_candles(candles):
    """Return nearby levels and confirmation conditions, never a trade instruction."""
    if len(candles) < 10:
        raise ValueError("At least 10 completed 5-minute candles are needed for market structure.")

    window = candles[-80:]
    closes = [float(candle["close"]) for candle in window]
    highs = [float(candle["high"]) for candle in window]
    lows = [float(candle["low"]) for candle in window]
    volumes = [float(candle.get("volume", 0) or 0) for candle in window]
    current_price = closes[-1]

    typical_range = median([max(high - low, 0.01) for high, low in zip(highs, lows)])
    zone_half_width = max(typical_range * 0.35, current_price * 0.00015, 0.05)
    cluster_tolerance = zone_half_width * 2
    swing_lows, swing_highs = _pivot_levels(highs, lows)
    support_zone = _best_zone(
        _cluster_levels(swing_lows, cluster_tolerance), current_price, "support",
        min(lows[-20:]), zone_half_width,
    )
    resistance_zone = _best_zone(
        _cluster_levels(swing_highs, cluster_tolerance), current_price, "resistance",
        max(highs[-20:]), zone_half_width,
    )
    support = support_zone["center"]
    resistance = resistance_zone["center"]

    ema_fast = _ema(closes[-20:], min(5, len(closes)))
    ema_slow = _ema(closes[-20:], min(20, len(closes)))
    if current_price > ema_fast > ema_slow:
        state = "Bullish structure"
    elif current_price < ema_fast < ema_slow:
        state = "Bearish structure"
    else:
        state = "Mixed / range structure"

    reference_volumes = [value for value in volumes[-21:-1] if value > 0]
    volume_average = sum(reference_volumes) / len(reference_volumes) if reference_volumes else 0
    volume_text = f"volume >= {volume_average * 1.2:,.0f}" if volume_average else "volume confirmation"
    buffer = max(current_price * 0.0002, zone_half_width * 0.25, 0.05)

    return {
        "price": current_price,
        "state": state,
        "support": support,
        "resistance": resistance,
        "support_zone": support_zone,
        "resistance_zone": resistance_zone,
        "breakout_level": resistance_zone["high"] + buffer,
        "breakdown_level": support_zone["low"] - buffer,
        "zone_tolerance": zone_half_width,
        "level_method": "clustered completed-candle swing zones",
        "volume_condition": volume_text,
        "candle_count": len(window),
    }

"""Explainable, read-only market-structure calculations for recent candles."""
from __future__ import annotations


def _ema(values, period):
    multiplier = 2 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = (value - result) * multiplier + result
    return result


def analyze_candles(candles):
    """Return nearby levels and confirmation conditions, never a trade instruction."""
    if len(candles) < 10:
        raise ValueError("At least 10 completed 5-minute candles are needed for market structure.")

    window = candles[-40:]
    closes = [float(candle["close"]) for candle in window]
    highs = [float(candle["high"]) for candle in window]
    lows = [float(candle["low"]) for candle in window]
    volumes = [float(candle.get("volume", 0) or 0) for candle in window]
    current_price = closes[-1]

    swing_lows, swing_highs = [], []
    for index in range(1, len(window) - 1):
        if lows[index] <= lows[index - 1] and lows[index] <= lows[index + 1]:
            swing_lows.append(lows[index])
        if highs[index] >= highs[index - 1] and highs[index] >= highs[index + 1]:
            swing_highs.append(highs[index])

    support_options = [level for level in swing_lows if level < current_price]
    resistance_options = [level for level in swing_highs if level > current_price]
    support = max(support_options) if support_options else min(lows[-20:])
    resistance = min(resistance_options) if resistance_options else max(highs[-20:])

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
    buffer = max(current_price * 0.0002, 0.05)

    return {
        "price": current_price,
        "state": state,
        "support": support,
        "resistance": resistance,
        "breakout_level": resistance + buffer,
        "breakdown_level": support - buffer,
        "volume_condition": volume_text,
        "candle_count": len(window),
    }

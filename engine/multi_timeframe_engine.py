"""Explainable multi-timeframe chart context; it does not forecast or place trades."""
from __future__ import annotations

from engine.market_structure import analyze_candles


def candle_pattern(candles):
    """Identify only the most recent, simple price-action formation."""
    current = candles[-1]
    open_price, high, low, close = (float(current[key]) for key in ("open", "high", "low", "close"))
    body, spread = abs(close - open_price), max(high - low, 0.0001)
    upper, lower = high - max(open_price, close), min(open_price, close) - low
    if body / spread <= 0.1:
        return "Doji / indecision"
    if lower >= body * 2 and upper <= body:
        return "Hammer" if close >= open_price else "Hanging-man shaped candle"
    if upper >= body * 2 and lower <= body:
        return "Shooting-star shaped candle" if close <= open_price else "Inverted-hammer shaped candle"
    if len(candles) >= 2:
        previous = candles[-2]
        previous_open, previous_close = float(previous["open"]), float(previous["close"])
        if close > open_price and previous_close < previous_open and close >= previous_open and open_price <= previous_close:
            return "Bullish engulfing"
        if close < open_price and previous_close > previous_open and close <= previous_open and open_price >= previous_close:
            return "Bearish engulfing"
    return "No major recent pattern"


def analyze_multi_timeframe(candles_by_timeframe):
    """Combine four chart views into transparent conditions and nearby zones."""
    analyses = {}
    for timeframe, candles in candles_by_timeframe.items():
        structure = analyze_candles(candles)
        structure["pattern"] = candle_pattern(candles)
        analyses[timeframe] = structure
    states = [analysis["state"] for analysis in analyses.values()]
    bullish, bearish = states.count("Bullish structure"), states.count("Bearish structure")
    if bullish >= 3:
        context, score = "Bullish multi-timeframe alignment", bullish * 25
    elif bearish >= 3:
        context, score = "Bearish multi-timeframe alignment", bearish * 25
    else:
        context, score = "Mixed multi-timeframe structure — wait for confirmation", max(bullish, bearish) * 25

    current_price = analyses["5m"]["price"]
    supports = [analysis["support"] for analysis in analyses.values() if analysis["support"] < current_price]
    resistances = [analysis["resistance"] for analysis in analyses.values() if analysis["resistance"] > current_price]
    return {
        "context": context,
        "alignment_score": score,
        "support": max(supports) if supports else analyses["5m"]["support"],
        "resistance": min(resistances) if resistances else analyses["5m"]["resistance"],
        "timeframes": analyses,
    }

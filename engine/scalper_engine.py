"""Explainable completed-candle scalp watcher; no broker order placement."""
from __future__ import annotations

from engine.live_setup_capture import atr, ema


def _f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def evaluate_scalp(one_minute, five_minute, global_context=None, minimum_score=72):
    if len(one_minute) < 51 or len(five_minute) < 51:
        raise ValueError("Scalper needs at least 51 completed 1-minute and 5-minute future candles.")
    c1 = [_f(row["close"]) for row in one_minute]
    c5 = [_f(row["close"]) for row in five_minute]
    latest = one_minute[-1]
    close, opening = _f(latest["close"]), _f(latest["open"])
    e5, e20, e50 = ema(c1, 5), ema(c1, 20), ema(c1, 50)
    h5e5, h5e20 = ema(c5, 5), ema(c5, 20)
    session = one_minute[-120:]
    volume = _f(latest.get("volume"))
    volume_avg = sum(_f(row.get("volume")) for row in session[-20:]) / 20
    volume_ratio = volume / volume_avg if volume_avg else 0
    total_volume = sum(_f(row.get("volume")) for row in session)
    vwap = (sum(((_f(row["high"]) + _f(row["low"]) + _f(row["close"])) / 3) * _f(row.get("volume")) for row in session) / total_volume) if total_volume else None
    momentum = close - c1[-4]
    candle_range = max(_f(latest["high"]) - _f(latest["low"]), .000001)
    body_quality = abs(close - opening) / candle_range
    local_atr = atr(one_minute, 14)
    prior = one_minute[-21:-1]
    resistance = max(_f(row["high"]) for row in prior)
    support = min(_f(row["low"]) for row in prior)
    bullish = [
        (e5 > e20 > e50, "1m EMA 5 > 20 > 50"),
        (h5e5 > h5e20, "5m EMA trend bullish"),
        (vwap is not None and close > vwap, "Price above session VWAP"),
        (momentum > 0, "Last three-minute momentum positive"),
        (close > opening and body_quality >= .45, "Bullish body has usable strength"),
        (volume_ratio >= 1.15, "Volume expansion at least 1.15x"),
        (close >= resistance or resistance - close >= local_atr * .40, "Enough room to resistance or breakout confirmed"),
    ]
    bearish = [
        (e5 < e20 < e50, "1m EMA 5 < 20 < 50"),
        (h5e5 < h5e20, "5m EMA trend bearish"),
        (vwap is not None and close < vwap, "Price below session VWAP"),
        (momentum < 0, "Last three-minute momentum negative"),
        (close < opening and body_quality >= .45, "Bearish body has usable strength"),
        (volume_ratio >= 1.15, "Volume expansion at least 1.15x"),
        (close <= support or close - support >= local_atr * .40, "Enough room to support or breakdown confirmed"),
    ]
    bull_count, bear_count = sum(ok for ok, _ in bullish), sum(ok for ok, _ in bearish)
    direction = "CE" if bull_count > bear_count else "PE" if bear_count > bull_count else None
    checks = bullish if direction == "CE" else bearish if direction == "PE" else []
    score = round(max(bull_count, bear_count) / 7 * 88)
    global_context = global_context or {}
    global_bias = global_context.get("bias", "UNAVAILABLE")
    adjustment = int(global_context.get("score_adjustment") or 0)
    if direction == "CE": score += adjustment
    elif direction == "PE": score -= adjustment
    score = max(0, min(100, score))
    blockers = [text for ok, text in checks if not ok]
    if vwap is None:
        blockers.append("Future traded volume/VWAP unavailable")
    published = bool(direction and score >= minimum_score and len(blockers) <= 2 and volume_ratio >= 1.0)
    action = f"{direction} SCALP WATCH" if published else "WAIT"
    risk = max(local_atr * .9, close * .00035)
    stop = close - risk if direction == "CE" else close + risk if direction == "PE" else None
    target1 = close + risk * 1.2 if direction == "CE" else close - risk * 1.2 if direction == "PE" else None
    target2 = close + risk * 1.8 if direction == "CE" else close - risk * 1.8 if direction == "PE" else None
    return {"action": action, "published": published, "candidate": direction, "score": score,
            "minimum_score": minimum_score, "entry_reference": close, "stop": stop,
            "target1": target1, "target2": target2, "candle_time": latest.get("time"),
            "ema5": e5, "ema20": e20, "ema50": e50, "vwap": vwap,
            "volume_ratio": volume_ratio, "momentum": momentum, "global_bias": global_bias,
            "support": support, "resistance": resistance,
            "passed": [text for ok, text in checks if ok], "blockers": blockers,
            "warning": "WATCH means research/paper confirmation, not an order or guaranteed profitable scalp."}

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
        raise ValueError("Direction engine needs at least 51 completed 1-minute and 5-minute index-future candles; the future is evidence, not the scalp instrument.")
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
    return {"action": action, "published": published, "candidate": direction, "score": score,
            "minimum_score": minimum_score, "underlying_reference": close, "candle_time": latest.get("time"),
            "ema5": e5, "ema20": e20, "ema50": e50, "vwap": vwap,
            "volume_ratio": volume_ratio, "momentum": momentum, "global_bias": global_bias,
            "support": support, "resistance": resistance,
            "passed": [text for ok, text in checks if ok], "blockers": blockers,
            "warning": "WATCH means research/paper confirmation, not an order or guaranteed profitable scalp."}


def evaluate_option_premium(candles, quote):
    """Confirm the selected buy-option itself and create premium-based risk levels."""
    if len(candles) < 21:
        raise ValueError("Selected option needs at least 21 completed 1-minute premium candles.")
    closes = [_f(row["close"]) for row in candles]
    latest = candles[-1]
    close = _f(latest["close"])
    e5, e20 = ema(closes, 5), ema(closes, 20)
    momentum = close - closes[-4]
    recent = candles[-20:]
    total_volume = sum(_f(row.get("volume")) for row in recent)
    average_volume = total_volume / len(recent) if recent else 0
    latest_volume = _f(latest.get("volume"))
    volume_ratio = latest_volume / average_volume if average_volume else 0
    vwap = (sum(((_f(row["high"]) + _f(row["low"]) + _f(row["close"])) / 3) * _f(row.get("volume")) for row in recent) / total_volume) if total_volume else None
    depth = quote.get("depth") or {}; buys, sells = depth.get("buy") or [], depth.get("sell") or []
    bid = _f(quote.get("bestBidPrice") or (buys[0].get("price") if buys else 0))
    ask = _f(quote.get("bestAskPrice") or (sells[0].get("price") if sells else 0))
    ltp = _f(quote.get("ltp"))
    spread = (ask - bid) / max((ask + bid) / 2, .01) * 100 if ask >= bid > 0 else None
    checks = [
        (close > e5 > e20, "Selected option premium above EMA 5 > EMA 20"),
        (vwap is not None and close > vwap, "Selected option premium above its VWAP"),
        (momentum > 0, "Selected option three-minute momentum positive"),
        (volume_ratio >= 1.0, "Selected option volume at/above 20-candle average"),
        (ltp > 0 and (spread is None or spread <= 12), "Selected option quote and spread usable"),
    ]
    passed = [text for ok, text in checks if ok]
    blockers = [text for ok, text in checks if not ok]
    confirmed = len(passed) >= 4 and checks[-1][0]
    entry = ask if ask > 0 else ltp if ltp > 0 else close
    premium_atr = atr(candles, 14)
    risk = max(premium_atr, entry * .08)
    return {"confirmed": confirmed, "entry": entry, "stop": max(.05, entry - risk),
            "target1": entry + risk * 1.2, "target2": entry + risk * 1.8,
            "premium_close": close, "ema5": e5, "ema20": e20, "vwap": vwap,
            "momentum": momentum, "volume_ratio": volume_ratio, "bid": bid, "ask": ask,
            "ltp": ltp, "spread_percent": spread, "passed": passed, "blockers": blockers}

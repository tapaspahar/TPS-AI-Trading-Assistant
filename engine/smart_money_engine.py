"""Deterministic, read-only price-action and SMC-style research engine.

The labels in this module are transparent TPS rules, not claims about hidden
institutional orders.  Only confirmed pivots are used, so the latest decision
does not look into future candles.
"""
from __future__ import annotations

from datetime import datetime

from engine.live_setup_capture import atr, ema


def _number(candle, key):
    return float(candle.get(key, 0) or 0)


def _pivots(candles, left=2, right=2):
    highs, lows = [], []
    for index in range(left, len(candles) - right):
        high, low = _number(candles[index], "high"), _number(candles[index], "low")
        window = candles[index - left:index + right + 1]
        if high == max(_number(item, "high") for item in window):
            highs.append((index, high))
        if low == min(_number(item, "low") for item in window):
            lows.append((index, low))
    return highs, lows


def _session_levels(candles):
    levels = {"previous_day_high": None, "previous_day_low": None,
              "opening_range_high": None, "opening_range_low": None}
    try:
        dated = [(datetime.fromisoformat(str(c["time"])).date(), c) for c in candles]
        current = dated[-1][0]
        today = [c for day, c in dated if day == current]
        prior_days = sorted({day for day, _ in dated if day < current})
        prior = [c for day, c in dated if prior_days and day == prior_days[-1]]
        if prior:
            levels["previous_day_high"] = max(_number(c, "high") for c in prior)
            levels["previous_day_low"] = min(_number(c, "low") for c in prior)
        if today:
            levels["opening_range_high"] = max(_number(c, "high") for c in today[:3])
            levels["opening_range_low"] = min(_number(c, "low") for c in today[:3])
    except (KeyError, TypeError, ValueError):
        pass
    return levels


def _vwap(candles):
    try:
        last_day = datetime.fromisoformat(str(candles[-1]["time"])).date()
        session = [c for c in candles if datetime.fromisoformat(str(c["time"])).date() == last_day]
    except (KeyError, TypeError, ValueError):
        session = candles
    volume = sum(_number(c, "volume") for c in session)
    if volume <= 0:
        return None
    return sum(((_number(c, "high") + _number(c, "low") + _number(c, "close")) / 3)
               * _number(c, "volume") for c in session) / volume


def _volume_profile(candles, bins=20):
    low = min(_number(c, "low") for c in candles)
    high = max(_number(c, "high") for c in candles)
    width = max((high - low) / bins, 1e-9)
    volumes = [0.0] * bins
    for candle in candles:
        typical = (_number(candle, "high") + _number(candle, "low") + _number(candle, "close")) / 3
        index = min(int((typical - low) / width), bins - 1)
        volumes[index] += _number(candle, "volume")
    poc_index = max(range(bins), key=volumes.__getitem__)
    target, selected = sum(volumes) * 0.70, {poc_index}
    accumulated, lower, upper = volumes[poc_index], poc_index, poc_index
    while accumulated < target and (lower > 0 or upper < bins - 1):
        left = volumes[lower - 1] if lower > 0 else -1
        right = volumes[upper + 1] if upper < bins - 1 else -1
        if right >= left:
            upper += 1; selected.add(upper); accumulated += volumes[upper]
        else:
            lower -= 1; selected.add(lower); accumulated += volumes[lower]
    center = lambda index: low + (index + 0.5) * width
    return {"poc": center(poc_index), "value_area_low": low + lower * width,
            "value_area_high": low + (upper + 1) * width,
            "method": "Candle typical-price volume approximation (not tick-level profile)"}


def _patterns(candles):
    latest, previous = candles[-1], candles[-2]
    opening, close = _number(latest, "open"), _number(latest, "close")
    high, low = _number(latest, "high"), _number(latest, "low")
    span, body = max(high - low, 1e-9), abs(close - opening)
    upper, lower = high - max(opening, close), min(opening, close) - low
    found = []
    if body / span <= 0.10: found.append("Doji")
    if lower >= body * 2 and upper <= max(body, span * .15): found.append("Hammer / bullish pin bar")
    if upper >= body * 2 and lower <= max(body, span * .15): found.append("Shooting star / bearish pin bar")
    po, pc = _number(previous, "open"), _number(previous, "close")
    if pc < po and close > opening and opening <= pc and close >= po: found.append("Bullish engulfing")
    if pc > po and close < opening and opening >= pc and close <= po: found.append("Bearish engulfing")
    if high < _number(previous, "high") and low > _number(previous, "low"): found.append("Inside bar")
    return found or ["No configured candle pattern"]


class SmartMoneyEngine:
    """Analyze completed OHLCV candles and return auditable evidence."""

    def analyze(self, candles):
        candles = list(candles)
        if len(candles) < 55:
            raise ValueError("At least 55 completed OHLCV candles are required.")
        highs, lows = _pivots(candles)
        if len(highs) < 2 or len(lows) < 2:
            raise ValueError("Not enough confirmed swing highs/lows were found.")
        latest = candles[-1]
        close, high, low = (_number(latest, key) for key in ("close", "high", "low"))
        last_high, prior_high = highs[-1][1], highs[-2][1]
        last_low, prior_low = lows[-1][1], lows[-2][1]
        if last_high > prior_high and last_low > prior_low:
            structure = "BULLISH (HH + HL)"
        elif last_high < prior_high and last_low < prior_low:
            structure = "BEARISH (LH + LL)"
        else:
            structure = "MIXED / RANGE"

        current_atr = atr(candles)
        buffer = current_atr * .05
        volume_avg = ema([_number(c, "volume") for c in candles[-20:]], 20)
        volume_ratio = _number(latest, "volume") / volume_avg if volume_avg else 0
        current_vwap = _vwap(candles)
        levels = _session_levels(candles)
        reference_high = max(x for x in (last_high, levels["previous_day_high"]) if x is not None)
        reference_low = min(x for x in (last_low, levels["previous_day_low"]) if x is not None)
        buy_sweep = high > reference_high + buffer and close < reference_high
        sell_sweep = low < reference_low - buffer and close > reference_low
        bullish_break = close > last_high + buffer
        bearish_break = close < last_low - buffer
        bos = "BULLISH BOS" if bullish_break and structure.startswith("BULLISH") else "BEARISH BOS" if bearish_break and structure.startswith("BEARISH") else "None"
        choch = "BULLISH CHOCH" if bullish_break and structure.startswith("BEARISH") else "BEARISH CHOCH" if bearish_break and structure.startswith("BULLISH") else "None"
        fake = "BUY-SIDE fake breakout" if buy_sweep else "SELL-SIDE fake breakdown" if sell_sweep else "None"

        prior_close = _number(candles[-2], "close")
        vwap_event = "Unavailable"
        if current_vwap is not None:
            if prior_close < current_vwap < close: vwap_event = "Bullish VWAP reclaim"
            elif prior_close > current_vwap > close: vwap_event = "Bearish VWAP loss"
            elif high > current_vwap and close < current_vwap: vwap_event = "VWAP bull trap"
            elif low < current_vwap and close > current_vwap: vwap_event = "VWAP bear trap"
            else: vwap_event = "No VWAP trap/reclaim"

        fvgs = []
        for index in range(max(2, len(candles) - 30), len(candles)):
            if _number(candles[index], "low") > _number(candles[index - 2], "high") + buffer:
                fvgs.append({"type": "Bullish FVG", "low": _number(candles[index - 2], "high"), "high": _number(candles[index], "low")})
            if _number(candles[index], "high") < _number(candles[index - 2], "low") - buffer:
                fvgs.append({"type": "Bearish FVG", "low": _number(candles[index], "high"), "high": _number(candles[index - 2], "low")})
        fvg = fvgs[-1] if fvgs else None
        demand = {"low": _number(candles[lows[-1][0]], "low"), "high": max(_number(candles[lows[-1][0]], "open"), _number(candles[lows[-1][0]], "close"))}
        supply = {"low": min(_number(candles[highs[-1][0]], "open"), _number(candles[highs[-1][0]], "close")), "high": _number(candles[highs[-1][0]], "high")}
        # TPS order-block proxy: the latest opposite-colour candle before the
        # current impulse. It is deliberately labelled as an approximation.
        preferred_bearish = bullish_break or sell_sweep
        order_source = next((c for c in reversed(candles[-8:-1])
                             if (_number(c, "close") < _number(c, "open")) == preferred_bearish), candles[-2])
        order_block = {
            "type": "Bullish order-block proxy" if preferred_bearish else "Bearish order-block proxy",
            "low": _number(order_source, "low"), "high": _number(order_source, "high"),
        }
        dealing_low, dealing_high = min(last_low, prior_low), max(last_high, prior_high)
        equilibrium = (dealing_low + dealing_high) / 2
        ict_location = "DISCOUNT" if close < equilibrium else "PREMIUM"

        bullish = bearish = 0
        closes = [_number(c, "close") for c in candles]
        e5, e20, e50 = ema(closes[-20:], 5), ema(closes[-50:], 20), ema(closes, 50)
        if e5 > e20 > e50: bullish += 20
        if e5 < e20 < e50: bearish += 20
        if current_vwap is not None and close > current_vwap: bullish += 15
        if current_vwap is not None and close < current_vwap: bearish += 15
        if structure.startswith("BULLISH"): bullish += 20
        if structure.startswith("BEARISH"): bearish += 20
        if bullish_break or sell_sweep: bullish += 20
        if bearish_break or buy_sweep: bearish += 20
        if volume_ratio >= 1.5 and close > _number(latest, "open"): bullish += 15
        if volume_ratio >= 1.5 and close < _number(latest, "open"): bearish += 15
        if demand["low"] <= close <= demand["high"] + current_atr: bullish += 10
        if supply["low"] - current_atr <= close <= supply["high"]: bearish += 10
        score = max(bullish, bearish)
        direction = "BULLISH" if bullish > bearish else "BEARISH" if bearish > bullish else "NEUTRAL"
        grade = "A+ research setup" if score >= 80 else "B setup" if score >= 65 else "WATCH" if score >= 50 else "NO TRADE"
        profile = _volume_profile(candles[-100:])
        event = "Sell-side liquidity sweep" if sell_sweep else "Buy-side liquidity sweep" if buy_sweep else choch if choch != "None" else bos
        return {
            "direction": direction, "score": score, "bullish_score": bullish, "bearish_score": bearish,
            "grade": grade, "structure": structure, "event": event, "bos": bos, "choch": choch,
            "liquidity_sweep": "SELL-SIDE" if sell_sweep else "BUY-SIDE" if buy_sweep else "None",
            "fake_breakout": fake, "vwap_event": vwap_event, "patterns": _patterns(candles),
            "volume_ratio": volume_ratio, "vwap": current_vwap, "atr": current_atr,
            "swing_high": last_high, "swing_low": last_low, "session_levels": levels,
            "supply_zone": supply, "demand_zone": demand, "fvg": fvg,
            "order_block": order_block,
            "ict_location": ict_location, "equilibrium": equilibrium, "volume_profile": profile,
            "evidence": [
                f"EMA stack: EMA5 {e5:.2f}, EMA20 {e20:.2f}, EMA50 {e50:.2f}",
                f"Close {close:.2f} vs VWAP {current_vwap:.2f}" if current_vwap is not None else "VWAP unavailable",
                f"Confirmed swings: high {last_high:.2f}, low {last_low:.2f}; structure {structure}",
                f"Latest volume {volume_ratio:.2f}x its EMA20", f"BOS: {bos}; CHOCH: {choch}",
            ],
            "warnings": [
                "Research support only; no broker order is placed.",
                "ICT, order-block, supply/demand and FVG labels are deterministic TPS approximations, not certainty.",
                "Scores rank rule confluence; they are not win probability.",
            ],
        }

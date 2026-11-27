"""Advanced, deterministic Smart Money Concepts research layer.

Works only on completed OHLCV candles. Structure breaks require a candle close;
zones are transparent price-action proxies, not evidence of hidden institutional
orders. This module never places or recommends an unattended broker order.
"""
from __future__ import annotations

from engine.smart_money_engine import SmartMoneyEngine, _number, _pivots
from engine.live_setup_capture import atr


def _body(candle):
    return abs(_number(candle, "close") - _number(candle, "open"))


def _range(candle):
    return max(_number(candle, "high") - _number(candle, "low"), 0.0)


def _trend(highs, lows):
    if len(highs) < 2 or len(lows) < 2:
        return "UNCONFIRMED"
    hh = highs[-1][1] > highs[-2][1]
    hl = lows[-1][1] > lows[-2][1]
    lh = highs[-1][1] < highs[-2][1]
    ll = lows[-1][1] < lows[-2][1]
    if hh and hl:
        return "BULLISH"
    if lh and ll:
        return "BEARISH"
    return "RANGE"


def _structure(candles, left=2, right=2):
    highs, lows = _pivots(candles, left=left, right=right)
    labels = []
    for points, name in ((highs, "HIGH"), (lows, "LOW")):
        for index in range(1, len(points)):
            relation = "HH" if name == "HIGH" and points[index][1] > points[index - 1][1] else (
                "LH" if name == "HIGH" else
                "HL" if points[index][1] > points[index - 1][1] else "LL"
            )
            labels.append({"type": relation, "price": points[index][1], "index": points[index][0]})
    labels.sort(key=lambda item: item["index"])
    return highs, lows, labels, _trend(highs, lows)


def _fvg_zones(candles, volatility, lookback=80):
    zones = []
    start = max(2, len(candles) - lookback)
    for i in range(start, len(candles)):
        first, middle, third = candles[i - 2], candles[i - 1], candles[i]
        middle_range = _range(middle)
        displacement = bool(volatility and middle_range >= 1.15 * volatility and
                            _body(middle) >= 0.55 * middle_range)
        if _number(third, "low") > _number(first, "high"):
            low, high, side = _number(first, "high"), _number(third, "low"), "BULLISH"
        elif _number(third, "high") < _number(first, "low"):
            low, high, side = _number(third, "high"), _number(first, "low"), "BEARISH"
        else:
            continue
        later = candles[i + 1:]
        touched = [c for c in later if _number(c, "low") <= high and _number(c, "high") >= low]
        fully_filled = any(
            (_number(c, "low") <= low if side == "BULLISH" else _number(c, "high") >= high)
            for c in later
        )
        zones.append({
            "side": side, "low": low, "high": high, "formed_index": i,
            "displacement_confirmed": displacement,
            "status": "MITIGATED" if touched else "FRESH",
            "fully_filled": fully_filled,
            "touch_count": len(touched),
        })
    return zones


def _order_blocks(candles, volatility, lookback=60):
    blocks = []
    start = max(2, len(candles) - lookback)
    for i in range(start, len(candles) - 1):
        impulse = candles[i + 1]
        impulse_range = _range(impulse)
        if not volatility or impulse_range < 1.25 * volatility or _body(impulse) < .60 * impulse_range:
            continue
        impulse_up = _number(impulse, "close") > _number(impulse, "open")
        source = candles[i]
        source_down = _number(source, "close") < _number(source, "open")
        if impulse_up == source_down:
            side = "BULLISH" if impulse_up else "BEARISH"
            low, high = _number(source, "low"), _number(source, "high")
            later = candles[i + 2:]
            invalid = any(
                _number(c, "close") < low if side == "BULLISH"
                else _number(c, "close") > high for c in later
            )
            touched = any(_number(c, "low") <= high and _number(c, "high") >= low for c in later)
            blocks.append({
                "side": side, "low": low, "high": high, "formed_index": i,
                "status": "INVALIDATED" if invalid else "RETESTED" if touched else "FRESH",
                "impulse_index": i + 1,
            })
    return blocks


def _liquidity_pools(highs, lows, tolerance):
    pools = []
    for points, kind in ((highs, "BUY_SIDE"), (lows, "SELL_SIDE")):
        clusters = []
        for index, price in points:
            match = next((cluster for cluster in clusters
                          if abs(price - cluster["mean"]) <= tolerance), None)
            if match is None:
                clusters.append({"prices": [price], "indices": [index], "mean": price})
            else:
                match["prices"].append(price)
                match["indices"].append(index)
                match["mean"] = sum(match["prices"]) / len(match["prices"])
        for cluster in clusters:
            if len(cluster["prices"]) >= 2:
                pools.append({
                    "side": kind, "level": cluster["mean"],
                    "touches": len(cluster["prices"]),
                    "first_index": cluster["indices"][0],
                    "last_index": cluster["indices"][-1],
                })
    return pools


def _break_events(candles, highs, lows, trend, tolerance):
    if len(candles) < 2:
        return []
    previous_close = _number(candles[-2], "close")
    close = _number(candles[-1], "close")
    events = []
    if highs:
        level = highs[-1][1]
        if close > level + tolerance and previous_close <= level + tolerance:
            events.append({
                "event": "BOS" if trend == "BULLISH" else "CHOCH",
                "direction": "BULLISH", "level": level, "confirmed_by": "completed candle close",
            })
    if lows:
        level = lows[-1][1]
        if close < level - tolerance and previous_close >= level - tolerance:
            events.append({
                "event": "BOS" if trend == "BEARISH" else "CHOCH",
                "direction": "BEARISH", "level": level, "confirmed_by": "completed candle close",
            })
    return events


class AdvancedSMCEngine:
    """Add confirmed structure, zone lifecycle and optional timeframe confluence."""

    def __init__(self, pivot_left=2, pivot_right=2):
        self.pivot_left = max(1, int(pivot_left))
        self.pivot_right = max(1, int(pivot_right))
        self.legacy = SmartMoneyEngine()

    def analyze(self, candles, timeframe_candles=None):
        rows = list(candles)
        if len(rows) < 55:
            raise ValueError("At least 55 completed OHLCV candles are required.")
        base = self.legacy.analyze(rows)
        highs, lows, swing_labels, trend = _structure(rows, self.pivot_left, self.pivot_right)
        volatility = float(atr(rows) or 0)
        tolerance = max(volatility * 0.08, 1e-9)
        breaks = _break_events(rows, highs, lows, trend, tolerance)
        fvgs = _fvg_zones(rows, volatility)
        blocks = _order_blocks(rows, volatility)
        pools = _liquidity_pools(highs, lows, tolerance)
        close = _number(rows[-1], "close")
        dealing_low = min((point[1] for point in lows[-2:]), default=close)
        dealing_high = max((point[1] for point in highs[-2:]), default=close)
        equilibrium = (dealing_low + dealing_high) / 2
        location = "DISCOUNT" if close < equilibrium else "PREMIUM" if close > equilibrium else "EQUILIBRIUM"

        # Sweep is only marked when price trades beyond a clustered pool and closes back inside.
        sweep_events = []
        latest = rows[-1]
        for pool in pools:
            level = pool["level"]
            if pool["side"] == "BUY_SIDE" and _number(latest, "high") > level + tolerance and close < level:
                sweep_events.append({"side": "BUY_SIDE", "level": level, "confirmation": "close back below pool"})
            elif pool["side"] == "SELL_SIDE" and _number(latest, "low") < level - tolerance and close > level:
                sweep_events.append({"side": "SELL_SIDE", "level": level, "confirmation": "close back above pool"})

        mtf = {}
        for timeframe, tf_rows in (timeframe_candles or {}).items():
            data = list(tf_rows)
            if len(data) < 10:
                mtf[str(timeframe)] = {"trend": "INSUFFICIENT DATA", "bars": len(data)}
                continue
            tf_highs, tf_lows, tf_labels, tf_trend = _structure(data, self.pivot_left, self.pivot_right)
            mtf[str(timeframe)] = {"trend": tf_trend, "bars": len(data),
                                   "last_structure": tf_labels[-4:]}
        trends = [item["trend"] for item in mtf.values() if item["trend"] in ("BULLISH", "BEARISH", "RANGE")]
        mtf_alignment = (
            "NOT PROVIDED" if not trends else
            "ALIGNED BULLISH" if all(x == "BULLISH" for x in trends) else
            "ALIGNED BEARISH" if all(x == "BEARISH" for x in trends) else "MIXED"
        )

        fresh_fvgs = [z for z in fvgs if z["status"] == "FRESH"]
        fresh_blocks = [z for z in blocks if z["status"] == "FRESH"]
        recent_break = breaks[-1] if breaks else None
        score = 0
        score_reasons = []
        if trend == "BULLISH" and location == "DISCOUNT":
            score += 15; score_reasons.append("Bullish structure in discount")
        elif trend == "BEARISH" and location == "PREMIUM":
            score += 15; score_reasons.append("Bearish structure in premium")
        if recent_break:
            score += 20; score_reasons.append(f"Latest confirmed {recent_break['event']} {recent_break['direction']}")
        if sweep_events:
            score += 20; score_reasons.append("Liquidity pool sweep confirmed by close")
        if any(z["side"] == trend and z["displacement_confirmed"] for z in fresh_fvgs):
            score += 15; score_reasons.append("Fresh displacement FVG agrees with structure")
        if any(z["side"] == trend for z in fresh_blocks):
            score += 15; score_reasons.append("Fresh order-block proxy agrees with structure")
        if mtf_alignment == f"ALIGNED {trend}" and trend in ("BULLISH", "BEARISH"):
            score += 15; score_reasons.append("Provided timeframes are aligned")
        score = min(score, 100)
        bias = trend if trend in ("BULLISH", "BEARISH") else "NEUTRAL"
        setup_state = "WATCH"
        if score >= 70 and bias in ("BULLISH", "BEARISH"):
            setup_state = f"{bias} CONFLUENCE - PAPER REVIEW"
        elif score < 30:
            setup_state = "NO CLEAR SMC SETUP"

        base.update({
            "advanced_smc": {
                "structure_trend": trend,
                "swing_sequence": swing_labels[-12:],
                "confirmed_breaks": breaks[-10:],
                "liquidity_pools": pools,
                "liquidity_sweeps": sweep_events,
                "fvg_zones": fvgs[-12:],
                "order_blocks": blocks[-12:],
                "dealing_range": {"low": dealing_low, "high": dealing_high,
                                  "equilibrium": equilibrium, "location": location},
                "timeframe_analysis": mtf,
                "timeframe_alignment": mtf_alignment,
                "confluence_score": score,
                "confluence_reasons": score_reasons,
                "setup_state": setup_state,
                "limitations": [
                    "Pivot confirmation is delayed by the configured right-hand bars; no future bars are used at decision time.",
                    "Order blocks and liquidity pools are OHLCV-derived proxies, not observed institutional orders.",
                    "FVG and order-block lifecycle is assessed from supplied candles only.",
                    "A confluence score is a rule score, not a win probability or trade instruction.",
                    "Multi-timeframe alignment is shown only when separate timeframe candles are supplied.",
                ],
            }
        })
        return base

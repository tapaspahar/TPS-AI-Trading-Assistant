"""Evidence-first explanation of one completed index-future candle."""
from __future__ import annotations

from statistics import median


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def analyze_index_candle(symbol, candles, oi_flow=None, cas_active=False):
    """Describe price, volume and OI without claiming unobservable causation."""
    rows = list(candles or [])
    if len(rows) < 10:
        return {"state": "DATA GAP", "direction": "UNKNOWN", "explanation": "10 completed 5-minute future candles available nahi hain."}
    latest = rows[-1]
    opening, high, low, close = (_number(latest.get(k)) for k in ("open", "high", "low", "close"))
    span = max(high - low, 1e-9)
    body = abs(close - opening)
    body_pct = body / span * 100
    close_position = (close - low) / span
    ranges = [max(_number(r.get("high")) - _number(r.get("low")), 0) for r in rows[-21:-1]]
    volumes = [_number(r.get("volume")) for r in rows[-21:-1] if _number(r.get("volume")) > 0]
    range_ratio = span / max(median(ranges), 1e-9) if ranges else None
    volume = _number(latest.get("volume"))
    volume_ratio = volume / median(volumes) if volumes and volume else None
    direction = "BULLISH" if close > opening else "BEARISH" if close < opening else "NEUTRAL"
    if direction == "BULLISH" and body_pct >= 55 and close_position >= .70:
        aggression = "BUYERS AGGRESSIVE"
    elif direction == "BEARISH" and body_pct >= 55 and close_position <= .30:
        aggression = "SELLERS AGGRESSIVE"
    elif close_position >= .65:
        aggression = "BUYERS HELD CLOSE"
    elif close_position <= .35:
        aggression = "SELLERS HELD CLOSE"
    else:
        aggression = "TWO-WAY / INDECISIVE"
    if volume_ratio is None:
        participation = "Future volume DATA GAP"
    elif volume_ratio >= 1.5:
        participation = f"high participation ({volume_ratio:.2f}x)"
    elif volume_ratio >= .8:
        participation = f"normal participation ({volume_ratio:.2f}x)"
    else:
        participation = f"low participation ({volume_ratio:.2f}x)"
    flow = oi_flow or {}
    flow_direction = str(flow.get("direction") or "DATA GAP")
    quality = int(flow.get("quality") or 0)
    aligned = direction in flow_direction
    state = "CAS / SETTLEMENT REPRICING" if cas_active else (
        "PRICE + OI ALIGNED" if aligned and quality >= 60 else
        "PRICE / OI DIVERGENCE" if quality >= 60 and direction in {"BULLISH", "BEARISH"} and flow_direction not in {"BALANCED FLOW", "DATA GAP"}
        else "PRICE MOVE; OI UNCONFIRMED"
    )
    wick = "upper-wick rejection" if (high - max(opening, close)) / span >= .4 else "lower-wick rejection" if (min(opening, close) - low) / span >= .4 else "clean body"
    caveat = " CAS me cash indicative price jump/stale ho sakta hai; futures/options settlement evidence ko priority di gayi hai." if cas_active else ""
    explanation = (
        f"{symbol} future candle {direction.lower()} raha: {opening:,.2f} se {close:,.2f} ({close-opening:+,.2f} pts), "
        f"range {span:,.2f} pts, {wick}, {aggression.lower()}, {participation}. "
        f"Near-ATM OI flow {flow_direction.lower()} (quality {quality}/100); "
        f"Call COI {float(flow.get('call_coi') or 0):+,.0f}, Put COI {float(flow.get('put_coi') or 0):+,.0f}."
        f"{caveat} Ye evidence explanation hai, exact news/participant intent ka proof nahi."
    )
    return {
        "state": state, "direction": direction, "aggression": aggression,
        "open": opening, "high": high, "low": low, "close": close,
        "move_points": round(close-opening, 2), "range_points": round(span, 2),
        "range_ratio": round(range_ratio, 2) if range_ratio is not None else None,
        "volume": volume or None, "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
        "oi_direction": flow_direction, "oi_quality": quality,
        "call_oi": flow.get("call_oi"), "put_oi": flow.get("put_oi"),
        "call_coi": flow.get("call_coi"), "put_coi": flow.get("put_coi"),
        "put_wall": flow.get("put_wall"), "put_wall_health": flow.get("put_wall_health"),
        "call_wall": flow.get("call_wall"), "call_wall_health": flow.get("call_wall_health"),
        "source_completeness": round((50 if volume_ratio is not None else 25) + quality * .5),
        "explanation": explanation,
    }


def combine_index_candles(results):
    valid = [r for r in results if r.get("direction") in {"BULLISH", "BEARISH", "NEUTRAL"}]
    bulls = sum(r["direction"] == "BULLISH" for r in valid)
    bears = sum(r["direction"] == "BEARISH" for r in valid)
    state = "BROAD BULLISH" if bulls == 3 else "BROAD BEARISH" if bears == 3 else "BULLISH BREADTH" if bulls >= 2 else "BEARISH BREADTH" if bears >= 2 else "MIXED / DIVERGENT"
    names = ", ".join(f"{r.get('symbol')}: {r.get('direction')}" for r in valid) or "no complete index data"
    return {"state": state, "coverage": f"{len(valid)}/3", "explanation": f"Cross-index read: {names}. {state}; ek index ko akela market-wide confirmation nahi maana gaya."}

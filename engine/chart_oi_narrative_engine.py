"""Chart-first candle anatomy combined with OI-flow context.

OHLCV can describe rejection/acceptance behaviour but cannot prove who caused
it.  The narrative therefore uses evidence language rather than invented
market-maker intent.
"""
from __future__ import annotations

from statistics import median


def _f(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _shape(row):
    opening, high, low, close = (_f(row.get(key)) for key in ("open", "high", "low", "close"))
    span = max(high - low, 1e-9)
    body = abs(close - opening)
    return {
        "range": span, "body_ratio": body / span,
        "upper_wick_ratio": max(0.0, high - max(opening, close)) / span,
        "lower_wick_ratio": max(0.0, min(opening, close) - low) / span,
        "close_position": (close - low) / span,
        "direction": "BULLISH" if close > opening else "BEARISH" if close < opening else "NEUTRAL",
    }


def analyze_chart_oi_narrative(candles, oi_flow):
    rows = list(candles or [])
    if len(rows) < 10:
        return {"state": "DATA GAP", "explanation": "At least 10 completed candles required.",
                "candle_time": None, "latency_note": "Completed-candle data unavailable"}
    shapes = [_shape(row) for row in rows]
    latest, latest_shape = rows[-1], shapes[-1]
    reference = shapes[-21:-1] or shapes[:-1]
    typical_range = median(item["range"] for item in reference)
    range_ratio = latest_shape["range"] / max(typical_range, 1e-9)
    volumes = [_f(row.get("volume")) for row in rows[-21:-1] if _f(row.get("volume")) > 0]
    typical_volume = median(volumes) if volumes else 0
    volume_ratio = _f(latest.get("volume")) / typical_volume if typical_volume else None
    recent = shapes[-8:]
    upper_rejections = sum(item["upper_wick_ratio"] >= .45 for item in recent)
    lower_rejections = sum(item["lower_wick_ratio"] >= .45 for item in recent)
    big_bar = range_ratio >= 1.5 and latest_shape["body_ratio"] >= .55
    high_participation = volume_ratio is not None and volume_ratio >= 1.5
    chart_direction = latest_shape["direction"] if big_bar else (
        "BULLISH" if latest_shape["close_position"] >= .70 and lower_rejections >= 2 else
        "BEARISH" if latest_shape["close_position"] <= .30 and upper_rejections >= 2 else "MIXED"
    )
    flow_direction = str((oi_flow or {}).get("direction") or "BALANCED FLOW")
    flow_side = "BULLISH" if flow_direction == "BULLISH FLOW" else "BEARISH" if flow_direction == "BEARISH FLOW" else "MIXED"
    aligned = chart_direction in {"BULLISH", "BEARISH"} and chart_direction == flow_side
    conflict = chart_direction in {"BULLISH", "BEARISH"} and flow_side in {"BULLISH", "BEARISH"} and chart_direction != flow_side
    if aligned and big_bar and high_participation and _f((oi_flow or {}).get("quality")) >= 60:
        state = "BIG MOVE CONFIRMATION WATCH"
    elif conflict:
        state = "DIVERGENCE / TRAP WATCH"
    elif upper_rejections >= 3 or lower_rejections >= 3:
        state = "REPEATED WICK WATCH"
    else:
        state = "DEVELOPING / NO CONFIRMATION"

    anatomy = (
        f"Range {range_ratio:.2f}x typical; body {latest_shape['body_ratio'] * 100:.0f}%; "
        f"upper wick {latest_shape['upper_wick_ratio'] * 100:.0f}%; lower wick {latest_shape['lower_wick_ratio'] * 100:.0f}%"
    )
    wick_reason = (
        f"Last 8 completed candles: upper rejection {upper_rejections}, lower rejection {lower_rejections}. "
        "Repeated upper wick supply/failed acceptance ke consistent hai; repeated lower wick demand/absorption ke consistent hai. "
        "OHLCV alone exact participant intent prove nahi karta."
    )
    if aligned:
        conclusion = f"Chart {chart_direction} aur fresh OI flow aligned hain; next completed candle acceptance zaroori hai."
    elif conflict:
        conclusion = f"Chart {chart_direction}, lekin OI flow {flow_side}; breakout chase karne ke bajay divergence resolve hone dein."
    else:
        conclusion = f"Chart {chart_direction}; OI flow {flow_side}. Big-move confirmation incomplete hai."
    return {
        "state": state, "chart_direction": chart_direction, "flow_direction": flow_direction,
        "aligned": aligned, "conflict": conflict, "big_bar": big_bar,
        "range_ratio": round(range_ratio, 2), "body_ratio": round(latest_shape["body_ratio"] * 100, 1),
        "upper_wick_ratio": round(latest_shape["upper_wick_ratio"] * 100, 1),
        "lower_wick_ratio": round(latest_shape["lower_wick_ratio"] * 100, 1),
        "upper_rejections": upper_rejections, "lower_rejections": lower_rejections,
        "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
        "anatomy": anatomy, "wick_explanation": wick_reason, "explanation": conclusion,
        "candle_time": str(latest.get("time") or "unavailable"),
        "latency_note": "Decision uses completed 5-minute candle; intrabar broker quote changes remain provisional.",
    }

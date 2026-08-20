"""Deterministic daily market fingerprints and historical analog matching."""

from __future__ import annotations

from difflib import SequenceMatcher
from statistics import mean


def _number(value, default=0.0):
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _state(latest: dict) -> tuple[str, str, str]:
    close = _number(latest.get("close"))
    ema5, ema20, ema50 = (_number(latest.get(k)) for k in ("ema_5", "ema_20", "ema_50"))
    vwap, supertrend = _number(latest.get("vwap")), _number(latest.get("supertrend"))
    ema = "BULLISH" if ema5 > ema20 > ema50 else "BEARISH" if ema5 < ema20 < ema50 else "MIXED"
    vw = "ABOVE" if close > vwap else "BELOW" if close < vwap else "AT"
    st = "BULLISH" if close > supertrend else "BEARISH" if close < supertrend else "AT"
    return ema, vw, st


def build_daily_fingerprint(rows: list[dict], symbol: str, trade_date: str) -> dict:
    """Build an explainable fingerprint from saved completed 5-minute observations."""
    normalized = [dict(row) for row in rows]
    candles = sorted((row for row in normalized if str(row.get("timeframe", "")).lower() == "5m"), key=lambda r: str(r.get("captured_at", "")))
    if not candles:
        raise ValueError("At least one 5-minute market snapshot is required")
    first, latest = candles[0], candles[-1]
    session_open = _number(first.get("open"))
    close = _number(latest.get("close"))
    high = max(_number(row.get("high")) for row in candles)
    low = min(_number(row.get("low")) for row in candles)
    return_pct = ((close - session_open) / session_open * 100.0) if session_open else 0.0
    range_pct = ((high - low) / session_open * 100.0) if session_open else 0.0
    ema_state, vwap_state, supertrend_state = _state(latest)
    row_states = [_state(row) for row in candles]
    bearish_ema_ratio = sum(state[0] == "BEARISH" for state in row_states) / len(row_states)
    bullish_ema_ratio = sum(state[0] == "BULLISH" for state in row_states) / len(row_states)
    below_vwap_ratio = sum(state[1] == "BELOW" for state in row_states) / len(row_states)
    above_vwap_ratio = sum(state[1] == "ABOVE" for state in row_states) / len(row_states)

    # Compress the session into at most twelve directional blocks. This is the
    # Candle DNA used to compare shape without depending on the index price.
    closes = [_number(row.get("close")) for row in candles]
    step = max(1, len(closes) // 12)
    sampled = closes[::step]
    if sampled[-1] != closes[-1]:
        sampled.append(closes[-1])
    tolerance = max(_number(latest.get("atr_14")) * 0.08, session_open * 0.00015)
    dna = "".join("U" if b - a > tolerance else "D" if a - b > tolerance else "F" for a, b in zip(sampled, sampled[1:])) or "F"

    mid = max(1, len(closes) // 2)
    first_move = closes[mid - 1] - session_open
    second_move = close - closes[mid - 1]
    if return_pct >= 0.20 and (bullish_ema_ratio >= .55 or above_vwap_ratio >= .60):
        trend = "BULLISH"
    elif return_pct <= -0.20 and (bearish_ema_ratio >= .55 or below_vwap_ratio >= .60):
        trend = "BEARISH"
    elif sum((vwap_state == "ABOVE", ema_state == "BULLISH", supertrend_state == "BULLISH")) >= 2 and return_pct > 0.12:
        trend = "BULLISH"
    elif sum((vwap_state == "BELOW", ema_state == "BEARISH", supertrend_state == "BEARISH")) >= 2 and return_pct < -0.12:
        trend = "BEARISH"
    else:
        trend = "RANGE / MIXED"
    if first_move < 0 < second_move and abs(second_move) > abs(first_move) * 0.65:
        pattern = "V REVERSAL"
    elif first_move > 0 > second_move and abs(second_move) > abs(first_move) * 0.65:
        pattern = "INVERTED-V REVERSAL"
    elif trend == "BULLISH":
        pattern = "UPTREND CONTINUATION"
    elif trend == "BEARISH":
        pattern = "DOWNTREND CONTINUATION"
    else:
        pattern = "RANGE / CHOP"

    volume_ratios = [_number(r.get("volume")) / _number(r.get("volume_ema"), 1.0) for r in candles if _number(r.get("volume_ema")) > 0]
    volume_state = "HIGH" if volume_ratios and mean(volume_ratios) >= 1.25 else "LOW" if volume_ratios and mean(volume_ratios) < 0.75 else "NORMAL"
    outcome = (
        f"{symbol} {trend.lower()} raha; open {session_open:,.2f}, high {high:,.2f}, "
        f"low {low:,.2f}, close {close:,.2f}, move {return_pct:+.2f}% aur range {range_pct:.2f}% thi. "
        f"Day shape: {pattern}."
    )
    features = {
        "trend": trend, "pattern": pattern, "dna": dna, "return_pct": round(return_pct, 4),
        "range_pct": round(range_pct, 4), "ema_state": ema_state, "vwap_state": vwap_state,
        "supertrend_state": supertrend_state, "volume_state": volume_state,
        "rsi": round(_number(latest.get("rsi_14")), 2),
        "atr_pct": round((_number(latest.get("atr_14")) / close * 100.0) if close else 0.0, 4),
        "oi_pcr": round(_number(latest.get("oi_pcr"), 1.0), 4),
        "volume_pcr": round(_number(latest.get("volume_pcr"), 1.0), 4),
        "bullish_ema_ratio": round(bullish_ema_ratio, 4), "bearish_ema_ratio": round(bearish_ema_ratio, 4),
        "above_vwap_ratio": round(above_vwap_ratio, 4), "below_vwap_ratio": round(below_vwap_ratio, 4),
        "snapshot_quality": round(min(1.0, len(candles) / 72.0), 4),
    }
    return {
        "trade_date": trade_date, "symbol": symbol.upper(), "trend": trend, "chart_pattern": pattern,
        "candle_signature": dna, "session_open": session_open, "session_high": high, "session_low": low,
        "session_close": close, "return_pct": round(return_pct, 4), "range_pct": round(range_pct, 4),
        "outcome_text": outcome, "features": features, "snapshot_count": len(candles),
    }


def similarity_score(current: dict, historical: dict) -> float:
    """Return 0-100 analog strength; it is similarity, not win probability."""
    a = current.get("features", current)
    b = historical.get("features", historical)
    score = 0.0
    score += 18 if a.get("trend") == b.get("trend") else 0
    score += 18 if a.get("pattern") == b.get("pattern") else 0
    score += 18 * SequenceMatcher(None, str(a.get("dna", "")), str(b.get("dna", ""))).ratio()
    score += 8 if a.get("ema_state") == b.get("ema_state") else 0
    score += 7 if a.get("vwap_state") == b.get("vwap_state") else 0
    score += 7 if a.get("supertrend_state") == b.get("supertrend_state") else 0
    score += 5 if a.get("volume_state") == b.get("volume_state") else 0
    score += 7 * max(0.0, 1.0 - abs(_number(a.get("return_pct")) - _number(b.get("return_pct"))) / 1.5)
    score += 6 * max(0.0, 1.0 - abs(_number(a.get("range_pct")) - _number(b.get("range_pct"))) / 2.0)
    score += 3 * max(0.0, 1.0 - abs(_number(a.get("oi_pcr"), 1) - _number(b.get("oi_pcr"), 1)) / 0.8)
    score += 3 * max(0.0, 1.0 - abs(_number(a.get("rsi"), 50) - _number(b.get("rsi"), 50)) / 35.0)
    return round(min(100.0, score), 1)


def find_best_analogs(current: dict, historical: list[dict], limit: int = 5) -> list[dict]:
    matches = []
    for record in historical:
        if record.get("symbol") != current.get("symbol") or record.get("trade_date") == current.get("trade_date"):
            continue
        item = dict(record)
        raw_similarity = similarity_score(current, item)
        item["quality_weight"] = min(
            _number(current.get("features", current).get("snapshot_quality")),
            _number(item.get("features", item).get("snapshot_quality")),
        )
        item["raw_similarity"] = raw_similarity
        item["similarity"] = round(raw_similarity * max(0.35, item["quality_weight"]), 1)
        item["context_only"] = True
        matches.append(item)
    return sorted(matches, key=lambda item: item["similarity"], reverse=True)[:limit]

"""Five-minute chart + futures volume + option OI/COI analog memory."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime


def candle_pattern(row) -> str:
    opening, high, low, close = (float(row[key] or 0) for key in ("open", "high", "low", "close"))
    span = max(high - low, 1e-9); body = abs(close - opening) / span
    upper = (high - max(opening, close)) / span; lower = (min(opening, close) - low) / span
    if body <= .15: return "DOJI / INDECISION"
    if lower >= .45 and close > opening: return "BULLISH REJECTION"
    if upper >= .45 and close < opening: return "BEARISH REJECTION"
    if body >= .65: return "BULLISH IMPULSE" if close > opening else "BEARISH IMPULSE"
    return "BULLISH BODY" if close > opening else "BEARISH BODY" if close < opening else "NEUTRAL"


def _sign(value):
    value = float(value or 0); return 1 if value > 0 else -1 if value < 0 else 0


def snapshot_similarity(current, historical) -> float:
    """Explainable resemblance score, deliberately not a profit probability."""
    score = 0.0
    score += 15 if current["direction"] == historical["direction"] else 0
    score += 10 if candle_pattern(current) == candle_pattern(historical) else 0
    score += 15 if current["aggression"] == historical["aggression"] else 0
    score += 20 if current["oi_direction"] == historical["oi_direction"] else 0
    score += 10 if _sign(current["call_coi"]) == _sign(historical["call_coi"]) else 0
    score += 10 if _sign(current["put_coi"]) == _sign(historical["put_coi"]) else 0
    for key, weight, scale in (("volume_ratio", 10, 1.5), ("range_ratio", 10, 1.5)):
        a, b = current[key], historical[key]
        if a is not None and b is not None:
            score += weight * max(0, 1 - abs(float(a) - float(b)) / scale)
    quality = min(float(current["source_completeness"] or 0), float(historical["source_completeness"] or 0)) / 100
    return round(score * quality, 1)


def build_live_verdict(rows: list[dict], window: int = 5) -> dict:
    """Combine recent completed candles into an explainable live-session verdict."""
    if not rows:
        return {
            "verdict": "FLAT", "confidence": 0.0, "last_candle": None,
            "evidence": "Aaj ki completed 5-minute candle abhi available nahi hai.",
        }

    recent = rows[-max(1, int(window)):]
    score = 0.0
    maximum = 0.0
    bullish = bearish = neutral = 0
    for recency, row in enumerate(recent, start=1):
        quality = max(0.0, min(1.0, float(row.get("source_completeness") or 0) / 100))
        volume = max(0.5, min(2.0, float(row.get("volume_ratio") or 1.0)))
        weight = recency * quality * volume
        direction = str(row.get("direction") or "").upper()
        aggression = str(row.get("aggression") or "").upper()
        oi_flow = str(row.get("oi_direction") or "").upper()
        candle_score = 0.0
        candle_score += 1.0 if "BULL" in direction else -1.0 if "BEAR" in direction else 0.0
        candle_score += 0.55 if "BUYER" in aggression else -0.55 if "SELLER" in aggression else 0.0
        candle_score += 0.70 if "BULL" in oi_flow else -0.70 if "BEAR" in oi_flow else 0.0
        score += candle_score * weight
        maximum += 2.25 * weight
        if candle_score > 0.25: bullish += 1
        elif candle_score < -0.25: bearish += 1
        else: neutral += 1

    normalized = score / maximum if maximum else 0.0
    verdict = "BULLISH" if normalized >= 0.18 else "BEARISH" if normalized <= -0.18 else "FLAT"
    confidence = round(min(100.0, abs(normalized) * 100), 1)
    latest = recent[-1]
    return {
        "verdict": verdict,
        "confidence": confidence,
        "last_candle": latest.get("candle_time"),
        "evidence": (
            f"Recent {len(recent)} completed candles: {bullish} bullish, "
            f"{bearish} bearish, {neutral} neutral; recency, volume, OI flow aur data coverage weighted."
        ),
    }


def build_options_memory_view(database, symbol: str, trade_date: str | None = None, analog_limit: int = 20) -> dict:
    trade_date = trade_date or datetime.now().strftime("%d-%m-%Y")
    history = [dict(row) for row in database.get_index_candle_history(symbol)]
    by_day = defaultdict(list)
    for row in history: by_day[str(row["trade_date"])].append(row)
    current_rows = by_day.get(trade_date, [])
    for rows in by_day.values(): rows.sort(key=lambda row: str(row["candle_time"]))
    latest = current_rows[-1] if current_rows else None
    analogs = []
    if latest and float(latest.get("source_completeness") or 0) >= 80:
        for day, rows in by_day.items():
            if day == trade_date: continue
            for index, row in enumerate(rows[:-1]):
                if float(row.get("source_completeness") or 0) < 80: continue
                following = rows[index + 1]
                move = float(following["close"] or 0) - float(row["close"] or 0)
                analogs.append({
                    "trade_date": day, "candle_time": row["candle_time"],
                    "similarity": snapshot_similarity(latest, row), "pattern": candle_pattern(row),
                    "oi_direction": row["oi_direction"], "next_move": round(move, 2),
                    "next_direction": "UP" if move > 0 else "DOWN" if move < 0 else "FLAT",
                })
    analogs.sort(key=lambda item: item["similarity"], reverse=True); analogs = analogs[:analog_limit]
    meaningful = [item for item in analogs if item["similarity"] >= 60]
    up_weight = sum(item["similarity"] for item in meaningful if item["next_direction"] == "UP")
    down_weight = sum(item["similarity"] for item in meaningful if item["next_direction"] == "DOWN")
    total = up_weight + down_weight
    probability = round(max(up_weight, down_weight) * 100 / total, 1) if total else 0.0
    direction = "UP" if up_weight > down_weight else "DOWN" if down_weight > up_weight else "UNRESOLVED"
    state = "USABLE ANALOG" if len(meaningful) >= 10 and probability >= 60 else "LEARNING / LOW CONFIDENCE"
    rows_view = [{**row, "pattern": candle_pattern(row)} for row in reversed(current_rows)]
    live_verdict = build_live_verdict(current_rows)
    return {
        "symbol": symbol.upper(), "trade_date": trade_date, "rows": rows_view, "latest": latest,
        "analogs": analogs, "meaningful_samples": len(meaningful), "predicted_direction": direction,
        "historical_follow_rate": probability, "state": state,
        "live_verdict": live_verdict,
        "note": "Historical follow-rate similar saved snapshots ka outcome hai; live prediction ya guaranteed trade signal nahi.",
    }

"""Pure expiry-after-3 PM contract selection and spike classification."""
from __future__ import annotations

from datetime import datetime
from statistics import median
from collections import defaultdict


def select_nearby_expiry_contracts(contracts, spot, itm_depth=2):
    """Return nearest-expiry ATM plus nearby ITM CE/PE contracts."""
    if not contracts or float(spot or 0) <= 0:
        return []
    expiry = min(row["expiry"] for row in contracts)
    active = [row for row in contracts if row["expiry"] == expiry]
    strikes = sorted({float(row["strike"]) for row in active})
    atm = min(strikes, key=lambda value: abs(value - float(spot)))
    ce_strikes = [atm] + sorted((s for s in strikes if s < atm), reverse=True)[:itm_depth]
    pe_strikes = [atm] + sorted((s for s in strikes if s > atm))[:itm_depth]
    paired_strikes = set(ce_strikes + pe_strikes)
    wanted = {(side, strike) for side in ("CE", "PE") for strike in paired_strikes}
    result = []
    for row in active:
        strike = float(row["strike"])
        if (row["option_type"], strike) not in wanted:
            continue
        item = dict(row)
        if strike == atm:
            item["moneyness"] = "ATM"
        else:
            item["moneyness"] = "ITM" if ((item["option_type"] == "CE" and strike < atm) or
                                               (item["option_type"] == "PE" and strike > atm)) else "OTM"
        item["atm_distance"] = strike - atm
        result.append(item)
    return sorted(result, key=lambda row: (row["option_type"], abs(row["atm_distance"])))


def _volume_ratio(samples):
    if len(samples) < 3:
        return None
    deltas = [max(0.0, float(b.get("volume", 0)) - float(a.get("volume", 0))) for a, b in zip(samples, samples[1:])]
    latest, prior = deltas[-1], [value for value in deltas[:-1] if value > 0]
    return latest / median(prior) if latest > 0 and prior else None


def evaluate_spike(samples, *, spot_breakout=False):
    """Evaluate a rolling quote series without inventing unavailable evidence."""
    if len(samples) < 2:
        return {"event": False, "state": "COLLECTING", "source_completeness": "PARTIAL"}
    latest = samples[-1]
    latest_at = latest["observed_at"]
    candidates = [row for row in samples[:-1] if 60 <= (latest_at - row["observed_at"]).total_seconds() <= 300]
    baseline = candidates[0] if candidates else samples[0]
    elapsed = max(1, int((latest_at - baseline["observed_at"]).total_seconds()))
    old, new = float(baseline.get("premium", 0)), float(latest.get("premium", 0))
    pct = ((new - old) / old * 100) if old > 0 else None
    volume_ratio = _volume_ratio(samples)
    old_oi, new_oi = float(baseline.get("open_interest", 0)), float(latest.get("open_interest", 0))
    oi_change = new_oi - old_oi
    oi_change_pct = (oi_change / old_oi * 100) if old_oi > 0 else None
    premium_gate = pct is not None and ((elapsed <= 180 and pct >= 40) or (elapsed <= 300 and pct >= 70))
    confirmations = []
    if volume_ratio is not None and volume_ratio >= 2:
        confirmations.append(f"Volume {volume_ratio:.1f}x")
    if oi_change_pct is not None and abs(oi_change_pct) >= 3:
        confirmations.append(f"OI {oi_change_pct:+.1f}%")
    if spot_breakout:
        confirmations.append("Spot breakout")
    available = sum(value is not None for value in (pct, volume_ratio, oi_change_pct)) + 1
    completeness = "COMPLETE" if available >= 4 else "PARTIAL"
    return {
        "event": bool(premium_gate and confirmations),
        "state": "SPIKE" if premium_gate and confirmations else "PRICE WATCH" if premium_gate else "NORMAL",
        "premium_change_pct": pct,
        "elapsed_seconds": elapsed,
        "volume_ratio": volume_ratio,
        "oi_change": oi_change,
        "oi_change_pct": oi_change_pct,
        "confirmations": confirmations,
        "source_completeness": completeness,
        "baseline_premium": old,
        "latest_premium": new,
        "baseline_at": baseline["observed_at"],
    }


def format_spike_event(symbol, contract, result, observed_at: datetime):
    change = float(result.get("premium_change_pct") or 0)
    minutes = max(1, round(float(result.get("elapsed_seconds") or 0) / 60))
    evidence = " | ".join(result.get("confirmations") or ["confirmation unavailable"])
    return (f"{observed_at.strftime('%I:%M %p').lstrip('0')} | {symbol} {contract['moneyness']} "
            f"{contract['option_type']} | {change:+.0f}% in {minutes} min | {evidence}")


def predict_expiry_spike(current_rows, historical_rows, historical_events):
    """Return an auditable historical-analogue watch, never a guaranteed signal."""
    if not current_rows:
        return {"state": "COLLECTING", "text": "Prediction ke liye aaj ka observation data abhi available nahi hai."}
    today = str(current_rows[0].get("trade_date") or "")
    ordered = sorted(current_rows, key=lambda row: str(row.get("observed_at") or ""))
    first_spot, last_spot = float(ordered[0].get("spot") or 0), float(ordered[-1].get("spot") or 0)
    move = last_spot - first_spot
    threshold = max(5.0, first_spot * .00025) if first_spot else 5.0
    direction = "FALLING" if move <= -threshold else "RISING" if move >= threshold else "FLAT"
    side = "PE" if direction == "FALLING" else "CE" if direction == "RISING" else "CE/PE"

    by_day = defaultdict(list)
    for row in historical_rows:
        day = str(row.get("trade_date") or "")
        if day and day != today:
            by_day[day].append(row)
    analog_days = []
    for day, rows in by_day.items():
        rows = sorted(rows, key=lambda row: str(row.get("observed_at") or ""))
        start, end = float(rows[0].get("spot") or 0), float(rows[-1].get("spot") or 0)
        gate = max(5.0, start * .00025) if start else 5.0
        day_direction = "FALLING" if end - start <= -gate else "RISING" if end - start >= gate else "FLAT"
        if day_direction == direction:
            analog_days.append(day)
    event_days = {
        str(row.get("trade_date") or "") for row in historical_events
        if str(row.get("trade_date") or "") in analog_days
        and (side == "CE/PE" or str(row.get("option_type") or "").upper() == side)
    }
    samples, hits = len(analog_days), len(event_days)
    probability = round(100.0 * (hits + 1) / (samples + 2), 1) if samples else 0.0
    confidence = "INSUFFICIENT" if samples < 3 else "LOW" if samples < 8 else "MEDIUM" if samples < 15 else "HIGH"
    watch = f"{side} SPIKE WATCH" if direction != "FLAT" else "TWO-SIDED SPIKE WATCH"
    return {
        "state": watch, "direction": direction, "side": side, "probability": probability,
        "samples": samples, "hits": hits, "confidence": confidence, "move": move,
        "text": (f"{watch} | Spot observation move {move:+,.2f} ({direction}) | "
                 f"Historical analogues: {hits}/{samples} event-day(s) | Smoothed probability {probability:.1f}% | "
                 f"Evidence confidence: {confidence}. Research prediction hai, entry guarantee nahi."),
    }

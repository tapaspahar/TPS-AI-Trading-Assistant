"""Pure expiry-after-3 PM contract selection and spike classification."""
from __future__ import annotations

from datetime import datetime
from statistics import median


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
    wanted = {("CE", s) for s in ce_strikes} | {("PE", s) for s in pe_strikes}
    result = []
    for row in active:
        strike = float(row["strike"])
        if (row["option_type"], strike) not in wanted:
            continue
        item = dict(row)
        item["moneyness"] = "ATM" if strike == atm else "ITM"
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
    }


def format_spike_event(symbol, contract, result, observed_at: datetime):
    change = float(result.get("premium_change_pct") or 0)
    minutes = max(1, round(float(result.get("elapsed_seconds") or 0) / 60))
    evidence = " | ".join(result.get("confirmations") or ["confirmation unavailable"])
    return (f"{observed_at.strftime('%I:%M %p').lstrip('0')} | {symbol} {contract['moneyness']} "
            f"{contract['option_type']} | {change:+.0f}% in {minutes} min | {evidence}")

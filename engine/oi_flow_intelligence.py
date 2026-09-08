"""Near-money OI-flow analysis that separates legacy walls from fresh flow."""
from __future__ import annotations

from statistics import median


def reconstruct_oi_change(rows, previous_rows=None):
    """Fill missing/all-zero broker COI from two timestamped OI surfaces.

    A local delta is evidence only when the exact contract existed in both
    snapshots.  It is never invented from PCR or price movement.
    """
    current = [dict(row) for row in rows or []]
    previous = {
        (float(row.get("strike") or 0), str(row.get("option_type") or "").upper()): float(row.get("oi") or 0)
        for row in (previous_rows or []) if float(row.get("strike") or 0) > 0
    }
    broker_signal = any(abs(float(row.get("oi_change") or 0)) > 0 for row in current)
    if broker_signal or not previous:
        return current, "BROKER" if broker_signal else "UNAVAILABLE", 0
    matched = 0
    for row in current:
        key = (float(row.get("strike") or 0), str(row.get("option_type") or "").upper())
        if key in previous:
            row["oi_change"] = float(row.get("oi") or 0) - previous[key]
            matched += 1
    coverage = round(100 * matched / max(len(current), 1))
    return current, "LOCAL SNAPSHOT DELTA" if coverage >= 70 else "UNAVAILABLE", coverage


def analyze_oi_flow(rows, spot, wing_count=5, previous_rows=None):
    rows, coi_source, delta_coverage = reconstruct_oi_change(rows, previous_rows)
    rows = [dict(row) for row in rows if float(row.get("strike") or 0) > 0]
    strikes = sorted({float(row["strike"]) for row in rows}, key=lambda value: abs(value - float(spot)))[: 1 + 2 * wing_count]
    focused = [row for row in rows if float(row["strike"]) in strikes]
    calls = [row for row in focused if row.get("option_type") == "CE"]
    puts = [row for row in focused if row.get("option_type") == "PE"]
    call_oi, put_oi = sum(float(r.get("oi") or 0) for r in calls), sum(float(r.get("oi") or 0) for r in puts)
    call_coi, put_coi = sum(float(r.get("oi_change") or 0) for r in calls), sum(float(r.get("oi_change") or 0) for r in puts)
    call_vol, put_vol = sum(float(r.get("volume") or 0) for r in calls), sum(float(r.get("volume") or 0) for r in puts)
    positive_bases = [float(r.get("oi") or 0) - float(r.get("oi_change") or 0) for r in focused]
    positive_bases = [value for value in positive_bases if value > 0]
    base_floor = median(positive_bases) * .10 if positive_bases else 0

    def enrich(row):
        oi, coi = float(row.get("oi") or 0), float(row.get("oi_change") or 0)
        base = max(0.0, oi - coi)
        coi_pct = coi / base * 100 if base >= max(base_floor, 1) else None
        premium_change = row.get("premium_change_percent")
        if coi > 0 and premium_change is not None:
            flow = "LONG BUILDUP" if float(premium_change) > 0 else "WRITING" if float(premium_change) < 0 else "FRESH OI"
        elif coi < 0 and premium_change is not None:
            flow = "SHORT COVERING" if float(premium_change) > 0 else "LONG UNWINDING" if float(premium_change) < 0 else "UNWINDING"
        else: flow = "FRESH OI" if coi > 0 else "UNWINDING" if coi < 0 else "UNCHANGED"
        return {**row, "coi_pct": round(coi_pct, 2) if coi_pct is not None else None, "flow": flow,
                "base_reliable": base >= max(base_floor, 1)}

    enriched = [enrich(row) for row in focused]
    ce_writing = sum(max(float(r.get("oi_change") or 0), 0) for r in enriched if r["option_type"] == "CE" and r["flow"] in {"WRITING", "FRESH OI"})
    pe_writing = sum(max(float(r.get("oi_change") or 0), 0) for r in enriched if r["option_type"] == "PE" and r["flow"] in {"WRITING", "FRESH OI"})
    denominator = max(ce_writing + pe_writing, 1)
    flow_score = (pe_writing - ce_writing) / denominator * 100
    direction = "BULLISH FLOW" if flow_score >= 20 else "BEARISH FLOW" if flow_score <= -20 else "BALANCED FLOW"
    put_wall = max(puts, key=lambda r: float(r.get("oi") or 0), default=None)
    call_wall = max(calls, key=lambda r: float(r.get("oi") or 0), default=None)
    put_health = "WEAKENING" if put_coi < 0 or flow_score < -35 else "DEFENDED" if put_coi > 0 and flow_score > 0 else "UNCONFIRMED"
    call_health = "WEAKENING" if call_coi < 0 or flow_score > 35 else "DEFENDED" if call_coi > 0 and flow_score < 0 else "UNCONFIRMED"
    coi_values = [r.get("oi_change") for r in focused if r.get("oi_change") is not None]
    coi_coverage = len(coi_values) / max(len(focused), 1)
    # Several broker payloads expose the COI key but fill every strike with
    # zero when change-in-OI is unavailable. Presence is not evidence. Treat
    # an all-zero surface as DATA GAP so it cannot earn 100% OI quality.
    coi_has_signal = any(abs(float(value or 0)) > 0 for value in coi_values)
    premium_coverage = sum(r.get("premium_change_percent") is not None for r in focused) / max(len(focused), 1)
    quality = round(coi_coverage * 60 + premium_coverage * 25 + (15 if len(strikes) >= 7 else 0))
    warnings = []
    if not coi_has_signal:
        quality = min(quality, 35)
        direction = "DATA GAP"
        warnings.append("Broker ne sab observed strikes par zero COI diya; OI-flow direction unavailable hai")
    elif coi_source == "LOCAL SNAPSHOT DELTA":
        quality = min(quality, 70)
        warnings.append(f"Broker COI unavailable tha; exact-contract local OI delta use hua ({delta_coverage}% coverage)")
    if premium_coverage < .5: warnings.append("Premium-change coverage low; writing/long-build classification provisional hai")
    if quality < 60: warnings.append("OI flow DATA GAP; direction ko entry permission na maanein")
    return {"direction": direction, "flow_score": round(flow_score, 1), "quality": quality,
            "legacy_pcr": round(put_oi / call_oi, 3) if call_oi else None,
            "fresh_coi_pcr": round(put_coi / call_coi, 3) if call_coi > 0 and put_coi >= 0 else None,
            "call_coi": call_coi, "put_coi": put_coi, "call_volume": call_vol, "put_volume": put_vol,
            "put_wall": float(put_wall["strike"]) if put_wall else None, "put_wall_health": put_health,
            "call_wall": float(call_wall["strike"]) if call_wall else None, "call_wall_health": call_health,
            "strikes_observed": len(strikes), "rows": enriched, "warnings": warnings,
            "coi_source": coi_source, "delta_coverage": delta_coverage}

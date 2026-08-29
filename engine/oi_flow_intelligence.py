"""Near-money OI-flow analysis that separates legacy walls from fresh flow."""
from __future__ import annotations

from statistics import median


def analyze_oi_flow(rows, spot, wing_count=5):
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
    coi_coverage = sum("oi_change" in r for r in focused) / max(len(focused), 1)
    premium_coverage = sum(r.get("premium_change_percent") is not None for r in focused) / max(len(focused), 1)
    quality = round(coi_coverage * 60 + premium_coverage * 25 + (15 if len(strikes) >= 7 else 0))
    warnings = []
    if premium_coverage < .5: warnings.append("Premium-change coverage low; writing/long-build classification provisional hai")
    if quality < 60: warnings.append("OI flow DATA GAP; direction ko entry permission na maanein")
    return {"direction": direction, "flow_score": round(flow_score, 1), "quality": quality,
            "legacy_pcr": round(put_oi / call_oi, 3) if call_oi else None,
            "fresh_coi_pcr": round(put_coi / call_coi, 3) if call_coi > 0 and put_coi >= 0 else None,
            "call_coi": call_coi, "put_coi": put_coi, "call_volume": call_vol, "put_volume": put_vol,
            "put_wall": float(put_wall["strike"]) if put_wall else None, "put_wall_health": put_health,
            "call_wall": float(call_wall["strike"]) if call_wall else None, "call_wall_health": call_health,
            "strikes_observed": len(strikes), "rows": enriched, "warnings": warnings}

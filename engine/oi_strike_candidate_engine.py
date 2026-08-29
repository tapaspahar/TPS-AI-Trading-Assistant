"""Transparent OI-flow strike shortlist for review-only decision support."""
from __future__ import annotations


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _evidence(name, value, reason):
    state = "UNKNOWN" if value is None else "TRUE" if value else "FALSE"
    return {"name": name, "state": state, "reason": reason}


def shortlist_oi_strike(chain, flow, spot, settings=None):
    """Return one liquid near-money strike or an explicit WAIT/DATA GAP result.

    OI flow supplies context, not a profit promise or order permission. The
    shortlist deliberately prefers ATM/slightly-ITM contracts and executable
    quotes over cheap remote-OTM premiums.
    """
    settings = settings or {}
    spot = _number(spot)
    direction = str((flow or {}).get("direction") or "BALANCED FLOW")
    flow_quality = int(_number((flow or {}).get("quality")))
    chain_quality = int(_number((chain or {}).get("data_quality")))
    option_type = "CE" if direction == "BULLISH FLOW" else "PE" if direction == "BEARISH FLOW" else None
    maximum_spread = _number(settings.get("maximum_option_spread_percent"), 8.0)
    minimum_volume = _number(settings.get("minimum_option_volume"), 100.0)
    base = {
        "state": "WAIT", "direction": direction, "option_type": option_type,
        "candidate": None, "entry_zone": None, "premium_invalidation": None,
        "target_1": None, "target_2": None, "spot_invalidation": None,
        "coverage": 0, "evidence": [], "warnings": [], "safer_alternative": None,
    }
    if not option_type:
        return {**base, "reason": "Fresh OI flow balanced hai; directional CE/PE shortlist nahi banayi gayi.",
                "safer_alternative": "Option Strategies page par defined-risk range structure review karein."}
    if spot <= 0:
        return {**base, "state": "DATA GAP", "reason": "Live underlying spot unavailable hai."}

    all_rows = [dict(row) for row in (flow or {}).get("rows", []) if row.get("option_type") == option_type]
    liquid = []
    for row in all_rows:
        bid, ask, ltp = _number(row.get("bid")), _number(row.get("ask")), _number(row.get("ltp"))
        spread = row.get("spread_percent")
        spread = _number(spread, 999.0) if spread is not None else 999.0
        if ask > 0 and bid > 0 and ask >= bid and spread <= maximum_spread and _number(row.get("volume")) >= minimum_volume:
            row["_entry"] = ask
            row["_spread"] = spread
            liquid.append(row)
    if not liquid:
        return {**base, "state": "DATA GAP", "reason":
                f"Koi near-money {option_type} live volume {minimum_volume:,.0f} aur spread ≤{maximum_spread:.1f}% gate pass nahi kar raha."}

    # Prefer slightly ITM/ATM, then liquidity and supportive premium/OI flow.
    def rank(row):
        strike = _number(row.get("strike"))
        is_itm = strike <= spot if option_type == "CE" else strike >= spot
        flow_bonus = 2 if row.get("flow") in {"LONG BUILDUP", "SHORT COVERING"} else 0
        return (is_itm, flow_bonus, -abs(strike - spot), _number(row.get("volume")), -row["_spread"])

    selected = max(liquid, key=rank)
    entry = selected["_entry"]
    spread_rupees = max(0.0, selected["_entry"] - _number(selected.get("bid")))
    risk = min(entry * .35, max(entry * .25, spread_rupees * 2.0))
    stop = max(0.05, entry - risk)
    entry_low = max(_number(selected.get("bid")), entry - spread_rupees * .25)
    support = (flow or {}).get("put_wall")
    resistance = (flow or {}).get("call_wall")
    spot_invalidation = resistance if option_type == "PE" else support
    wall_ok = ((flow or {}).get("call_wall_health") == "WEAKENING" if option_type == "CE"
               else (flow or {}).get("put_wall_health") == "WEAKENING")
    premium_flow = selected.get("flow")
    premium_supportive = premium_flow in {"LONG BUILDUP", "SHORT COVERING"} if premium_flow else None
    evidence = [
        _evidence("Directional fresh OI flow", True, f"{direction}; score {(flow or {}).get('flow_score', 0):+.1f}"),
        _evidence("OI-flow source quality", flow_quality >= 60, f"{flow_quality}/100"),
        _evidence("Option-chain quality", chain_quality >= 60, f"{chain_quality}/100"),
        _evidence("Executable liquidity", True, f"Volume {_number(selected.get('volume')):,.0f}; spread {selected['_spread']:.2f}%"),
        _evidence("Selected premium/OI flow supports buying", premium_supportive,
                  premium_flow or "Premium-change classification unavailable"),
        _evidence("Opposing OI wall is weakening", wall_ok,
                  f"PE {(flow or {}).get('put_wall_health', '-')}; CE {(flow or {}).get('call_wall_health', '-')}"),
    ]
    known = [item for item in evidence if item["state"] != "UNKNOWN"]
    passed = sum(item["state"] == "TRUE" for item in known)
    coverage = round(len(known) / len(evidence) * 100)
    score = round(passed / max(len(known), 1) * 100)
    warnings = list((flow or {}).get("warnings") or [])
    if flow_quality < 60 or chain_quality < 60:
        warnings.append("Source quality limited; candidate entry permission nahi hai")
    state = "REVIEW CANDIDATE" if score >= 80 and coverage >= 80 and not warnings else "WATCH CANDIDATE"

    strikes = sorted({_number(row.get("strike")) for row in liquid})
    strike = _number(selected.get("strike"))
    farther = [value for value in strikes if value > strike] if option_type == "CE" else [value for value in strikes if value < strike]
    hedge_strike = min(farther) if option_type == "CE" and farther else max(farther) if farther else None
    safer = (f"{strike:,.0f}-{hedge_strike:,.0f} {'Bull Call' if option_type == 'CE' else 'Bear Put'} Debit Spread review"
             if hedge_strike is not None else "Option Strategies page par live defined-risk vertical review karein")
    return {
        **base, "state": state, "reason": "Near-money liquidity aur fresh OI-flow evidence se shortlist.",
        "candidate": {**selected, "strike": strike},
        "entry_zone": (round(entry_low, 2), round(entry, 2)),
        "premium_invalidation": round(stop, 2), "target_1": round(entry + risk, 2),
        "target_2": round(entry + risk * 1.5, 2), "spot_invalidation": spot_invalidation,
        "coverage": coverage, "score": score, "evidence": evidence,
        "warnings": warnings, "safer_alternative": safer,
    }

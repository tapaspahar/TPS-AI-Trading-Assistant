"""Explainable put-call OI sentiment; context only, never an order instruction."""

from __future__ import annotations


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def analyze_pcr_sentiment(chain: dict, previous: dict | None = None) -> dict:
    call_oi = _number(chain.get("call_oi")) or 0.0
    put_oi = _number(chain.get("put_oi")) or 0.0
    pcr = _number(chain.get("pcr_oi"))
    volume_pcr = _number(chain.get("pcr_volume"))
    previous = previous or {}
    previous_call = _number(previous.get("call_oi"))
    previous_put = _number(previous.get("put_oi"))
    reported_call_change = _number(chain.get("call_oi_change"))
    reported_put_change = _number(chain.get("put_oi_change"))
    if reported_call_change or reported_put_change:
        call_change, put_change = reported_call_change, reported_put_change
    else:
        call_change = call_oi - previous_call if previous_call is not None else None
        put_change = put_oi - previous_put if previous_put is not None else None
    score, evidence, warnings = 0, [], []

    if pcr is None:
        warnings.append("OI-PCR unavailable")
    elif pcr >= 1.15:
        score += 2; evidence.append(f"Put OI dominates: OI-PCR {pcr:.2f}")
    elif pcr <= .85:
        score -= 2; evidence.append(f"Call OI dominates: OI-PCR {pcr:.2f}")
    else:
        evidence.append(f"OI-PCR {pcr:.2f} is balanced")

    if call_change is None or put_change is None:
        warnings.append("This is the first saved observation; Change in OI will appear after the next refresh")
    elif put_change > 0 >= call_change:
        score += 3; evidence.append("Put OI added while Call OI was flat/unwound")
    elif call_change > 0 >= put_change:
        score -= 3; evidence.append("Call OI added while Put OI was flat/unwound")
    elif call_change > 0 and put_change > 0:
        scale = max(abs(call_change), abs(put_change), 1)
        if put_change - call_change > scale * .10:
            score += 2; evidence.append("Both sides added OI, with stronger Put addition")
        elif call_change - put_change > scale * .10:
            score -= 2; evidence.append("Both sides added OI, with stronger Call addition")
        else:
            evidence.append("Call and Put OI are building together: range-writing context")
    elif call_change < 0 and put_change < 0:
        evidence.append("Both Call and Put OI are unwinding: transition/volatility context")

    # Volume identifies where activity is concentrated, but cannot tell buying
    # from writing on its own, so it receives only a small contextual weight.
    if volume_pcr is not None:
        if volume_pcr >= 1.20:
            score += 1; evidence.append(f"Put-side activity is heavier: Volume-PCR {volume_pcr:.2f}")
        elif volume_pcr <= .80:
            score -= 1; evidence.append(f"Call-side activity is heavier: Volume-PCR {volume_pcr:.2f}")
        else:
            evidence.append(f"Volume-PCR {volume_pcr:.2f} is balanced")

    if score >= 3:
        sentiment, direction = "BULLISH OI BIAS", "CE WATCH ONLY AFTER CHART CONFIRMATION"
    elif score <= -3:
        sentiment, direction = "BEARISH OI BIAS", "PE WATCH ONLY AFTER CHART CONFIRMATION"
    else:
        sentiment, direction = "BALANCED / RANGE OI", "WAIT FOR PRICE BREAKOUT OR BREAKDOWN"
    confidence = min(75, 35 + abs(score) * 7)
    warnings.append("OI does not reveal whether positions are bought or written; chart structure, price and volume must confirm direction")
    return {
        "sentiment": sentiment, "direction": direction, "score": score,
        "confidence": confidence, "call_oi_change": call_change, "put_oi_change": put_change,
        "evidence": evidence, "warnings": warnings,
        "support": chain.get("put_support"), "resistance": chain.get("call_resistance"),
    }

"""Read-only expiry/hedge strategy classification; never places broker orders."""
from __future__ import annotations


def analyze_expiry_strategy(spot, chain, environment, days_to_expiry):
    rows = chain.get("quote_rows") or []
    calls = [row for row in rows if row.get("option_type") == "CE" and row.get("ltp", 0) > 0]
    puts = [row for row in rows if row.get("option_type") == "PE" and row.get("ltp", 0) > 0]
    atm_call = min(calls, key=lambda row: abs(float(row["strike"]) - float(spot)), default=None)
    atm_put = min(puts, key=lambda row: abs(float(row["strike"]) - float(spot)), default=None)
    combined = round(float(atm_call["ltp"]) + float(atm_put["ltp"]), 2) if atm_call and atm_put else None
    high_risk = environment.get("regime") == "HIGH VOLATILITY" or (environment.get("event_risk") or {}).get("blocked")
    expiry = int(days_to_expiry) <= 0
    if high_risk and atm_call and atm_put:
        strategy = "ATM LONG STRADDLE WATCH" if expiry else "DEFINED-RISK HEDGE WATCH"
        reason = "Volatility/event risk can overwhelm a single directional option; verify combined premium and decay."
    elif environment.get("regime") == "LOW VOLATILITY":
        strategy = "NO LONG STRADDLE - DIRECTIONAL BREAKOUT ONLY"
        reason = "Low volatility and theta decay require confirmed VWAP/volume breakout before option buying."
    else:
        strategy = "DIRECTIONAL CE/PE"
        reason = "Use the independently stronger CE/PE side after checklist and hard-risk validation."
    return {
        "strategy": strategy, "reason": reason, "days_to_expiry": int(days_to_expiry),
        "atm_call": atm_call, "atm_put": atm_put, "combined_atm_premium": combined,
        "paper_execution_supported": strategy == "DIRECTIONAL CE/PE",
        "warning": "Multi-leg hedge output is research-only; TPS does not send broker orders.",
    }

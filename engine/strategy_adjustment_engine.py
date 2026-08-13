"""Read-only monitoring for a previously suggested defined-risk option plan.

The monitor never creates a naked option leg and never places an order.  It
compares the saved plan with fresh spot, trend and executable bid/ask quotes,
then returns HOLD, WATCH or EXIT/REASSESS instructions for manual review.
"""
from __future__ import annotations


def _reverse(action: str) -> str:
    return "BUY" if str(action).upper() == "SELL" else "SELL"


def _quote_map(latest: dict) -> dict:
    return {
        str(row.get("symbol")): row
        for row in (latest.get("chain") or {}).get("quote_rows", [])
        if row.get("symbol")
    }


def _close_price(leg: dict, quote: dict) -> float | None:
    """Use the conservative executable side for a hypothetical close."""
    if leg.get("action") == "BUY":
        value = quote.get("bid") or quote.get("ltp")
    else:
        value = quote.get("ask") or quote.get("ltp")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _estimated_pnl(plan: dict, latest: dict) -> float | None:
    quotes = _quote_map(latest)
    signed_close = 0.0
    lot_size = None
    for leg in plan.get("legs") or []:
        price = _close_price(leg, quotes.get(str(leg.get("symbol")), {}))
        if price is None:
            return None
        signed_close += price if leg.get("action") == "BUY" else -price
        lot_size = int(leg.get("lot_size") or 0) or lot_size
    if not lot_size:
        return None
    entry = float(plan.get("net_premium") or 0)
    per_unit = signed_close - entry if plan.get("net_type") == "DEBIT" else entry + signed_close
    return round(per_unit * lot_size, 2)


def _close_actions(plan: dict, scope: str = "ALL") -> list[dict]:
    actions = []
    for leg in plan.get("legs") or []:
        if scope in {"CE", "PE"} and leg.get("option_type") != scope:
            continue
        actions.append({
            "step": "CLOSE SAVED PLAN", "action": _reverse(leg.get("action")),
            "option_type": leg.get("option_type"), "strike": leg.get("strike"),
            "symbol": leg.get("symbol"), "reason": "Close the existing defined-risk leg; verify live quote first.",
        })
    return actions


def monitor_strategy_plan(saved_plan: dict, latest: dict) -> dict:
    """Assess a saved plan against a fresh analysis without executing trades."""
    if not saved_plan or not saved_plan.get("legs"):
        raise ValueError("Save a REVIEW CANDIDATE plan before starting monitoring.")
    spot = float(latest.get("spot") or 0)
    entry_spot = float(saved_plan.get("spot") or spot)
    expected = float(saved_plan.get("expected_daily_range") or latest.get("expected_daily_range") or 0)
    warning_distance = max(expected * .20, abs(entry_spot) * .001)
    strategy = str(saved_plan.get("strategy") or "")
    bias = str(latest.get("bias") or "RANGE / MIXED")
    breakevens = sorted(float(value) for value in (saved_plan.get("breakevens") or []))
    state, reason, scope = "HOLD", "Saved plan remains inside its monitored structure.", None

    if "Iron Condor" in strategy and len(breakevens) == 2:
        lower, upper = breakevens
        if spot <= lower or spot >= upper:
            state = "EXIT / REASSESS"
            scope = "PE" if spot <= lower else "CE"
            reason = f"Spot {spot:,.2f} breached the {'lower' if spot <= lower else 'upper'} breakeven {lower if spot <= lower else upper:,.2f}."
        elif spot - lower <= warning_distance or upper - spot <= warning_distance:
            state = "WATCH"
            reason = f"Spot {spot:,.2f} is within {warning_distance:,.2f} points of a condor breakeven. Do not add a naked hedge."
        elif bias != "RANGE / MIXED":
            state = "WATCH"
            reason = f"Fresh chart bias changed to {bias}; wait for a completed-candle breach before changing the condor."
    elif "Bull Call" in strategy:
        invalid = bias == "BEARISH" and spot < entry_spot - warning_distance
        if invalid:
            state, scope = "EXIT / REASSESS", "ALL"
            reason = f"Bullish thesis invalidated: fresh bias is BEARISH and spot moved below the monitored buffer from {entry_spot:,.2f}."
        elif bias != "BULLISH":
            state = "WATCH"; reason = f"Fresh bias is {bias}; do not add another call spread until direction reconfirms."
    elif "Bear Put" in strategy:
        invalid = bias == "BULLISH" and spot > entry_spot + warning_distance
        if invalid:
            state, scope = "EXIT / REASSESS", "ALL"
            reason = f"Bearish thesis invalidated: fresh bias is BULLISH and spot moved above the monitored buffer from {entry_spot:,.2f}."
        elif bias != "BEARISH":
            state = "WATCH"; reason = f"Fresh bias is {bias}; do not add another put spread until direction reconfirms."

    actions = _close_actions(saved_plan, scope or "ALL") if state == "EXIT / REASSESS" else []
    replacement = []
    if state == "EXIT / REASSESS" and latest.get("state") == "REVIEW CANDIDATE":
        for leg in latest.get("legs") or []:
            replacement.append({
                "step": "OPTIONAL NEW PLAN (ONLY AFTER CLOSE)", "action": leg.get("action"),
                "option_type": leg.get("option_type"), "strike": leg.get("strike"),
                "symbol": leg.get("symbol"), "reason": f"Fresh defined-risk {latest.get('strategy')} candidate; recheck margin and total risk.",
            })
    return {
        "state": state, "reason": reason, "spot": spot, "fresh_bias": bias,
        "estimated_pnl": _estimated_pnl(saved_plan, latest),
        "actions": actions + replacement,
        "warning": "Manual review only. Close/roll multi-leg positions as one controlled structure; never leave an uncovered short option.",
    }

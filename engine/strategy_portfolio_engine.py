"""Multi-strategy, defined-risk paper research for TPS Release 1.4.6.

The module compares payoff shapes from one live option-chain snapshot.  It is
scenario analysis, not a claim of historical win probability, and it never
places a broker order.
"""
from __future__ import annotations

def _quote(rows, strike, kind):
    return next((r for r in rows if float(r.get("strike", -1)) == float(strike)
                 and str(r.get("option_type")) == kind), None)


def _leg(action, row, lots=1):
    price = float(row.get("ask") or row.get("ltp") or 0) if action == "BUY" else float(row.get("bid") or row.get("ltp") or 0)
    return {"action": action, "option_type": row["option_type"], "strike": float(row["strike"]),
            "symbol": row.get("symbol", ""), "price": round(price, 2), "lots": int(lots),
            "lot_size": int(row.get("lot_size") or 1), "quantity": int(row.get("lot_size") or 1) * int(lots)}


def payoff_at_expiry(legs, settlement):
    """Return total cash P&L at expiry for a multi-leg position."""
    total = 0.0
    for leg in legs:
        intrinsic = max(0.0, settlement - float(leg["strike"])) if leg["option_type"] == "CE" else max(0.0, float(leg["strike"]) - settlement)
        unit = intrinsic - float(leg["price"])
        if leg["action"] == "SELL":
            unit = -unit
        total += unit * int(leg["quantity"])
    return round(total, 2)


def _analyse(name, family, bias, legs, spot, expected_move, note, bounded_profit=True):
    if not legs or any(float(x.get("price") or 0) <= 0 for x in legs):
        return None
    # Any short option must be bounded by another same-type long option or by
    # an opposite long option in an iron structure.  All builders below meet
    # this rule; keep the explicit flag visible in saved evidence.
    width = max(float(x["strike"]) for x in legs) - min(float(x["strike"]) for x in legs)
    span = max(float(expected_move or 0) * 1.75, width * 2.5, float(spot) * .025)
    points = [float(spot) - span + (2 * span * i / 160) for i in range(161)]
    values = [payoff_at_expiry(legs, point) for point in points]
    max_profit, max_loss = max(values), abs(min(values))
    if max_loss <= 0:
        return None
    profitable = [point for point, value in zip(points, values) if value > 0]
    breakevens = []
    for i in range(1, len(points)):
        if (values[i - 1] <= 0 < values[i]) or (values[i - 1] >= 0 > values[i]):
            breakevens.append(round((points[i - 1] + points[i]) / 2, 2))
    ratio = round(max_profit / max_loss, 2) if max_loss else 0
    win_ratio = round(len(profitable) / len(points) * 100, 1)
    profit_zone = "No positive scenario in tested range"
    if profitable:
        profit_zone = f"{min(profitable):,.2f} to {max(profitable):,.2f} settlement zone"
    return {"strategy": name, "family": family, "bias": bias, "legs": legs,
            "max_profit": round(max_profit, 2), "max_loss": round(max_loss, 2),
            "payoff_ratio": ratio, "scenario_profitable_percent": win_ratio,
            "breakevens": breakevens, "profit_zone": profit_zone,
            "scenario_low": round(points[0], 2), "scenario_high": round(points[-1], 2),
            "explanation": note, "defined_risk": True, "bounded_profit": bounded_profit}


def build_strategy_catalog(result, settings=None):
    """Build and rank many same-expiry, fully-defined-risk candidates."""
    settings = settings or {}
    chain = result.get("chain") or {}
    minimum_volume = float(settings.get("minimum_option_volume", 0))
    rows = [r for r in chain.get("quote_rows", []) if float(r.get("ltp") or 0) > 0
            and float(r.get("volume") or 0) >= minimum_volume]
    strikes = sorted({float(r["strike"]) for r in rows})
    if len(strikes) < 5:
        return []
    spot = float(result.get("spot") or 0)
    atm_i = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
    if atm_i < 2 or atm_i + 2 >= len(strikes):
        return []
    k2l, kl, ka, kh, k2h = strikes[atm_i - 2:atm_i + 3]
    q = lambda strike, kind: _quote(rows, strike, kind)
    candidates = []

    def add(name, family, bias, specs, note, bounded_profit=True):
        selected = [(action, q(strike, kind), lots) for action, strike, kind, lots in specs]
        if any(row is None for _action, row, _lots in selected):
            return
        item = _analyse(name, family, bias, [_leg(a, r, n) for a, r, n in selected], spot,
                        chain.get("expected_move") or result.get("expected_daily_range"), note, bounded_profit)
        if item:
            candidates.append(item)

    add("Bull Call Debit Spread", "DIRECTIONAL", "BULLISH", [("BUY", ka, "CE", 1), ("SELL", kh, "CE", 1)], "Bullish move; debit is the predefined maximum loss.")
    add("Bear Put Debit Spread", "DIRECTIONAL", "BEARISH", [("BUY", ka, "PE", 1), ("SELL", kl, "PE", 1)], "Bearish move; debit is the predefined maximum loss.")
    add("Bull Put Credit Spread", "DIRECTIONAL INCOME", "BULLISH", [("BUY", k2l, "PE", 1), ("SELL", kl, "PE", 1)], "Profits when settlement stays above the short put; long put caps loss.")
    add("Bear Call Credit Spread", "DIRECTIONAL INCOME", "BEARISH", [("SELL", kh, "CE", 1), ("BUY", k2h, "CE", 1)], "Profits when settlement stays below the short call; long call caps loss.")
    add("Iron Condor", "RANGE INCOME", "RANGE / MIXED", [("BUY", k2l, "PE", 1), ("SELL", kl, "PE", 1), ("SELL", kh, "CE", 1), ("BUY", k2h, "CE", 1)], "Defined range income; both tails are hedged.")
    add("Iron Butterfly", "TIGHT RANGE", "RANGE / MIXED", [("BUY", kl, "PE", 1), ("SELL", ka, "PE", 1), ("SELL", ka, "CE", 1), ("BUY", kh, "CE", 1)], "Highest expiry payoff near ATM; both wings cap loss.")
    add("Long Call Butterfly", "BULLISH TARGET", "BULLISH", [("BUY", kl, "CE", 1), ("SELL", ka, "CE", 2), ("BUY", kh, "CE", 1)], "Defined-risk bullish target structure around ATM.")
    add("Long Put Butterfly", "BEARISH TARGET", "BEARISH", [("BUY", kh, "PE", 1), ("SELL", ka, "PE", 2), ("BUY", kl, "PE", 1)], "Defined-risk bearish target structure around ATM.")
    add("Long Straddle", "VOLATILITY", "LARGE MOVE", [("BUY", ka, "CE", 1), ("BUY", ka, "PE", 1)], "Defined loss equals both premiums; profit is unbounded and the displayed benefit is scenario-only.", False)
    add("Long Strangle", "VOLATILITY", "LARGE MOVE", [("BUY", kh, "CE", 1), ("BUY", kl, "PE", 1)], "Lower-cost defined-risk volatility structure; profit is unbounded and the displayed benefit is scenario-only.", False)

    active_bias = str(result.get("bias") or "RANGE / MIXED")
    risk_cap = float(settings.get("capital", 100000)) * float(settings.get("risk_percent", 1)) / 100
    for item in candidates:
        alignment = 25 if item["bias"] == active_bias else 18 if active_bias == "RANGE / MIXED" and "RANGE" in item["bias"] else 0
        item["market_alignment"] = item["bias"] == active_bias or (active_bias == "RANGE / MIXED" and "RANGE" in item["bias"])
        item["eligible"] = bool(item["bounded_profit"]) and item["max_loss"] <= risk_cap and item["scenario_profitable_percent"] >= 20
        item["rank_score"] = round(min(100, alignment + min(35, item["scenario_profitable_percent"] * .45) + min(30, item["payoff_ratio"] * 15) + (10 if item["max_loss"] <= risk_cap else 0)))
        item["risk_cap"] = round(risk_cap, 2)
        item["suitability"] = (
            "Fully bounded payoff; eligible for paper validation."
            if item["eligible"] and item["market_alignment"] else
            "Defined loss but unbounded profit; comparison only."
            if not item["bounded_profit"] else
            "Watch only: market bias or configured risk cap does not align."
        )
    return sorted(candidates, key=lambda x: (x["eligible"], x["market_alignment"], x["rank_score"]), reverse=True)

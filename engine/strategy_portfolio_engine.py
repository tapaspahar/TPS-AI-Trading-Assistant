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


def fund_requirement_profile(legs, maximum_loss):
    """Separate payoff funding from an exchange/broker margin quote.

    Premium cash-flow and expiry maximum loss can be calculated from the
    captured option quotes.  SPAN/exposure margin cannot: it also depends on
    the broker, product, existing portfolio and execution order.  Never label
    the payoff reserve as an exact account-margin requirement.
    """
    net_debit = sum(
        (1 if leg["action"] == "BUY" else -1)
        * float(leg["price"])
        * int(leg["quantity"])
        for leg in legs
    )
    has_short_leg = any(leg["action"] == "SELL" for leg in legs)
    premium_payable = max(0.0, net_debit)
    premium_receivable = max(0.0, -net_debit)
    risk_reserve = max(0.0, float(maximum_loss or 0))
    return {
        "net_premium_payable": round(premium_payable, 2),
        "net_premium_receivable": round(premium_receivable, 2),
        "payoff_risk_reserve": round(risk_reserve, 2),
        "broker_margin_required": None,
        "broker_margin_status": (
            "NOT FETCHED — broker basket/SPAN margin quote required"
            if has_short_leg
            else "PREMIUM-ONLY — add brokerage, taxes and execution buffer"
        ),
        "requires_broker_margin_quote": has_short_leg,
        "fund_estimate_basis": "PAYOFF RISK RESERVE, NOT BROKER BLOCKED MARGIN",
    }


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
    funding = fund_requirement_profile(legs, max_loss)
    debit = funding["net_premium_payable"] - funding["net_premium_receivable"]
    # Retain this legacy field for database compatibility and ranking.  Its
    # meaning is now explicit: a payoff risk reserve, never an exact broker
    # margin promise.
    capital_required = funding["payoff_risk_reserve"]
    return {"strategy": name, "family": family, "bias": bias, "legs": legs,
            "max_profit": round(max_profit, 2), "max_loss": round(max_loss, 2),
            "entry_cashflow": round(-debit, 2), "capital_required": round(capital_required, 2),
            "return_on_capital": round(max_profit / capital_required * 100, 1) if capital_required else 0,
            "payoff_ratio": ratio, "scenario_profitable_percent": win_ratio,
            "breakevens": breakevens, "profit_zone": profit_zone,
            "scenario_low": round(points[0], 2), "scenario_high": round(points[-1], 2),
            "explanation": note, "defined_risk": True, "bounded_profit": bounded_profit,
            **funding}


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
    q = lambda strike, kind: _quote(rows, strike, kind)
    candidates = []
    aliases = {
        "Bull Call Debit Spread": "Cutie Rocket Shield",
        "Bear Put Debit Spread": "Cutie Downhill Guard",
        "Bull Put Credit Spread": "Cutie Green Floor",
        "Bear Call Credit Spread": "Cutie Red Roof",
        "Iron Condor": "Cutie Peace Zone",
        "Iron Butterfly": "Cutie Pin Master",
        "Long Call Butterfly": "Cutie Bullseye Up",
        "Long Put Butterfly": "Cutie Bullseye Down",
        "Long Straddle": "Cutie Big Move Hunter",
        "Long Strangle": "Cutie Wide Move Hunter",
    }

    def add(name, family, bias, specs, note, bounded_profit=True):
        selected = [(action, q(strike, kind), lots) for action, strike, kind, lots in specs]
        if any(row is None for _action, row, _lots in selected):
            return
        item = _analyse(name, family, bias, [_leg(a, r, n) for a, r, n in selected], spot,
                        chain.get("expected_move") or result.get("expected_daily_range"), note, bounded_profit)
        if item:
            item["friendly_name"] = aliases.get(name, name)
            item["structure_key"] = "|".join(
                f"{leg['action']}:{leg['option_type']}:{leg['strike']:g}:{leg['lots']}" for leg in item["legs"]
            )
            candidates.append(item)

    # Explore multiple liquid strike widths instead of treating one ATM shape
    # as representative. Keep the search bounded for a responsive live UI.
    low = max(1, atm_i - 4); high = min(len(strikes) - 1, atm_i + 4)
    centres = range(max(1, atm_i - 2), min(len(strikes) - 1, atm_i + 3))
    for centre in centres:
        ka = strikes[centre]
        for wing in (1, 2):
            if centre - wing < 0 or centre + wing >= len(strikes):
                continue
            kl, kh = strikes[centre - wing], strikes[centre + wing]
            add("Bull Call Debit Spread", "DIRECTIONAL", "BULLISH", [("BUY", ka, "CE", 1), ("SELL", kh, "CE", 1)], "Bullish move; debit is the predefined maximum loss.")
            add("Bear Put Debit Spread", "DIRECTIONAL", "BEARISH", [("BUY", ka, "PE", 1), ("SELL", kl, "PE", 1)], "Bearish move; debit is the predefined maximum loss.")
            add("Long Call Butterfly", "BULLISH TARGET", "BULLISH", [("BUY", kl, "CE", 1), ("SELL", ka, "CE", 2), ("BUY", kh, "CE", 1)], "Defined-risk bullish target structure around the middle strike.")
            add("Long Put Butterfly", "BEARISH TARGET", "BEARISH", [("BUY", kh, "PE", 1), ("SELL", ka, "PE", 2), ("BUY", kl, "PE", 1)], "Defined-risk bearish target structure around the middle strike.")
        add("Long Straddle", "VOLATILITY", "LARGE MOVE", [("BUY", ka, "CE", 1), ("BUY", ka, "PE", 1)], "Defined loss equals both premiums; scenario benefit is not capped.", False)
    # Credit and range structures need an additional hedge strike beyond each short leg.
    for short_i in range(low, min(atm_i + 1, high)):
        add("Bull Put Credit Spread", "DIRECTIONAL INCOME", "BULLISH", [("BUY", strikes[short_i - 1], "PE", 1), ("SELL", strikes[short_i], "PE", 1)], "Settlement above the short put benefits; long put defines maximum loss.")
    for short_i in range(max(atm_i + 1, low), high):
        add("Bear Call Credit Spread", "DIRECTIONAL INCOME", "BEARISH", [("SELL", strikes[short_i], "CE", 1), ("BUY", strikes[short_i + 1], "CE", 1)], "Settlement below the short call benefits; long call defines maximum loss.")
    for distance in (1, 2, 3):
        if atm_i - distance - 1 < 0 or atm_i + distance + 1 >= len(strikes):
            continue
        lp, sp, sc, lc = strikes[atm_i-distance-1], strikes[atm_i-distance], strikes[atm_i+distance], strikes[atm_i+distance+1]
        add("Iron Condor", "RANGE INCOME", "RANGE / MIXED", [("BUY", lp, "PE", 1), ("SELL", sp, "PE", 1), ("SELL", sc, "CE", 1), ("BUY", lc, "CE", 1)], "Defined range income; both tails are hedged.")
    if atm_i > 0 and atm_i + 1 < len(strikes):
        kl, ka, kh = strikes[atm_i-1], strikes[atm_i], strikes[atm_i+1]
        add("Iron Butterfly", "TIGHT RANGE", "RANGE / MIXED", [("BUY", kl, "PE", 1), ("SELL", ka, "PE", 1), ("SELL", ka, "CE", 1), ("BUY", kh, "CE", 1)], "Highest expiry payoff near ATM; both wings cap loss.")
        add("Long Strangle", "VOLATILITY", "LARGE MOVE", [("BUY", kh, "CE", 1), ("BUY", kl, "PE", 1)], "Lower-cost defined-risk volatility structure; scenario benefit is not capped.", False)

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
    unique = {item["structure_key"]: item for item in candidates}
    return sorted(unique.values(), key=lambda x: (x["eligible"], x["market_alignment"], x["rank_score"], -x["capital_required"]), reverse=True)[:30]

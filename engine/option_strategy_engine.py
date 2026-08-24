"""Defined-risk option-strategy research from live market evidence.

Suggestions are review-only.  The engine never places orders and deliberately
avoids uncovered option selling.
"""
from __future__ import annotations

from engine.greeks_engine import calculate_greeks
from engine.market_structure import analyze_candles


def _price(row, action):
    if action == "BUY":
        return float(row.get("ask") or 0)
    return float(row.get("bid") or 0)


def _row(rows, strike, option_type):
    return next((item for item in rows if item["strike"] == strike and item["option_type"] == option_type), None)


def _direction(capture, candles):
    close = float(capture["close"])
    ema5, ema20, ema50 = (float(capture[key]) for key in ("ema_5", "ema_20", "ema_50"))
    vwap = float(capture["vwap"]) if capture.get("vwap") else None
    trend = float(capture["supertrend"])
    structure = analyze_candles(candles)["state"]
    bull = sum((ema5 > ema20 > ema50, vwap is not None and close > vwap, close > trend, structure.startswith("Bullish")))
    bear = sum((ema5 < ema20 < ema50, vwap is not None and close < vwap, close < trend, structure.startswith("Bearish")))
    if bull >= 3 and bull > bear:
        return "BULLISH", bull, structure
    if bear >= 3 and bear > bull:
        return "BEARISH", bear, structure
    return "RANGE / MIXED", max(bull, bear), structure


def _fibonacci_context(candles, spot, direction):
    """Return supporting completed-candle retracement evidence, never permission."""
    rows = list(candles or [])[-60:]
    if len(rows) < 10:
        return {"state": "DATA GAP", "alignment": False, "reason": "At least 10 completed candles are required"}
    highs = [float(row.get("high", row.get("close"))) for row in rows]
    lows = [float(row.get("low", row.get("close"))) for row in rows]
    swing_high, swing_low = max(highs), min(lows)
    width = swing_high - swing_low
    if width <= 0:
        return {"state": "DATA GAP", "alignment": False, "reason": "No usable swing range"}
    impulse = "BULLISH" if lows.index(swing_low) < highs.index(swing_high) else "BEARISH"
    ratios = (0.236, 0.382, 0.5, 0.618, 0.786)
    levels = {
        str(ratio): round(swing_high - width * ratio, 2) if impulse == "BULLISH"
        else round(swing_low + width * ratio, 2)
        for ratio in ratios
    }
    nearest_ratio = min(ratios, key=lambda ratio: abs(float(spot) - levels[str(ratio)]))
    nearest = levels[str(nearest_ratio)]
    tolerance = max(width * .06, float(spot) * .0005)
    in_value_zone = 0.382 <= nearest_ratio <= 0.618 and abs(float(spot) - nearest) <= tolerance
    aligned = direction in {"BULLISH", "BEARISH"} and impulse == direction and in_value_zone
    return {
        "state": "ALIGNED" if aligned else "CONTEXT ONLY", "alignment": aligned,
        "impulse": impulse, "swing_high": round(swing_high, 2), "swing_low": round(swing_low, 2),
        "nearest_ratio": round(nearest_ratio * 100, 1), "nearest_level": nearest, "levels": levels,
        "reason": f"{impulse} swing; price nearest {nearest_ratio * 100:.1f}% retracement {nearest:,.2f}",
    }


def _gate_simulation(score, passed, total, settings, hard_blockers):
    current_score = max(0, min(int(settings.get("trade_plan_min_score", 95)), 100))
    current_matches = max(1, min(int(settings.get("tps_required_matches", 5)), total))
    adaptive = settings.get("tps_match_mode", "adaptive") == "adaptive"
    scenarios = (
        ("Active adaptive gate" if adaptive else "Current saved fixed gate",
         60 if adaptive else current_score, min(4, total) if adaptive else current_matches),
        ("Saved fixed-gate comparison" if adaptive else "Adaptive paper-study gate",
         current_score if adaptive else 60, current_matches if adaptive else min(4, total)),
        ("Exploratory paper study", 40, min(3, total)),
    )
    return [{
        "name": name, "score_gate": score_gate, "matches_gate": matches_gate,
        "would_qualify": score >= score_gate and passed >= matches_gate and not hard_blockers,
        "result": ("WOULD QUALIFY" if score >= score_gate and passed >= matches_gate and not hard_blockers
                   else "STILL BLOCKED" if hard_blockers else "NOT ENOUGH EVIDENCE"),
    } for name, score_gate, matches_gate in scenarios]


def _leg(action, row, lots=1):
    return {
        "action": action, "option_type": row["option_type"], "strike": row["strike"],
        "symbol": row["symbol"], "price": round(_price(row, action), 2),
        "lots": lots, "lot_size": int(row["lot_size"]), "quantity": int(row["lot_size"]) * lots,
    }


def _portfolio_greeks(plan, rows, spot):
    """Aggregate estimated Greeks for a defined-risk plan when inputs permit."""
    totals = {"delta": 0.0, "gamma": 0.0, "theta_per_day": 0.0, "vega_per_1pct": 0.0}
    calculated = 0
    by_symbol = {row.get("symbol"): row for row in rows}
    for leg in plan.get("legs") or []:
        row = by_symbol.get(leg.get("symbol")) or {}
        estimate = calculate_greeks(
            spot, leg.get("strike"), row.get("ltp") or leg.get("price"),
            row.get("expiry"), leg.get("option_type"),
        )
        if not estimate:
            continue
        sign = 1 if leg.get("action") == "BUY" else -1
        quantity = int(leg.get("quantity") or 0)
        leg["greeks_estimate"] = estimate
        for key in totals:
            totals[key] += sign * float(estimate[key]) * quantity
        calculated += 1
    if calculated != len(plan.get("legs") or []):
        return None
    return {key: round(value, 4 if key == "gamma" else 2) for key, value in totals.items()}


def _debit_spread(rows, strikes, spot, direction):
    atm_index = min(range(len(strikes)), key=lambda index: abs(strikes[index] - spot))
    width_steps = 2 if len(strikes) >= 5 else 1
    if direction == "BULLISH":
        buy_strike = strikes[atm_index]
        sell_index = min(len(strikes) - 1, atm_index + width_steps)
        sell_strike, option_type, name = strikes[sell_index], "CE", "Bull Call Debit Spread"
    else:
        buy_strike = strikes[atm_index]
        sell_index = max(0, atm_index - width_steps)
        sell_strike, option_type, name = strikes[sell_index], "PE", "Bear Put Debit Spread"
    buy, sell = _row(rows, buy_strike, option_type), _row(rows, sell_strike, option_type)
    if not buy or not sell:
        return None
    buy_price, sell_price = _price(buy, "BUY"), _price(sell, "SELL")
    width = abs(sell_strike - buy_strike)
    debit = buy_price - sell_price
    if min(buy_price, sell_price) <= 0 or debit <= 0 or debit >= width:
        return None
    lot_size = int(buy["lot_size"])
    return {
        "strategy": name, "net_type": "DEBIT", "net_premium": round(debit, 2),
        "max_loss": round(debit * lot_size, 2), "max_profit": round((width - debit) * lot_size, 2),
        "payoff_ratio": round((width - debit) / debit, 2),
        "breakevens": [round(buy_strike + debit, 2) if direction == "BULLISH" else round(buy_strike - debit, 2)],
        "legs": [_leg("BUY", buy), _leg("SELL", sell)],
    }


def _iron_condor(rows, strikes, spot, support, resistance):
    below = [strike for strike in strikes if strike < spot]
    above = [strike for strike in strikes if strike > spot]
    if len(below) < 2 or len(above) < 2:
        return None
    # Keep one quoted strike beyond every short leg so the suggestion is
    # always a fully defined-risk spread even when the implied range lies
    # outside the focused quote window.
    short_put_choices, short_call_choices = below[1:], above[:-1]
    short_put = min(short_put_choices, key=lambda strike: abs(strike - support)) if support and support < spot else short_put_choices[-1]
    short_call = min(short_call_choices, key=lambda strike: abs(strike - resistance)) if resistance and resistance > spot else short_call_choices[0]
    put_index, call_index = strikes.index(short_put), strikes.index(short_call)
    if put_index < 1 or call_index >= len(strikes) - 1:
        return None
    long_put, long_call = strikes[put_index - 1], strikes[call_index + 1]
    selected = (
        _row(rows, long_put, "PE"), _row(rows, short_put, "PE"),
        _row(rows, short_call, "CE"), _row(rows, long_call, "CE"),
    )
    if not all(selected):
        return None
    lp, sp, sc, lc = selected
    credit = _price(sp, "SELL") + _price(sc, "SELL") - _price(lp, "BUY") - _price(lc, "BUY")
    width = max(short_put - long_put, long_call - short_call)
    if credit <= 0 or credit >= width or any(_price(row, action) <= 0 for row, action in ((lp, "BUY"), (sp, "SELL"), (sc, "SELL"), (lc, "BUY"))):
        return None
    lot_size = int(sp["lot_size"])
    return {
        "strategy": "Defined-Risk Iron Condor", "net_type": "CREDIT", "net_premium": round(credit, 2),
        "max_loss": round((width - credit) * lot_size, 2), "max_profit": round(credit * lot_size, 2),
        "payoff_ratio": round(credit / (width - credit), 2),
        "breakevens": [round(short_put - credit, 2), round(short_call + credit, 2)],
        "legs": [_leg("BUY", lp), _leg("SELL", sp), _leg("SELL", sc), _leg("BUY", lc)],
    }


def _management_reference(plan):
    """Return conservative paper-management references, never guarantees."""
    is_debit = plan.get("net_type") == "DEBIT"
    target_fraction = .35 if is_debit else .50
    loss_review_fraction = .50 if is_debit else .40
    max_profit = float(plan.get("max_profit") or 0)
    max_loss = float(plan.get("max_loss") or 0)
    return {
        "target_profit": round(max_profit * target_fraction, 2),
        "target_profit_percent_of_max": round(target_fraction * 100),
        "loss_review_amount": round(max_loss * loss_review_fraction, 2),
        "loss_review_percent_of_max": round(loss_review_fraction * 100),
        "defined_max_loss": round(max_loss, 2),
        "note": "Paper-management reference only; slippage, gaps and execution can change realised P&L.",
    }


def recommend_option_strategy(symbol, spot, candles, capture, chain, environment, settings):
    """Return one executable-shape research suggestion or an explicit wait."""
    minimum_volume = float(settings.get("minimum_option_volume", 100))
    maximum_spread = float(settings.get("maximum_option_spread_percent", 8))
    rows = []
    for row in chain.get("quote_rows", []):
        bid, ask = float(row.get("bid") or 0), float(row.get("ask") or 0)
        spread = (ask - bid) / max((ask + bid) / 2, .01) * 100 if bid > 0 and ask >= bid else 999
        if float(row.get("ltp") or 0) > 0 and float(row.get("volume") or 0) >= minimum_volume and spread <= maximum_spread:
            rows.append(row)
    strikes = sorted({row["strike"] for row in rows})
    direction, votes, structure = _direction(capture, candles)
    fib = _fibonacci_context(candles, spot, direction)
    regime = environment.get("regime", "UNAVAILABLE")
    vix_zone = environment.get("vix_historical_regime") or environment.get("vix_zone", "UNAVAILABLE")
    reasons = [
        f"Direction {direction}: {votes}/4 chart votes; structure {structure}",
        f"Regime {regime}; India VIX {environment.get('vix') or 'unavailable'} ({vix_zone})",
        f"OI support {chain.get('put_support') or '-'}; resistance {chain.get('call_resistance') or '-'}; OI PCR {chain.get('pcr_oi') or '-'}",
        f"ATM expected move {chain.get('expected_move') or '-'}; focused max pain {chain.get('focused_max_pain') or '-'}; chain quality {chain.get('data_quality', 0)}/100",
        f"Fibonacci context: {fib.get('reason')}; state {fib.get('state')}",
    ]
    base = {
        "symbol": symbol, "spot": float(spot), "bias": direction, "regime": regime,
        "vix": environment.get("vix"), "vix_zone": vix_zone,
        "expected_daily_range": environment.get("expected_daily_range"),
        "remaining_expected_range": environment.get("remaining_expected_range"),
        "vix_expected_low": round(float(spot) - float(environment.get("expected_daily_range") or 0), 2) if environment.get("expected_daily_range") else None,
        "vix_expected_high": round(float(spot) + float(environment.get("expected_daily_range") or 0), 2) if environment.get("expected_daily_range") else None,
        "regular_move_target_points": environment.get("regular_move_target_points"),
        "fibonacci": fib, "reasons": reasons, "warning": "Cutie keh rahi hai: ye review-only defined-risk research hai. Manual action se pehle broker me live prices, liquidity, margin aur payoff verify kijiye.",
    }
    if environment.get("time_state") == "LATE SESSION" or vix_zone in {"EXTREME RISK", "EXTREME VOLATILITY"}:
        return {**base, "state": "WAIT", "strategy": "No new strategy", "legs": [], "blockers": ["Late session or extreme-VIX risk blocks a new strategy"]}
    if len(strikes) < 4:
        return {**base, "state": "WAIT", "strategy": "No liquid structure", "legs": [], "blockers": ["Insufficient live option strikes/prices"]}
    plan = None
    soft_warnings = []
    if not environment.get("regular_move_available", True):
        soft_warnings.append("VIX-implied daily range is substantially consumed; new entry needs a fresh breakout/reversal confirmation")
    if direction in {"BULLISH", "BEARISH"}:
        plan = _debit_spread(rows, strikes, float(spot), direction)
    elif direction == "RANGE / MIXED" and regime in {"SIDEWAYS / TRANSITION", "LOW VOLATILITY", "HIGH VOLATILITY"}:
        vix_move = float(environment.get("expected_daily_range") or 0)
        # Place the short wings around the more conservative of the VIX estimate
        # and live ATM-straddle estimate; OI zones remain confirmation context.
        option_move = float(chain.get("expected_move") or 0)
        boundary_move = max(vix_move, option_move)
        lower = float(spot) - boundary_move if boundary_move else chain.get("put_support")
        upper = float(spot) + boundary_move if boundary_move else chain.get("call_resistance")
        plan = _iron_condor(rows, strikes, float(spot), lower, upper)
    if not plan:
        blocker = "Live direction/regime and tradeable spread prices do not form a valid defined-risk payoff"
        return {**base, "state": "DATA GAP / WAIT", "strategy": "No clean limited-risk setup", "legs": [],
                "blockers": [blocker], "what_if": _gate_simulation(0, 0, 7, settings, [blocker])}
    risk_cap = float(settings.get("capital", 0)) * float(settings.get("risk_percent", 1)) / 100
    within_cap = plan["max_loss"] <= risk_cap
    payoff_ok = plan["payoff_ratio"] >= .30
    evidence = [
        ("Chart direction", direction in {"BULLISH", "BEARISH"} and votes >= 3),
        ("Market structure", structure.startswith(direction.title()) if direction in {"BULLISH", "BEARISH"} else "range" in structure.lower() or "mixed" in structure.lower()),
        ("Fibonacci alignment", bool(fib.get("alignment"))),
        ("OI context", bool(chain.get("put_support") or chain.get("call_resistance"))),
        ("Option-chain quality", float(chain.get("data_quality") or 0) >= 50),
        ("Movement budget", bool(environment.get("regular_move_available", True))),
        ("Defined-risk payoff", payoff_ok),
    ]
    passed = sum(bool(value) for _name, value in evidence); total = len(evidence)
    evidence_score = round(passed / total * 100)
    adaptive_gate = settings.get("tps_match_mode", "adaptive") == "adaptive"
    requested_score = 60 if adaptive_gate else max(0, min(int(settings.get("trade_plan_min_score", 95)), 100))
    requested_matches = min(4, total) if adaptive_gate else max(1, min(int(settings.get("tps_required_matches", 5)), total))
    gate_passed = evidence_score >= requested_score and passed >= requested_matches
    state = ("RISK BLOCKED" if not within_cap or not payoff_ok else
             "REVIEW CANDIDATE" if gate_passed and not soft_warnings else "WATCH CANDIDATE")
    blockers = []
    if not within_cap:
        blockers.append(f"One-lot maximum loss {plan['max_loss']:,.2f} exceeds risk cap {risk_cap:,.2f}")
    if not payoff_ok:
        blockers.append(f"Maximum profit/loss ratio {plan['payoff_ratio']:.2f} is below 0.30")
    if not gate_passed:
        blockers.append(f"Evidence gate: {passed}/{total} checks and score {evidence_score}/100; saved gate requires {requested_matches} and {requested_score}/100")
    blockers.extend(soft_warnings)
    confidence = min(85, 45 + votes * 8 + (8 if environment.get("regular_move_available", True) else 0))
    portfolio_greeks = _portfolio_greeks(plan, rows, float(spot))
    management = _management_reference(plan)
    candidate_side = "CE" if direction == "BULLISH" else "PE" if direction == "BEARISH" else "HEDGED RANGE"
    hard_blockers = [item for item in blockers if item.startswith("One-lot") or item.startswith("Maximum profit")]
    return {**base, **plan, "state": state, "confidence": confidence, "risk_cap": round(risk_cap, 2),
            "risk_within_cap": within_cap, "portfolio_greeks_estimate": portfolio_greeks,
            "candidate_side": candidate_side, "management_reference": management, "blockers": blockers,
            "strategy_evidence": [{"name": name, "passed": bool(value)} for name, value in evidence],
            "strategy_score": evidence_score, "strategy_passed": passed, "strategy_total": total,
            "what_if": _gate_simulation(evidence_score, passed, total, settings, hard_blockers)}

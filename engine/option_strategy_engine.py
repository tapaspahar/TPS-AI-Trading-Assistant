"""Defined-risk option-strategy research from live market evidence.

Suggestions are review-only.  The engine never places orders and deliberately
avoids uncovered option selling.
"""
from __future__ import annotations

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


def _leg(action, row, lots=1):
    return {
        "action": action, "option_type": row["option_type"], "strike": row["strike"],
        "symbol": row["symbol"], "price": round(_price(row, action), 2),
        "lots": lots, "lot_size": int(row["lot_size"]), "quantity": int(row["lot_size"]) * lots,
    }


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
    short_put = min(below, key=lambda strike: abs(strike - support)) if support and support < spot else below[-1]
    short_call = min(above, key=lambda strike: abs(strike - resistance)) if resistance and resistance > spot else above[0]
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
    regime = environment.get("regime", "UNAVAILABLE")
    vix_zone = environment.get("vix_zone", "UNAVAILABLE")
    reasons = [
        f"Direction {direction}: {votes}/4 chart votes; structure {structure}",
        f"Regime {regime}; India VIX {environment.get('vix') or 'unavailable'} ({vix_zone})",
        f"OI support {chain.get('put_support') or '-'}; resistance {chain.get('call_resistance') or '-'}; OI PCR {chain.get('pcr_oi') or '-'}",
    ]
    base = {
        "symbol": symbol, "spot": float(spot), "bias": direction, "regime": regime,
        "vix": environment.get("vix"), "vix_zone": vix_zone,
        "expected_daily_range": environment.get("expected_daily_range"),
        "remaining_expected_range": environment.get("remaining_expected_range"),
        "regular_move_target_points": environment.get("regular_move_target_points"),
        "reasons": reasons, "warning": "Review-only defined-risk research. Verify live prices, liquidity, margin and payoff in the broker before any manual action.",
    }
    if environment.get("time_state") == "LATE SESSION" or vix_zone == "EXTREME RISK":
        return {**base, "state": "WAIT", "strategy": "No new strategy", "legs": [], "blockers": ["Late session or extreme-VIX risk blocks a new strategy"]}
    if len(strikes) < 4:
        return {**base, "state": "WAIT", "strategy": "No liquid structure", "legs": [], "blockers": ["Insufficient live option strikes/prices"]}
    plan = None
    if not environment.get("regular_move_available", True):
        return {**base, "state": "WAIT", "strategy": "Range budget consumed", "legs": [], "blockers": ["VIX-implied daily range is substantially consumed; the regular-move objective has insufficient room"]}
    if direction in {"BULLISH", "BEARISH"}:
        plan = _debit_spread(rows, strikes, float(spot), direction)
    elif regime == "SIDEWAYS / TRANSITION" and vix_zone in {"HEALTHY TREND", "HIGH VOLATILITY"}:
        plan = _iron_condor(rows, strikes, float(spot), chain.get("put_support"), chain.get("call_resistance"))
    if not plan:
        return {**base, "state": "WAIT", "strategy": "No clean limited-risk setup", "legs": [], "blockers": ["Live direction/regime and tradeable spread prices do not form a valid defined-risk payoff"]}
    risk_cap = float(settings.get("capital", 0)) * float(settings.get("risk_percent", 1)) / 100
    within_cap = plan["max_loss"] <= risk_cap
    payoff_ok = plan["payoff_ratio"] >= .30
    state = "REVIEW CANDIDATE" if within_cap and payoff_ok else "RISK BLOCKED"
    blockers = []
    if not within_cap:
        blockers.append(f"One-lot maximum loss {plan['max_loss']:,.2f} exceeds risk cap {risk_cap:,.2f}")
    if not payoff_ok:
        blockers.append(f"Maximum profit/loss ratio {plan['payoff_ratio']:.2f} is below 0.30")
    confidence = min(85, 45 + votes * 8 + (8 if environment.get("regular_move_available", True) else 0))
    return {**base, **plan, "state": state, "confidence": confidence, "risk_cap": round(risk_cap, 2), "risk_within_cap": within_cap, "blockers": blockers}

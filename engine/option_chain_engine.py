"""Transparent option-chain context from a selected expiry's live quote data."""
from __future__ import annotations

from statistics import median

from engine.greeks_engine import calculate_greeks


def _focused_max_pain(rows):
    """Return the minimum aggregate intrinsic payout inside the quoted window."""
    strikes = sorted({float(row["strike"]) for row in rows})
    if not strikes or not any(row["oi"] > 0 for row in rows):
        return None
    payouts = {}
    for settlement in strikes:
        payouts[settlement] = sum(
            row["oi"] * (
                max(settlement - float(row["strike"]), 0)
                if row["option_type"] == "CE"
                else max(float(row["strike"]) - settlement, 0)
            )
            for row in rows
        )
    return min(payouts, key=payouts.get)


def analyze_option_chain(contracts, quotes, spot=None):
    """Summarize OI and volume concentration; it never issues an order instruction."""
    quote_by_token = {str(quote.get("symbolToken", quote.get("symboltoken", ""))): quote for quote in quotes}
    rows = []
    for contract in contracts:
        quote = quote_by_token.get(str(contract["token"]), {})
        depth = quote.get("depth") or {}
        buys, sells = depth.get("buy") or [], depth.get("sell") or []
        bid = quote.get("bestBidPrice") or (buys[0].get("price") if buys else 0)
        ask = quote.get("bestAskPrice") or (sells[0].get("price") if sells else 0)
        ltp = float(quote.get("ltp", 0) or 0)
        row = {
            **contract,
            "oi": float(quote.get("opnInterest", 0) or 0),
            "volume": float(quote.get("tradeVolume", 0) or 0),
            "ltp": ltp,
            "bid": float(bid or 0), "ask": float(ask or 0),
            "oi_change": float(
                quote.get("changeinOpenInterest", quote.get("changeInOI", quote.get("oiChange", 0))) or 0
            ),
        }
        row["spread_percent"] = (
            (row["ask"] - row["bid"]) / max((row["ask"] + row["bid"]) / 2, .01) * 100
            if row["ask"] >= row["bid"] > 0 else None
        )
        rows.append(row)
    calls = [row for row in rows if row["option_type"] == "CE"]
    puts = [row for row in rows if row["option_type"] == "PE"]
    call_oi, put_oi = sum(row["oi"] for row in calls), sum(row["oi"] for row in puts)
    call_oi_change = sum(row["oi_change"] for row in calls)
    put_oi_change = sum(row["oi_change"] for row in puts)
    call_volume, put_volume = sum(row["volume"] for row in calls), sum(row["volume"] for row in puts)
    pcr_oi = put_oi / call_oi if call_oi else None
    pcr_volume = put_volume / call_volume if call_volume else None
    call_wall = max(calls, key=lambda row: row["oi"], default=None)
    put_wall = max(puts, key=lambda row: row["oi"], default=None)
    quoted = sum(1 for row in rows if row["ltp"] > 0)
    oi_covered = sum(1 for row in rows if row["oi"] > 0)
    spreads = [row["spread_percent"] for row in rows if row["spread_percent"] is not None]

    spot_value = float(spot or 0)
    atm_strike = min((row["strike"] for row in rows), key=lambda value: abs(float(value) - spot_value), default=None) if spot_value > 0 else None
    atm_call = next((row for row in calls if row["strike"] == atm_strike and row["ltp"] > 0), None)
    atm_put = next((row for row in puts if row["strike"] == atm_strike and row["ltp"] > 0), None)
    expected_move = (atm_call["ltp"] + atm_put["ltp"]) if atm_call and atm_put else None
    expiry = next((row.get("expiry") for row in rows if row.get("expiry") is not None), None)
    atm_greeks = {}
    for label, row in (("call", atm_call), ("put", atm_put)):
        if row and expiry is not None:
            estimate = calculate_greeks(spot_value, float(row["strike"]), row["ltp"], expiry, row["option_type"])
            if estimate:
                atm_greeks[label] = estimate
    atm_ivs = [value["iv"] for value in atm_greeks.values() if value.get("iv") is not None]

    data_quality = round(
        (quoted / max(len(rows), 1)) * 40
        + (oi_covered / max(len(rows), 1)) * 25
        + (len(spreads) / max(len(rows), 1)) * 20
        + (15 if atm_call and atm_put else 0),
    )
    if pcr_oi is None:
        context = "OI unavailable"
    elif pcr_oi > 1.1:
        context = "Put OI is higher than Call OI in this focused range"
    elif pcr_oi < 0.9:
        context = "Call OI is higher than Put OI in this focused range"
    else:
        context = "Call and Put OI are balanced in this focused range"
    return {
        "pcr_oi": pcr_oi,
        "pcr_volume": pcr_volume,
        "call_oi": call_oi,
        "put_oi": put_oi,
        "call_oi_change": call_oi_change,
        "put_oi_change": put_oi_change,
        "call_volume": call_volume,
        "put_volume": put_volume,
        "put_support": put_wall["strike"] if put_wall else None,
        "call_resistance": call_wall["strike"] if call_wall else None,
        "quoted_contracts": quoted,
        "total_contracts": len(rows),
        "atm_strike": atm_strike,
        "atm_straddle": round(expected_move, 2) if expected_move is not None else None,
        "expected_move": round(expected_move, 2) if expected_move is not None else None,
        "expected_move_percent": round(expected_move / spot_value * 100, 2) if expected_move is not None and spot_value > 0 else None,
        "expected_low": round(spot_value - expected_move, 2) if expected_move is not None else None,
        "expected_high": round(spot_value + expected_move, 2) if expected_move is not None else None,
        "focused_max_pain": _focused_max_pain(rows),
        "median_spread_percent": round(median(spreads), 2) if spreads else None,
        "spread_coverage": round(len(spreads) / max(len(rows), 1) * 100),
        "atm_iv": round(sum(atm_ivs) / len(atm_ivs), 2) if atm_ivs else None,
        "atm_greeks": atm_greeks,
        "data_quality": data_quality,
        "data_quality_label": "STRONG" if data_quality >= 80 else "USABLE" if data_quality >= 60 else "LIMITED",
        "context": context,
        "quote_rows": rows,
    }

"""Transparent option-chain context from a selected expiry's live quote data."""
from __future__ import annotations


def analyze_option_chain(contracts, quotes):
    """Summarize OI and volume concentration; it never issues an order instruction."""
    quote_by_token = {str(quote.get("symbolToken", quote.get("symboltoken", ""))): quote for quote in quotes}
    rows = []
    for contract in contracts:
        quote = quote_by_token.get(str(contract["token"]), {})
        depth = quote.get("depth") or {}
        buys, sells = depth.get("buy") or [], depth.get("sell") or []
        bid = quote.get("bestBidPrice") or (buys[0].get("price") if buys else 0)
        ask = quote.get("bestAskPrice") or (sells[0].get("price") if sells else 0)
        rows.append({
            **contract,
            "oi": float(quote.get("opnInterest", 0) or 0),
            "volume": float(quote.get("tradeVolume", 0) or 0),
            "ltp": float(quote.get("ltp", 0) or 0),
            "bid": float(bid or 0), "ask": float(ask or 0),
        })
    calls = [row for row in rows if row["option_type"] == "CE"]
    puts = [row for row in rows if row["option_type"] == "PE"]
    call_oi, put_oi = sum(row["oi"] for row in calls), sum(row["oi"] for row in puts)
    call_volume, put_volume = sum(row["volume"] for row in calls), sum(row["volume"] for row in puts)
    pcr_oi = put_oi / call_oi if call_oi else None
    pcr_volume = put_volume / call_volume if call_volume else None
    call_wall = max(calls, key=lambda row: row["oi"], default=None)
    put_wall = max(puts, key=lambda row: row["oi"], default=None)
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
        "put_support": put_wall["strike"] if put_wall else None,
        "call_resistance": call_wall["strike"] if call_wall else None,
        "quoted_contracts": sum(1 for row in rows if row["ltp"] > 0),
        "total_contracts": len(rows),
        "context": context,
        "quote_rows": rows,
    }

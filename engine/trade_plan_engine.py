"""Build review-required option trade plans from verified TPS contexts.

This module deliberately creates a draft only. It never places orders or marks
a proposed plan as an executed journal trade.
"""
from __future__ import annotations

from services.option_contract_service import buying_risk


def create_review_plan(underlying, spot_price, contracts, quote_rows, chart_context, chain_context, settings):
    """Select a liquid near-ATM contract only when every required context agrees."""
    if not chart_context or chart_context.get("score", 0) <= 75 or str(chart_context.get("decision", "")) == "NO TRADE":
        raise ValueError("Trade Plan requires a fresh chart score above 75/100.")
    if str(chart_context.get("symbol", "")).upper() != str(underlying).upper():
        raise ValueError("The latest chart evaluation is for a different underlying. Capture and evaluate this symbol first.")
    if not chain_context:
        raise ValueError("Run the selected-expiry OI / PCR analysis before creating a trade plan.")

    option_type = "CE" if chart_context["direction"] == "BULLISH" else "PE"
    quote_by_token = {str(row.get("token", row.get("symbolToken", row.get("symboltoken", "")))): row for row in quote_rows}
    candidates = []
    for contract in contracts:
        if contract["option_type"] != option_type:
            continue
        quote = quote_by_token.get(str(contract["token"]), {})
        premium = float(quote.get("ltp", 0) or 0)
        volume = float(quote.get("volume", quote.get("tradeVolume", 0)) or 0)
        if premium > 0 and volume > 0:
            candidates.append((contract, quote, premium, volume))
    if not candidates:
        raise ValueError(f"No liquid {option_type} candidate is available in the focused strikes.")

    # Prefer the closest tradeable strike; volume breaks a distance tie.
    contract, quote, premium, volume = min(
        candidates, key=lambda item: (abs(float(item[0]["strike"]) - float(spot_price)), -item[3])
    )
    stop_loss = round(premium * 0.80, 2)
    target = round(premium + (premium - stop_loss) * 2, 2)
    risk = buying_risk(premium, contract["lot_size"], settings["capital"], settings["risk_percent"])
    quantity = risk["lots"] * contract["lot_size"]
    if quantity <= 0:
        raise ValueError("Configured risk cap does not allow even one whole lot at the current premium.")

    return {
        "underlying": underlying,
        "contract": contract,
        "option_type": option_type,
        "spot_price": float(spot_price),
        "entry": round(premium, 2),
        "stoploss": stop_loss,
        "target": target,
        "quantity": quantity,
        "confidence": int(chart_context["score"]),
        "reasons": [
            f"{chart_context['decision']} ({chart_context['score']}/100)",
            f"Focused OI/PCR context: {chain_context.get('context', 'available')}",
            f"Near-ATM liquid contract selected (volume {volume:,.0f})",
        ],
        "warning": "Conditional review plan: verify live premium, bid/ask, volume, stop-loss and target in Angel One before manually placing an order.",
    }

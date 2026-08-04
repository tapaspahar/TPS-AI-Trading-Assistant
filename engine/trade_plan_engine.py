"""Build review-required option trade plans from verified TPS contexts.

This module deliberately creates a draft only. It never places orders or marks
a proposed plan as an executed journal trade.
"""
from __future__ import annotations

from services.option_contract_service import buying_risk


def create_review_plan(underlying, spot_price, contracts, quote_rows, chart_context, chain_context, settings, requested_lots=None, minimum_score=None):
    """Select a liquid near-ATM contract only when every required context agrees."""
    minimum_score = int(settings.get("trade_plan_min_score", 95) if minimum_score is None else minimum_score)
    if not 50 <= minimum_score <= 100:
        raise ValueError("Trade Plan minimum score must be between 50 and 100.")
    if (
        not chart_context or chart_context.get("score", 0) < minimum_score
        or not chart_context.get("volume_confirmed")
        or chart_context.get("direction") not in {"BULLISH", "BEARISH"}
    ):
        raise ValueError(f"Trade Plan requires score {minimum_score}/100 or above with Volume above Volume EMA 20.")
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
    safe_lots = risk["lots"]
    if requested_lots is None:
        requested_lots = safe_lots
    requested_lots = int(requested_lots)
    if requested_lots < 1:
        raise ValueError("Select at least one whole lot for the review plan.")
    quantity = requested_lots * contract["lot_size"]
    if quantity <= 0:
        raise ValueError("Configured risk cap does not allow even one whole lot at the current premium.")
    selected_risk = requested_lots * risk["per_lot_risk"]
    risk_within_cap = selected_risk <= risk["risk_cap"]
    risk_warning = (
        "Selected quantity is within the configured risk cap."
        if risk_within_cap else
        f"Selected {requested_lots} lot(s) has estimated premium risk of ₹{selected_risk:,.2f}, above your configured cap of ₹{risk['risk_cap']:,.2f}. Reduce lots or review Risk Settings before manually placing an order."
    )

    return {
        "underlying": underlying,
        "contract": contract,
        "option_type": option_type,
        "spot_price": float(spot_price),
        "entry": round(premium, 2),
        "stoploss": stop_loss,
        "target": target,
        "lots": requested_lots,
        "lot_size": contract["lot_size"],
        "quantity": quantity,
        "estimated_risk": selected_risk,
        "risk_cap": risk["risk_cap"],
        "risk_within_cap": risk_within_cap,
        "confidence": int(chart_context["score"]),
        "minimum_score": minimum_score,
        "rule_version": "TPS V2 configurable review — chart/volume/OI confirmation",
        "reasons": [
            f"Chart score {chart_context['score']}/100 meets configured minimum {minimum_score}",
            f"Focused OI/PCR context: {chain_context.get('context', 'available')}",
            f"Near-ATM liquid contract selected (volume {volume:,.0f})",
        ],
        "warning": "Conditional review plan: verify live premium, bid/ask, volume, stop-loss and target in Angel One before manually placing an order. " + risk_warning,
    }

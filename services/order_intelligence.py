"""Read-only Angel One order-book intelligence with evidence-led hindsight review."""
from __future__ import annotations

from datetime import datetime

from core.database_manager import Database


FINAL_STATES = {"COMPLETE", "COMPLETED", "FILLED", "REJECTED", "CANCELLED", "CANCELED"}


def _number(row: dict, *keys) -> float:
    for key in keys:
        try:
            if row.get(key) not in (None, ""):
                return float(row[key])
        except (TypeError, ValueError):
            pass
    return 0.0


def _text(row: dict, *keys, default="") -> str:
    for key in keys:
        if row.get(key) not in (None, ""):
            return str(row[key])
    return default


def analyze_order(order: dict, quote: dict | None = None, candles: list[dict] | None = None) -> dict:
    """Explain one order without treating a heuristic as guaranteed advice."""
    quote, candles = quote or {}, candles or []
    side = _text(order, "transactiontype", "transactionType", "side", default="BUY").upper()
    direction = 1 if side == "BUY" else -1
    entry = _number(order, "averageprice", "averagePrice", "price")
    market = _number(quote, "ltp", "last_traded_price", "close")
    status = _text(order, "status", "orderstatus", "orderStatus", default="UNKNOWN").upper()
    points = direction * (market - entry) if entry and market else None
    highs = [_number(row, "high") for row in candles if _number(row, "high")]
    lows = [_number(row, "low") for row in candles if _number(row, "low")]
    mfe = max([direction * (value - entry) for value in (highs if direction > 0 else lows)] or [0]) if entry else None
    mae = abs(min([direction * (value - entry) for value in (lows if direction > 0 else highs)] or [0])) if entry else None
    target = _number(order, "target_price", "targetPrice") or None
    stop = _number(order, "stoploss", "stopLoss", "triggerprice", "triggerPrice") or None
    evidence = []
    if points is None:
        state, explanation = "DATA GAP", "Fresh market price available nahi hai; hold/exit review reliable nahi hai."
    elif status in {"REJECTED", "CANCELLED", "CANCELED"}:
        state, explanation = "ORDER NOT ACTIVE", f"Broker status {status}; position outcome infer nahi kiya gaya."
    elif points > 0 and mfe is not None and points < max(0, mfe) * .45:
        state, explanation = "PROTECT PROFIT REVIEW", "Order profit me hai, lekin saved maximum favourable move ka bada hissa retrace ho chuka hai. Target/trailing protection review karein."
    elif points < 0 and mae is not None and abs(points) >= max(1, mae * .80):
        state, explanation = "EXIT-RISK REVIEW", "Current move saved adverse excursion ke paas hai. Original stop aur setup invalidation turant verify karein."
    elif points >= 0:
        state, explanation = "HOLD REVIEW", "Current move entry ke favour me hai. Original target, stop aur trend invalidation active rakhein."
    else:
        state, explanation = "WAIT / RISK REVIEW", "Trade entry ke against hai, par stop-hit evidence ke bina automatic exit conclusion nahi diya ja raha."
    if target:
        evidence.append(f"Target distance {direction * (target - market):+.2f} points")
    else:
        evidence.append("Broker order book me linked target unavailable")
    if stop:
        evidence.append(f"Stop distance {direction * (market - stop):+.2f} points")
    else:
        evidence.append("Broker order book me linked stop unavailable")
    evidence.append(f"MFE {mfe:.2f} | MAE {mae:.2f}" if mfe is not None and mae is not None else "MFE/MAE candle evidence unavailable")
    return {
        "broker_order_id": _text(order, "orderid", "orderId", default="UNKNOWN"),
        "trading_symbol": _text(order, "tradingsymbol", "tradingSymbol", default="UNKNOWN"),
        "exchange": _text(order, "exchange", default="NFO"), "symbol_token": _text(order, "symboltoken", "symbolToken"),
        "side": side, "quantity": int(_number(order, "filledshares", "filledShares", "quantity")),
        "entry_price": entry or None, "market_price": market or None, "order_status": status,
        "unrealized_points": round(points, 2) if points is not None else None,
        "mfe_points": round(max(0, mfe), 2) if mfe is not None else None,
        "mae_points": round(max(0, mae), 2) if mae is not None else None,
        "analysis_state": state, "explanation": explanation, "evidence": evidence,
        "source_complete": bool(entry and market),
    }


class OrderIntelligenceService:
    def __init__(self, client, database: Database | None = None):
        self.client = client; self.database = database or Database()

    def scan(self) -> list[dict]:
        now = datetime.now().astimezone(); results = []; market_cache = {}
        # Angel One can return a long day book. Bound the live scan and reuse
        # one quote/candle request for repeated orders in the same contract.
        orders = list(self.client.get_order_book())[-100:]
        for order in reversed(orders):
            token = _text(order, "symboltoken", "symbolToken")
            exchange = _text(order, "exchange", default="NFO")
            quote, candles = {}, []
            if token:
                key = (exchange, token)
                if key not in market_cache:
                    try: quote = self.client.get_option_quote(exchange, token) or {}
                    except Exception: quote = {}
                    try: candles = self.client.get_recent_candles(exchange, token, "FIVE_MINUTE", 1) or []
                    except Exception: candles = []
                    market_cache[key] = (quote, candles)
                quote, candles = market_cache[key]
            result = analyze_order(order, quote, candles)
            result.update({"captured_at": now.isoformat(timespec="seconds"), "trading_date": now.date().isoformat()})
            self.database.save_order_intelligence_snapshot(result); results.append(result)
        return results

"""Strict, rate-aware forward paper trading. It never calls an order endpoint."""
from __future__ import annotations

from datetime import datetime

from core.database_manager import Database
from engine.decision_engine import ChartSnapshot, DecisionEngine
from engine.live_setup_capture import build_live_capture
from engine.option_chain_engine import analyze_option_chain
from engine.trade_plan_engine import create_review_plan
from services.option_contract_service import UNDERLYING_QUOTES, OptionContractService, contracts_near_spot


def run_auto_paper_cycle(client, symbol: str, settings: dict) -> dict:
    """Capture one ATM one-lot paper trade only if every strict TPS condition passes."""
    symbol = str(symbol).upper()
    database = Database()
    try:
        today = datetime.now().strftime("%d-%m-%Y")
        progress = database.paper_trade_progress(today)
        if progress["open_trades"]:
            return {"status": "Waiting: an open paper trade is already being monitored."}
        if progress["trades"] >= int(settings["max_trades_per_day"]):
            return {"status": f"Daily paper-trade limit reached ({progress['trades']}/{settings['max_trades_per_day']})."}
        service = OptionContractService()
        future = service.get_front_month_future(symbol)
        candles = client.get_recent_candles(future["exchange"], future["token"], "FIVE_MINUTE", 5)
        capture = build_live_capture(symbol, "5m", candles, f"Angel One current-month future {future['symbol']}")
        snapshot = ChartSnapshot(
            price=float(capture["close"]), ema_5=float(capture["ema_5"]), ema_20=float(capture["ema_20"]), ema_50=float(capture["ema_50"]),
            vwap=float(capture["vwap"]) if capture["vwap"] else None, supertrend=float(capture["supertrend"]),
            volume=float(capture["volume"]) if capture["volume"] else None, volume_ema=float(capture["volume_ema"]) if capture["volume_ema"] else None,
            rsi_14=float(capture["rsi_14"]) if capture["rsi_14"] else None, atr_14=float(capture["atr_14"]) if capture["atr_14"] else None,
            volume_ratio=float(capture["volume_ratio"]) if capture["volume_ratio"] else None, candle_direction=capture.get("candle_direction"),
            fake_breakout_risk=bool(capture.get("fake_breakout_risk", True)),
        )
        candidate = "CE" if snapshot.price > snapshot.supertrend else "PE"
        chart = DecisionEngine().evaluate(snapshot, candidate, "Calm")
        if not chart["trade_ready"]:
            return {"status": f"No paper trade: {chart['decision']} ({chart['score']}/100)."}
        spot_config = UNDERLYING_QUOTES[symbol]
        spot = float(client.get_option_quote(spot_config["exchange"], spot_config["token"]).get("ltp", 0) or 0)
        if spot <= 0:
            return {"status": "No paper trade: usable underlying spot quote unavailable."}
        contracts = contracts_near_spot(service.get_contracts(symbol), spot, wings=5)
        expiry = min(contract["expiry"] for contract in contracts)
        contracts = [contract for contract in contracts if contract["expiry"] == expiry]
        chain = analyze_option_chain(contracts, client.get_option_chain_quotes(contracts[0]["exchange"], [contract["token"] for contract in contracts]))
        plan = create_review_plan(symbol, spot, contracts, chain["quote_rows"], {"symbol": symbol, **chart}, chain, settings, requested_lots=1, minimum_score=95)
        plan["rule_version"] = "TPS Auto Paper V1 - 5m strict confirmation"
        trade_id = database.save_paper_trade(plan)
        return {"status": "Paper trade captured", "trade_id": trade_id, "plan": plan, "capture": capture}
    finally:
        database.close()

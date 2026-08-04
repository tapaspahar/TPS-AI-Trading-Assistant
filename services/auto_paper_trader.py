"""Strict, rate-aware forward paper trading. It never calls an order endpoint."""
from __future__ import annotations

from datetime import datetime

from core.database_manager import Database
from engine.decision_engine import ChartSnapshot, DecisionEngine
from engine.live_setup_capture import build_live_capture
from engine.option_chain_engine import analyze_option_chain
from engine.trade_plan_engine import create_review_plan
from services.option_contract_service import UNDERLYING_QUOTES, OptionContractService, contracts_near_spot


def _attempt(status, checked_at, *, capture=None, chart=None, candidate=None, future=None, blockers=None, chain=None):
    """Return a transparent audit record for every automatic decision."""
    return {
        "status": status,
        "attempt": {
            "checked_at": checked_at.isoformat(timespec="seconds"),
            "candle_time": (capture or {}).get("candle_time"),
            "future_symbol": (future or {}).get("symbol"),
            "candidate": candidate,
            "capture": capture or {},
            "chart": chart or {},
            "chain": chain or {},
            "blockers": list(blockers or []),
        },
    }


def run_auto_paper_cycle(client, symbol: str, settings: dict) -> dict:
    """Capture one ATM one-lot paper trade only if every strict TPS condition passes."""
    symbol = str(symbol).upper()
    database = Database()
    try:
        checked_at = datetime.now()
        today = checked_at.strftime("%d-%m-%Y")
        progress = database.paper_trade_progress(today)
        if progress["open_trades"]:
            reason = "An open paper trade is already being monitored"
            return _attempt("Waiting: an open paper trade is already being monitored.", checked_at, blockers=[reason])
        if progress["trades"] >= int(settings["max_trades_per_day"]):
            reason = f"Daily paper-trade limit reached ({progress['trades']}/{settings['max_trades_per_day']})"
            return _attempt(f"{reason}.", checked_at, blockers=[reason])
        service = OptionContractService()
        future = service.get_front_month_future(symbol)
        candles = client.get_recent_candles(future["exchange"], future["token"], "FIVE_MINUTE", 5)
        capture = build_live_capture(symbol, "5m", candles, f"Angel One current-month future {future['symbol']}")
        capture["candle_time"] = candles[-1].get("time")
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
            blockers = list(chart.get("warnings") or [])
            if chart["score"] < 95:
                blockers.insert(0, f"Score {chart['score']}/100 is below strict auto-paper minimum 95")
            if not chart.get("volume_confirmed"):
                blockers.append("Heavy-volume confirmation is not satisfied")
            return _attempt(
                f"No paper trade: {chart['decision']} ({chart['score']}/100).",
                checked_at, capture=capture, chart=chart, candidate=candidate, future=future, blockers=blockers,
            )
        spot_config = UNDERLYING_QUOTES[symbol]
        spot = float(client.get_option_quote(spot_config["exchange"], spot_config["token"]).get("ltp", 0) or 0)
        if spot <= 0:
            reason = "Usable underlying spot quote is unavailable"
            return _attempt(f"No paper trade: {reason.lower()}.", checked_at, capture=capture, chart=chart, candidate=candidate, future=future, blockers=[reason])
        contracts = contracts_near_spot(service.get_contracts(symbol), spot, wings=5)
        expiry = min(contract["expiry"] for contract in contracts)
        contracts = [contract for contract in contracts if contract["expiry"] == expiry]
        chain = analyze_option_chain(contracts, client.get_option_chain_quotes(contracts[0]["exchange"], [contract["token"] for contract in contracts]))
        plan = create_review_plan(symbol, spot, contracts, chain["quote_rows"], {"symbol": symbol, **chart}, chain, settings, requested_lots=1, minimum_score=95)
        plan["rule_version"] = "TPS Auto Paper V1 - 5m strict confirmation"
        trade_id = database.save_paper_trade(plan)
        result = _attempt("Paper trade captured", checked_at, capture=capture, chart=chart, candidate=candidate, future=future, chain=chain)
        result.update({"trade_id": trade_id, "plan": plan, "capture": capture})
        return result
    finally:
        database.close()

"""Strict, rate-aware forward paper trading. It never calls an order endpoint."""
from __future__ import annotations

from datetime import datetime

from core.database_manager import Database
from engine.decision_engine import ChartSnapshot, DecisionEngine
from engine.live_setup_capture import build_live_capture
from engine.option_chain_engine import analyze_option_chain
from engine.trade_plan_engine import create_review_plan
from engine.tps_entry_confirmation import evaluate_tps_entry_v2
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


def _record(database, symbol, result):
    database.save_auto_trade_attempt(symbol, result)
    return result


def _completed_candles(candles, checked_at):
    """Exclude the currently forming 5-minute candle when the feed includes it."""
    if not candles:
        return candles
    bucket = checked_at.replace(minute=(checked_at.minute // 5) * 5, second=0, microsecond=0)
    try:
        latest_start = datetime.fromisoformat(str(candles[-1]["time"])).replace(tzinfo=None)
    except (KeyError, TypeError, ValueError):
        return candles
    return candles[:-1] if latest_start >= bucket.replace(tzinfo=None) else candles


def run_auto_paper_cycle(client, symbol: str, settings: dict) -> dict:
    """Capture one ATM one-lot paper trade only if every strict TPS condition passes."""
    symbol = str(symbol).upper()
    database = Database()
    try:
        checked_at = datetime.now()
        today = checked_at.strftime("%d-%m-%Y")
        progress = database.paper_trade_progress(today)
        service = OptionContractService()
        future = service.get_front_month_future(symbol)
        candles = client.get_recent_candles(future["exchange"], future["token"], "FIVE_MINUTE", 5)
        candles = _completed_candles(candles, checked_at)
        if len(candles) < 51:
            raise ValueError("At least 51 completed 5-minute candles are required for the automatic TPS v2 check.")
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
        legacy_candidate = "CE" if snapshot.price > snapshot.supertrend else "PE"
        legacy_chart = DecisionEngine().evaluate(snapshot, legacy_candidate, "Calm")
        spot_config = UNDERLYING_QUOTES[symbol]
        spot = float(client.get_option_quote(spot_config["exchange"], spot_config["token"]).get("ltp", 0) or 0)
        if spot <= 0:
            reason = "Usable underlying spot quote is unavailable"
            result = _attempt(f"No paper trade: {reason.lower()}.", checked_at, capture=capture, chart=legacy_chart, candidate=None, future=future, blockers=[reason])
            return _record(database, symbol, result)
        contracts = contracts_near_spot(service.get_contracts(symbol), spot, wings=5)
        expiry = min(contract["expiry"] for contract in contracts)
        contracts = [contract for contract in contracts if contract["expiry"] == expiry]
        chain = analyze_option_chain(contracts, client.get_option_chain_quotes(contracts[0]["exchange"], [contract["token"] for contract in contracts]))
        strategy = evaluate_tps_entry_v2(candles, capture, chain)
        candidate = strategy["candidate"]
        chart = {
            "symbol": symbol, "score": strategy["score"], "direction": strategy["direction"],
            "decision": strategy["decision"], "trade_ready": strategy["trade_ready"],
            "volume_confirmed": any(item["name"] == "Directional volume" and item["passed"] for item in strategy["confirmations"]),
            "reasons": [f"{item['name']}: {item['detail']}" for item in strategy["confirmations"] if item["passed"]],
            "warnings": strategy["blockers"] + [f"{item['name']}: {item['detail']}" for item in strategy["confirmations"] if not item["passed"]],
            "strategy": strategy, "legacy_score": legacy_chart["score"],
        }
        operational_blockers = []
        if progress["open_trades"]:
            operational_blockers.append("An open paper trade is already being monitored")
        if progress["trades"] >= int(settings["max_trades_per_day"]):
            operational_blockers.append(f"Daily paper-trade limit reached ({progress['trades']}/{settings['max_trades_per_day']})")
        if operational_blockers:
            chart["warnings"].extend(operational_blockers)
            result = _attempt(
                "No new paper trade: TPS v2 candle evaluation completed but an operational safety limit blocked capture.",
                checked_at, capture=capture, chart=chart, candidate=candidate, future=future,
                blockers=chart["warnings"], chain=chain,
            )
            return _record(database, symbol, result)
        if not strategy["trade_ready"]:
            result = _attempt(
                f"No paper trade: TPS v2 confirmations {strategy['passed']}/6 (minimum 5/6).",
                checked_at, capture=capture, chart=chart, candidate=candidate, future=future,
                blockers=chart["warnings"], chain=chain,
            )
            return _record(database, symbol, result)
        plan = create_review_plan(symbol, spot, contracts, chain["quote_rows"], chart, chain, settings, requested_lots=1, minimum_score=80)
        plan["rule_version"] = "TPS Entry Confirmation System v2 - 5m + OI/PCR"
        trade_id = database.save_paper_trade(plan)
        result = _attempt("Paper trade captured", checked_at, capture=capture, chart=chart, candidate=candidate, future=future, chain=chain)
        result.update({"trade_id": trade_id, "plan": plan, "capture": capture})
        return _record(database, symbol, result)
    finally:
        database.close()

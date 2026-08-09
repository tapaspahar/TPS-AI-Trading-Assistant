"""Read-only CAS and stock-option research using Angel One market data."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from core.settings_store import SettingsStore
from engine.cas_analysis import analyze_cas_session
from engine.live_setup_capture import build_live_capture
from engine.option_chain_engine import analyze_option_chain
from engine.tps_entry_confirmation import evaluate_tps_entry_v2
from engine.trade_plan_engine import create_review_plan
from services.option_contract_service import OptionContractService, contracts_near_spot


def _completed(candles):
    result = list(candles)
    if not result:
        raise RuntimeError("Angel One returned no candles.")
    try:
        start = datetime.fromisoformat(str(result[-1]["time"]))
        now = datetime.now(start.tzinfo) if start.tzinfo else datetime.now()
        if start + timedelta(minutes=5) > now:
            result.pop()
    except (KeyError, TypeError, ValueError):
        pass
    return result


class StockDerivativeService:
    def __init__(self, client, contract_service=None):
        self.client = client
        self.contract_service = contract_service or OptionContractService()

    def universe(self):
        return self.contract_service.get_stock_option_universe()

    def analyze_cas(self, equity):
        future = self.contract_service.get_stock_front_month_future(equity["underlying"])
        cash = _completed(self.client.get_recent_candles(equity["exchange"], equity["token"], "FIVE_MINUTE", 5))
        future_candles = _completed(self.client.get_recent_candles(future["exchange"], future["token"], "FIVE_MINUTE", 5))
        result = analyze_cas_session(cash, future_candles)
        result.update({"underlying": equity["underlying"], "cash_symbol": equity["symbol"], "future_symbol": future["symbol"]})
        return result

    def analyze_option_setup(self, equity, settings=None):
        settings = settings or SettingsStore().load()
        underlying = equity["underlying"]
        future = self.contract_service.get_stock_front_month_future(underlying)
        candles = _completed(self.client.get_recent_candles(future["exchange"], future["token"], "FIVE_MINUTE", 5))
        if len(candles) < 51:
            raise RuntimeError("At least 51 completed stock-future candles are required.")
        capture = build_live_capture(underlying, "5m", candles, f"Angel One {future['symbol']} stock-future candles")
        capture["candle_time"] = candles[-1].get("time")
        spot = float(self.client.get_option_quote(equity["exchange"], equity["token"]).get("ltp", 0) or 0)
        if spot <= 0:
            raise RuntimeError("Usable cash-stock quote is unavailable.")

        contracts = self.contract_service.get_stock_contracts(underlying)
        expiries = [contract["expiry"] for contract in contracts if contract["expiry"] >= date.today()]
        expiry = min(expiries)
        expiry_contracts = [contract for contract in contracts if contract["expiry"] == expiry]
        focused = contracts_near_spot(expiry_contracts, spot, wings=8)
        if not focused:
            raise RuntimeError("No near-ATM stock-option contracts were found.")
        quotes = self.client.get_option_chain_quotes("NFO", [contract["token"] for contract in focused])
        chain = analyze_option_chain(focused, quotes)
        strategy = evaluate_tps_entry_v2(candles, capture, chain, settings, environment={})
        side = (strategy.get("side_evaluations") or {}).get(strategy["candidate"], {})
        result = {
            "underlying": underlying, "cash_symbol": equity["symbol"], "future_symbol": future["symbol"],
            "expiry": expiry.strftime("%d-%m-%Y"), "spot": spot, "capture": capture, "chain": chain,
            "strategy": strategy, "candidate": strategy["candidate"], "score": strategy["score"],
            "state": "PAPER CANDIDATE" if strategy["trade_ready"] else side.get("state", "WATCH"),
            "entry_quality": side.get("entry_quality") or {}, "blockers": side.get("hard_blockers") or [],
            "plan": None,
        }
        if strategy["trade_ready"]:
            selected = strategy.get("selected_confirmations") or []
            chart = {
                "symbol": underlying, "score": strategy["score"],
                "direction": "BULLISH" if strategy["candidate"] == "CE" else "BEARISH",
                "volume_confirmed": any(item["name"] == "Directional volume" and item["passed"] for item in selected),
                "market_environment": {},
            }
            try:
                result["plan"] = create_review_plan(
                    underlying, spot, focused, chain["quote_rows"], chart, chain, settings,
                    requested_lots=1, minimum_score=strategy["minimum_score"],
                )
            except ValueError as error:
                result["state"] = "EVIDENCE PASSED / CONTRACT WAIT"
                result["blockers"].append(str(error))
        return result

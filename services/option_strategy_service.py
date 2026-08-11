"""Live read-only data service for defined-risk index option strategies."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from core.settings_store import SettingsStore
from engine.live_setup_capture import INSTRUMENTS, build_live_capture
from engine.market_environment import analyze_market_environment
from engine.option_chain_engine import analyze_option_chain
from engine.option_strategy_engine import recommend_option_strategy
from services.option_contract_service import OptionContractService, contracts_near_spot


def _completed(candles):
    rows = list(candles)
    if not rows:
        raise RuntimeError("Angel One returned no candles.")
    try:
        start = datetime.fromisoformat(str(rows[-1]["time"]))
        now = datetime.now(start.tzinfo) if start.tzinfo else datetime.now()
        if start + timedelta(minutes=5) > now:
            rows.pop()
    except (KeyError, TypeError, ValueError):
        pass
    if len(rows) < 51:
        raise RuntimeError("At least 51 completed 5-minute candles are required.")
    return rows


class OptionStrategyService:
    def __init__(self, client, contract_service=None):
        self.client = client
        self.contract_service = contract_service or OptionContractService()

    def analyze(self, symbol, settings=None):
        symbol = str(symbol).upper()
        if symbol not in INSTRUMENTS:
            raise ValueError("Choose NIFTY, BANKNIFTY, or SENSEX.")
        settings = settings or SettingsStore().load()
        spot_exchange, spot_token = INSTRUMENTS[symbol]
        future = self.contract_service.get_front_month_future(symbol)
        candles = _completed(self.client.get_recent_candles(future["exchange"], future["token"], "FIVE_MINUTE", 5))
        provider = getattr(self.client, "provider_name", "Broker")
        capture = build_live_capture(symbol, "5m", candles, f"{provider} {future['symbol']} index-future candles")
        spot = float(self.client.get_option_quote(spot_exchange, spot_token).get("ltp", 0) or capture["close"])
        try:
            vix_instrument = self.contract_service.get_india_vix_instrument()
            vix = float(self.client.get_option_quote(vix_instrument["exchange"], vix_instrument["token"]).get("ltp", 0) or 0) or None
        except (RuntimeError, ValueError, TypeError):
            vix = None
        environment = analyze_market_environment(candles, capture, spot, vix)

        contracts = self.contract_service.get_contracts(symbol)
        expiries = [contract["expiry"] for contract in contracts if contract["expiry"] >= date.today()]
        expiry = min(expiries)
        expiry_contracts = [contract for contract in contracts if contract["expiry"] == expiry]
        focused = contracts_near_spot(expiry_contracts, spot, wings=10)
        quotes = self.client.get_option_chain_quotes(focused[0]["exchange"], [contract["token"] for contract in focused])
        chain = analyze_option_chain(focused, quotes)
        result = recommend_option_strategy(symbol, spot, candles, capture, chain, environment, settings)
        result.update({
            "expiry": expiry.strftime("%d-%m-%Y"), "future_symbol": future["symbol"],
            "candle_time": str(candles[-1].get("time", "")), "quoted_contracts": chain.get("quoted_contracts", 0),
            "environment": environment, "chain": chain,
        })
        return result

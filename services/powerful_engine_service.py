"""Point-in-time data assembly for the TPS Powerful Engine."""
from __future__ import annotations

from datetime import datetime, timedelta

from engine.live_setup_capture import build_live_capture
from engine.market_environment import analyze_market_environment
from engine.multi_timeframe_engine import analyze_multi_timeframe
from engine.option_chain_engine import analyze_option_chain
from engine.powerful_engine import evaluate_powerful_engine
from engine.pre_candle_probability import analyze_pre_candle_probability
from engine.smart_money_engine import SmartMoneyEngine
from services.option_contract_service import UNDERLYING_QUOTES, OptionContractService, contracts_near_spot


class PowerfulEngineService:
    def __init__(self, client, contract_service=None):
        self.client = client
        self.contract_service = contract_service or OptionContractService()

    @staticmethod
    def _completed(candles, minutes):
        rows = list(candles)
        if not rows:
            return rows
        try:
            last = datetime.fromisoformat(str(rows[-1]["time"]))
            now = datetime.now(last.tzinfo) if last.tzinfo else datetime.now()
            if last + timedelta(minutes=minutes) > now:
                rows.pop()
        except (KeyError, TypeError, ValueError):
            pass
        return rows

    def analyze(self, symbol):
        symbol = str(symbol).upper()
        future = self.contract_service.get_front_month_future(symbol)
        provider = getattr(self.client, "provider_name", "Broker")
        datasets = {
            "5m": self._completed(self.client.get_recent_candles(future["exchange"], future["token"], "FIVE_MINUTE", 30), 5),
            "15m": self._completed(self.client.get_recent_candles(future["exchange"], future["token"], "FIFTEEN_MINUTE", 30), 15),
            "1h": self._completed(self.client.get_recent_candles(future["exchange"], future["token"], "ONE_HOUR", 60), 60),
        }
        if len(datasets["5m"]) < 140:
            raise RuntimeError("Powerful Engine needs at least 140 completed 5-minute future candles.")
        if any(len(rows) < 20 for rows in datasets.values()):
            raise RuntimeError("Powerful Engine needs at least 20 completed candles on 5m, 15m and 1h.")
        pre = analyze_pre_candle_probability(datasets["5m"], 60)
        capture = build_live_capture(symbol, "5m", datasets["5m"], f"{provider} {future['symbol']}")
        capture["candle_time"] = datasets["5m"][-1].get("time")
        mtf = analyze_multi_timeframe(datasets)
        try:
            smart = SmartMoneyEngine().analyze(datasets["5m"])
        except ValueError as error:
            smart = {"direction": "NEUTRAL", "score": 0, "structure": "UNAVAILABLE", "event": str(error)}

        spot_instrument = UNDERLYING_QUOTES[symbol]
        spot = float(self.client.get_option_quote(spot_instrument["exchange"], spot_instrument["token"]).get("ltp", 0) or 0)
        if spot <= 0:
            raise RuntimeError(f"Usable {symbol} spot quote is unavailable.")
        contracts = contracts_near_spot(self.contract_service.get_contracts(symbol), spot, wings=5)
        expiry = min(contract["expiry"] for contract in contracts)
        contracts = [contract for contract in contracts if contract["expiry"] == expiry]
        quotes = self.client.get_option_chain_quotes(contracts[0]["exchange"], [item["token"] for item in contracts])
        chain = analyze_option_chain(contracts, quotes)
        try:
            vix_instrument = self.contract_service.get_india_vix_instrument()
            vix = float(self.client.get_option_quote(vix_instrument["exchange"], vix_instrument["token"]).get("ltp", 0) or 0)
        except (RuntimeError, ValueError, TypeError, KeyError):
            vix = None
        environment = analyze_market_environment(datasets["5m"], capture, spot, vix)

        preliminary = evaluate_powerful_engine(
            pre_candle=pre, capture=capture, multi_timeframe=mtf, smart_money=smart,
            chain=chain, environment=environment,
        )
        candidate = preliminary.get("candidate")
        option_quote = None
        if candidate:
            option_type = candidate
            option_quote = min(
                (row for row in chain["quote_rows"] if row.get("option_type") == option_type and float(row.get("ltp", 0) or 0) > 0),
                key=lambda row: abs(float(row["strike"]) - spot), default=None,
            )
        result = evaluate_powerful_engine(
            pre_candle=pre, capture=capture, multi_timeframe=mtf, smart_money=smart,
            chain=chain, environment=environment, option_quote=option_quote,
        )
        result.update({
            "symbol": symbol, "future_symbol": future["symbol"], "provider": provider,
            "candle_time": capture["candle_time"], "spot": spot, "expiry": str(expiry),
            "pre_candle": pre, "capture": capture, "multi_timeframe": mtf,
            "smart_money": smart, "chain": chain, "environment": environment,
            "option_quote": option_quote,
        })
        return result

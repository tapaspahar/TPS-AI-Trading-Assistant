"""Broker-data assembly for the TPS Scalper Command Center."""
from __future__ import annotations

from datetime import datetime, timedelta

from engine.scalper_engine import evaluate_scalp
from services.global_market_context import GlobalMarketContextService
from services.option_contract_service import UNDERLYING_QUOTES, OptionContractService


class ScalperService:
    def __init__(self, client, contract_service=None, global_service=None):
        self.client = client
        self.contracts = contract_service or OptionContractService()
        self.global_service = global_service or GlobalMarketContextService()

    @staticmethod
    def _completed(rows, minutes):
        data = list(rows)
        if not data:
            return data
        try:
            stamp = datetime.fromisoformat(str(data[-1]["time"]))
            now = datetime.now(stamp.tzinfo) if stamp.tzinfo else datetime.now()
            if stamp + timedelta(minutes=minutes) > now:
                data.pop()
        except (KeyError, TypeError, ValueError):
            pass
        return data

    def analyze(self, symbol, minimum_score=72, global_context=None):
        future = self.contracts.get_front_month_future(symbol)
        one = self._completed(self.client.get_recent_candles(future["exchange"], future["token"], "ONE_MINUTE", 5), 1)
        five = self._completed(self.client.get_recent_candles(future["exchange"], future["token"], "FIVE_MINUTE", 30), 5)
        context = global_context or self.global_service.snapshot()
        result = evaluate_scalp(one, five, context, minimum_score)
        candidate = result.get("candidate")
        liquidity = {"available": False, "status": "No directional option selected"}
        if candidate:
            spot_item = UNDERLYING_QUOTES[symbol]
            spot_quote = self.client.get_option_quote(spot_item["exchange"], spot_item["token"])
            spot = float(spot_quote.get("ltp", 0) or 0)
            contracts = self.contracts.get_contracts(symbol)
            expiry = min(row["expiry"] for row in contracts)
            choices = [row for row in contracts if row["expiry"] == expiry and row["option_type"] == candidate]
            contract = min(choices, key=lambda row: abs(float(row["strike"]) - spot))
            quote = self.client.get_option_quote(contract["exchange"], contract["token"])
            depth = quote.get("depth") or {}; buys, sells = depth.get("buy") or [], depth.get("sell") or []
            bid = float(quote.get("bestBidPrice") or (buys[0].get("price") if buys else 0) or 0)
            ask = float(quote.get("bestAskPrice") or (sells[0].get("price") if sells else 0) or 0)
            ltp = float(quote.get("ltp", 0) or 0); volume = float(quote.get("tradeVolume", quote.get("volume", 0)) or 0)
            spread = (ask - bid) / max((ask + bid) / 2, .01) * 100 if ask >= bid > 0 else None
            liquid = ltp > 0 and (spread is None or spread <= 12)
            liquidity = {"available": ltp > 0, "passed": liquid, "symbol": contract["symbol"],
                         "ltp": ltp, "bid": bid, "ask": ask, "spread_percent": spread, "volume": volume,
                         "status": "Liquidity gate passed" if liquid else "Option quote/spread gate failed"}
            if result.get("published") and not liquid:
                result["published"] = False; result["action"] = "WAIT"
                result["blockers"].append("ATM option liquidity/spread gate failed")
        result["option_liquidity"] = liquidity
        result.update({"symbol": symbol, "future_symbol": future["symbol"],
                       "provider": getattr(self.client, "provider_name", "Broker"),
                       "global_context": context})
        return result

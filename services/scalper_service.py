"""Broker-data assembly for the TPS near-expiry options scalper."""
from __future__ import annotations

from datetime import datetime, timedelta

from engine.scalper_engine import evaluate_option_premium, evaluate_scalp
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

    @staticmethod
    def _select_contract(choices, spot, candidate, strike_mode):
        strikes = sorted({float(row["strike"]) for row in choices})
        atm_index = min(range(len(strikes)), key=lambda index: abs(strikes[index] - spot))
        offset = 0
        if strike_mode == "1-step ITM":
            offset = -1 if candidate == "CE" else 1
        elif strike_mode == "1-step OTM":
            offset = 1 if candidate == "CE" else -1
        strike = strikes[max(0, min(len(strikes) - 1, atm_index + offset))]
        return next(row for row in choices if float(row["strike"]) == strike)

    def analyze(self, symbol, minimum_score=72, global_context=None, strike_mode="ATM"):
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
            contract = self._select_contract(choices, spot, candidate, strike_mode)
            quote = self.client.get_option_quote(contract["exchange"], contract["token"])
            option_rows = self._completed(
                self.client.get_recent_candles(contract["exchange"], contract["token"], "ONE_MINUTE", 5), 1
            )
            try:
                premium = evaluate_option_premium(option_rows, quote)
            except ValueError as error:
                result["published"] = False
                result["action"] = "WAIT"
                result["blockers"].append(f"Option: {error}")
                result.update({"option_contract": contract, "expiry": expiry,
                               "strike_mode": strike_mode,
                               "option_candle_time": option_rows[-1].get("time") if option_rows else None})
                liquidity = {
                    "available": bool(float(quote.get("ltp", 0) or 0)), "passed": False,
                    "symbol": contract["symbol"], "strike": contract["strike"],
                    "option_type": candidate, "expiry": expiry, "strike_mode": strike_mode,
                    "ltp": float(quote.get("ltp", 0) or 0), "bid": 0.0, "ask": 0.0,
                    "spread_percent": None, "premium_passed": [],
                    "premium_blockers": [str(error)],
                    "status": "Waiting for enough completed option-premium candles",
                }
                result["option_liquidity"] = liquidity
                result.update({"symbol": symbol, "future_symbol": future["symbol"],
                               "provider": getattr(self.client, "provider_name", "Broker"),
                               "global_context": context})
                return result
            liquidity = {"available": premium["ltp"] > 0, "passed": premium["confirmed"],
                         "symbol": contract["symbol"], "strike": contract["strike"],
                         "option_type": candidate, "expiry": expiry, "strike_mode": strike_mode,
                         "ltp": premium["ltp"], "bid": premium["bid"], "ask": premium["ask"],
                         "spread_percent": premium["spread_percent"], "volume_ratio": premium["volume_ratio"],
                         "premium_passed": premium["passed"], "premium_blockers": premium["blockers"],
                         "status": "Option premium confirmation passed" if premium["confirmed"] else "Option premium confirmation failed"}
            result.update({"option_contract": contract, "expiry": expiry, "strike_mode": strike_mode,
                           "entry_reference": premium["entry"], "stop": premium["stop"],
                           "target1": premium["target1"], "target2": premium["target2"],
                           "option_candle_time": option_rows[-1].get("time")})
            if result.get("published") and not premium["confirmed"]:
                result["published"] = False; result["action"] = "WAIT"
                result["blockers"].extend("Option: " + item for item in premium["blockers"])
        result["option_liquidity"] = liquidity
        result.update({"symbol": symbol, "future_symbol": future["symbol"],
                       "provider": getattr(self.client, "provider_name", "Broker"),
                       "global_context": context})
        return result

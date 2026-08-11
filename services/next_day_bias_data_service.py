"""Read-only Angel One closing evidence for the Next-Day Bias Lab."""

from datetime import date, datetime, timedelta

from engine.live_setup_capture import INSTRUMENTS, build_live_capture
from engine.option_chain_engine import analyze_option_chain
from services.option_contract_service import OptionContractService, contracts_near_spot


class NextDayBiasDataService:
    def __init__(self, client, contract_service=None):
        self.client = client
        self.contract_service = contract_service or OptionContractService()

    def load(self, symbol):
        symbol = str(symbol).upper()
        if symbol not in INSTRUMENTS:
            raise ValueError("Choose NIFTY, BANKNIFTY, or SENSEX.")
        spot_exchange, spot_token = INSTRUMENTS[symbol]
        future = self.contract_service.get_front_month_future(symbol)
        spot_candles = self._completed_candles(self.client.get_recent_candles(spot_exchange, spot_token, "FIVE_MINUTE", 5))
        future_candles = self._completed_candles(self.client.get_recent_candles(future["exchange"], future["token"], "FIVE_MINUTE", 5))
        provider = getattr(self.client, "provider_name", "Broker")
        spot = build_live_capture(symbol, "5m", spot_candles, f"{provider} {symbol} spot candles")
        future_capture = build_live_capture(symbol, "5m", future_candles, f"{provider} {future['symbol']}")

        contracts = self.contract_service.get_contracts(symbol)
        future_expiries = [contract["expiry"] for contract in contracts if contract["expiry"] > date.today()]
        nearest_expiry = min(future_expiries or [contract["expiry"] for contract in contracts])
        nearest = [contract for contract in contracts if contract["expiry"] == nearest_expiry]
        focused = contracts_near_spot(nearest, float(spot["close"]), wings=10)
        if not focused:
            raise RuntimeError(f"No nearest-expiry {symbol} option contracts were found.")
        quotes = self.client.get_option_chain_quotes(focused[0]["exchange"], [contract["token"] for contract in focused])
        chain = analyze_option_chain(focused, quotes)
        positive_calls = [row for row in chain["quote_rows"] if row["option_type"] == "CE" and row["oi"] > 0]
        positive_puts = [row for row in chain["quote_rows"] if row["option_type"] == "PE" and row["oi"] > 0]
        if not positive_calls or not positive_puts:
            raise RuntimeError("Angel One returned insufficient positive Call/Put OI for closing analysis.")
        strikes = {row["strike"] for row in chain["quote_rows"]}
        if not strikes:
            raise RuntimeError("Angel One returned no option-chain strikes.")
        atm_strike = min(strikes, key=lambda strike: abs(strike - float(spot["close"])))
        atm_call = next((row["ltp"] for row in chain["quote_rows"] if row["strike"] == atm_strike and row["option_type"] == "CE" and row["ltp"] > 0), None)
        atm_put = next((row["ltp"] for row in chain["quote_rows"] if row["strike"] == atm_strike and row["option_type"] == "PE" and row["ltp"] > 0), None)
        return {
            "symbol": symbol, "future_symbol": future["symbol"], "expiry": nearest_expiry.strftime("%d-%m-%Y"),
            "spot": spot, "future": future_capture,
            "put_support": chain.get("put_support"), "call_resistance": chain.get("call_resistance"),
            "oi_pcr": chain.get("pcr_oi"), "volume_pcr": chain.get("pcr_volume"),
            "atm_strike": atm_strike, "atm_call": atm_call, "atm_put": atm_put,
            "quoted_contracts": chain.get("quoted_contracts", 0),
            "spot_candle_time": str(spot_candles[-1].get("time", "")),
            "future_candle_time": str(future_candles[-1].get("time", "")),
            "session_final": datetime.now().time() >= datetime.strptime("15:30", "%H:%M").time(),
        }

    @staticmethod
    def _completed_candles(candles):
        result = list(candles)
        if not result:
            raise RuntimeError("Angel One returned no candles.")
        try:
            last_time = datetime.fromisoformat(str(result[-1]["time"]))
            now = datetime.now(last_time.tzinfo) if last_time.tzinfo else datetime.now()
            if last_time + timedelta(minutes=5) > now:
                result.pop()
        except (KeyError, TypeError, ValueError):
            pass
        if len(result) < 51:
            raise RuntimeError("At least 51 completed candles are required for closing indicators.")
        return result

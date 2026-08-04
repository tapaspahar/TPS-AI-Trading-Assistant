"""Read-only Angel One closing evidence for the Next-Day Bias Lab."""

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
        spot_candles = self.client.get_recent_candles(spot_exchange, spot_token, "FIVE_MINUTE", 5)
        future_candles = self.client.get_recent_candles(future["exchange"], future["token"], "FIVE_MINUTE", 5)
        spot = build_live_capture(symbol, "5m", spot_candles, f"Angel One {symbol} spot candles")
        future_capture = build_live_capture(symbol, "5m", future_candles, f"Angel One {future['symbol']}")

        contracts = self.contract_service.get_contracts(symbol)
        nearest_expiry = min(contract["expiry"] for contract in contracts)
        nearest = [contract for contract in contracts if contract["expiry"] == nearest_expiry]
        focused = contracts_near_spot(nearest, float(spot["close"]), wings=10)
        if not focused:
            raise RuntimeError(f"No nearest-expiry {symbol} option contracts were found.")
        quotes = self.client.get_option_chain_quotes(focused[0]["exchange"], [contract["token"] for contract in focused])
        chain = analyze_option_chain(focused, quotes)
        strikes = {row["strike"] for row in chain["quote_rows"]}
        if not strikes:
            raise RuntimeError("Angel One returned no option-chain strikes.")
        atm_strike = min(strikes, key=lambda strike: abs(strike - float(spot["close"])))
        atm_call = next((row["ltp"] for row in chain["quote_rows"] if row["strike"] == atm_strike and row["option_type"] == "CE"), 0)
        atm_put = next((row["ltp"] for row in chain["quote_rows"] if row["strike"] == atm_strike and row["option_type"] == "PE"), 0)
        return {
            "symbol": symbol, "future_symbol": future["symbol"], "expiry": nearest_expiry.strftime("%d-%m-%Y"),
            "spot": spot, "future": future_capture,
            "put_support": chain.get("put_support"), "call_resistance": chain.get("call_resistance"),
            "oi_pcr": chain.get("pcr_oi"), "volume_pcr": chain.get("pcr_volume"),
            "atm_strike": atm_strike, "atm_call": atm_call, "atm_put": atm_put,
            "quoted_contracts": chain.get("quoted_contracts", 0),
        }

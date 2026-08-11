"""Read-only Angel One candle loader for the Smart Money Lab."""
from datetime import datetime, timedelta

from engine.live_setup_capture import TIMEFRAMES
from services.option_contract_service import OptionContractService


class SmartMoneyDataService:
    def __init__(self, client, contract_service=None):
        self.client = client
        self.contract_service = contract_service or OptionContractService()

    def load(self, symbol, timeframe="5m"):
        symbol = str(symbol).upper()
        if timeframe not in ("5m", "15m"):
            raise ValueError("Choose 5m or 15m.")
        future = self.contract_service.get_front_month_future(symbol)
        interval, minutes = TIMEFRAMES[timeframe]
        candles = list(self.client.get_recent_candles(future["exchange"], future["token"], interval, minutes))
        if not candles:
            raise RuntimeError("Angel One returned no future candles.")
        try:
            last_time = datetime.fromisoformat(str(candles[-1]["time"]))
            now = datetime.now(last_time.tzinfo) if last_time.tzinfo else datetime.now()
            if last_time + timedelta(minutes=minutes) > now:
                candles.pop()
        except (KeyError, TypeError, ValueError):
            pass
        if len(candles) < 55:
            raise RuntimeError("At least 55 completed future candles are required.")
        return {"symbol": symbol, "future_symbol": future["symbol"], "timeframe": timeframe,
                "candles": candles, "candle_time": str(candles[-1].get("time", "")),
                "source": f"{getattr(self.client, 'provider_name', 'Broker')} {future['symbol']} completed {timeframe} OHLCV candles"}

"""Rate-conscious component heat-map breadth from one batched broker snapshot."""
from __future__ import annotations

from datetime import datetime

from engine.index_component_breadth import analyze_component_breadth, combine_component_breadth
from services.option_contract_service import OptionContractService


COMPONENTS = {
    "NIFTY": "ADANIENT ADANIPORTS APOLLOHOSP ASIANPAINT AXISBANK BAJAJ-AUTO BAJFINANCE BAJAJFINSV BEL BHARTIARTL CIPLA COALINDIA DRREDDY EICHERMOT ETERNAL GRASIM HCLTECH HDFCBANK HDFCLIFE HEROMOTOCO HINDALCO HINDUNILVR ICICIBANK INDUSINDBK INFY ITC JIOFIN KOTAKBANK LT M&M MARUTI NESTLEIND NTPC ONGC POWERGRID RELIANCE SBILIFE SBIN SHRIRAMFIN SUNPHARMA TATACONSUM TATAMOTORS TATASTEEL TCS TECHM TITAN TRENT ULTRACEMCO WIPRO".split(),
    "BANKNIFTY": "AUBANK AXISBANK BANKBARODA CANBK FEDERALBNK HDFCBANK ICICIBANK IDFCFIRSTB INDUSINDBK KOTAKBANK PNB SBIN".split(),
    "SENSEX": "ADANIPORTS ASIANPAINT AXISBANK BAJFINANCE BAJAJFINSV BHARTIARTL HCLTECH HDFCBANK HINDUNILVR ICICIBANK INDUSINDBK INFY ITC KOTAKBANK LT M&M MARUTI NESTLEIND NTPC POWERGRID RELIANCE SBIN SUNPHARMA TATAMOTORS TATASTEEL TCS TECHM TITAN ULTRACEMCO ZOMATO".split(),
}


class IndexComponentBreadthService:
    def __init__(self, client, database):
        self.client, self.database = client, database

    @staticmethod
    def _change(quote):
        value = quote.get("percentChange")
        if value not in (None, ""):
            return float(value)
        close = float(quote.get("close") or 0); ltp = float(quote.get("ltp") or 0)
        return (ltp - close) * 100 / close if close > 0 and ltp > 0 else None

    def scan(self, now=None):
        now = now or datetime.now().astimezone()
        instruments = OptionContractService().get_cash_instruments(set(sum(COMPONENTS.values(), [])))
        quotes = []
        tokens = [row["token"] for row in instruments.values()]
        for start in range(0, len(tokens), 50):
            quotes.extend(self.client.get_market_quotes({"NSE": tokens[start:start + 50]}))
        quote_by_token = {str(row.get("symbolToken") or row.get("symboltoken") or ""): row for row in quotes}
        results = []
        for symbol, names in COMPONENTS.items():
            rows = []
            for name in names:
                instrument = instruments.get(name)
                quote = quote_by_token.get(str((instrument or {}).get("token") or ""))
                if instrument and quote:
                    rows.append({"name": name, "change_percent": self._change(quote)})
            result = analyze_component_breadth(symbol, rows, len(names))
            result["captured_at"] = now.isoformat(timespec="seconds")
            self.database.save_index_component_breadth(result)
            results.append(result)
        return {"results": results, "combined": combine_component_breadth(results)}

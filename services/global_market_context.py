"""Read-only global context used as a small intraday confirmation layer."""
from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import quote
from urllib.request import Request, urlopen


NSE_IX_QUOTES = "https://www.nseix.com/api/getquotes?symbol=NIFTY&instrumenttype=FUT"
REFERENCE_MARKETS = {
    "S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Dow": "^DJI",
    "Nikkei": "^N225", "Hang Seng": "^HSI",
}


def _number(value):
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_gift_nifty(payload: dict) -> dict:
    """Select the nearest usable GIFT NIFTY future from NSE IX JSON."""
    rows = payload.get("data") or []
    usable = [row for row in rows if _number(row.get("LASTPRICE")) is not None]
    if not usable:
        return {"available": False, "source": "NSE IX official", "status": "Official quote unavailable"}
    row = usable[0]
    last = _number(row.get("LASTPRICE"))
    previous = _number(row.get("PREVCLOSE"))
    change = _number(row.get("DAYCHANGE"))
    percent = _number(row.get("PERCHANGE"))
    if percent is None and last is not None and previous:
        percent = (last - previous) / previous * 100
    return {
        "available": True, "name": "GIFT Nifty", "price": last,
        "change": change if change is not None else (last - previous if previous else None),
        "change_percent": percent, "open": _number(row.get("DAYOPEN")),
        "high": _number(row.get("DAYHIGH")), "low": _number(row.get("DAYLOW")),
        "expiry": str(row.get("EXPIRY") or ""), "source": "NSE IX official",
        "status": "Live/last available official quote",
    }


class GlobalMarketContextService:
    def __init__(self, timeout=5, opener=None):
        self.timeout = timeout
        self.opener = opener or urlopen

    def _json(self, url):
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 TPS-AI-Trading-Assistant/1.2"})
        with self.opener(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def gift_nifty(self):
        try:
            return parse_gift_nifty(self._json(NSE_IX_QUOTES))
        except Exception as error:
            return {"available": False, "source": "NSE IX official", "status": f"Unavailable: {error}"}

    def reference_markets(self):
        rows = []
        for name, symbol in REFERENCE_MARKETS.items():
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?interval=5m&range=1d"
                result = self._json(url)["chart"]["result"][0]
                meta = result.get("meta") or {}
                price = _number(meta.get("regularMarketPrice"))
                previous = _number(meta.get("chartPreviousClose") or meta.get("previousClose"))
                percent = (price - previous) / previous * 100 if price is not None and previous else None
                rows.append({"name": name, "available": percent is not None, "price": price,
                             "change_percent": percent, "source": "External reference; may be delayed"})
            except Exception as error:
                rows.append({"name": name, "available": False, "status": str(error),
                             "source": "External reference; may be delayed"})
        return rows

    def snapshot(self):
        gift = self.gift_nifty()
        markets = self.reference_markets()
        changes = [row["change_percent"] for row in markets if row.get("available")]
        positive = sum(value > .15 for value in changes)
        negative = sum(value < -.15 for value in changes)
        breadth = "POSITIVE" if positive >= 3 else "NEGATIVE" if negative >= 3 else "MIXED"
        gift_move = gift.get("change_percent") if gift.get("available") else None
        votes = (1 if gift_move is not None and gift_move > .10 else -1 if gift_move is not None and gift_move < -.10 else 0)
        votes += 1 if breadth == "POSITIVE" else -1 if breadth == "NEGATIVE" else 0
        bias = "POSITIVE" if votes > 0 else "NEGATIVE" if votes < 0 else "MIXED"
        return {"captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "gift_nifty": gift, "markets": markets, "breadth": breadth, "bias": bias,
                "score_adjustment": 6 if votes >= 2 else -6 if votes <= -2 else 3 if votes == 1 else -3 if votes == -1 else 0,
                "warning": "Global context is confirmation only; it never overrides completed Indian-market candles."}

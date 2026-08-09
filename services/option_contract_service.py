"""Read-only option-contract discovery from Angel One's daily instrument master."""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from time import perf_counter
from urllib.request import urlopen


# The current Angel One host resolves on normal Windows/Python installations.
MASTER_URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
UNDERLYINGS = {
    "NIFTY": "NFO",
    "BANKNIFTY": "NFO",
    "SENSEX": "BFO",
}
UNDERLYING_QUOTES = {
    "NIFTY": {"exchange": "NSE", "token": "99926000"},
    "BANKNIFTY": {"exchange": "NSE", "token": "99926009"},
    "SENSEX": {"exchange": "BSE", "token": "99919000"},
}


def _expiry_date(value):
    try:
        return datetime.strptime(str(value).upper(), "%d%b%Y").date()
    except ValueError:
        return None


def _strike(value):
    strike = float(value or 0)
    return strike / 100 if strike >= 100000 else strike


def parse_option_contracts(rows, underlying):
    """Keep valid, unexpired CE/PE index contracts for one underlying."""
    exchange = UNDERLYINGS[underlying]
    contracts = []
    for row in rows:
        if str(row.get("exch_seg", "")).upper() != exchange:
            continue
        if str(row.get("name", "")).upper() != underlying:
            continue
        if str(row.get("instrumenttype", "")).upper() != "OPTIDX":
            continue
        symbol = str(row.get("symbol", "")).upper()
        option_type = "CE" if symbol.endswith("CE") else "PE" if symbol.endswith("PE") else ""
        expiry = _expiry_date(row.get("expiry"))
        if not option_type or not expiry or expiry < date.today():
            continue
        contracts.append({
            "token": str(row["token"]), "symbol": row["symbol"], "exchange": exchange,
            "expiry": expiry, "strike": _strike(row.get("strike")), "option_type": option_type,
            "lot_size": int(float(row.get("lotsize", 0) or 0)),
        })
    return sorted(contracts, key=lambda item: (item["expiry"], item["strike"], item["option_type"]))


def parse_front_month_future(rows, underlying):
    """Return the nearest active index future used for traded-volume analysis."""
    exchange = UNDERLYINGS[underlying]
    futures = []
    for row in rows:
        if str(row.get("exch_seg", "")).upper() != exchange:
            continue
        if str(row.get("name", "")).upper() != underlying:
            continue
        if str(row.get("instrumenttype", "")).upper() != "FUTIDX":
            continue
        expiry = _expiry_date(row.get("expiry"))
        if not expiry or expiry < date.today():
            continue
        futures.append({
            "token": str(row["token"]), "symbol": str(row["symbol"]),
            "exchange": exchange, "expiry": expiry,
        })
    if not futures:
        raise RuntimeError(f"No active {underlying} index future was found in Angel One's instrument master.")
    return min(futures, key=lambda item: item["expiry"])


def buying_risk(premium, lot_size, capital, risk_percent):
    """Suggest the maximum whole lots within the user's configured premium-risk cap."""
    per_lot_risk = float(premium) * int(lot_size)
    risk_cap = float(capital) * float(risk_percent) / 100
    lots = int(risk_cap // per_lot_risk) if per_lot_risk > 0 else 0
    return {"risk_cap": risk_cap, "per_lot_risk": per_lot_risk, "lots": lots}


def contracts_near_spot(contracts, spot_price, wings=20):
    """Return ATM plus a fixed number of available strikes on either side of spot."""
    if not contracts:
        return []
    strikes = sorted({contract["strike"] for contract in contracts})
    atm_index = min(range(len(strikes)), key=lambda index: abs(strikes[index] - float(spot_price)))
    selected_strikes = set(strikes[max(0, atm_index - wings): atm_index + wings + 1])
    return [contract for contract in contracts if contract["strike"] in selected_strikes]


class OptionContractService:
    def __init__(self, cache_path=None):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TPS AI Trading Assistant" / "cache"
        self.cache_path = Path(cache_path) if cache_path else base / "angel_instruments.json"

    def _load_master(self, progress_callback=None):
        if self.cache_path.exists() and datetime.fromtimestamp(self.cache_path.stat().st_mtime).date() == date.today():
            if progress_callback:
                progress_callback(100, "Using today's saved Angel One instrument list.")
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        try:
            with urlopen(MASTER_URL, timeout=45) as response:
                total = int(response.headers.get("Content-Length", 0) or 0)
                chunks, downloaded, started = [], 0, perf_counter()
                if progress_callback:
                    progress_callback(0, "Connecting to Angel One instrument list…")
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total:
                        elapsed = max(perf_counter() - started, 0.1)
                        percent = min(int(downloaded * 100 / total), 99)
                        rate = downloaded / elapsed
                        remaining = max(total - downloaded, 0) / rate if rate else 0
                        progress_callback(percent, f"Downloading Angel One list: {percent}% ({downloaded / 1_048_576:.1f} / {total / 1_048_576:.1f} MB) - about {max(1, round(remaining))} sec left")
                    elif progress_callback:
                        progress_callback(-1, f"Downloading Angel One list: {downloaded / 1_048_576:.1f} MB received…")
                rows = json.loads(b"".join(chunks).decode("utf-8"))
        except Exception as error:
            raise RuntimeError("Could not download Angel One's instrument master. Check internet and try again.") from error
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(rows), encoding="utf-8")
        if progress_callback:
            progress_callback(100, "Download complete. Preparing the share list…")
        return rows

    def get_contracts(self, underlying):
        if underlying not in UNDERLYINGS:
            raise ValueError("Choose NIFTY, BANKNIFTY, or SENSEX.")
        contracts = parse_option_contracts(self._load_master(), underlying)
        if not contracts:
            raise RuntimeError(f"No current {underlying} option contracts were found.")
        return contracts

    def get_front_month_future(self, underlying):
        if underlying not in UNDERLYINGS:
            raise ValueError("Choose NIFTY, BANKNIFTY, or SENSEX.")
        return parse_front_month_future(self._load_master(), underlying)

    def get_india_vix_instrument(self):
        """Discover India VIX from the daily master instead of hard-coding a token."""
        for row in self._load_master():
            identity = f"{row.get('name', '')} {row.get('symbol', '')}".upper()
            if str(row.get("exch_seg", "")).upper() == "NSE" and "INDIA VIX" in identity:
                return {"exchange": "NSE", "token": str(row["token"]), "symbol": str(row.get("symbol") or "INDIA VIX")}
        raise RuntimeError("India VIX instrument was not found in Angel One's daily instrument master.")

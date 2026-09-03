"""Read-only option-contract discovery from Angel One's daily instrument master."""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from threading import RLock
from time import perf_counter, sleep
from urllib.request import Request, urlopen


# The current Angel One host resolves on normal Windows/Python installations.
MASTER_URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
MASTER_DOWNLOAD_ATTEMPTS = 3
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


def parse_stock_option_universe(rows):
    """Map NSE cash shares that currently have active stock-option contracts."""
    active_names = {
        str(row.get("name", "")).upper().strip()
        for row in rows
        if str(row.get("exch_seg", "")).upper() == "NFO"
        and str(row.get("instrumenttype", "")).upper() == "OPTSTK"
        and (_expiry_date(row.get("expiry")) or date.min) >= date.today()
    }
    universe, seen = [], set()
    for row in rows:
        name = str(row.get("name", "")).upper().strip()
        symbol = str(row.get("symbol", "")).upper().strip()
        token = str(row.get("token", "")).strip()
        if (
            str(row.get("exch_seg", "")).upper() != "NSE" or not symbol.endswith("-EQ")
            or name not in active_names or not token or name in seen
        ):
            continue
        seen.add(name)
        universe.append({
            "underlying": name, "company": str(row.get("name") or name),
            "symbol": symbol, "token": token, "exchange": "NSE", "derivative_exchange": "NFO",
        })
    return sorted(universe, key=lambda item: item["underlying"])


def parse_stock_option_contracts(rows, underlying):
    underlying = str(underlying).upper().strip()
    contracts = []
    for row in rows:
        if str(row.get("exch_seg", "")).upper() != "NFO":
            continue
        if str(row.get("name", "")).upper().strip() != underlying:
            continue
        if str(row.get("instrumenttype", "")).upper() != "OPTSTK":
            continue
        symbol = str(row.get("symbol", "")).upper()
        option_type = "CE" if symbol.endswith("CE") else "PE" if symbol.endswith("PE") else ""
        expiry = _expiry_date(row.get("expiry"))
        if not option_type or not expiry or expiry < date.today():
            continue
        contracts.append({
            "token": str(row["token"]), "symbol": str(row["symbol"]), "exchange": "NFO",
            "expiry": expiry, "strike": _strike(row.get("strike")), "option_type": option_type,
            "lot_size": int(float(row.get("lotsize", 0) or 0)),
        })
    return sorted(contracts, key=lambda item: (item["expiry"], item["strike"], item["option_type"]))


def parse_stock_front_month_future(rows, underlying):
    underlying = str(underlying).upper().strip()
    futures = []
    for row in rows:
        if str(row.get("exch_seg", "")).upper() != "NFO":
            continue
        if str(row.get("name", "")).upper().strip() != underlying:
            continue
        if str(row.get("instrumenttype", "")).upper() != "FUTSTK":
            continue
        expiry = _expiry_date(row.get("expiry"))
        if not expiry or expiry < date.today():
            continue
        futures.append({
            "token": str(row["token"]), "symbol": str(row["symbol"]), "exchange": "NFO",
            "expiry": expiry, "lot_size": int(float(row.get("lotsize", 0) or 0)),
        })
    if not futures:
        raise RuntimeError(f"No active {underlying} stock future was found in Angel One's instrument master.")
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
    _memory_lock = RLock()
    _memory_master = None
    _memory_day = None
    _memory_source = None
    _parsed_contracts = {}
    _parsed_futures = {}
    def __init__(self, cache_path=None):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TPS AI Trading Assistant" / "cache"
        self.cache_path = Path(cache_path) if cache_path else base / "angel_instruments.json"

    @staticmethod
    def _validate_master(rows):
        """Reject broker error pages/partial JSON before they can replace a good cache."""
        if not isinstance(rows, list) or not rows:
            raise ValueError("Instrument master did not contain a non-empty instrument list.")
        if not any(
            isinstance(row, dict) and row.get("token") and row.get("exch_seg")
            for row in rows
        ):
            raise ValueError("Instrument master rows are missing required token/exchange fields.")
        return rows

    def _read_cache(self):
        if not self.cache_path.exists():
            return None
        try:
            return self._validate_master(json.loads(self.cache_path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            return None

    def _download_master(self, progress_callback=None):
        request = Request(MASTER_URL, headers={"User-Agent": "TPS-AI-Trading-Assistant/1.4"})
        with urlopen(request, timeout=30) as response:
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
        return self._validate_master(json.loads(b"".join(chunks).decode("utf-8")))

    def _write_cache(self, rows):
        """Keep the previous usable cache intact if Windows/app shutdown interrupts a write."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
        temporary_path.write_text(json.dumps(rows), encoding="utf-8")
        os.replace(temporary_path, self.cache_path)

    def _load_master(self, progress_callback=None):
        today = date.today()
        with self._memory_lock:
            if (self._memory_day == today and self._memory_master is not None
                    and self._memory_source == str(self.cache_path.resolve())):
                return self._memory_master
        cached_rows = self._read_cache()
        if cached_rows is not None and datetime.fromtimestamp(self.cache_path.stat().st_mtime).date() == date.today():
            if progress_callback:
                progress_callback(100, "Using today's saved Angel One instrument list.")
            with self._memory_lock:
                self.__class__._memory_master = cached_rows
                self.__class__._memory_day = today
                self.__class__._memory_source = str(self.cache_path.resolve())
            return cached_rows
        last_error = None
        rows = None
        for attempt_number in range(1, MASTER_DOWNLOAD_ATTEMPTS + 1):
            try:
                rows = self._download_master(progress_callback)
                break
            except Exception as error:
                last_error = error
                if progress_callback:
                    progress_callback(-1, f"Instrument-list attempt {attempt_number}/{MASTER_DOWNLOAD_ATTEMPTS} failed; retrying…")
                if attempt_number < MASTER_DOWNLOAD_ATTEMPTS:
                    sleep(attempt_number)
        if rows is None:
            if cached_rows is not None:
                cache_date = datetime.fromtimestamp(self.cache_path.stat().st_mtime).strftime("%d-%m-%Y")
                if progress_callback:
                    progress_callback(100, f"Live list unavailable; using verified saved list from {cache_date}.")
                with self._memory_lock:
                    self.__class__._memory_master = cached_rows
                    self.__class__._memory_day = today
                    self.__class__._memory_source = str(self.cache_path.resolve())
                return cached_rows
            raise RuntimeError(
                "Could not download Angel One's instrument master and no verified saved list is available. Check internet and try again."
            ) from last_error
        self._write_cache(rows)
        if progress_callback:
            progress_callback(100, "Download complete. Preparing the share list…")
        with self._memory_lock:
            self.__class__._memory_master = rows
            self.__class__._memory_day = today
            self.__class__._memory_source = str(self.cache_path.resolve())
            self.__class__._parsed_contracts.clear()
            self.__class__._parsed_futures.clear()
        return rows

    def get_contracts(self, underlying):
        if underlying not in UNDERLYINGS:
            raise ValueError("Choose NIFTY, BANKNIFTY, or SENSEX.")
        self._load_master()
        cache_key = (date.today(), str(self.cache_path.resolve()), underlying)
        with self._memory_lock:
            contracts = self._parsed_contracts.get(cache_key)
            if contracts is None:
                contracts = parse_option_contracts(self._memory_master, underlying)
                self.__class__._parsed_contracts[cache_key] = contracts
        if not contracts:
            raise RuntimeError(f"No current {underlying} option contracts were found.")
        return list(contracts)

    def get_front_month_future(self, underlying):
        if underlying not in UNDERLYINGS:
            raise ValueError("Choose NIFTY, BANKNIFTY, or SENSEX.")
        self._load_master()
        cache_key = (date.today(), str(self.cache_path.resolve()), underlying)
        with self._memory_lock:
            future = self._parsed_futures.get(cache_key)
            if future is None:
                future = parse_front_month_future(self._memory_master, underlying)
                self.__class__._parsed_futures[cache_key] = future
        return dict(future)

    def get_india_vix_instrument(self):
        """Discover India VIX from the daily master instead of hard-coding a token."""
        for row in self._load_master():
            identity = f"{row.get('name', '')} {row.get('symbol', '')}".upper()
            if str(row.get("exch_seg", "")).upper() == "NSE" and "INDIA VIX" in identity:
                return {"exchange": "NSE", "token": str(row["token"]), "symbol": str(row.get("symbol") or "INDIA VIX")}
        raise RuntimeError("India VIX instrument was not found in Angel One's daily instrument master.")

    def get_stock_option_universe(self):
        universe = parse_stock_option_universe(self._load_master())
        if not universe:
            raise RuntimeError("No active NSE stock-option underlyings were found in Angel One's instrument master.")
        return universe

    def get_stock_contracts(self, underlying):
        contracts = parse_stock_option_contracts(self._load_master(), underlying)
        if not contracts:
            raise RuntimeError(f"No active {underlying} stock-option contracts were found.")
        return contracts

    def get_cash_instruments(self, symbols):
        """Resolve requested NSE cash components from the daily broker master."""
        rows = self._load_master()
        wanted = {str(symbol).upper().replace("-EQ", "") for symbol in symbols}
        result = {}
        for row in rows:
            symbol = str(row.get("symbol") or "").upper()
            name = str(row.get("name") or "").upper()
            key = symbol[:-3] if symbol.endswith("-EQ") else name
            if str(row.get("exch_seg") or "").upper() == "NSE" and symbol.endswith("-EQ") and key in wanted:
                result[key] = {"symbol": symbol, "token": str(row.get("token") or ""), "exchange": "NSE"}
        return result

    def get_stock_front_month_future(self, underlying):
        return parse_stock_front_month_future(self._load_master(), underlying)

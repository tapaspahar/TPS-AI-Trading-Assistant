"""Translate TPS/Angel instrument references to Paytm Money security IDs."""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from threading import Lock
from urllib.request import urlopen

from services.option_contract_service import MASTER_URL as ANGEL_MASTER_URL


PAYTM_MASTER_URL = "https://developer.paytmmoney.com/data/v1/scrips/security_master.csv"


@dataclass(frozen=True)
class PaytmMoneyInstrument:
    security_id: str
    exchange: str
    segment: str
    instrument_type: str
    scrip_type: str
    symbol: str
    underlying: str
    expiry: str = ""
    strike: float = 0.0
    option_type: str = ""


class PaytmMoneyInstrumentMapper:
    """Build a daily, public cross-broker instrument map."""

    SPOT = {
        ("NSE", "99926000"): PaytmMoneyInstrument("13", "NSE", "I", "I", "INDEX", "NIFTY", "NIFTY 50"),
        ("NSE", "99926009"): PaytmMoneyInstrument("25", "NSE", "I", "I", "INDEX", "BANKNIFTY", "NIFTY BANK"),
        ("NSE", "99926017"): PaytmMoneyInstrument("21", "NSE", "I", "I", "INDEX", "INDIA VIX", "INDIA VIX"),
        ("BSE", "99919000"): PaytmMoneyInstrument("51", "BSE", "I", "I", "INDEX", "SENSEX", "SENSEX"),
    }

    def __init__(self, cache_dir=None):
        base = Path(cache_dir) if cache_dir else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TPS AI Trading Assistant" / "cache"
        self.angel_path = base / "angel_instruments.json"
        self.paytm_path = base / "paytm_money_security_master.csv"
        self._lock = Lock()
        self._angel_by_token = None
        self._cash_index = None
        self._derivative_index = None

    @staticmethod
    def _fresh(path):
        return path.exists() and datetime.fromtimestamp(path.stat().st_mtime).date() == date.today()

    @staticmethod
    def _download(url, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(url, timeout=90) as response:
            path.write_bytes(response.read())

    @staticmethod
    def _normal(value):
        return "".join(ch for ch in str(value or "").upper() if ch.isalnum())

    def _load(self):
        if self._angel_by_token is not None:
            return
        with self._lock:
            if self._angel_by_token is not None:
                return
            if not self._fresh(self.angel_path):
                self._download(ANGEL_MASTER_URL, self.angel_path)
            if not self._fresh(self.paytm_path):
                self._download(PAYTM_MASTER_URL, self.paytm_path)
            angel_rows = json.loads(self.angel_path.read_text(encoding="utf-8"))
            self._angel_by_token = {
                (str(row.get("exch_seg", "")).upper(), str(row.get("token", ""))): row
                for row in angel_rows
            }
            self._cash_index, self._derivative_index = {}, {}
            with self.paytm_path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    exchange = str(row.get("exchange", "")).upper()
                    segment = str(row.get("segment", "")).upper()
                    kind = str(row.get("instrument_type", "")).upper()
                    if exchange not in {"NSE", "BSE"}:
                        continue
                    if segment == "E":
                        for candidate in (row.get("symbol"), row.get("name")):
                            key = (exchange, self._normal(candidate).removesuffix("EQ"))
                            if key[1]:
                                self._cash_index.setdefault(key, row)
                    elif segment == "D":
                        symbol = str(row.get("symbol", "")).upper()
                        underlying = symbol.split("-")[0]
                        option_type = "CE" if symbol.endswith("-CE") else "PE" if symbol.endswith("-PE") else ""
                        expiry = str(row.get("expiry_date", ""))[:10]
                        strike = round(float(row.get("strike_price") or 0), 3)
                        key = (exchange, kind, self._normal(underlying), expiry, strike, option_type)
                        self._derivative_index.setdefault(key, row)

    @staticmethod
    def _angel_expiry(value):
        try:
            return datetime.strptime(str(value).upper(), "%d%b%Y").date().isoformat()
        except ValueError:
            return ""

    @staticmethod
    def _angel_strike(value):
        strike = float(value or 0)
        return strike / 100 if strike >= 100000 else strike

    def resolve(self, exchange, angel_token):
        exchange, angel_token = str(exchange).upper(), str(angel_token)
        if (exchange, angel_token) in self.SPOT:
            return self.SPOT[(exchange, angel_token)]
        self._load()
        angel = self._angel_by_token.get((exchange, angel_token))
        if not angel:
            raise RuntimeError(f"Paytm Money mapping unavailable for {exchange} instrument token {angel_token}.")
        kind = str(angel.get("instrumenttype", "")).upper()
        underlying = str(angel.get("name", "")).upper().strip()
        symbol = str(angel.get("symbol", "")).upper().strip()
        paytm_exchange = "NSE" if exchange in {"NSE", "NFO"} else "BSE"
        segment = "D" if exchange in {"NFO", "BFO"} else "E"
        expiry = self._angel_expiry(angel.get("expiry"))
        strike = self._angel_strike(angel.get("strike"))
        option_type = "CE" if symbol.endswith("CE") else "PE" if symbol.endswith("PE") else ""
        if segment == "E":
            row = self._cash_index.get((paytm_exchange, self._normal(underlying))) or self._cash_index.get(
                (paytm_exchange, self._normal(symbol).removesuffix("EQ"))
            )
        else:
            row = self._derivative_index.get((
                paytm_exchange, kind, self._normal(underlying), expiry,
                round(strike if kind.startswith("OPT") else 0, 3), option_type,
            ))
        if not row:
            raise RuntimeError(
                f"Paytm Money Security ID was not found for {symbol or underlying}. "
                "Reconnect after Paytm Money publishes today's security master."
            )
        paytm_symbol = str(row.get("symbol") or symbol)
        return PaytmMoneyInstrument(
            security_id=str(row["security_id"]), exchange=paytm_exchange, segment=segment,
            instrument_type=str(row.get("instrument_type") or kind).upper(),
            scrip_type=str(row.get("instrument_type") or "EQUITY").upper(), symbol=paytm_symbol,
            underlying=underlying, expiry=expiry, strike=float(row.get("strike_price") or 0),
            option_type=option_type,
        )

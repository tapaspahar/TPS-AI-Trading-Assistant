"""Translate the existing TPS instrument references to Dhan Security IDs."""
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


DHAN_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"


@dataclass(frozen=True)
class DhanInstrument:
    security_id: str
    exchange_segment: str
    instrument: str
    symbol: str


class DhanInstrumentMapper:
    """Build a daily cached cross-broker instrument map without user secrets."""

    SPOT = {
        ("NSE", "99926000"): DhanInstrument("13", "IDX_I", "INDEX", "NIFTY"),
        ("NSE", "99926009"): DhanInstrument("25", "IDX_I", "INDEX", "BANKNIFTY"),
        ("NSE", "99926017"): DhanInstrument("21", "IDX_I", "INDEX", "INDIA VIX"),
        ("BSE", "99919000"): DhanInstrument("51", "IDX_I", "INDEX", "SENSEX"),
    }
    EXCHANGE_SEGMENTS = {
        ("NSE", "E"): "NSE_EQ", ("BSE", "E"): "BSE_EQ",
        ("NSE", "D"): "NSE_FNO", ("BSE", "D"): "BSE_FNO",
    }

    def __init__(self, cache_dir=None):
        base = Path(cache_dir) if cache_dir else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TPS AI Trading Assistant" / "cache"
        self.angel_path = base / "angel_instruments.json"
        self.dhan_path = base / "dhan_instruments.csv"
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

    def _load(self):
        if self._angel_by_token is not None and self._cash_index is not None:
            return
        with self._lock:
            if self._angel_by_token is not None and self._cash_index is not None:
                return
            if not self._fresh(self.angel_path):
                self._download(ANGEL_MASTER_URL, self.angel_path)
            if not self._fresh(self.dhan_path):
                self._download(DHAN_MASTER_URL, self.dhan_path)
            rows = json.loads(self.angel_path.read_text(encoding="utf-8"))
            self._angel_by_token = {
                (str(row.get("exch_seg", "")).upper(), str(row.get("token", ""))): row for row in rows
            }
            self._cash_index, self._derivative_index = {}, {}
            with self.dhan_path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    dhan_exchange = str(row.get("EXCH_ID", "")).upper()
                    segment = str(row.get("SEGMENT", "")).upper()
                    if dhan_exchange not in {"NSE", "BSE"}:
                        continue
                    if segment == "E":
                        for name in (row.get("SYMBOL_NAME"), row.get("UNDERLYING_SYMBOL")):
                            if str(name or "").strip():
                                self._cash_index.setdefault((dhan_exchange, str(name).upper().strip()), row)
                    elif segment == "D":
                        key = (
                            dhan_exchange, str(row.get("INSTRUMENT", "")).upper(),
                            str(row.get("UNDERLYING_SYMBOL", "")).upper().strip(),
                            str(row.get("SM_EXPIRY_DATE", ""))[:10],
                            round(float(row.get("STRIKE_PRICE", 0) or 0), 3),
                            str(row.get("OPTION_TYPE", "")).upper(),
                        )
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
            raise RuntimeError(f"Dhan mapping unavailable for {exchange} instrument token {angel_token}.")
        kind = str(angel.get("instrumenttype", "")).upper()
        underlying = str(angel.get("name", "")).upper().strip()
        symbol = str(angel.get("symbol", "")).upper().strip()
        expiry = self._angel_expiry(angel.get("expiry"))
        strike = self._angel_strike(angel.get("strike"))
        option_type = "CE" if symbol.endswith("CE") else "PE" if symbol.endswith("PE") else ""
        segment = "D" if exchange in {"NFO", "BFO"} else "E"
        dhan_exchange = "NSE" if exchange in {"NSE", "NFO"} else "BSE"
        if segment == "E":
            row = self._cash_index.get((dhan_exchange, underlying)) or self._cash_index.get((dhan_exchange, symbol.removesuffix("-EQ")))
        else:
            row = self._derivative_index.get((
                dhan_exchange, kind, underlying, expiry,
                round(strike if kind.startswith("OPT") else -0.01, 3), option_type if kind.startswith("OPT") else "XX",
            ))
            if row is None and not kind.startswith("OPT"):
                # Dhan currently represents the non-applicable future strike as
                # either -0.01 or 0 depending on the exchange master revision.
                row = self._derivative_index.get((dhan_exchange, kind, underlying, expiry, 0.0, "XX"))
        if not row:
            raise RuntimeError(
                f"Dhan Security ID was not found for {symbol or underlying}. "
                "Refresh again after Dhan publishes today's instrument list."
            )
        instrument = "EQUITY" if segment == "E" else str(row.get("INSTRUMENT", kind)).upper()
        return DhanInstrument(
            str(row["SECURITY_ID"]), self.EXCHANGE_SEGMENTS[(dhan_exchange, segment)], instrument,
            str(row.get("DISPLAY_NAME") or row.get("SYMBOL_NAME") or symbol),
        )

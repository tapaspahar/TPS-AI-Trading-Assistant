"""Manual import of official NSE end-of-day UDiFF/bhavcopy reports."""
from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from datetime import datetime
from pathlib import Path


def _key(value):
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def _value(row, *names):
    normalized = {_key(k): v for k, v in row.items()}
    return next((normalized[_key(name)] for name in names if normalized.get(_key(name)) not in (None, "")), None)


def _number(value):
    try: return float(str(value).replace(",", ""))
    except (TypeError, ValueError): return None


class NseEodImportService:
    def __init__(self, database): self.database = database

    @staticmethod
    def _csv_payloads(path: Path):
        raw = path.read_bytes()
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                return [(name, archive.read(name)) for name in archive.namelist() if name.lower().endswith(('.csv', '.txt'))]
        return [(path.name, raw)]

    def import_file(self, path):
        path = Path(path); digest = hashlib.sha256(path.read_bytes()).hexdigest()
        existing = self.database.cursor.execute("SELECT id FROM nse_eod_imports WHERE sha256=?", (digest,)).fetchone()
        if existing: raise ValueError("Ye exact NSE report pehle hi import ho chuki hai.")
        parsed, segment, detected_date = [], "UNKNOWN", None
        for name, payload in self._csv_payloads(path):
            text = payload.decode("utf-8-sig", errors="replace")
            reader = csv.DictReader(io.StringIO(text))
            for raw in reader:
                instrument = str(_value(raw, "FinInstrmTp", "INSTRUMENT", "Instrument Type") or "").upper()
                if instrument.startswith(("OP", "FU")) or _value(raw, "XpryDt", "EXPIRY_DT", "EXPIRY DATE"):
                    segment = "FO"
                elif segment == "UNKNOWN": segment = "CM"
                trade_date = _value(raw, "TradDt", "TIMESTAMP", "TRADE_DATE", "DATE1")
                detected_date = detected_date or trade_date
                parsed.append({
                    "trade_date": trade_date, "symbol": _value(raw, "TckrSymb", "SYMBOL", "SC_NAME"),
                    "expiry": _value(raw, "XpryDt", "EXPIRY_DT", "EXPIRY DATE"),
                    "strike": _number(_value(raw, "StrkPric", "STRIKE_PR", "STRIKE PRICE")),
                    "option_type": _value(raw, "OptnTp", "OPTION_TYP", "OPTION TYPE"),
                    "open": _number(_value(raw, "OpnPric", "OPEN", "OPEN_PRICE")),
                    "high": _number(_value(raw, "HghPric", "HIGH", "HIGH_PRICE")),
                    "low": _number(_value(raw, "LwPric", "LOW", "LOW_PRICE")),
                    "close": _number(_value(raw, "ClsPric", "CLOSE", "CLOSE_PRICE")),
                    "volume": _number(_value(raw, "TtlTradgVol", "CONTRACTS", "TOTTRDQTY", "VOLUME")),
                    "open_interest": _number(_value(raw, "OpnIntrst", "OPEN_INT", "OPEN INTEREST")), "raw": raw,
                })
        if not parsed: raise ValueError("ZIP/CSV me readable NSE bhavcopy rows nahi mili.")
        summary = {"imported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                   "source_file": path.name, "segment": segment, "trade_date": detected_date,
                   "status": "BACKFILLED", "sha256": digest, "matched_rows": 0,
                   "files": [name for name, _ in self._csv_payloads(path)]}
        summary["import_id"] = self.database.save_nse_eod_import(summary, parsed)
        summary["row_count"] = len(parsed)
        return summary

"""Read-only option-contract discovery from Angel One's daily instrument master."""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from urllib.request import urlopen


# The current Angel One host resolves on normal Windows/Python installations.
MASTER_URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
UNDERLYINGS = {
    "NIFTY": "NFO",
    "BANKNIFTY": "NFO",
    "SENSEX": "BFO",
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


def buying_risk(premium, lot_size, capital, risk_percent):
    """Suggest the maximum whole lots within the user's configured premium-risk cap."""
    per_lot_risk = float(premium) * int(lot_size)
    risk_cap = float(capital) * float(risk_percent) / 100
    lots = int(risk_cap // per_lot_risk) if per_lot_risk > 0 else 0
    return {"risk_cap": risk_cap, "per_lot_risk": per_lot_risk, "lots": lots}


class OptionContractService:
    def __init__(self, cache_path=None):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TPS AI Trading Assistant" / "cache"
        self.cache_path = Path(cache_path) if cache_path else base / "angel_instruments.json"

    def _load_master(self):
        if self.cache_path.exists() and datetime.fromtimestamp(self.cache_path.stat().st_mtime).date() == date.today():
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        try:
            with urlopen(MASTER_URL, timeout=45) as response:
                rows = json.loads(response.read().decode("utf-8"))
        except Exception as error:
            raise RuntimeError("Could not download Angel One's instrument master. Check internet and try again.") from error
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(rows), encoding="utf-8")
        return rows

    def get_contracts(self, underlying):
        if underlying not in UNDERLYINGS:
            raise ValueError("Choose NIFTY, BANKNIFTY, or SENSEX.")
        contracts = parse_option_contracts(self._load_master(), underlying)
        if not contracts:
            raise RuntimeError(f"No current {underlying} option contracts were found.")
        return contracts

"""Read-only discovery of NSE equity instruments from Angel One's master file."""
from __future__ import annotations

from services.option_contract_service import OptionContractService


def parse_equity_instruments(rows):
    """Return active NSE delivery-equity records suitable for chart analysis."""
    equities = []
    seen_tokens = set()
    for row in rows:
        if str(row.get("exch_seg", "")).upper() != "NSE":
            continue
        symbol = str(row.get("symbol", "")).upper().strip()
        token = str(row.get("token", "")).strip()
        if not symbol.endswith("-EQ") or not token or token in seen_tokens:
            continue
        seen_tokens.add(token)
        company = str(row.get("name", "")).strip() or symbol.removesuffix("-EQ")
        equities.append({"company": company, "symbol": symbol, "token": token, "exchange": "NSE"})
    return sorted(equities, key=lambda item: (item["company"].upper(), item["symbol"]))


class EquityInstrumentService(OptionContractService):
    """Uses the existing daily Angel One instrument-master cache."""

    def get_equities(self, progress_callback=None):
        equities = parse_equity_instruments(self._load_master(progress_callback))
        if not equities:
            raise RuntimeError("No NSE equity instruments were found in Angel One's instrument master.")
        return equities

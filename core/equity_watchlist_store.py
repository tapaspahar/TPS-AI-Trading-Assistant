"""Persistent local watchlist for the Equity Research workspace."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path


class EquityWatchlistStore:
    def __init__(self, path: str | Path | None = None):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TPS AI Trading Assistant"
        self.path = Path(path) if path else base / "equity_watchlist.json"

    def load(self) -> list[dict]:
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict) and row.get("symbol") and row.get("token")]

    def save_equity(self, equity: dict) -> list[dict]:
        rows = self.load()
        item = {
            "company": str(equity.get("company", "")).strip(),
            "symbol": str(equity["symbol"]).upper().strip(),
            "token": str(equity["token"]).strip(),
            "exchange": str(equity.get("exchange", "NSE")).upper().strip(),
            "last_price": equity.get("last_price"),
            "score": equity.get("score"),
            "plan_state": str(equity.get("plan_state", "Not analysed")),
            "analyzed_at": equity.get("analyzed_at"),
        }
        rows = [row for row in rows if str(row.get("symbol", "")).upper() != item["symbol"]]
        rows.append(item)
        rows.sort(key=lambda row: (str(row.get("company", "")).upper(), str(row["symbol"])))
        self._write(rows)
        return rows

    def update_analysis(self, symbol: str, result: dict) -> list[dict]:
        rows = self.load()
        for row in rows:
            if str(row.get("symbol", "")).upper() == str(symbol).upper():
                row.update({
                    "last_price": round(float(result["price"]), 2),
                    "score": int(result["score"]),
                    "plan_state": str(result["plan_state"]),
                    "analyzed_at": datetime.now().isoformat(timespec="minutes"),
                })
                self._write(rows)
                break
        return rows

    def remove(self, symbol: str) -> list[dict]:
        rows = [row for row in self.load() if str(row.get("symbol", "")).upper() != str(symbol).upper()]
        self._write(rows)
        return rows

    def _write(self, rows: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        temporary.replace(self.path)

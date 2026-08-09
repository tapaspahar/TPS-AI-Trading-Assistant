"""Small local watchlist for NSE stocks with listed option contracts."""
from __future__ import annotations

import json
import os
from pathlib import Path


class StockOptionWatchlistStore:
    def __init__(self, path=None):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TPS AI Trading Assistant"
        self.path = Path(path) if path else base / "stock_option_watchlist.json"

    def load(self):
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        return rows if isinstance(rows, list) else []

    def save(self, equity):
        rows = self.load()
        if any(row.get("underlying") == equity.get("underlying") for row in rows):
            return rows
        if len(rows) >= 8:
            raise ValueError("Automatic stock-option watchlist is limited to 8 shares to protect Angel One rate limits.")
        rows.append(dict(equity))
        self._write(rows)
        return rows

    def remove(self, underlying):
        rows = [row for row in self.load() if row.get("underlying") != underlying]
        self._write(rows)
        return rows

    def _write(self, rows):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

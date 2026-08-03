"""Persistent, local-only application preferences."""

from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULT_SETTINGS = {
    "capital": 100000.0,
    "risk_percent": 1.0,
    "daily_loss_percent": 3.0,
    "max_trades_per_day": 5,
    "theme": "dark",
}


class SettingsStore:
    def __init__(self, path: str | Path | None = None):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TPS AI Trading Assistant"
        self.path = Path(path) if path else base / "settings.json"

    def load(self) -> dict:
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            saved = {}
        return {**DEFAULT_SETTINGS, **saved}

    def save(self, settings: dict) -> dict:
        values = {
            "capital": float(settings["capital"]),
            "risk_percent": float(settings["risk_percent"]),
            "daily_loss_percent": float(settings["daily_loss_percent"]),
            "max_trades_per_day": int(settings["max_trades_per_day"]),
            "theme": str(settings.get("theme", self.load()["theme"])).lower(),
        }
        if values["capital"] <= 0 or not 0 < values["risk_percent"] <= 100:
            raise ValueError("Capital must be positive and risk percentage must be between 0 and 100.")
        if not 0 < values["daily_loss_percent"] <= 100 or values["max_trades_per_day"] < 1:
            raise ValueError("Daily-loss percentage must be between 0 and 100, and trade limit must be at least 1.")
        if values["theme"] not in {"dark", "light", "emerald", "sunset"}:
            raise ValueError("Choose a valid TPS visual theme.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(values, indent=2), encoding="utf-8")
        return values

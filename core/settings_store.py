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
    "trade_plan_min_score": 95,
    "theme": "dark",
    "ui_style": "glassmorphism",
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
            "trade_plan_min_score": int(settings.get("trade_plan_min_score", self.load()["trade_plan_min_score"])),
            "theme": str(settings.get("theme", self.load()["theme"])).lower(),
            "ui_style": str(settings.get("ui_style", self.load()["ui_style"])).lower(),
        }
        if values["capital"] <= 0 or not 0 < values["risk_percent"] <= 100:
            raise ValueError("Capital must be positive and risk percentage must be between 0 and 100.")
        if not 0 < values["daily_loss_percent"] <= 100 or values["max_trades_per_day"] < 1:
            raise ValueError("Daily-loss percentage must be between 0 and 100, and trade limit must be at least 1.")
        if not 50 <= values["trade_plan_min_score"] <= 100:
            raise ValueError("Trade-plan minimum score must be between 50 and 100.")
        if values["theme"] not in {"dark", "light", "emerald", "sunset"}:
            raise ValueError("Choose a valid TPS visual theme.")
        if values["ui_style"] not in {"skeuomorphism", "neomorphism", "glassmorphism", "claymorphism", "minimalism", "maximalism", "brutalism", "liquid_glass", "bento_grid", "spatial_ui"}:
            raise ValueError("Choose a valid TPS UI design style.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(values, indent=2), encoding="utf-8")
        return values

"""Persistent, local-only application preferences."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


DEFAULT_SETTINGS = {
    "capital": 100000.0,
    "risk_percent": 1.0,
    "daily_loss_percent": 3.0,
    "max_trades_per_day": 5,
    # Release 1.3 capital-protection defaults. Recovery mode governs paper
    # captures only; TPS remains unable to place a broker order.
    "recovery_mode_enabled": True,
    "recovery_daily_trade_limit": 1,
    "recovery_loss_streak_limit": 2,
    "recovery_lock_hours": 48,
    "recovery_min_paper_sessions": 30,
    "trade_plan_min_score": 95,
    "tps_required_matches": 5,
    "tps_match_mode": "adaptive",
    "tps_enabled_conditions": [
        "Market structure", "Price vs VWAP", "EMA 5/20/50 alignment",
        "SuperTrend confirmation", "Pullback and reversal", "Directional volume", "OI/PCR context",
        "Market environment / VIX",
    ],
    "news_risk_pause": False,
    "event_no_trade_minutes": 30,
    "economic_calendar_api_key": "",
    "economic_calendar_enabled": True,
    "event_feed_fail_closed": False,
    "event_risk_override": False,
    "paper_trade_cooldown_minutes": 15,
    "minimum_rr_ratio": 1.5,
    "maximum_option_spread_percent": 8.0,
    "minimum_option_volume": 100.0,
    "trailing_stop_enabled": True,
    "trailing_stop_trigger_r": 1.0,
    "trailing_stop_lock_r": 0.25,
    "time_exit_minutes_before_close": 10,
    "theme": "dark",
    "ui_style": "glassmorphism",
    "broker_provider": "angel_one",
    "notifications_enabled": True,
    "notification_sound": True,
    "notification_preferences": {
        "trade_capture": True,
        "trade_exit": True,
        "target_achieved": True,
        "stop_loss": True,
        "market_snapshot": True,
        "market_structure": True,
        "support_resistance": True,
        "put_call_ratio": True,
        "auto_attempt_report": False,
        # Near-qualified setup observation only. Disabled by default so it can
        # never be mistaken for a trade-entry approval.
        "early_watch": False,
        "equity_research": False,
        "chart_capture": False,
        "ai_analysis": True,
        "trade_journal": True,
        "risk_manager": True,
        "reports": False,
        "backtesting": False,
        "candle_replay": False,
        "post_market_report": True,
        "post_market_analysis": True,
        "next_day_bias": True,
        "cas_analysis": False,
        "stock_options_watch": True,
        "option_strategies": True,
        "smart_money_lab": True,
        "pre_candle_lab": False,
        "powerful_engine": True,
        "auto_opportunity": True,
        "broker_connection": True,
        "trend_memory": True,
        "scalper": True,
        "self_development": True,
    },
}


class SettingsStore:
    def __init__(self, path: str | Path | None = None):
        if path is not None:
            self.path = Path(path)
        else:
            # Roaming AppData is independent of the source folder, build/dist
            # folder and installer directory.  A code update must therefore
            # never replace a trader's chosen setup.
            roaming = Path(os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or Path.home())
            self.path = roaming / "TPS AI Trading Assistant" / "settings.json"
            legacy = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TPS AI Trading Assistant" / "settings.json"
            if not self.path.exists() and legacy.exists() and legacy != self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(legacy, self.path)
        self.backup_path = self.path.with_name("settings.backup.json")
        if self.path.exists() and not self.backup_path.exists() and self._read_file(self.path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.path, self.backup_path)

    @staticmethod
    def _read_file(path: Path) -> dict:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def load(self) -> dict:
        saved = self._read_file(self.path)
        if not saved:
            saved = self._read_file(self.backup_path)
        values = {**DEFAULT_SETTINGS, **saved}
        values["notification_preferences"] = {
            **DEFAULT_SETTINGS["notification_preferences"],
            **(saved.get("notification_preferences") or {}),
        }
        return values

    def save(self, settings: dict) -> dict:
        current = self.load()
        # Start with the current file so fields introduced by another module
        # or a future release survive a partial Settings-page save.
        values = {**current,
            "capital": float(settings["capital"]),
            "risk_percent": float(settings["risk_percent"]),
            "daily_loss_percent": float(settings["daily_loss_percent"]),
            "max_trades_per_day": int(settings["max_trades_per_day"]),
            "recovery_mode_enabled": bool(settings.get("recovery_mode_enabled", current["recovery_mode_enabled"])),
            "recovery_daily_trade_limit": int(settings.get("recovery_daily_trade_limit", current["recovery_daily_trade_limit"])),
            "recovery_loss_streak_limit": int(settings.get("recovery_loss_streak_limit", current["recovery_loss_streak_limit"])),
            "recovery_lock_hours": int(settings.get("recovery_lock_hours", current["recovery_lock_hours"])),
            "recovery_min_paper_sessions": int(settings.get("recovery_min_paper_sessions", current["recovery_min_paper_sessions"])),
            "trade_plan_min_score": int(settings.get("trade_plan_min_score", current["trade_plan_min_score"])),
            "tps_required_matches": int(settings.get("tps_required_matches", current["tps_required_matches"])),
            "tps_match_mode": str(settings.get("tps_match_mode", current["tps_match_mode"])),
            "tps_enabled_conditions": list(settings.get("tps_enabled_conditions", current["tps_enabled_conditions"])),
            "news_risk_pause": bool(settings.get("news_risk_pause", current["news_risk_pause"])),
            "event_no_trade_minutes": int(settings.get("event_no_trade_minutes", current["event_no_trade_minutes"])),
            "economic_calendar_api_key": str(settings.get("economic_calendar_api_key", current["economic_calendar_api_key"])).strip(),
            "economic_calendar_enabled": bool(settings.get("economic_calendar_enabled", current["economic_calendar_enabled"])),
            "event_feed_fail_closed": bool(settings.get("event_feed_fail_closed", current["event_feed_fail_closed"])),
            "event_risk_override": bool(settings.get("event_risk_override", current["event_risk_override"])),
            "paper_trade_cooldown_minutes": int(settings.get("paper_trade_cooldown_minutes", current["paper_trade_cooldown_minutes"])),
            "minimum_rr_ratio": float(settings.get("minimum_rr_ratio", current["minimum_rr_ratio"])),
            "maximum_option_spread_percent": float(settings.get("maximum_option_spread_percent", current["maximum_option_spread_percent"])),
            "minimum_option_volume": float(settings.get("minimum_option_volume", current["minimum_option_volume"])),
            "trailing_stop_enabled": bool(settings.get("trailing_stop_enabled", current["trailing_stop_enabled"])),
            "trailing_stop_trigger_r": float(settings.get("trailing_stop_trigger_r", current["trailing_stop_trigger_r"])),
            "trailing_stop_lock_r": float(settings.get("trailing_stop_lock_r", current["trailing_stop_lock_r"])),
            "time_exit_minutes_before_close": int(settings.get("time_exit_minutes_before_close", current["time_exit_minutes_before_close"])),
            "theme": str(settings.get("theme", current["theme"])).lower(),
            "ui_style": str(settings.get("ui_style", current["ui_style"])).lower(),
            "broker_provider": str(settings.get("broker_provider", current["broker_provider"])).lower(),
            "notifications_enabled": bool(settings.get("notifications_enabled", current["notifications_enabled"])),
            "notification_sound": bool(settings.get("notification_sound", current["notification_sound"])),
            "notification_preferences": {
                **current["notification_preferences"],
                **dict(settings.get("notification_preferences", {})),
            },
        }
        if values["capital"] <= 0 or not 0 < values["risk_percent"] <= 100:
            raise ValueError("Capital must be positive and risk percentage must be between 0 and 100.")
        if not 0 < values["daily_loss_percent"] <= 100 or values["max_trades_per_day"] < 1:
            raise ValueError("Daily-loss percentage must be between 0 and 100, and trade limit must be at least 1.")
        if not 1 <= values["recovery_daily_trade_limit"] <= values["max_trades_per_day"]:
            raise ValueError("Recovery daily limit must be between 1 and the normal maximum-trades limit.")
        if not 1 <= values["recovery_loss_streak_limit"] <= 10:
            raise ValueError("Recovery loss-streak limit must be between 1 and 10.")
        if not 1 <= values["recovery_lock_hours"] <= 168:
            raise ValueError("Recovery lock must be between 1 and 168 hours.")
        if not 1 <= values["recovery_min_paper_sessions"] <= 250:
            raise ValueError("Recovery paper-session target must be between 1 and 250.")
        if not 0 <= values["trade_plan_min_score"] <= 100:
            raise ValueError("Trade-plan minimum score must be between 0 and 100.")
        allowed_conditions = {
            "Market structure", "Price vs VWAP", "EMA 5/20/50 alignment",
            "SuperTrend confirmation", "Pullback and reversal", "Directional volume", "OI/PCR context",
            "Market environment / VIX",
        }
        if not values["tps_enabled_conditions"] or not set(values["tps_enabled_conditions"]) <= allowed_conditions:
            raise ValueError("Select at least one valid TPS checklist condition.")
        if values["tps_match_mode"] not in {"count", "all", "adaptive"}:
            raise ValueError("TPS checklist mode must be count, all, or adaptive.")
        if not 1 <= values["tps_required_matches"] <= len(values["tps_enabled_conditions"]):
            raise ValueError("Required TPS matches must fit within the enabled checklist.")
        if values["event_no_trade_minutes"] not in {15, 30, 60}:
            raise ValueError("Event no-trade window must be 15, 30, or 60 minutes.")
        if not 0 <= values["paper_trade_cooldown_minutes"] <= 240:
            raise ValueError("Paper-trade cooldown must be between 0 and 240 minutes.")
        if not 1 <= values["minimum_rr_ratio"] <= 10:
            raise ValueError("Minimum risk-reward ratio must be between 1 and 10.")
        if not 0 < values["maximum_option_spread_percent"] <= 100 or values["minimum_option_volume"] < 0:
            raise ValueError("Use a positive option-spread limit and non-negative minimum option volume.")
        if not 0.25 <= values["trailing_stop_trigger_r"] <= 10 or not 0 <= values["trailing_stop_lock_r"] < values["trailing_stop_trigger_r"]:
            raise ValueError("Trailing-stop trigger/lock R values are invalid.")
        if not 0 <= values["time_exit_minutes_before_close"] <= 60:
            raise ValueError("Time-exit window must be between 0 and 60 minutes.")
        if values["theme"] not in {"dark", "light", "emerald", "sunset"}:
            raise ValueError("Choose a valid TPS visual theme.")
        if values["ui_style"] not in {"skeuomorphism", "neomorphism", "glassmorphism", "claymorphism", "minimalism", "maximalism", "brutalism", "liquid_glass", "bento_grid", "spatial_ui"}:
            raise ValueError("Choose a valid TPS UI design style.")
        from services.broker_registry import BROKERS
        if values["broker_provider"] not in BROKERS:
            raise ValueError("Choose a valid broker provider.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self._read_file(self.path):
            shutil.copy2(self.path, self.backup_path)
        temporary = self.path.with_name("settings.pending.json")
        temporary.write_text(json.dumps(values, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)
        shutil.copy2(self.path, self.backup_path)
        return values

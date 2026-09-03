"""Persistent, local-only application preferences."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


DEFAULT_SETTINGS = {
    "capital": 100000.0,
    "risk_percent": 0.25,
    "daily_loss_percent": 0.5,
    "max_trades_per_day": 5,
    # Exchange-session clock is configurable so a future NSE/BSE timing
    # change does not require a software release. Values are stored as HH:MM.
    "market_pre_open_time": "09:00",
    "market_open_time": "09:15",
    "market_close_time": "15:30",
    # Release 1.3 capital-protection defaults. Recovery mode governs paper
    # captures only; TPS remains unable to place a broker order.
    "recovery_mode_enabled": True,
    "recovery_daily_trade_limit": 1,
    # Explicit paper-only validation mode. It suspends behavioural recovery
    # locks, but keeps a bounded daily capture limit and never enables orders.
    "paper_validation_testing_mode": False,
    "paper_validation_daily_limit": 10,
    "paper_validation_soft_miss_allowance": 2,
    "paper_validation_max_open_trades": 10,
    # A successful broker HTTP call is not usable evidence when its completed
    # candle is old. This fail-closed threshold preserves paper/real safety.
    "market_data_max_age_seconds": 420,
    "paper_execution_fixed_cost": 40.0,
    "paper_execution_slippage_points": 0.25,
    "paper_unique_thesis_window_minutes": 15,
    "recovery_loss_streak_limit": 2,
    "recovery_lock_hours": 48,
    "recovery_min_paper_sessions": 30,
    "trade_plan_min_score": 95,
    # Separate, opt-in research mode.  It can label a candle READY/WATCH but
    # cannot place or capture a trade and never weakens the strict TPS engine.
    "regular_scalp_validation_enabled": False,
    "regular_scalp_underlying_target_points": 20.0,
    "regular_scalp_premium_target_points": 20.0,
    "regular_scalp_min_score": 55,
    "regular_scalp_min_confirmations": 3,
    # User opt-in for the completed-candle audit loop.  This persists so an
    # approved forward test can resume after an application update/restart,
    # but it still requires a live read-only broker session and safety checks.
    "auto_paper_monitor_enabled": False,
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
    "adaptive_stop_min_percent": 18.0,
    "adaptive_stop_max_percent": 35.0,
    "stop_sweep_buffer_percent": 3.0,
    "trailing_stop_enabled": True,
    "trailing_stop_trigger_r": 1.0,
    "trailing_stop_lock_r": 0.25,
    "time_exit_minutes_before_close": 10,
    # PAPER-only overnight research. A saved matching gap forecast may defer
    # time exit; target/stop are revalidated from a fresh next-session quote.
    "paper_overnight_gap_hold_enabled": True,
    "theme": "dark",
    "ui_style": "glassmorphism",
    "broker_provider": "angel_one",
    # A user-approved, read-only strategy monitor survives software restarts.
    # It contains plan legs only, never broker credentials or an order token.
    "active_option_strategy_plan": None,
    # Combined paper-strategy day guard. Zero keeps either limit disabled.
    # The dated state prevents an app restart from reopening captures after a
    # target or maximum-loss exit; a new trading date starts ACTIVE again.
    "strategy_daily_target_profit": 0.0,
    "strategy_daily_max_loss": 0.0,
    "strategy_daily_limit_state": {},
    # Real broker execution remains off by default. Arming is session-only and
    # is intentionally never persisted across an application restart.
    "real_execution_enabled": False,
    "limited_real_pilot_enabled": False,
    "real_pilot_max_orders": 2,
    "real_pilot_max_quantity": 65,
    "real_pilot_risk_percent": 0.25,
    "real_pilot_daily_loss_percent": 0.5,
    # The visible mode is a preference, not an authorization. REAL still
    # requires the saved opt-in, a session unlock and a per-order phrase.
    "execution_mode": "PAPER",
    "execution_target_basis": "PERCENT",
    "execution_target_value": 20.0,
    "execution_stop_basis": "PERCENT",
    "execution_stop_value": 10.0,
    "execution_time_exit_enabled": True,
    "execution_time_exit": "15:20",
    "execution_max_orders_per_day": 3,
    "execution_max_quantity": 65,
    "execution_max_order_value": 25000.0,
    "execution_max_daily_loss": 1000.0,
    "execution_duplicate_window_seconds": 120,
    # REAL submission must see a recent successful shared market-data read.
    # Existing unit adapters that do not opt in remain independently testable.
    "execution_require_live_data_gate": True,
    "real_require_shadow_eligibility": True,
    # Dedicated options-only algorithm controller. It is PAPER by default and
    # session activation is deliberately never persisted.
    "options_algo_enabled": False,
    "options_algo_daily_target_net": 1000.0,
    "options_algo_daily_max_loss": 500.0,
    "options_algo_max_trades": 10,
    "options_algo_estimated_charges": 60.0,
    "options_algo_estimated_slippage": 20.0,
    "options_algo_lots": 1,
    "options_algo_entry_start": "09:20",
    "options_algo_last_entry": "15:00",
    "options_algo_min_validation_trades": 30,
    "options_algo_min_validation_win_rate": 55.0,
    "options_algo_max_validation_drawdown": 5000.0,
    "expiry_pair_auto_execute": False,
    "expiry_pair_lots": 1,
    "expiry_pair_target_pnl": 1000.0,
    "expiry_pair_stop_pnl": 500.0,
    "expiry_pair_time_exit": "15:25",
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
        # Release 1.5.2 Options Workspace validation uses a fixed safe testing
        # ceiling of ten; transparently migrate the older 20-trade preference.
        values["paper_validation_daily_limit"] = min(10, max(1, int(values.get("paper_validation_daily_limit", 10))))
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
            "real_execution_enabled": bool(settings.get("real_execution_enabled", current["real_execution_enabled"])),
            "limited_real_pilot_enabled": bool(settings.get("limited_real_pilot_enabled", current["limited_real_pilot_enabled"])),
            "real_pilot_max_orders": int(settings.get("real_pilot_max_orders", current["real_pilot_max_orders"])),
            "real_pilot_max_quantity": int(settings.get("real_pilot_max_quantity", current["real_pilot_max_quantity"])),
            "real_pilot_risk_percent": float(settings.get("real_pilot_risk_percent", current["real_pilot_risk_percent"])),
            "real_pilot_daily_loss_percent": float(settings.get("real_pilot_daily_loss_percent", current["real_pilot_daily_loss_percent"])),
            "execution_mode": str(settings.get("execution_mode", current["execution_mode"])).upper(),
            "execution_target_basis": str(settings.get("execution_target_basis", current["execution_target_basis"])).upper(),
            "execution_target_value": float(settings.get("execution_target_value", current["execution_target_value"])),
            "execution_stop_basis": str(settings.get("execution_stop_basis", current["execution_stop_basis"])).upper(),
            "execution_stop_value": float(settings.get("execution_stop_value", current["execution_stop_value"])),
            "execution_time_exit_enabled": bool(settings.get("execution_time_exit_enabled", current["execution_time_exit_enabled"])),
            "execution_time_exit": str(settings.get("execution_time_exit", current["execution_time_exit"])).strip(),
            "execution_max_orders_per_day": int(settings.get("execution_max_orders_per_day", current["execution_max_orders_per_day"])),
            "execution_max_quantity": int(settings.get("execution_max_quantity", current["execution_max_quantity"])),
            "execution_max_order_value": float(settings.get("execution_max_order_value", current["execution_max_order_value"])),
            "execution_max_daily_loss": float(settings.get("execution_max_daily_loss", current["execution_max_daily_loss"])),
            "execution_duplicate_window_seconds": int(settings.get("execution_duplicate_window_seconds", current["execution_duplicate_window_seconds"])),
            "execution_require_live_data_gate": bool(settings.get("execution_require_live_data_gate", current["execution_require_live_data_gate"])),
            "real_require_shadow_eligibility": bool(settings.get("real_require_shadow_eligibility", current["real_require_shadow_eligibility"])),
            "market_pre_open_time": str(settings.get("market_pre_open_time", current["market_pre_open_time"])).strip(),
            "market_open_time": str(settings.get("market_open_time", current["market_open_time"])).strip(),
            "market_close_time": str(settings.get("market_close_time", current["market_close_time"])).strip(),
            "recovery_mode_enabled": bool(settings.get("recovery_mode_enabled", current["recovery_mode_enabled"])),
            "recovery_daily_trade_limit": int(settings.get("recovery_daily_trade_limit", current["recovery_daily_trade_limit"])),
            "paper_validation_testing_mode": bool(settings.get("paper_validation_testing_mode", current["paper_validation_testing_mode"])),
            "paper_validation_daily_limit": int(settings.get("paper_validation_daily_limit", current["paper_validation_daily_limit"])),
            "paper_validation_soft_miss_allowance": max(0, min(2, int(settings.get("paper_validation_soft_miss_allowance", current["paper_validation_soft_miss_allowance"])))),
            "paper_validation_max_open_trades": max(1, min(10, int(settings.get("paper_validation_max_open_trades", current["paper_validation_max_open_trades"])))),
            "paper_execution_fixed_cost": max(0.0, float(settings.get("paper_execution_fixed_cost", current["paper_execution_fixed_cost"]))),
            "paper_execution_slippage_points": max(0.0, float(settings.get("paper_execution_slippage_points", current["paper_execution_slippage_points"]))),
            "paper_unique_thesis_window_minutes": max(5, min(60, int(settings.get("paper_unique_thesis_window_minutes", current["paper_unique_thesis_window_minutes"])))),
            "recovery_loss_streak_limit": int(settings.get("recovery_loss_streak_limit", current["recovery_loss_streak_limit"])),
            "recovery_lock_hours": int(settings.get("recovery_lock_hours", current["recovery_lock_hours"])),
            "recovery_min_paper_sessions": int(settings.get("recovery_min_paper_sessions", current["recovery_min_paper_sessions"])),
            "trade_plan_min_score": int(settings.get("trade_plan_min_score", current["trade_plan_min_score"])),
            "regular_scalp_validation_enabled": bool(settings.get("regular_scalp_validation_enabled", current["regular_scalp_validation_enabled"])),
            "regular_scalp_underlying_target_points": float(settings.get("regular_scalp_underlying_target_points", current["regular_scalp_underlying_target_points"])),
            "regular_scalp_premium_target_points": float(settings.get("regular_scalp_premium_target_points", current["regular_scalp_premium_target_points"])),
            "regular_scalp_min_score": int(settings.get("regular_scalp_min_score", current["regular_scalp_min_score"])),
            "regular_scalp_min_confirmations": int(settings.get("regular_scalp_min_confirmations", current["regular_scalp_min_confirmations"])),
            "auto_paper_monitor_enabled": bool(settings.get("auto_paper_monitor_enabled", current["auto_paper_monitor_enabled"])),
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
            "adaptive_stop_min_percent": float(settings.get("adaptive_stop_min_percent", current["adaptive_stop_min_percent"])),
            "adaptive_stop_max_percent": float(settings.get("adaptive_stop_max_percent", current["adaptive_stop_max_percent"])),
            "stop_sweep_buffer_percent": float(settings.get("stop_sweep_buffer_percent", current["stop_sweep_buffer_percent"])),
            "trailing_stop_enabled": bool(settings.get("trailing_stop_enabled", current["trailing_stop_enabled"])),
            "trailing_stop_trigger_r": float(settings.get("trailing_stop_trigger_r", current["trailing_stop_trigger_r"])),
            "trailing_stop_lock_r": float(settings.get("trailing_stop_lock_r", current["trailing_stop_lock_r"])),
            "time_exit_minutes_before_close": int(settings.get("time_exit_minutes_before_close", current["time_exit_minutes_before_close"])),
            "paper_overnight_gap_hold_enabled": bool(settings.get("paper_overnight_gap_hold_enabled", current["paper_overnight_gap_hold_enabled"])),
            "theme": str(settings.get("theme", current["theme"])).lower(),
            "ui_style": str(settings.get("ui_style", current["ui_style"])).lower(),
            "broker_provider": str(settings.get("broker_provider", current["broker_provider"])).lower(),
            "active_option_strategy_plan": settings.get("active_option_strategy_plan", current["active_option_strategy_plan"]),
            "strategy_daily_target_profit": max(0.0, float(settings.get("strategy_daily_target_profit", current["strategy_daily_target_profit"]))),
            "strategy_daily_max_loss": max(0.0, float(settings.get("strategy_daily_max_loss", current["strategy_daily_max_loss"]))),
            "strategy_daily_limit_state": dict(settings.get("strategy_daily_limit_state", current["strategy_daily_limit_state"]) or {}),
            "options_algo_enabled": bool(settings.get("options_algo_enabled", current["options_algo_enabled"])),
            "options_algo_daily_target_net": max(0.0, float(settings.get("options_algo_daily_target_net", current["options_algo_daily_target_net"]))),
            "options_algo_daily_max_loss": max(0.0, float(settings.get("options_algo_daily_max_loss", current["options_algo_daily_max_loss"]))),
            "options_algo_max_trades": max(1, min(10, int(settings.get("options_algo_max_trades", current["options_algo_max_trades"])))),
            "options_algo_estimated_charges": max(0.0, float(settings.get("options_algo_estimated_charges", current["options_algo_estimated_charges"]))),
            "options_algo_estimated_slippage": max(0.0, float(settings.get("options_algo_estimated_slippage", current["options_algo_estimated_slippage"]))),
            "options_algo_lots": max(1, min(100, int(settings.get("options_algo_lots", current["options_algo_lots"])))),
            "options_algo_entry_start": str(settings.get("options_algo_entry_start", current["options_algo_entry_start"])).strip(),
            "options_algo_last_entry": str(settings.get("options_algo_last_entry", current["options_algo_last_entry"])).strip(),
            "options_algo_min_validation_trades": max(1, min(1000, int(settings.get("options_algo_min_validation_trades", current["options_algo_min_validation_trades"])))),
            "options_algo_min_validation_win_rate": max(0.0, min(100.0, float(settings.get("options_algo_min_validation_win_rate", current["options_algo_min_validation_win_rate"])))),
            "options_algo_max_validation_drawdown": max(0.0, float(settings.get("options_algo_max_validation_drawdown", current["options_algo_max_validation_drawdown"]))),
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
        from core.market_session import parse_session_times
        parse_session_times(values)
        from datetime import time
        try:
            algo_start = time.fromisoformat(values["options_algo_entry_start"])
            algo_end = time.fromisoformat(values["options_algo_last_entry"])
        except ValueError as error:
            raise ValueError("Algo entry times must use HH:MM format.") from error
        if not algo_start < algo_end:
            raise ValueError("Algo entry start must be earlier than last-entry time.")
        if not 1 <= values["recovery_daily_trade_limit"] <= values["max_trades_per_day"]:
            raise ValueError("Recovery daily limit must be between 1 and the normal maximum-trades limit.")
        if not 1 <= values["paper_validation_daily_limit"] <= 10:
            raise ValueError("Paper-validation testing limit must be between 1 and 10 trades per day.")
        if not 1 <= values["recovery_loss_streak_limit"] <= 10:
            raise ValueError("Recovery loss-streak limit must be between 1 and 10.")
        if not 1 <= values["recovery_lock_hours"] <= 168:
            raise ValueError("Recovery lock must be between 1 and 168 hours.")
        if not 1 <= values["recovery_min_paper_sessions"] <= 250:
            raise ValueError("Recovery paper-session target must be between 1 and 250.")
        if not 0 <= values["trade_plan_min_score"] <= 100:
            raise ValueError("Trade-plan minimum score must be between 0 and 100.")
        if not 1 <= values["regular_scalp_underlying_target_points"] <= 500:
            raise ValueError("Regular scalp underlying target must be between 1 and 500 points.")
        if not 1 <= values["regular_scalp_premium_target_points"] <= 500:
            raise ValueError("Regular scalp option-premium target must be between 1 and 500 rupees.")
        if not 0 <= values["regular_scalp_min_score"] <= 100:
            raise ValueError("Regular scalp minimum score must be between 0 and 100.")
        if not 1 <= values["regular_scalp_min_confirmations"] <= 8:
            raise ValueError("Regular scalp confirmations must be between 1 and 8.")
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
        if not 5 <= values["adaptive_stop_min_percent"] <= values["adaptive_stop_max_percent"] <= 60:
            raise ValueError("Adaptive stop limits must satisfy 5% <= minimum <= maximum <= 60%.")
        if not 0 <= values["stop_sweep_buffer_percent"] <= 10:
            raise ValueError("Stop sweep buffer must be between 0% and 10%.")
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
        if values["active_option_strategy_plan"] is not None and not isinstance(values["active_option_strategy_plan"], dict):
            raise ValueError("Active option strategy plan must be a saved plan or empty.")
        if not 1 <= values["execution_max_orders_per_day"] <= 20:
            raise ValueError("Real execution order cap must be between 1 and 20 per day.")
        if not 1 <= values["real_pilot_max_orders"] <= 2:
            raise ValueError("Limited REAL pilot allows only 1 or 2 entries per day.")
        if not 1 <= values["real_pilot_max_quantity"] <= 65:
            raise ValueError("Limited REAL pilot quantity must be between 1 and 65.")
        if not 0 < values["real_pilot_risk_percent"] <= 0.25:
            raise ValueError("Limited REAL pilot per-trade risk cannot exceed 0.25% of capital.")
        if not 0 < values["real_pilot_daily_loss_percent"] <= 0.5:
            raise ValueError("Limited REAL pilot daily-loss budget cannot exceed 0.5% of capital.")
        if not 1 <= values["execution_max_quantity"] <= 10000:
            raise ValueError("Real execution quantity cap must be between 1 and 10,000.")
        if values["execution_max_order_value"] <= 0 or values["execution_max_daily_loss"] < 0:
            raise ValueError("Execution value cap must be positive and loss lock cannot be negative.")
        if not 30 <= values["execution_duplicate_window_seconds"] <= 3600:
            raise ValueError("Duplicate-order window must be between 30 and 3,600 seconds.")
        if values["execution_mode"] not in {"PAPER", "REAL"}:
            raise ValueError("Order mode must be PAPER or REAL.")
        if values["execution_target_basis"] not in {"PRICE", "AMOUNT", "PERCENT"} or values["execution_stop_basis"] not in {"PRICE", "AMOUNT", "PERCENT"}:
            raise ValueError("Target and stop basis must be exact price, amount, or percentage.")
        if values["execution_target_value"] <= 0 or values["execution_stop_value"] <= 0:
            raise ValueError("Target and stop values must be positive.")
        if not __import__("re").fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", values["execution_time_exit"]):
            raise ValueError("Execution time exit must use HH:MM format.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self._read_file(self.path):
            shutil.copy2(self.path, self.backup_path)
        temporary = self.path.with_name("settings.pending.json")
        temporary.write_text(json.dumps(values, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)
        shutil.copy2(self.path, self.backup_path)
        return values

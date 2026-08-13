"""Local desktop notifications for TPS decision and paper-trade events."""

from __future__ import annotations

from datetime import datetime
from time import monotonic

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyle, QSystemTrayIcon

from core.database_manager import Database
from core.settings_store import SettingsStore


NOTIFICATION_LABELS = {
    "trade_capture": "Trade captured",
    "trade_exit": "Trade exit / time exit",
    "target_achieved": "Target achieved",
    "stop_loss": "Stop loss / trailing stop",
    "market_snapshot": "Market Snapshot alerts",
    "market_structure": "Market structure change",
    "support_resistance": "Support / resistance zone",
    "put_call_ratio": "Put-Call Ratio sentiment",
    "auto_attempt_report": "Auto Attempt Report results",
    "early_watch": "Early Watch (paper observation only)",
    "equity_research": "Equity Research",
    "chart_capture": "Chart Capture",
    "ai_analysis": "AI Analysis",
    "trade_journal": "Trade Journal",
    "risk_manager": "Risk Manager / Open Trade Guard",
    "reports": "Reports",
    "backtesting": "Backtesting",
    "candle_replay": "Candle Replay",
    "post_market_report": "Post-Market Report",
    "post_market_analysis": "Post Market Analysis of TPS",
    "next_day_bias": "Next-Day Bias",
    "cas_analysis": "CAS Analysis",
    "stock_options_watch": "Stock Options Watch",
    "option_strategies": "Option Strategies",
    "smart_money_lab": "Smart Money Lab",
    "pre_candle_lab": "Pre-Candle Lab",
    "powerful_engine": "Powerful Engine",
    "auto_opportunity": "Auto Opportunity Radar",
    "broker_connection": "Broker connection status",
    "trend_memory": "Trend Memory historical-pattern match",
    "scalper": "Near-expiry options scalper watch",
    "self_development": "AI Self-Development Decision Center",
}


def category_enabled(settings: dict, category: str) -> bool:
    """Return the saved global + per-category notification decision."""
    return bool(
        settings.get("notifications_enabled", True)
        and (settings.get("notification_preferences") or {}).get(category, False)
    )


def daily_event_key(category: str, dedupe_key: str, now: datetime | None = None) -> str:
    """Build a restart-safe identity for one logical alert per local day."""
    current = now or datetime.now().astimezone()
    return f"{current.strftime('%Y-%m-%d')}:{category}:{str(dedupe_key).strip().upper()}"


class NotificationService(QObject):
    """One system-tray notifier shared by the whole desktop application."""

    notification_sent = Signal(str, str, str)
    _instance = None

    def __init__(self, parent=None):
        super().__init__(parent)
        app = QApplication.instance()
        icon = app.windowIcon() if app and not app.windowIcon().isNull() else QIcon()
        if icon.isNull() and app:
            icon = app.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("TPS AI Trading Assistant alerts")
        self.tray.show()
        self._recent = {}
        self.db = Database()

    @classmethod
    def instance(cls, parent=None):
        if cls._instance is None:
            cls._instance = cls(parent)
        return cls._instance

    def notify(
        self, category: str, title: str, message: str, *, force: bool = False,
        dedupe_key: str | None = None, once_per_day: bool = False,
        repeat_after_seconds: int = 20,
    ) -> bool:
        settings = SettingsStore().load()
        if not force and not category_enabled(settings, category):
            return False
        event_key = daily_event_key(category, dedupe_key) if dedupe_key and once_per_day else None
        signature = (category, dedupe_key or title, "" if dedupe_key else message)
        now = monotonic()
        if not force and now - self._recent.get(signature, 0) < max(0, int(repeat_after_seconds)):
            return False
        # The notification ledger is independent of the transient Windows
        # popup.  This makes every delivered TPS alert permanently auditable.
        try:
            notification_id = self.db.save_notification(category, title, message, event_key=event_key)
            if event_key and not notification_id:
                return False
        except Exception:
            # A temporary database lock must not suppress a time-sensitive
            # desktop alert; subsequent alerts continue to be recorded.
            pass
        self._recent[signature] = now
        if settings.get("notification_sound", True):
            QApplication.beep()
        self.tray.showMessage(title, message, QSystemTrayIcon.Information, 10_000)
        self.notification_sent.emit(category, title, message)
        return True

    def test(self):
        return self.notify(
            "trade_capture", "TPS desktop alerts are ready",
            "Notification Center is working. Control every alert category from Settings.", force=True,
        )

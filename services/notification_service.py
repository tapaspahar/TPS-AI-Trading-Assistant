"""Local desktop notifications for TPS decision and paper-trade events."""

from __future__ import annotations

from time import monotonic

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyle, QSystemTrayIcon

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
    "scalper": "Scalper Command Center watch",
}


def category_enabled(settings: dict, category: str) -> bool:
    """Return the saved global + per-category notification decision."""
    return bool(
        settings.get("notifications_enabled", True)
        and (settings.get("notification_preferences") or {}).get(category, False)
    )


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

    @classmethod
    def instance(cls, parent=None):
        if cls._instance is None:
            cls._instance = cls(parent)
        return cls._instance

    def notify(self, category: str, title: str, message: str, *, force: bool = False) -> bool:
        settings = SettingsStore().load()
        if not force and not category_enabled(settings, category):
            return False
        signature = (category, title, message)
        now = monotonic()
        if not force and now - self._recent.get(signature, 0) < 20:
            return False
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

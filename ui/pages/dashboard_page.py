from datetime import datetime

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QGridLayout, QPushButton, QVBoxLayout, QWidget

from core.database_manager import Database
from services.live_session import LiveSession
from services.analysis_scheduler import AnalysisScheduler
from services.market_data_hub import MarketDataHub
from core.settings_store import SettingsStore
from core.market_session import market_session
from engine.performance_calibration import calibrate_outcomes
from ui.widgets.cards.dashboard_card import DashboardCard


class DashboardPage(QWidget):
    """Overview of the locally recorded trading journal."""

    funds_loaded = Signal(dict)
    funds_failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.db = Database()
        self._funds_refresh_running = False
        self.funds_loaded.connect(self._show_funds)
        self.funds_failed.connect(self._show_funds_error)
        layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(20)
        self.cards = {
            "market": DashboardCard("Live Data Status", "Not connected"),
            "pnl": DashboardCard("Journal P&L", "₹0.00"),
            "ai": DashboardCard("Average AI Confidence", "0%"),
            "win_rate": DashboardCard("Win Rate", "0%"),
            "risk": DashboardCard("Risk Status", "Review each trade"),
            "trades": DashboardCard("Recorded Trades", "0"),
            "funds": DashboardCard("Broker Funds", "Connect broker\nOpen Settings"),
            "performance": DashboardCard("Analysis Performance", "Queue ready"),
            "feed": DashboardCard("Data Freshness & Cache", "Waiting for first snapshot"),
            "validation": DashboardCard("Paper Accuracy Lab", "No closed outcomes"),
            "today": DashboardCard("Today Control Center", "Loading controls"),
        }
        for index, card in enumerate(self.cards.values()):
            grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(grid)
        refresh_button = QPushButton("Refresh Dashboard")
        refresh_button.clicked.connect(self.refresh_all)
        layout.addWidget(refresh_button)
        layout.addStretch()
        self.funds_timer = QTimer(self)
        self.funds_timer.setInterval(60_000)
        self.funds_timer.timeout.connect(self.refresh_funds)
        QTimer.singleShot(AnalysisScheduler.stagger_ms("dashboard-funds"), self.funds_timer.start)
        self.refresh()

    def refresh(self):
        summary = self.db.get_summary()
        self.cards["market"].set_value(
            "Connected (read-only)\nOpen Market Snapshot" if LiveSession.connected() else "Not connected\nOpen Settings"
        )
        self.cards["pnl"].set_value(f"₹{summary['pnl']:,.2f}")
        self.cards["ai"].set_value(f"{summary['average_ai']:.0f}%")
        self.cards["win_rate"].set_value(f"{summary['win_rate']:.1f}%")
        self.cards["trades"].set_value(summary["trades"])
        self.cards["risk"].set_value("Safe" if summary["trades"] == 0 or summary["pnl"] >= 0 else "Review loss")
        metrics = AnalysisScheduler.metrics()
        active = sum(bool(item.get("active")) for item in metrics.values())
        runs = sum(int(item.get("runs", 0)) for item in metrics.values())
        skipped = sum(int(item.get("skipped", 0)) for item in metrics.values())
        slowest = max((float(item.get("last_seconds", 0)) for item in metrics.values()), default=0)
        self.cards["performance"].set_value(
            f"Active {active}/3 | Completed {runs}\nDuplicates saved {skipped} | Slowest {slowest:.1f}s"
        )
        feed = MarketDataHub.health()
        self.cards["feed"].set_value(
            f"{feed['state']} | cache hit {feed['hit_rate']:.1f}%\n"
            f"Snapshots {feed['cached_snapshots']} | failures {feed['failures']}\n"
            f"Source {feed.get('last_source_timestamp') or 'waiting'}"
        )
        paper_rows = self.db.get_paper_outcome_quality(5000)
        calibration = calibrate_outcomes([row.get("pnl") for row in paper_rows])
        factor = "∞" if calibration["profit_factor"] == float("inf") else f"{calibration['profit_factor']:.2f}"
        self.cards["validation"].set_value(
            f"{calibration['validation_tier']} | {calibration['wins']}/{calibration['samples']} wins\n"
            f"Win {calibration['win_rate']:.1f}% | lower bound {calibration['wilson_lower_bound']:.1f}%\n"
            f"Expectancy ₹{calibration['expectancy']:,.2f} | PF {factor}"
        )
        settings = SettingsStore().load()
        today = datetime.now().strftime("%d-%m-%Y")
        progress = self.db.paper_trade_progress(today)
        session = market_session(settings=settings)
        mode = "PAPER TEST" if settings.get("paper_validation_testing_mode") else str(settings.get("execution_mode", "PAPER"))
        limit = int(settings.get("paper_validation_daily_limit", 10)) if mode == "PAPER TEST" else int(settings.get("max_trades_per_day", 5))
        self.cards["today"].set_value(
            f"{mode} | Market {session['state']}\n"
            f"Samples {progress['trades']}/{limit} | Open {progress['open_trades']}\n"
            f"Net paper P&L ₹{progress['realized_pnl']:,.2f}"
        )

    def refresh_all(self):
        self.refresh()
        self.refresh_funds()

    def refresh_funds(self):
        if not LiveSession.connected() or LiveSession.broker_id != "angel_one":
            self.cards["funds"].set_value("Not connected\nOpen Settings")
            return
        if self._funds_refresh_running:
            return
        self._funds_refresh_running = True
        self.cards["funds"].set_value("Refreshing…")
        if not AnalysisScheduler.submit_unique("dashboard-funds", self._load_funds):
            self._funds_refresh_running = False

    def _load_funds(self):
        try:
            self.funds_loaded.emit(dict(LiveSession.client.get_funds()))
        except Exception as error:
            self.funds_failed.emit(str(error))

    def _show_funds(self, values):
        from core.market_session import IST
        updated = datetime.now(IST).strftime("%H:%M:%S IST")
        self.cards["funds"].set_value(
            f"Available ₹{values['available_cash']:,.2f}\n"
            f"Net ₹{values['net']:,.2f} | Used ₹{values['utilized']:,.2f}\n"
            f"Updated {updated}"
        )
        self._funds_refresh_running = False

    def _show_funds_error(self, _error):
        self.cards["funds"].set_value("Refresh failed\nValue not current")
        self._funds_refresh_running = False

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.refresh_all)

from datetime import datetime

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QGridLayout, QPushButton, QVBoxLayout, QWidget

from core.database_manager import Database
from services.live_session import LiveSession
from services.analysis_scheduler import AnalysisScheduler
from services.market_data_hub import MarketDataHub
from core.settings_store import SettingsStore
from core.market_session import market_session
from core.market_session import IST
from engine.performance_calibration import calibrate_outcomes
from ui.widgets.cards.dashboard_card import DashboardCard


class DashboardPage(QWidget):
    """Overview of the locally recorded trading journal."""

    funds_loaded = Signal(dict)
    funds_failed = Signal(str)
    reliability_requested = Signal()
    page_requested = Signal(int)

    def __init__(self):
        super().__init__()
        self.db = Database()
        self._journal_summary_date = None
        self._funds_refresh_running = False
        self.funds_loaded.connect(self._show_funds)
        self.funds_failed.connect(self._show_funds_error)
        layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(20)
        self.cards = {
            "market": DashboardCard("Live Data Status", "Not connected"),
            "pnl": DashboardCard("Today's Journal P&L", "₹0.00"),
            "ai": DashboardCard("Average AI Confidence", "0%"),
            "win_rate": DashboardCard("Win Rate", "0%"),
            "risk": DashboardCard("Risk Status", "Review each trade"),
            "trades": DashboardCard("Recorded Trades", "0"),
            "funds": DashboardCard("Broker Funds", "Connect broker\nOpen Settings"),
            "performance": DashboardCard("Analysis Performance", "Queue ready"),
            "feed": DashboardCard("Data Freshness & Cache", "Waiting for first snapshot"),
            "validation": DashboardCard("Paper Accuracy Lab", "No closed outcomes"),
            "today": DashboardCard("Today Control Center", "Loading controls"),
            "reliability": DashboardCard("Reliability & Shadow Gate", "Loading evidence"),
        }
        for index, card in enumerate(self.cards.values()):
            grid.addWidget(card, index // 3, index % 3)
        destinations = {
            "market": (1, "Open Market Snapshot"),
            "pnl": (4, "Open Trade Journal"),
            "ai": (31, "Open AI Development Center"),
            "win_rate": (10, "Open Backtesting"),
            "risk": (36, "Open Broker Execution and risk controls"),
            "trades": (4, "Open Trade Journal"),
            "funds": (36, "Open Broker Execution and account funds"),
            "performance": (40, "Open Reliability Cockpit"),
            "feed": (40, "Open data freshness evidence"),
            "validation": (40, "Open Paper Accuracy and Shadow Gate"),
            "today": (32, "Open today's protection and validation controls"),
            "reliability": (40, "Open Reliability Cockpit"),
        }
        for key, (route, tooltip) in destinations.items():
            card = self.cards[key]
            card.set_clickable(True, tooltip)
            card.clicked.connect(lambda page_route=route: self.page_requested.emit(page_route))
        layout.addLayout(grid)
        refresh_button = QPushButton("Refresh Dashboard")
        refresh_button.clicked.connect(self.refresh_all)
        layout.addWidget(refresh_button)
        reliability_button = QPushButton("Open Reliability Cockpit — Timeline, Missed Trades & Execution Quality")
        reliability_button.clicked.connect(self.reliability_requested)
        layout.addWidget(reliability_button)
        layout.addStretch()
        self.funds_timer = QTimer(self)
        self.funds_timer.setInterval(60_000)
        self.funds_timer.timeout.connect(self.refresh_funds)
        QTimer.singleShot(AnalysisScheduler.stagger_ms("dashboard-funds"), self.funds_timer.start)
        self.date_rollover_timer = QTimer(self)
        self.date_rollover_timer.setInterval(30_000)
        self.date_rollover_timer.timeout.connect(self._refresh_on_date_rollover)
        self.date_rollover_timer.start()
        self.refresh()

    def refresh(self):
        summary = self.db.get_summary()
        current_date = datetime.now(IST).strftime("%d-%m-%Y")
        daily_summary = self.db.get_day_summary(current_date)
        self._journal_summary_date = current_date
        self.cards["market"].set_value(
            "Connected (read-only)\nOpen Market Snapshot" if LiveSession.connected() else "Not connected\nOpen Settings"
        )
        self.cards["pnl"].set_value(f"₹{daily_summary['pnl']:,.2f}\n{current_date}")
        self.cards["ai"].set_value(f"{summary['average_ai']:.0f}%")
        self.cards["win_rate"].set_value(f"{summary['win_rate']:.1f}%")
        self.cards["trades"].set_value(summary["trades"])
        self.cards["risk"].set_value("Safe" if daily_summary["trades"] == 0 or daily_summary["pnl"] >= 0 else "Review loss")
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
        today = current_date
        progress = self.db.paper_trade_progress(today)
        session = market_session(settings=settings)
        mode = "PAPER TEST" if settings.get("paper_validation_testing_mode") else str(settings.get("execution_mode", "PAPER"))
        limit = int(settings.get("paper_validation_daily_limit", 10)) if mode == "PAPER TEST" else int(settings.get("max_trades_per_day", 5))
        self.cards["today"].set_value(
            f"{mode} | Market {session['state']}\n"
            f"Samples {progress['trades']}/{limit} | Open {progress['open_trades']}\n"
            f"Net paper P&L ₹{progress['realized_pnl']:,.2f}"
        )
        from services.reliability_intelligence import data_quality_gate, missed_opportunities, shadow_eligibility
        gate = data_quality_gate(
            connected=LiveSession.connected(), market_state=session["state"], hub_health=feed,
            broker_health=self.db.get_broker_health(limit=200),
        )
        shadow = shadow_eligibility(self.db)
        missed = missed_opportunities(self.db, today)
        self.cards["reliability"].set_value(
            f"Data gate {gate['status']} | {shadow['state']}\n"
            f"Missed/replay shortlist {len(missed)} | Sample {shadow['samples']}\n"
            f"95% lower confidence {shadow['wilson_lower_bound']:.1f}%"
        )

    def refresh_all(self):
        self.refresh()
        self.refresh_funds()

    def _refresh_on_date_rollover(self):
        """Clear yesterday's dashboard P&L as soon as the IST date changes."""
        current_date = datetime.now(IST).strftime("%d-%m-%Y")
        if current_date != self._journal_summary_date:
            self.refresh()

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
